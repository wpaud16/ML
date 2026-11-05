"""탐색 (2026-11-05): 성적표 아파트를 M 시세로 다시 계산 — 예측했던 단지들의 지번·동 (dev/probe/danji_jibun.json)."""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import nearby
OUT = os.path.join(HERE, 'probe')
ids = json.load(open(os.path.join(HERE, 'probe_ids.json')))


def one(i):
    d = nearby.page_props('danji', i).get('data') or {}
    return i, dict(jibun=((d.get('basic') or {}).get('address') or {}).get('jibun'), bjd=d.get('bjdInfo'))


with ThreadPoolExecutor(8) as ex:
    res = dict(ex.map(one, ids))
json.dump(res, open(os.path.join(OUT, 'danji_jibun.json'), 'w'), ensure_ascii=False, indent=0)
print(len(res), sum(1 for v in res.values() if v['jibun']))
