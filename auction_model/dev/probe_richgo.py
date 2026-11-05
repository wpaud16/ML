"""리치고 탐색 (2026-11-05): 학습 사례(아파트 1,413건)의 경매 물건 주소(층·호) — 시세 층 보정 백테스트용 (dev/probe/case_addr.json).
단지 페이지 auctionInfo(과거 경매 포함)에서 auction_id 의 address."""
import json, os, sys, csv
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); AM = os.path.dirname(HERE); sys.path.insert(0, AM)
import nearby
OUT = os.path.join(HERE, 'probe')
rows = list(csv.DictReader(open(os.path.join(AM, 'court_backfill', 'apt_case_map.csv'), encoding='utf-8')))
need = {}
for r in rows: need.setdefault(r['danji'], set()).add(r['auction_id'])


def one(dj):
    d = nearby.page_props('danji', dj).get('data') or {}
    out = {}
    def flat(x):
        if not x: return
        if x.get('auctionId') in need[dj]:
            out[x['auctionId']] = dict(address=x.get('address'), floor=x.get('floor'), dong=x.get('dong'), ho=x.get('ho'), keys=sorted(x)[:60])
        for s in x.get('subList') or []: flat(s)
    flat(d.get('auctionInfo'))
    return out


res = {}
with ThreadPoolExecutor(8) as ex:
    for o in ex.map(one, sorted(need)): res.update(o)
json.dump(res, open(os.path.join(OUT, 'case_addr.json'), 'w'), ensure_ascii=False, indent=0)
print(len(res), '/', len(rows))
