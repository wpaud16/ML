#!/usr/bin/env python3
"""빌라·상가·건물 경매 목록 (2026-11-16 사용자 요청: 웹페이지에 아파트·오피스텔처럼 탭 추가). 예측 모델은 없음 — 사실만.

조건 (사용자 결정 2026-11-16):
  🏘 빌라 = 서울 25개 구 다세대·연립, 역 도보 15분(직선 920m) 이내
  🏪 상가 = 서울 근린시설 중 구분상가 1칸(대지 없이 호실만 매각; 근린상가·단지 내 상가), 역 도보 15분 이내
  🏢 건물 = 서울 근린시설(꼬마빌딩: 대지 포함)·근린주택(상가주택)·다가구주택, 역 도보 15분 이내, 최저가 20억 이하
  공통 원칙: 권리가 깨끗한 물건만 (등기 요약 있음 + 인수 권리·대항력 임차인 없음 + 지분·유치권·법정지상권·대지권·건물만/토지만 아님)

역 거리: 카카오 로컬 API (.env KAKAO_REST_KEY) — 주소 → 좌표 → 반경 920m 지하철역(직선, 가까운 순).
  키가 없으면 역 거리를 알 수 없어 목록에 넣지 않는다 (counts.no_station). 결과는 geo_cache.json 에 저장해 다시 묻지 않음.
결과: predictions/others.json {date, generated_at, items:{key:{...category:'빌라'|'상가'|'건물'}}, counts, errors}
"""
import json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from batch_predict import get, next_data, auction_detail, sold_already, sold_recent  # noqa: E402
from villa_log import GU as SEOUL_GU  # noqa: E402   서울 25개 구 전체 (오피스텔 GUI 지역과 별개)

KST = timezone(timedelta(hours=9))
OUT = os.path.join(HERE, 'predictions', 'others.json')
GEO = os.path.join(HERE, 'geo_cache.json')
WALK_M = 920            # 도보 15분 ≈ 직선 920m (도보분 = 직선 × 1.3 ÷ 80)
BLDG_MAX_LOW = 20e8     # 건물 최저가 20억 이하
HARD = {'지분': r'지분\s*(?:매각|경매|만)|\d+\s*분의\s*\d+\s*지분\s*(?:매각|경매)', '유치권': r'유치권',
        '법정지상권': r'법정지상권', '대지권없음': r'대지권\s*(?:없|미등기)', '건물만': r'건물만\s*(?:매각|경매)',
        '토지만': r'토지만\s*(?:매각|경매)', '별도등기': r'별도\s*등기', '분묘': r'분묘'}
q = urllib.parse.quote


def category(ty, td, addr=''):
    """리치고 검색 유형 + typeDetails (+주소) → '빌라'|'상가'|'건물'|None."""
    unit = bool(re.search(r'\d+층\s*\S*\d+호|\S+호\s*$|지하?\d*층\S*호', addr or ''))   # 'n층 m호' = 집합건물 호실
    # 검색 유형이 맞지 않으면 리치고가 전체 목록을 돌려주므로(예: '연립') typeDetails 로만 판정
    td = set(td or [])
    if td & {'아파트', '오피스텔', '주상복합(상가)', '단독주택', '다중주택'}:
        return None
    if td & {'근린주택', '다가구주택'}:
        return None if unit else '건물'   # 호실 주소인 다가구는 자료 오류로 보고 제외
    if '근린시설' in td:
        return '건물' if '대지' in td and not unit else '상가'
    if td & {'다세대', '연립'}:
        return '빌라'
    return None


SEARCH = ['다세대', '연립', '근린시설', '근린주택', '다가구주택']


def list_items(args):
    gu, ty = args
    out, page = [], 1
    while page <= 30:
        raw = get(f'https://m.richgo.ai/auction/hub/region/{q("서울")}/{q(gu)}/{q(ty)}' + (f'?page={page}' if page > 1 else ''))
        if not raw:
            return out, f'{gu} {ty} p{page} 목록 실패'
        d = next_data(raw)['data']
        out += [dict(it, _type=ty, _gu=gu) for it in d['items']]
        if page * d['size'] >= d['totalCount'] or not d['items']:
            break
        page += 1
    return out, None


# ---------- 카카오 로컬: 주소 → 좌표 → 가까운 지하철역 ----------
def _kakao(path, params):
    key = os.environ.get('KAKAO_REST_KEY', '').strip()
    url = 'https://dapi.kakao.com' + path + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'Authorization': 'KakaoAK ' + key})
    for k in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise RuntimeError(f'카카오 키 오류 {e.code}')
            time.sleep(1 + 2 * k)
        except Exception:
            time.sleep(1 + 2 * k)
    return None


def lot_address(addr):
    """'서울특별시 마포구 연남동 564-25 도화엘리시아  5층504호' → '서울특별시 마포구 연남동 564-25'
       '서울특별시 마포구 만리재로 14, 지하1층15호 (공덕동,...)' → '서울특별시 마포구 만리재로 14'."""
    a = re.sub(r'\s*\(.*$', '', addr or '').split(',')[0].strip()
    m = re.match(r'(.*?\S+(?:동|가|리|로|길)\d*\s+(?:산\s?)?\d+(?:-\d+)?)', a)
    return (m.group(1) if m else a).strip()


def stations_for(addr, geo):
    """→ [{name, distance_m, walk_min, lines}] (반경 920m, 가까운 순, 역 이름 중복 제거) / None(좌표 못 찾음)."""
    la = lot_address(addr)
    if la in geo:
        return geo[la].get('stations')
    d = _kakao('/v2/local/search/address.json', {'query': la})
    docs = (d or {}).get('documents') or []
    if not docs:
        geo[la] = dict(stations=None, at=str(datetime.now(KST).date()))
        return None
    x, y = docs[0]['x'], docs[0]['y']
    c = _kakao('/v2/local/search/category.json', {'category_group_code': 'SW8', 'x': x, 'y': y, 'radius': WALK_M, 'sort': 'distance'})
    out, seen = [], set()
    for p in (c or {}).get('documents') or []:
        nm = re.sub(r'역.*$', '', p.get('place_name') or '').strip()
        line = (p.get('place_name') or '').split('역', 1)[-1].strip()
        dm = int(p.get('distance') or 0)
        if not nm: continue
        if nm in seen:
            for o in out:
                if o['name'] == nm and line and line not in o['lines']: o['lines'].append(line)
            continue
        seen.add(nm)
        out.append(dict(name=nm, distance_m=dm, walk_min=int(-(-dm * 1.3 // 80)), lines=[line] if line else []))
    geo[la] = dict(x=x, y=y, stations=out[:3], at=str(datetime.now(KST).date()))
    return out[:3]


def rights_ok(pg, it):
    """권리 깨끗함: 등기 요약 있음 + 인수 권리·대항력(불확실 포함) 임차인 없음 + 특수 문구 없음. → (ok, 사유)."""
    r = (pg or {}).get('rights') or {}
    head = ' '.join([it.get('address') or '', ' '.join(it.get('typeDetails') or [])])
    text = head + ' ' + ((pg or {}).get('appraisalSummary') or '')
    # 빌라 감정서에 흔한 '대지권 비율'·'공유지분' 같은 문구는 걸리지 않게 매각 조건 문구만 본다
    hard = [n for n, pat in HARD.items() if re.search(pat, text)] + (['지분'] if '지분' in head else [])
    if hard:
        return False, '특수(' + ','.join(hard) + ')'
    if not r.get('hasRegistryData'):
        return False, '등기 요약 없음'
    if (r.get('assumedTenantCount') or 0) or (r.get('uncertainTenantCount') or 0):
        return False, '대항력 임차인(가능성)'
    if (r.get('assumedRightCount') or 0) or r.get('hasAssumption'):
        return False, '인수 권리'
    return True, ''


def traffic_line(pg):
    """감정평가 요항표의 '교통상황' 문장 (참고)."""
    import html
    t = html.unescape(html.unescape((pg or {}).get('appraisalSummary') or ''))
    m = re.search(r'교통(?:상황|관계)?\s*([^\n]{5,160})', t)
    return re.sub(r'["“”]{2,}', '', m.group(1)).strip() if m else None


def main():
    now = datetime.now(KST); today = str(now.date())
    day = str((now + timedelta(hours=6)).date())
    geo = json.load(open(GEO, encoding='utf-8')) if os.path.exists(GEO) else {}
    have_key = bool(os.environ.get('KAKAO_REST_KEY', '').strip())
    errors, cand, seen = [], [], set()
    counts = dict(listed=0, wrong_type=0, over_budget=0, no_station=0, far=0, sold=0, rights=0, shown=0)
    with ThreadPoolExecutor(6) as ex:
        for items, err in ex.map(list_items, [(g, t) for g in SEOUL_GU for t in SEARCH]):
            if err: errors.append(err)
            for it in items:
                if it['id'] in seen or not it.get('appraisedPrice') or not it.get('lowestSellingPrice'):
                    continue
                seen.add(it['id']); counts['listed'] += 1
                cat = category(it['_type'], it.get('typeDetails'), it.get('address'))
                if cat is None or '오피스텔' in (it.get('typeDetails') or []) or '아파트' in (it.get('typeDetails') or []):
                    counts['wrong_type'] += 1; continue
                if cat == '건물' and it['lowestSellingPrice'] > BLDG_MAX_LOW:
                    counts['over_budget'] += 1; continue
                cand.append((cat, it))
    # 역 거리 (카카오, 순차·캐시)
    near = []
    key_err = []

    def geo_one(arg):
        if not have_key or key_err:
            return arg, None
        try:
            return arg, stations_for(arg[1].get('address'), geo)
        except RuntimeError as e:
            key_err.append(str(e)); return arg, None
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(geo_one, cand))
    errors += sorted(set(key_err))
    for (cat, it), st in res:
        if st is None:
            counts['no_station'] += 1; continue
        if not st or st[0]['distance_m'] > WALK_M:
            counts['far'] += 1; continue
        near.append((cat, it, st))
    json.dump(dict(sorted(geo.items())), open(GEO, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)

    def work(arg):
        cat, it, st = arg
        key = f"{it['caseName']}[{it.get('itemNumber') or 1}]"
        base = dict(key=key, category=cat, auction_id=it['id'], region=f"서울 {it['_gu']}", address=it.get('address'),
                    emd=it.get('emd'), type_details=it.get('typeDetails'), item_type=it.get('itemType'),
                    appr_manwon=int(it['appraisedPrice'] / 1e4), low_manwon=int(it['lowestSellingPrice'] / 1e4),
                    fails=it.get('numberOfFailures'), bidding_date=(it.get('biddingDate') or '')[:10],
                    area=it.get('buildingTotalArea'), land_area=it.get('groundTotalArea'), court=it.get('caseSite'),
                    stations=st, station=st[0])
        try:
            pg = auction_detail(it['id']) or {}
        except Exception:
            pg = {}
        if not pg:
            return 'rights', None
        if sold_already(pg) or sold_recent(key, base['bidding_date']):
            return 'sold', None
        ok, why = rights_ok(pg, it)
        if not ok:
            return 'rights', None
        r = pg.get('rights') or {}
        return 'ok', dict(base, construct_year=pg.get('constructYear'), traffic=traffic_line(pg),
                          rights=dict(base_right=(r.get('baseRight') or {}).get('type'), base_date=((r.get('baseRight') or {}).get('date') or '')[:10]),
                          history=[dict(date=h.get('appointedDayAt'), type=h.get('appointedDayType'),
                                        low_manwon=int(h['lowestSellingPrice'] / 1e4) if h.get('lowestSellingPrice') else None, result=h.get('results'))
                                   for h in (pg.get('historyList') or [])])
    items = {}
    with ThreadPoolExecutor(6) as ex:
        for kind, v in ex.map(work, near):
            if kind == 'ok':
                items[v['key']] = v; counts['shown'] += 1
            else:
                counts[kind] += 1
    counts['by_category'] = {c: sum(v['category'] == c for v in items.values()) for c in ('빌라', '상가', '건물')}
    out = dict(date=day, generated_at=now.isoformat(timespec='seconds'), station_source='카카오 로컬' if have_key else None,
               counts=counts, errors=errors, items=items)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(dict(counts, errors=errors[:5]), ensure_ascii=False))


if __name__ == '__main__':
    main()
