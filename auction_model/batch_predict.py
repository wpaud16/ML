#!/usr/bin/env python3
"""매일 새벽 GitHub Actions에서 실행: 10개 관심 지역의 진행 중 아파트 경매를 모아 앙상블 예측을 미리 계산한다.

결과: predictions/latest.json (+ predictions/YYYY-MM-DD.json)
  items: { "<사건번호>[<물건번호>]": {auction_id, danji_id, ..., bid_by_prob_manwon, prob_by_bid_5m, ...} }
  skipped: 필터 탈락(면적·예산), failed: 단지 연결 또는 예측 실패 (사유 포함)
아침 브리핑은 이 파일을 '읽기만' 하고 코드를 실행하지 않는다.
단지 연결 캐시: danji_map.json { "<경매ID>": "<단지ID>" } (수동으로 추가해도 됨)
"""
import json, os, re, sys, time, subprocess, urllib.parse
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import auction_predictor as ap

KST = timezone(timedelta(hours=9))
REGIONS = [('서울', '강남구'), ('서울', '서초구'), ('서울', '강동구'), ('서울', '광진구'), ('서울', '송파구'),
           ('경기', '성남시 수정구'), ('경기', '성남시 분당구'), ('경기', '성남시 중원구'), ('경기', '남양주시'), ('경기', '구리시')]
MIN_AREA, MAX_LOW = 0.0, float("inf")   # 2026-11-02 사용자 요청으로 면적·최저가 필터 해제
MAP_PATH = os.path.join(HERE, 'danji_map.json')
OUT_DIR = os.path.join(HERE, 'predictions')


def get(url, tries=3):
    for k in range(tries):
        try:   # 응답이 중간에 잘려도(멀티바이트 끊김) 죽지 않게 bytes로 받아 'replace' 디코딩
            r = subprocess.run(['curl', '-sL', '-m', '40', '-A', 'Mozilla/5.0', url], capture_output=True).stdout.decode('utf-8', 'replace')
        except Exception:
            r = ''
        if '__NEXT_DATA__' in r:
            return r
        time.sleep(2 + 3 * k)
    return ''


def next_data(raw):
    i = raw.find('__NEXT_DATA__'); j = raw.find('>', i); k = raw.find('</script>', j)
    return json.loads(raw[j + 1:k])['props']['pageProps']


def q(s):
    return urllib.parse.quote(s)


def region_items(sd, sgg, ty='아파트'):
    out, page = [], 1
    while True:
        url = f'https://m.richgo.ai/auction/hub/region/{q(sd)}/{q(sgg)}/{q(ty)}' + (f'?page={page}' if page > 1 else '')
        raw = get(url)
        if not raw:
            raise RuntimeError(f'list fetch failed {sd} {sgg} p{page}')
        d = next_data(raw)['data']
        out += d['items']
        if page * d['size'] >= d['totalCount'] or not d['items']:
            return out
        page += 1


def danji_auctions(danji, kind='danji'):
    raw = get(f'https://m.richgo.ai/realty/{kind}/' + danji)
    if not raw:
        return set()
    d = next_data(raw).get('data') or {}
    ids = set()

    def flat(x):
        if not x: return
        ids.add(x.get('auctionId'))
        for s in x.get('subList') or []: flat(s)
    flat(d.get('auctionInfo'))
    return ids


def search(term, kind='apart'):
    raw = get('https://m.richgo.ai/realty/search?q=' + q(term))
    if not raw:
        return []
    res = []
    for g in (next_data(raw).get('agentSearch') or {}).get('groups') or []:
        if g.get('kind') != kind: continue
        for it in g.get('items') or []:
            m = re.search(r'/realty/(?:danji|officetel)/([0-9A-Za-z]+)', it.get('href', ''))
            if m: res.append((m.group(1), it.get('name', ''), it.get('address', '')))
    return res


def name_candidates(addr, emd):
    names = []
    m = re.search(r'\(([^)]*)\)\s*$', addr)
    if m:
        parts = [p.strip() for p in m.group(1).split(',')]
        names += [p for p in parts if p and not re.fullmatch(r'\S+[동가리]', p)]
    for t in re.findall(r'(\S+?)(?:아파트)?\s+\S*\d+동\s', addr + ' '):
        t = re.sub(r'(아파트|\(.*)$', '', t)
        if t and not re.fullmatch(r'[\d\-]+|\S+[시구읍면]|' + re.escape(emd or '#'), t):
            names.append(t)
    # 지번 바로 뒤 단어 (예: '신사동 593-21 장자울아파트  3층303호', '방배동 799-9 캐슬렉스  6층')
    m = re.search(r'\d+(?:-\d+)?\s+([^\s\d][^\s]*?)(?:아파트)?(?:\(\S*\))?\s', addr + ' ')
    if m:
        w = re.sub(r'제?\d+동$', '', m.group(1))
        if w and not re.fullmatch(r'\S+[동층호]|.*빌딩.*|제\d+.*', w):
            names.append(w)
    names += re.findall(r'([가-힣A-Za-z0-9]+?)아파트', addr)
    names = [re.sub(r'\(.*?\)', '', n) for n in names] + [n for n in names if '(' in n]
    seen, out = set(), []
    for n in names:
        n2 = re.sub(r'아파트$', '', n)
        if n2 and n2 not in seen:
            seen.add(n2); out.append(n2)
    return out


def find_danji(item, cache, kind='apart'):
    page_kind = 'officetel' if kind == 'officetel' else 'danji'
    aid = item['id']
    if cache.get(aid):
        return cache[aid], 'cache'
    tried = set()
    cands = []
    for n in name_candidates(item.get('address', ''), item.get('emd')):
        n2 = re.sub(r'(제?\d+동|주건축물.*)$', '', n)
        for nn in dict.fromkeys([n, n2]):
            if not nn: continue
            cands += [c for c in search(nn, kind)][:8]
            if item.get('emd'):
                cands += [c for c in search(f"{item['emd']} {nn}", kind)][:5]
    if item.get('emd'):
        cands += search(item['emd'], kind)
        if item.get('sgg'):
            cands += search(f"{item['sgg']} {item['emd']}", kind)  # 단지명이 없는 지번 주소: 같은 동의 단지 전부 확인
    sgg_word = item.get('sgg', '').split()[-1]
    for dj, nm, ad in cands:
        if dj in tried: continue
        tried.add(dj)
        if sgg_word and sgg_word not in ad and item.get('sgg', '') not in ad:
            continue
        if aid in danji_auctions(dj, page_kind):
            cache[aid] = dj
            return dj, nm
        if len(tried) > (20 if kind == 'officetel' else 40): break
    return None, f'단지 못 찾음 (확인 {len(tried)}곳)'


# ---------------- 모델 성적표: 예측했던 물건의 실제 결과 ----------------
RESULTS_PATH = os.path.join(OUT_DIR, 'results.json')


def auction_detail(aid):
    raw = get('https://m.richgo.ai/auctionMobile/' + aid)
    if not raw:
        return None
    return next_data(raw).get('auctionPageData') or None


def band_of(actual, prices):
    """실제 낙찰가가 앙상블 확률 가격표의 어느 구간인지."""
    lv = [(40, prices['40%']), (45, prices['45%']), (50, prices['50%']), (55, prices['55%']), (60, prices['60%'])]
    if actual < lv[0][1]: return '40% 미만'
    if actual >= lv[-1][1]: return '60% 초과'
    for (a, pa), (b, pb) in zip(lv, lv[1:]):
        if pa <= actual < pb: return f'{a}~{b}%'
    return '-'


def update_results(today):
    """과거 예측 파일에서 매각기일이 지난 물건을 골라 실제 결과를 기록 (입찰 전에 만든 예측만 사용)."""
    res = json.load(open(RESULTS_PATH)) if os.path.exists(RESULTS_PATH) else {}
    snaps = sorted(f for f in os.listdir(OUT_DIR) if re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json', f))
    last_pred = {}   # (key, bidding_date) -> 그 기일 당일 또는 이전에 만든 마지막 예측
    for fn in snaps:
        d = fn[:10]
        if d >= today: continue
        snap = json.load(open(os.path.join(OUT_DIR, fn)))
        for k, it in snap.get('items', {}).items():
            bd = it.get('bidding_date') or ''
            if not bd or d > bd: continue
            last_pred[(k, bd)] = dict(it, pred_date=d)
    def excluded(it):
        # 지분매각·대지권 없음 등 특수물건은 성적표에서 뺀다 (시세 대비 가격이 원래 낮아 오차 노이즈, 2026-11-03 사용자 요청)
        r = it.get('risk') or {}
        if r.get('decision') == 'hide': return True
        if it.get('appr_vs_sise') is not None and it['appr_vs_sise'] < 0.6: return True
        return any(any(h in w for h in HARD_KW + ['지분경매']) for w in (it.get('warnings') or []) + (r.get('keywords') or []))
    for (k, bd), it in list(last_pred.items()):
        if excluded(it):
            res.pop(f'{k}|{bd}', None); last_pred.pop((k, bd))
    for (k, bd), it in last_pred.items():
        rid = f'{k}|{bd}'
        if bd >= today or bd < str((datetime.fromisoformat(today) - timedelta(days=30)).date()): continue
        if rid in res and res[rid]['status'] in ('매각', '유찰', '변경', '취하', '기각', '정지'): continue
        page = auction_detail(it['auction_id'])
        status, actual, bidders, second = '결과대기', None, None, None
        if page:
            st = page.get('itemStatus') or ''
            if page.get('sellingPrice'):
                status = '매각'; actual = int(page['sellingPrice'] / 1e4)
                bidders = page.get('bidders'); second = int(page['secondHighBiddingPrice'] / 1e4) if page.get('secondHighBiddingPrice') else None
            elif any(w in st for w in ['취하', '기각', '정지', '변경', '연기']):
                status = next(w for w in ['취하', '기각', '정지', '변경', '연기'] if w in st)
            elif (page.get('biddingDate') or '').startswith('9999') or st == '종료':
                status = '취하'   # 매각가 없이 종료 = 취하·기각 등
            elif (page.get('numberOfFailures') or 0) > (it.get('fails') or 0) or ((page.get('biddingDate') or '')[:10] > bd):
                status = '유찰'
        r = dict(key=k, category=it.get('category', '아파트'), danji_name=it.get('danji_name'), area=it.get('area'), region=it.get('region'),
                 bidding_date=bd, pred_date=it['pred_date'], low_manwon=it.get('low_manwon'),
                 bid_by_prob_manwon=it.get('bid_by_prob_manwon'), status=status, checked=today)
        if actual:
            p50 = it['bid_by_prob_manwon']['50%']
            r.update(actual_manwon=actual, bidders=bidders, second_manwon=second,
                     diff_pct=round((actual / p50 - 1) * 100, 1), band=band_of(actual, it['bid_by_prob_manwon']))
        res[rid] = r
    json.dump(dict(sorted(res.items())), open(RESULTS_PATH, 'w'), ensure_ascii=False, indent=1)
    lo = str((datetime.fromisoformat(today) - timedelta(days=7)).date())
    recent = sorted([r for r in res.values() if lo <= r['bidding_date'] < today], key=lambda r: r['bidding_date'], reverse=True)
    sold = [r for r in recent if r['status'] == '매각']
    summ = dict(window=f'{lo}~{today}', n_checked=len(recent), n_sold=len(sold))
    if sold:
        e = [abs(r['diff_pct']) for r in sold]
        summ.update(mean_abs_err_pct=round(sum(e) / len(e), 1), within_5pct=sum(x <= 5 for x in e),
                    in_40_60=sum(r['band'] not in ('40% 미만', '60% 초과') for r in sold),
                    above_p50=sum(r['diff_pct'] > 0 for r in sold))
    return dict(summary=summ, items=recent)


# ---------------- 권리 위험 판정: 리치고 키워드 vs 등기 기준 권리분석 요약 ----------------
HARD_KW = ['지분', '유치권', '법정지상권', '별도등기', '대지권', '건물만', '토지제외']   # 대지권 없음/미등기·건물만 매각 포함 (2026-11-03)   # 요약으로 확인할 수 없는 특수물건 → 숨김


def risk_check(keyword, appr_vs_sise, rights):
    """decision: show / check(키워드와 요약이 다름 → 확인 필요) / hide(둘 다 경고 또는 특수물건)."""
    kw = [k.strip() for k in (keyword or '').split(',') if k.strip()]
    hard = [k for k in kw if any(h in k for h in HARD_KW)]
    r = rights or {}
    known = bool(r.get('hasRegistryData'))
    s_tenant = (r.get('assumedTenantCount') or 0) + (r.get('uncertainTenantCount') or 0) > 0
    s_right = (r.get('assumedRightCount') or 0) > 0 or bool(r.get('hasAssumption'))
    k_tenant = any('대항력' in k for k in kw)
    k_right = any('선순위' in k for k in kw)
    resale = any('재매각' in k for k in kw)
    out = dict(keywords=kw, summary=dict(registry=known, tenant_risk=s_tenant, right_risk=s_right,
                                         base_right=(r.get('baseRight') or {}).get('type'),
                                         base_date=((r.get('baseRight') or {}).get('date') or '')[:10]),
               resale=resale)
    if hard or (appr_vs_sise is not None and appr_vs_sise < 0.6):
        return dict(out, decision='hide', reason='특수물건(' + ','.join(hard or ['감정가<시세60%']) + ')')
    reasons_hide, reasons_check = [], []
    for k_flag, s_flag, name in [(k_tenant, s_tenant, '대항력 임차인'), (k_right, s_right, '인수 권리')]:
        if k_flag and s_flag:
            reasons_hide.append(f'{name}: 키워드·요약 모두 있음')
        elif k_flag and not known:
            reasons_check.append(f'{name}: 키워드엔 있음·등기 요약 없음(미확인)')
        elif k_flag != s_flag:
            reasons_check.append(f'{name}: ' + ('키워드엔 있음·요약엔 없음' if k_flag else '요약엔 있음·키워드엔 없음'))
    if reasons_hide:
        return dict(out, decision='hide', reason=' / '.join(reasons_hide))
    if reasons_check:
        return dict(out, decision='check', reason=' / '.join(reasons_check))
    return dict(out, decision='show', reason='재매각' if resale else '')


# ---------------- 서울 오피스텔 (2026-11-02~) ----------------
SEOUL_GU = ['강남구', '강동구', '강북구', '강서구', '관악구', '광진구', '구로구', '금천구', '노원구', '도봉구', '동대문구', '동작구',
            '마포구', '서대문구', '서초구', '성동구', '성북구', '송파구', '양천구', '영등포구', '용산구', '은평구', '종로구', '중구', '중랑구']
OT_STATION_M = 615   # 역 도보 10분 ≈ 직선 615m (도보분 = 직선거리 × 1.3 ÷ 80)


def page_station(page_id, kind='officetel'):
    raw = get(f'https://m.richgo.ai/realty/{kind}/' + page_id)
    st = [(int(m.group(1)), m.group(2)) for m in re.finditer(r'"distance":(\d+),"targetName":"([^"]*)","indexName":"지하철"', raw)]
    return min(st) if st else (None, None)


def officetel_items(items, skipped, failed, cache, now, workers=8):
    from concurrent.futures import ThreadPoolExecutor
    import officetel_model as om
    odf = om.load_train(); ocfg = json.load(open(om.CFG))
    models = om.fit_models(odf, pd.Timestamp(now.date()))

    def lst(gu):
        try:
            return gu, region_items('서울', gu, '오피스텔')
        except Exception:
            return gu, []
    todo, seen = [], set()
    with ThreadPoolExecutor(workers) as ex:
        for gu, l in ex.map(lst, SEOUL_GU):
            for it in l:
                key = f"{it['caseName']}[{it.get('itemNumber') or 1}]"
                if it['id'] in seen or key in items: continue
                seen.add(it['id']); todo.append((gu, key, it))

    neg_path = os.path.join(HERE, 'officetel', 'nomatch.json')
    neg = json.load(open(neg_path)) if os.path.exists(neg_path) else {}
    today = str(now.date())
    week_ago = str((now - timedelta(days=7)).date())

    def work(arg):
        gu, key, it = arg
        base = dict(key=key, category='오피스텔', auction_id=it['id'], region=f'서울 {gu}', address=it.get('address'),
                    appr_manwon=int((it.get('appraisedPrice') or 0) / 1e4), low_manwon=int((it.get('lowestSellingPrice') or 0) / 1e4),
                    fails=it.get('numberOfFailures'), bidding_date=(it.get('biddingDate') or '')[:10], area=it.get('buildingTotalArea'))
        if not it.get('appraisedPrice') or not it.get('lowestSellingPrice'):
            return 'skip', dict(base, reason='가격정보없음')
        try:
            if neg.get(it['id'], '') >= week_ago and not cache.get(it['id']):
                return 'fail', dict(base, reason='단지 못 찾음 (7일 내 재시도 안 함)')
            dj, how = find_danji(it, cache, 'officetel')
            if not dj:
                neg[it['id']] = today
                return 'fail', dict(base, reason=how)
            st_m, st_name = page_station(dj)
            if st_m is None or st_m > OT_STATION_M:
                return 'skip', dict(base, danji_id=dj, reason=f'역세권아님({st_name or "역 정보 없음"} {st_m}m)')
            pg = auction_detail(it['id']) or {}
            p = om.predict_dict(dj, it['id'], 0, df=odf, cfg=ocfg, models=models)
            rk = risk_check(p.get('keyword'), p.get('appr_vs_sise'), pg.get('rights'))
            if rk['decision'] == 'check':
                p = om.predict_dict(dj, it['id'], 1, df=odf, cfg=ocfg, models=models)
            return 'ok', dict(base, danji_id=dj, danji_name=p.get('name'), court=pg.get('caseSite'),
                              station=dict(name=st_name, distance_m=st_m, walk_min=int(-(-st_m * 1.3 // 80))),
                              **{k: v for k, v in p.items() if k not in ('address', 'area', 'category')}, risk=rk)
        except SystemExit as e:
            return 'fail', dict(base, reason=f'예측 실패: {e}')
        except Exception as e:
            return 'fail', dict(base, reason=f'예측 실패: {type(e).__name__}: {e}')
    with ThreadPoolExecutor(workers) as ex:
        for kind, r in ex.map(work, todo):
            if kind == 'ok': items[r['key']] = r
            elif kind == 'skip': skipped.append(r)
            else: failed.append(r)
    json.dump({k: v for k, v in neg.items() if v >= week_ago}, open(neg_path, 'w'), ensure_ascii=False)


def main():
    now = datetime.now(KST)
    cache = json.load(open(MAP_PATH)) if os.path.exists(MAP_PATH) else {}
    cfg = json.load(open(os.path.join(HERE, 'auction_config.json')))
    df = ap.load_train()
    items, skipped, failed, errors = {}, [], [], []
    seen = set()
    for sd, sgg in REGIONS:
        try:
            lst = region_items(sd, sgg)
        except Exception as e:
            errors.append(str(e)); continue
        for it in lst:
            key = f"{it['caseName']}[{it.get('itemNumber') or 1}]"
            if it['id'] in seen: continue
            seen.add(it['id'])
            if not it.get('appraisedPrice') or not it.get('lowestSellingPrice'):
                skipped.append(dict(key=key, auction_id=it['id'], address=it.get('address'), reason='가격정보없음')); continue
            base = dict(key=key, auction_id=it['id'], region=f'{sd} {sgg}', address=it.get('address'),
                        appr_manwon=int(it['appraisedPrice'] / 1e4), low_manwon=int(it['lowestSellingPrice'] / 1e4),
                        fails=it.get('numberOfFailures'), bidding_date=(it.get('biddingDate') or '')[:10],
                        area=it.get('buildingTotalArea'))
            if 'typeDetails' in it and '아파트' not in (it.get('typeDetails') or []) and it.get('itemType') != '아파트':
                skipped.append(dict(base, reason='아파트 아님')); continue
            if (it.get('buildingTotalArea') or 0) < MIN_AREA:
                skipped.append(dict(base, reason='면적미달')); continue
            if it['lowestSellingPrice'] > MAX_LOW:
                skipped.append(dict(base, reason='예산초과')); continue
            dj, how = find_danji(it, cache)
            if not dj:
                failed.append(dict(base, reason=how)); continue
            try:
                p = ap.predict_dict(dj, it['id'], df=df, cfg=cfg)
                items[key] = dict(base, danji_id=dj, danji_name=p.get('name'), **{k: v for k, v in p.items() if k not in ('address', 'area')})
                try:
                    pg = auction_detail(it['id']) or {}
                except Exception:
                    pg = {}
                items[key]['risk'] = risk_check(p.get('keyword'), p.get('appr_vs_sise'), pg.get('rights'))
                items[key]['court'] = pg.get('caseSite')
                items[key]['category'] = '아파트'
            except SystemExit as e:
                failed.append(dict(base, danji_id=dj, reason=f'예측 실패: {e}'))
            except Exception as e:
                failed.append(dict(base, danji_id=dj, reason=f'예측 실패: {type(e).__name__}: {e}'))
    try:
        officetel_items(items, skipped, failed, cache, now)
    except Exception as e:
        errors.append(f'오피스텔 단계 실패: {type(e).__name__}: {e}')
    # 임차인 자료(사용자 PC가 법원 매각물건명세서에서 읽어 올림)로 보증금 인수 여부 다시 판정 (2026-11-03)
    try:
        import tenant_rules
        n_ten = tenant_rules.apply(items, str(now.date()))
    except Exception as e:
        n_ten = 0; errors.append(f'임차인 판정 실패: {type(e).__name__}: {e}')
    # 안전 등급 + 투자금 회수기간 (2026-11-03)
    try:
        import invest_calc
        invest_calc.apply(items)
    except Exception as e:
        errors.append(f'안전등급·회수기간 실패: {type(e).__name__}: {e}')
    # PC가 다음 날 새벽 조회할 물건 목록 (특수물건은 제외)
    tgt = [dict(key=k, case=k.split('[')[0], item_no=int(k.split('[')[1].rstrip(']')), court=v.get('court'),
                auction_id=v.get('auction_id'), bidding_date=v.get('bidding_date'), category=v.get('category'))
           for k, v in sorted(items.items()) if not (v.get('risk') or {}).get('reason', '').startswith('특수물건')]
    os.makedirs(OUT_DIR, exist_ok=True)
    json.dump(dict(date=str(now.date()), n=len(tgt), items=tgt), open(os.path.join(OUT_DIR, 'tenant_targets.json'), 'w'), ensure_ascii=False, indent=1)
    out = dict(generated_at=now.isoformat(timespec='seconds'), date=str(now.date()), tenant_overrides=n_ten,
               model='앙상블(부스팅+군집별회귀)', config_built=cfg.get('built'),
               filters=dict(min_area=None, max_low_manwon=None),
               counts=dict(predicted=len(items), skipped=len(skipped), failed=len(failed),
                           by_category={c: sum(v.get('category') == c for v in items.values()) for c in ('아파트', '오피스텔')}),
               errors=errors, items=items, failed=failed, skipped=skipped)
    os.makedirs(OUT_DIR, exist_ok=True)
    try:
        out['recent_results'] = update_results(str(now.date()))
    except Exception as e:
        out['recent_results'] = dict(summary=dict(error=f'{type(e).__name__}: {e}'), items=[])
    for fn in ['latest.json', f'{now.date()}.json']:
        json.dump(out, open(os.path.join(OUT_DIR, fn), 'w'), ensure_ascii=False, indent=1)
    json.dump(dict(sorted(cache.items())), open(MAP_PATH, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(out['counts'], ensure_ascii=False), 'errors', errors)
    for f in failed: print('FAILED', f['key'], f['address'], f['reason'])


if __name__ == '__main__':
    main()
