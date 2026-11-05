"""리치고 탐색 (2026-11-05): 학습 단지(아파트 708·오피스텔 314)의 단지명·지번·준공 → 국토부 실거래 매칭용 (dev/probe/danji_info.json)."""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
import csv
HERE = os.path.dirname(os.path.abspath(__file__)); AM = os.path.dirname(HERE); sys.path.insert(0, AM)
import nearby
OUT = os.path.join(HERE, 'probe'); os.makedirs(OUT, exist_ok=True)
ids = []
for f, kind in [(os.path.join(AM, 'auction_train.csv'), 'danji'), (os.path.join(AM, 'officetel', 'ot_train.csv'), 'officetel')]:
    ids += sorted({(kind, r['danji']) for r in csv.DictReader(open(f, encoding='utf-8'))})


def one(a):
    kind, pid = a
    d = nearby.page_props(kind, pid).get('data') or {}
    if not d: return pid, dict(kind=kind, error='no page')
    return pid, dict(kind=kind, name=d.get('name'), bjd=d.get('bjdInfo'), basic=d.get('basic'), location=d.get('location'),
                     areas=sorted({(v.get('minPrivateArea'), v.get('maxPrivateArea')) for v in (d.get('pyeongInfos') or {}).values()}, key=str))


with ThreadPoolExecutor(8) as ex:
    res = dict(ex.map(one, ids))
json.dump(res, open(os.path.join(OUT, 'danji_info.json'), 'w'), ensure_ascii=False, indent=0)
print(len(res), sum('error' in v for v in res.values()))
