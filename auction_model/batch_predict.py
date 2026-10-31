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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import auction_predictor as ap

KST = timezone(timedelta(hours=9))
REGIONS = [('서울', '강남구'), ('서울', '서초구'), ('서울', '강동구'), ('서울', '광진구'), ('서울', '송파구'),
           ('경기', '성남시 수정구'), ('경기', '성남시 분당구'), ('경기', '성남시 중원구'), ('경기', '남양주시'), ('경기', '구리시')]
MIN_AREA, MAX_LOW = 54.0, 13e8
MAP_PATH = os.path.join(HERE, 'danji_map.json')
OUT_DIR = os.path.join(HERE, 'predictions')


def get(url, tries=3):
    for k in range(tries):
        r = subprocess.run(['curl', '-sL', '-m', '40', '-A', 'Mozilla/5.0', url], capture_output=True, text=True).stdout
        if '__NEXT_DATA__' in r:
            return r
        time.sleep(2 + 3 * k)
    return ''


def next_data(raw):
    i = raw.find('__NEXT_DATA__'); j = raw.find('>', i); k = raw.find('</script>', j)
    return json.loads(raw[j + 1:k])['props']['pageProps']


def q(s):
    return urllib.parse.quote(s)


def region_items(sd, sgg):
    out, page = [], 1
    while True:
        url = f'https://m.richgo.ai/auction/hub/region/{q(sd)}/{q(sgg)}/{q("아파트")}' + (f'?page={page}' if page > 1 else '')
        raw = get(url)
        if not raw:
            raise RuntimeError(f'list fetch failed {sd} {sgg} p{page}')
        d = next_data(raw)['data']
        out += d['items']
        if page * d['size'] >= d['totalCount'] or not d['items']:
            return out
        page += 1


def danji_auctions(danji):
    raw = get('https://m.richgo.ai/realty/danji/' + danji)
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


def search(term):
    raw = get('https://m.richgo.ai/realty/search?q=' + q(term))
    if not raw:
        return []
    res = []
    for g in (next_data(raw).get('agentSearch') or {}).get('groups') or []:
        if g.get('kind') != 'apart': continue
        for it in g.get('items') or []:
            m = re.search(r'/realty/danji/([0-9A-Za-z]+)', it.get('href', ''))
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
    if m and not re.fullmatch(r'\S+[동층호]|.*빌딩.*', m.group(1)):
        names.append(m.group(1))
    names += re.findall(r'([가-힣A-Za-z0-9]+?)아파트', addr)
    names = [re.sub(r'\(.*?\)', '', n) for n in names] + [n for n in names if '(' in n]
    seen, out = set(), []
    for n in names:
        n2 = re.sub(r'아파트$', '', n)
        if n2 and n2 not in seen:
            seen.add(n2); out.append(n2)
    return out


def find_danji(item, cache):
    aid = item['id']
    if cache.get(aid):
        return cache[aid], 'cache'
    tried = set()
    cands = []
    for n in name_candidates(item.get('address', ''), item.get('emd')):
        cands += [c for c in search(n)][:8]
        if item.get('emd'):
            cands += [c for c in search(f"{item['emd']} {n}")][:5]
    if item.get('emd'):
        cands += search(item['emd'])  # 단지명이 없는 지번 주소: 같은 동의 단지 전부 확인
    sgg_word = item.get('sgg', '').split()[-1]
    for dj, nm, ad in cands:
        if dj in tried: continue
        tried.add(dj)
        if sgg_word and sgg_word not in ad and item.get('sgg', '') not in ad:
            continue
        if aid in danji_auctions(dj):
            cache[aid] = dj
            return dj, nm
        if len(tried) > 40: break
    return None, f'단지 못 찾음 (확인 {len(tried)}곳)'


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
            except SystemExit as e:
                failed.append(dict(base, danji_id=dj, reason=f'예측 실패: {e}'))
            except Exception as e:
                failed.append(dict(base, danji_id=dj, reason=f'예측 실패: {type(e).__name__}: {e}'))
    out = dict(generated_at=now.isoformat(timespec='seconds'), date=str(now.date()),
               model='앙상블(부스팅+군집별회귀)', config_built=cfg.get('built'),
               filters=dict(min_area=MIN_AREA, max_low_manwon=int(MAX_LOW / 1e4)),
               counts=dict(predicted=len(items), skipped=len(skipped), failed=len(failed)),
               errors=errors, items=items, failed=failed, skipped=skipped)
    os.makedirs(OUT_DIR, exist_ok=True)
    for fn in ['latest.json', f'{now.date()}.json']:
        json.dump(out, open(os.path.join(OUT_DIR, fn), 'w'), ensure_ascii=False, indent=1)
    json.dump(dict(sorted(cache.items())), open(MAP_PATH, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(out['counts'], ensure_ascii=False), 'errors', errors)
    for f in failed: print('FAILED', f['key'], f['address'], f['reason'])


if __name__ == '__main__':
    main()
