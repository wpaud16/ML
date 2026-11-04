"""학습 사례(아파트) 단지별 주변 비교 데이터 수집 (2026-11-05, 주변 시세 백테스트용).
auction_train.csv 의 단지 → 리치고 단지 페이지 emdComparison(같은 동 단지 평당가·연식·세대수) → dev/nearby_apt.json"""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); AM = os.path.dirname(HERE)
sys.path.insert(0, AM)
import pandas as pd
import nearby

OUT = os.path.join(HERE, 'nearby_apt.json')
done = json.load(open(OUT)) if os.path.exists(OUT) else {}
ids = sorted(set(pd.read_csv(os.path.join(AM, 'auction_train.csv')).danji) - set(done))
print('todo', len(ids), 'done', len(done))


def work(d):
    pp = nearby.page_props('danji', d)
    ec = pp.get('emdComparison') or {}
    rows = [[r.get('id'), r.get('age'), r.get('households'), r.get('pyeong'), r.get('perPyeong'), r.get('localRank')]
            for r in (ec.get('rows') or []) if isinstance(r, dict)]
    return d, dict(emd=ec.get('emd'), total=ec.get('total'), rank=ec.get('rank'), per_pyeong=ec.get('perPyeong'),
                   price_date=ec.get('priceDate'), rows=rows, ok=bool(pp))


with ThreadPoolExecutor(8) as ex:
    for i, (d, r) in enumerate(ex.map(work, ids)):
        done[d] = r
        if i % 100 == 0:
            print(i, d, r['emd'], len(r['rows']))
json.dump(done, open(OUT, 'w'), ensure_ascii=False)
print('saved', len(done), 'with rows', sum(1 for v in done.values() if v['rows']))
