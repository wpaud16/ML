#!/usr/bin/env python3
"""KB 시세 붙이기 (2026-11-17 사용자 요청: 성적표에 KB 시세 대비 %, 물건 카드에 KB 시세).

리치고가 2026-11-09부터 KB 시세를 주지 않아 KB부동산(kbland.kr) 공개 화면이 쓰는 API에서 직접 받는다.
  1) 리치고 단지 좌표(location x,y) 주변 KB 단지 목록 (map250mBlwInfoList) → 이름·거리로 같은 단지 찾기
  2) KB 단지 면적 목록 (typInfo) → 전용면적이 가장 가까운 면적 (±2㎡ 안)
  3) 현재 시세 (BasePrcInfoNew: 매매 일반가·하한가·상한가) + 월별 시세 (preSaleChart: 기일 당시 값)
KB 시세는 모델 입력이 아니다 (참고·성적표 비교용). 단지 연결은 kb_cache.json 에 저장해 다시 찾지 않는다.

python kb_sise.py            # 오늘 예측 파일·latest.json 에 'kb' 붙이고, results.json 최근 30일 행에 kb_manwon 채움
"""
import json, os, re, sys, time
from datetime import datetime, timedelta, timezone
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PRED = os.path.join(HERE, 'predictions')
CACHE = os.path.join(HERE, 'kb_cache.json')
KST = timezone(timedelta(hours=9))
B = 'https://api.kbland.kr'
H = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://kbland.kr/', 'Origin': 'https://kbland.kr'}
KINDS = '01,02,04,05,41'   # 아파트·주상복합·오피스텔·(분양권)·재건축
SES = requests.Session()


def _get(path, **p):
    time.sleep(0.3)
    r = SES.get(B + path, params=p, headers=H, timeout=20)
    return ((r.json().get('dataBody') or {}).get('data'))


def _post(path, body):
    time.sleep(0.3)
    r = SES.post(B + path, json=body, headers=H, timeout=20)
    return ((r.json().get('dataBody') or {}).get('data'))


def norm(s):
    s = re.sub(r'\(.*?\)|아파트|오피스텔|주상복합|[\s\-·,.]', '', s or '')
    return s.lower()


def sim(a, b):
    a, b = norm(a), norm(b)
    if not a or not b: return 0.0
    if a in b or b in a: return 1.0
    common = sum(min(a.count(c), b.count(c)) for c in set(a))
    return 2 * common / (len(a) + len(b))


def dist_m(y1, x1, y2, x2):
    return (((y1 - y2) * 111000) ** 2 + ((x1 - x2) * 88000) ** 2) ** 0.5


def richgo_loc(danji_id, kind):
    from batch_predict import get, next_data
    d = next_data(get(f'https://m.richgo.ai/realty/{kind}/{danji_id}'))
    d = d.get('data') or d
    loc = d.get('location') or {}
    x, y = loc.get('x'), loc.get('y')
    return (float(y), float(x), d.get('name')) if x and y else (None, None, d.get('name'))


def find_complex(name, lat, lng):
    """좌표 주변 KB 단지 중 이름이 가장 비슷한 것. 반환 (KB단지번호, KB단지명, 거리m, 유사도) 또는 None."""
    d = 0.0025
    body = dict(selectCode='1,2,3', zoomLevel=17, 물건종류=KINDS, 거래유형='1,2,3', webCheck='Y', 전용면적선택여부='false',
                latitude=lat, longitude=lng, startLat=lat - d, startLng=lng - d * 1.3, endLat=lat + d, endLng=lng + d * 1.3)
    L = (_post('/land-complex/map/map250mBlwInfoList', body) or {}).get('단지리스트') or []
    best = None
    for c in L:
        try: m = dist_m(lat, lng, float(c['wgs84위도']), float(c['wgs84경도']))
        except (TypeError, ValueError, KeyError): continue
        s = sim(name, c.get('단지명'))
        score = s - m / 1000
        if (s >= 0.6 or (m <= 60 and s >= 0.3)) and (best is None or score > best[0]):
            best = (score, c['단지기본일련번호'], c.get('단지명'), round(m), round(s, 2))
    return best[1:] if best else None


def find_area(kb_id, area):
    """전용면적이 가장 가까운 KB 면적 (±2㎡). 반환 (면적일련번호, 전용면적) 또는 None."""
    best = None
    for t in _get('/land-complex/complex/typInfo', 단지기본일련번호=kb_id) or []:
        try: a = float(t.get('전용면적'))
        except (TypeError, ValueError): continue
        if best is None or abs(a - area) < abs(best[1] - area):
            best = (t['면적일련번호'], a)
    return best if best and abs(best[1] - area) <= 2.0 else None


def price_now(kb_id, area_id):
    d = _get('/land-price/price/BasePrcInfoNew', 단지기본일련번호=kb_id, 면적일련번호=area_id) or {}
    s = (d.get('시세') or [{}])[0]
    if not s.get('매매일반거래가'): return None
    return dict(manwon=int(s['매매일반거래가']), low=s.get('매매하한가'), high=s.get('매매상한가'),
                date=(s.get('시세기준년월일') or '')[:8])


def price_hist(kb_id, area_id, start):
    d = _get('/land-price/price/complex/preSaleChart', 거래구분=0, 단지기본일련번호=kb_id, 조회구분=2, 면적일련번호=area_id,
             면적그룹여부=0, 조회시작일=start.replace('-', ''), 조회종료일=datetime.now(KST).strftime('%Y%m%d')) or {}
    return {x['기준년월']: int(x['매매일반거래가']) for x in d.get('시세') or [] if x.get('매매일반거래가')}


class KB:
    def __init__(self):
        try: self.c = json.load(open(CACHE, encoding='utf-8'))
        except Exception: self.c = {}
        self.c.setdefault('link', {}); self.c.setdefault('area', {})
        self.today = datetime.now(KST).strftime('%Y-%m-%d'); self.price = {}; self.hist = {}

    def save(self):
        json.dump(self.c, open(CACHE + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
        os.replace(CACHE + '.tmp', CACHE)

    def link(self, it):
        did = it.get('danji_id'); cat = it.get('category') or '아파트'
        if not did: return None
        if did not in self.c['link']:
            kind = 'officetel' if cat == '오피스텔' else 'danji'
            try:
                lat, lng, nm = richgo_loc(did, kind)
                f = find_complex(nm or it.get('danji_name'), lat, lng) if lat else None
            except Exception as e:
                print('KB 연결 실패', did, e); return None
            self.c['link'][did] = dict(kb_id=f[0], kb_name=f[1], dist_m=f[2], sim=f[3]) if f else None
        return self.c['link'][did]

    def area(self, kb_id, area):
        k = f'{kb_id}|{round(float(area), 1)}'
        if k not in self.c['area']:
            try: f = find_area(kb_id, float(area))
            except Exception as e:
                print('KB 면적 실패', k, e); return None
            self.c['area'][k] = dict(area_id=f[0], kb_area=f[1]) if f else None
        return self.c['area'][k]

    def lookup(self, it, at_date=None):
        """물건 → dict(manwon, eok, date, kb_name, kb_area, low, high) 또는 None. at_date(YYYY-MM-DD) 주면 그 달 KB 시세."""
        if not it.get('area'): return None
        ln = self.link(it)
        if not ln: return None
        ar = self.area(ln['kb_id'], it['area'])
        if not ar: return None
        key = (ln['kb_id'], ar['area_id'])
        base = dict(kb_id=ln['kb_id'], kb_name=ln['kb_name'], kb_area=ar['kb_area'])
        if at_date:
            if key not in self.hist:
                try: self.hist[key] = price_hist(*key, start=str((datetime.now(KST) - timedelta(days=400)).date()))
                except Exception as e:
                    print('KB 월별 실패', key, e); self.hist[key] = {}
            ym = at_date[:7].replace('-', ''); hs = self.hist[key]
            pr = [m for m in sorted(hs) if m <= ym]
            if not pr: return None
            v = hs[pr[-1]]
            return dict(base, manwon=v, eok=round(v / 1e4, 2), date=pr[-1][:4] + '-' + pr[-1][4:], basis='월별')
        if key not in self.price:
            try: self.price[key] = price_now(*key)
            except Exception as e:
                print('KB 시세 실패', key, e); self.price[key] = None
        p = self.price[key]
        if not p: return None
        d = p['date']
        return dict(base, manwon=p['manwon'], eok=round(p['manwon'] / 1e4, 2), low=p.get('low'), high=p.get('high'),
                    date=f'{d[:4]}-{d[4:6]}-{d[6:8]}' if len(d) == 8 else d, basis='현재')


def annotate(kb, path):
    try: d = json.load(open(path, encoding='utf-8'))
    except Exception: return 0
    n = 0
    for it in d.get('items', {}).values():
        v = kb.lookup(it)
        it['kb'] = v
        n += bool(v)
    json.dump(d, open(path + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(path + '.tmp', path)
    return n


def backfill_results(kb, days=30):
    p = os.path.join(PRED, 'results.json')
    try: res = json.load(open(p, encoding='utf-8'))
    except Exception: return 0
    lo = str((datetime.now(KST) - timedelta(days=days)).date())
    need = {rid: r for rid, r in res.items() if r.get('bidding_date', '') >= lo and 'kb_manwon' not in r}
    if not need: return 0
    # results 행에는 단지 번호가 없어 예측 파일에서 찾는다
    info = {}
    for fn in sorted(f for f in os.listdir(PRED) if re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json', f))[-45:]:
        try: items = json.load(open(os.path.join(PRED, fn), encoding='utf-8'))['items']
        except Exception: continue
        for k, it in items.items():
            if it.get('danji_id'): info[k] = it
    n = 0
    for rid, r in need.items():
        it = info.get(r['key'])
        if not it: continue
        v = kb.lookup(dict(it, area=r.get('area') or it.get('area')), at_date=r['bidding_date'])
        r['kb_manwon'] = v['manwon'] if v else None
        r['kb_date'] = v['date'] if v else None
        n += bool(v)
    json.dump(dict(sorted(res.items())), open(p + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(p + '.tmp', p)
    return n


def main():
    kb = KB()
    today = kb.today
    try:
        a = annotate(kb, os.path.join(PRED, f'{today}.json'))
        b = annotate(kb, os.path.join(PRED, 'latest.json'))
        c = backfill_results(kb)
    finally:
        kb.save()
    links = kb.c['link']
    print(json.dumps(dict(today=a, latest=b, results=c, danji=len(links), linked=sum(1 for v in links.values() if v)), ensure_ascii=False))


if __name__ == '__main__':
    main()
