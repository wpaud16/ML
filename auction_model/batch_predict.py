#!/usr/bin/env python3
"""매일 새벽 GitHub Actions에서 실행: 10개 관심 지역의 진행 중 아파트 경매를 모아 앙상블 예측을 미리 계산한다.

결과: predictions/latest.json (+ predictions/YYYY-MM-DD.json)
  items: { "<사건번호>[<물건번호>]": {auction_id, danji_id, ..., bid_by_prob_manwon, prob_by_bid_5m, ...} }
  skipped: 필터 탈락(면적·예산), failed: 단지 연결 또는 예측 실패 (사유 포함)
아침 브리핑은 이 파일을 '읽기만' 하고 코드를 실행하지 않는다.
단지 연결 캐시: danji_map.json { "<경매ID>": "<단지ID>" } (수동으로 추가해도 됨)
"""
import nearby
import json, os, re, sys, time, subprocess, urllib.parse
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import auction_predictor as ap

KST = timezone(timedelta(hours=9))
REGIONS = [('서울', '강남구'), ('서울', '서초구'), ('서울', '강동구'), ('서울', '광진구'), ('서울', '송파구'),
           ('경기', '성남시 수정구'), ('경기', '성남시 분당구'), ('경기', '성남시 중원구'), ('경기', '남양주시'), ('경기', '구리시'),
           ('경기', '하남시')]
REGIONS_PATH = os.path.join(HERE, 'search_regions.json')   # 2026-11-08: 검색 지역은 GUI(local_runner/region_gui.pyw)로 수정
try:
    _rc = json.load(open(REGIONS_PATH, encoding='utf-8'))
    REGIONS = [tuple(x) for x in _rc.get('apt') or REGIONS]
except Exception:
    _rc = {}
MIN_AREA, MAX_LOW = 0.0, float("inf")   # 2026-11-02 사용자 요청으로 면적·최저가 필터 해제
MAP_PATH = os.path.join(HERE, 'danji_map.json')
OUT_DIR = os.path.join(HERE, 'predictions')


_GET = {}


def get(url, tries=3):
    if url in _GET:
        return _GET[url]
    if url in getattr(ap, '_PAGES', {}) and '/auctionMobile/' not in url:   # 예측 모듈이 이미 받은 단지 페이지
        return ap._PAGES[url]
    r = _get(url, tries)
    if r and '/auctionMobile/' not in url:   # 경매 상세는 결과 확인용이라 매번 새로
        if len(_GET) > 3000: _GET.clear()
        _GET[url] = r
    return r


def _get(url, tries=3):
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


def sold_already(pg):
    """상세 페이지에 낙찰가가 있으면 이미 매각된 물건 (재매각 표시 물건은 제외)."""
    if not pg or not pg.get('sellingPrice'):
        return False
    kw = f"{pg.get('keyword') or ''} {pg.get('historyKeyword') or ''}"
    return '재매각' not in kw


def band_of(actual, prices):
    """실제 낙찰가가 앙상블 확률 가격표의 어느 구간인지."""
    if prices['40%'] == prices['60%']:
        return '최저가 단일'   # 확률표가 최저가 하나로 모인 경우 (예상 1명)
    lv = [(40, prices['40%']), (45, prices['45%']), (50, prices['50%']), (55, prices['55%']), (60, prices['60%'])]
    if actual < lv[0][1]: return '40% 미만'
    if actual >= lv[-1][1]: return '60% 초과'
    for (a, pa), (b, pb) in zip(lv, lv[1:]):
        if pa <= actual < pb: return f'{a}~{b}%'
    return '-'


def closest_cell(it, actual_manwon):
    """실제 낙찰가와 가장 가까운 확률 칸 — 예상 인원 줄 안에서 (2026-11-05 사용자 요청: '3명 45% · 9억 (시세 대비 N%)').
    인원별 표가 없으면 전체 확률표. 시세 = 그 예측에 쓴 모델 시세."""
    import cards_page as _cp
    bb = it.get('by_bidders') or {}
    row = _cp.exp_row(it.get('category') or '아파트', bb.get('expected_bidders'))
    tbl = (bb.get('bid_by_prob_eok') or {}).get(row) if row else None
    if tbl:
        cells = [(f'{row} {pk}', v * 1e4) for pk, v in tbl.items() if v]
    else:
        cells = [(f'전체 {pk}', v) for pk, v in (it.get('bid_by_prob_manwon') or {}).items() if v]
    if not cells or not actual_manwon: return None
    lab, v = min(cells, key=lambda c: abs(c[1] - actual_manwon))
    sise = (it.get('model_sise_eok') or it.get('richgo_sise_eok') or 0) * 1e4
    return dict(label=lab, manwon=int(round(v)), pct_of_sise=round(v / sise * 100, 1) if sise else None,
                actual_pct_of_sise=round(actual_manwon / sise * 100, 1) if sise else None,
                sise_basis='M' if (it.get('model_sise_eok') and (it.get('category') or '아파트') == '아파트' and it.get('m_sise')) else '리치고')


def trade_manwon(it):
    """성적표 실거래 기준 % 용: 예측 당시 M 시세의 층 보정 실거래 가중 평균(만원). 아파트·실거래 있는 물건만 (2026-11-10 사용자 요청)."""
    m = it.get('m_sise') or {}
    if (it.get('category') or '아파트') != '아파트' or m.get('no_trade') or not m.get('trade_w'): return None
    return int(round(m['trade_w'] * 1e4))


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
        if rid in res and res[rid].get('expected_bidders') is None and (it.get('by_bidders') or {}).get('expected_bidders'):
            res[rid].update(expected_bidders=it['by_bidders']['expected_bidders'], expected_range=it['by_bidders'].get('expected_range'))
        if rid in res and res[rid].get('actual_manwon') and (res[rid].get('closest') or {}).get('sise_basis') is None:
            res[rid]['closest'] = closest_cell(it, res[rid]['actual_manwon'])   # 예전 기록 채우기
        if rid in res and 'trade_manwon' not in res[rid]:
            res[rid]['trade_manwon'] = trade_manwon(dict(it, **(res[rid].get('rescored_pred') or {})))   # 예전 기록 채우기
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
        r = dict(key=k, auction_id=it.get('auction_id'), category=it.get('category', '아파트'), danji_name=it.get('danji_name'), area=it.get('area'), region=it.get('region'),
                 bidding_date=bd, pred_date=it['pred_date'], low_manwon=it.get('low_manwon'),
                 bid_by_prob_manwon=it.get('bid_by_prob_manwon'), status=status, checked=today,
                 expected_bidders=(it.get('by_bidders') or {}).get('expected_bidders'), expected_range=(it.get('by_bidders') or {}).get('expected_range'),
                 sise_manwon=int(round((it.get('model_sise_eok') or it.get('richgo_sise_eok') or 0) * 1e4)) or None,   # 성적표 시세 대비 % (2026-11-08)
                 trade_manwon=trade_manwon(it))
        old = res.get(rid) or {}
        if old.get('rescored'):   # dev/rescore_pred_m.py 로 M 시세 재계산한 값 유지 (2026-11-08)
            for f in ('orig_bid_by_prob_manwon', 'bid_by_prob_manwon', 'rescored', 'rescored_pred', 'expected_bidders', 'expected_range', 'sise_manwon', 'trade_manwon'):
                r[f] = old.get(f)
            it = dict(it, **(old.get('rescored_pred') or {}))
        if actual:
            p50 = it['bid_by_prob_manwon']['50%']
            r.update(actual_manwon=actual, bidders=bidders, second_manwon=second,
                     diff_pct=round((actual / p50 - 1) * 100, 1), band=band_of(actual, it['bid_by_prob_manwon']),
                     closest=closest_cell(it, actual))
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
if _rc.get('ot') is not None: SEOUL_GU = list(_rc['ot'])   # 오피스텔 검색 구 (GUI)
OT_STATION_M = 615   # 역 도보 10분 ≈ 직선 615m (도보분 = 직선거리 × 1.3 ÷ 80)


def page_station(page_id, kind='officetel'):
    raw = get(f'https://m.richgo.ai/realty/{kind}/' + page_id)
    st = [(int(m.group(1)), m.group(2)) for m in re.finditer(r'"distance":(\d+),"targetName":"([^"]*)","indexName":"지하철"', raw)]
    return min(st) if st else (None, None)


def page_stations(page_id, kind='danji'):
    """단지 페이지 주변 지하철역 목록 [(직선거리m, 역명, [노선...])], 가까운 순."""
    raw = get(f'https://m.richgo.ai/realty/{kind}/' + page_id)
    out = []
    for m in re.finditer(r'\{[^{}]*"indexName":"지하철"[^{}]*\}', raw):
        try:
            o = json.loads(m.group(0)); ln = o.get('subwayLineInfo') or '[]'
            ln = json.loads(ln) if isinstance(ln, str) else ln
            out.append((int(o['distance']), o.get('targetName'), [x.replace('수도권 ', '') for x in ln]))
        except Exception:
            continue
    return sorted(out)


def near_list(sts, limit_m, n=2):
    """가까운 역 최대 n개 (역 이름 중복 제거). 2번째부터는 limit_m(도보 기준) 안에 있을 때만 (2026-11-05 사용자 요청: 가까운 역 2개)."""
    out, seen = [], set()
    for d, nm, ln in sts:
        nm = (nm or '').removesuffix('역')
        if not nm or nm in seen: continue
        if out and d > limit_m: break
        seen.add(nm); out.append(dict(name=nm, distance_m=d, walk_min=int(-(-d * 1.3 // 80)), lines=ln))
        if len(out) >= n: break
    return out


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
            if sold_already(pg):
                return 'skip', dict(base, danji_id=dj, reason='매각완료')
            p = om.predict_dict(dj, it['id'], 0, df=odf, cfg=ocfg, models=models)
            rk = risk_check(p.get('keyword'), p.get('appr_vs_sise'), pg.get('rights'))
            if rk['decision'] == 'check':
                p = om.predict_dict(dj, it['id'], 1, df=odf, cfg=ocfg, models=models)
            try:   # 주변 오피스텔 시세 (2026-11-05)
                bj = ((nearby.page_props('officetel', dj).get('data') or {}).get('bjdInfo') or {})
                nb = nearby.nearby_ot(dj, bj.get('sgg') or gu, bj.get('emd'), it.get('buildingTotalArea'))
                if nb and p.get('sise'):
                    p['sise'] = nearby.merge_into_sise(p['sise'], nb, base['low_manwon'])
            except Exception:
                pass
            try:
                sts2 = near_list(page_stations(dj, 'officetel'), OT_STATION_M)
            except Exception:
                sts2 = []
            return 'ok', dict(base, danji_id=dj, danji_name=p.get('name'), court=pg.get('caseSite'),
                              station=dict(name=st_name, distance_m=st_m, walk_min=int(-(-st_m * 1.3 // 80))), stations=sts2,
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


RECENT_K, RECENT_DAYS, RECENT_CAP = 15, 60, 0.05


def recent_sgg_adj(cfg, today):
    """성적표 최근 매각(아파트)의 지역별 예측 치우침을 구별 보정에 더함 (2026-11-10 사용자 요청).
    계기: 11/2~11/10 남양주·구리 18건 실제가 예측보다 평균 +3.8% (학습 데이터에 최근 남양주 사례 부족).
    결과 예측에는 이미 구별 보정이 들어 있으므로 남은 잔차만 축소(n/(n+K))해서 더함. 날짜순 검증 29건 오차 5.36→5.26%.
    월간 재학습(retrain)으로 이 사례들이 학습에 들어가면 잔차가 줄어 자연히 작아짐."""
    try: res = json.load(open(RESULTS_PATH))
    except Exception: return {}
    keys = sorted(cfg.get('sgg_adj') or {}, key=len, reverse=True)
    lo = str((datetime.fromisoformat(today) - timedelta(days=RECENT_DAYS)).date())
    acc, seen = {}, set()
    for r in res.values():
        if r.get('category', '아파트') != '아파트' or r.get('status') != '매각' or not r.get('actual_manwon'): continue
        if not (lo <= (r.get('bidding_date') or '') < today): continue
        p = (r.get('bid_by_prob_manwon') or {}).get('50%')
        k = (r.get('danji_name'), r['actual_manwon'])
        if not p or k in seen: continue
        seen.add(k)
        reg = r.get('region') or ''
        g = next((x for x in keys if reg.startswith(x)), ' '.join(reg.split()[:2]))
        acc.setdefault(g, []).append(np.log(r['actual_manwon'] / p))
    return {g: float(np.clip(np.mean(v) * len(v) / (len(v) + RECENT_K), -RECENT_CAP, RECENT_CAP)) for g, v in acc.items()}


def main():
    now = datetime.now(KST)
    cache = json.load(open(MAP_PATH)) if os.path.exists(MAP_PATH) else {}
    cfg = json.load(open(os.path.join(HERE, 'auction_config.json')))
    radj = recent_sgg_adj(cfg, str(now.date()))   # 최근 성적표 지역 치우침 (cfg 사본에만 더함, 파일은 그대로)
    cfg['sgg_adj'] = {g: round(float((cfg.get('sgg_adj') or {}).get(g, 0.0) + radj.get(g, 0.0)), 5) for g in set(cfg.get('sgg_adj') or {}) | set(radj)}
    print('최근 성적표 지역 보정:', {g: f'{v * 100:+.1f}%' for g, v in sorted(radj.items(), key=lambda x: -abs(x[1]))[:8]})
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
            try:
                pg = auction_detail(it['id']) or {}
            except Exception:
                pg = {}
            if sold_already(pg):
                skipped.append(dict(base, reason='매각완료')); continue
            dj, how = find_danji(it, cache)
            if not dj:   # 예측은 못 해도 목록에 표시·추적 (2026-11-05 사용자 요청)
                failed.append(dict(base, reason=how, category='아파트', court=pg.get('caseSite'),
                                   risk=risk_check(pg.get('keyword'), None, pg.get('rights')))); continue
            try:
                p = ap.predict_dict(dj, it['id'], df=df, cfg=cfg)
                items[key] = dict(base, danji_id=dj, danji_name=p.get('name'), **{k: v for k, v in p.items() if k not in ('address', 'area')})
                items[key]['risk'] = risk_check(p.get('keyword'), p.get('appr_vs_sise'), pg.get('rights'))
                items[key]['court'] = pg.get('caseSite')
                items[key]['category'] = '아파트'
                # 가장 가까운 지하철역 (2026-11-04 사용자 요청: 아파트도 오피스텔처럼 역 표시)
                try:
                    sts = page_stations(dj, 'danji')
                    if sts:
                        d0, n0, l0 = sts[0]
                        items[key]['station'] = dict(name=n0, distance_m=d0, walk_min=int(-(-d0 * 1.3 // 80)), lines=l0)
                        items[key]['stations'] = near_list(sts, 920)   # 도보 15분 안 역 최대 2개
                        s8 = [x for x in sts if any('8호선' in ln for ln in x[2])]
                        if s8:
                            items[key]['station8'] = dict(name=s8[0][1], distance_m=s8[0][0], walk_min=int(-(-s8[0][0] * 1.3 // 80)))
                        s5 = [x for x in sts if any('5호선' in ln for ln in x[2])]   # 하남: 5호선역 도보 15분 (2026-11-05)
                        if s5:
                            items[key]['station5'] = dict(name=s5[0][1], distance_m=s5[0][0], walk_min=int(-(-s5[0][0] * 1.3 // 80)))
                except Exception:
                    pass
                # 주변 단지 시세를 종합 시세의 네 번째 근거로 (2026-11-05)
                try:
                    nb = nearby.nearby_apt(dj, p.get('pyeong'))
                    if nb:
                        items[key]['sise'] = nearby.merge_into_sise(items[key].get('sise'), nb, items[key]['low_manwon'])
                except Exception:
                    pass
                try:   # 가중 시세: 3개월 실거래 60 · 층 보정 20 · 최저 호가 15(상한) · 감정 시차 5 (2026-11-05)
                    ws = nearby.weighted_apt(dj, p.get('pyeong'), base.get('address'), base['appr_manwon'], items[key].get('sise'))
                    if ws and items[key].get('sise') is not None:
                        items[key]['sise'] = dict(items[key]['sise'], weighted=ws)
                except Exception:
                    pass
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
    tgt += [dict(key=f['key'], case=f['key'].split('[')[0], item_no=int(f['key'].split('[')[1].rstrip(']')), court=f.get('court'),
                 auction_id=f.get('auction_id'), bidding_date=f.get('bidding_date'), category='아파트')
            for f in failed if f.get('category') == '아파트' and (f.get('risk') or {}).get('decision') == 'show']
    os.makedirs(OUT_DIR, exist_ok=True)
    # 결과 날짜: 18시 이후 실행은 다음 날 아침 메일용 (2026-11-05: 예약 실행 지연 대비 전날 21시부터 실행)
    day = (now + timedelta(hours=6)).date()
    json.dump(dict(date=str(day), n=len(tgt), items=tgt), open(os.path.join(OUT_DIR, 'tenant_targets.json'), 'w'), ensure_ascii=False, indent=1)
    out = dict(generated_at=now.isoformat(timespec='seconds'), date=str(day), tenant_overrides=n_ten,
               model='앙상블(부스팅+군집별회귀)', config_built=cfg.get('built'),
               filters=dict(min_area=None, max_low_manwon=None),
               counts=dict(predicted=len(items), skipped=len(skipped), failed=len(failed),
                           by_category={c: sum(v.get('category') == c for v in items.values()) for c in ('아파트', '오피스텔')}),
               errors=errors, items=items, failed=failed, skipped=skipped)
    os.makedirs(OUT_DIR, exist_ok=True)
    try:
        out['recent_results'] = update_results(str(day))
    except Exception as e:
        out['recent_results'] = dict(summary=dict(error=f'{type(e).__name__}: {e}'), items=[])
    for fn in ['latest.json', f'{day}.json']:
        json.dump(out, open(os.path.join(OUT_DIR, fn), 'w'), ensure_ascii=False, indent=1)
    json.dump(dict(sorted(cache.items())), open(MAP_PATH, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(out['counts'], ensure_ascii=False), 'errors', errors)
    for f in failed: print('FAILED', f['key'], f['address'], f['reason'])


if __name__ == '__main__':
    main()
