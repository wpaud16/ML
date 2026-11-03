"""오피스텔 학습 단지(ot_train.csv)의 이름·지번·준공일 수집 → officetel/ot_addr.json
국토부 실거래(오피스텔 매매) 파일과 단지를 맞추기 위한 키. 리치고 공개 단지 페이지만 읽는다."""
import sys, os, json
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import batch_predict as bp

OUT = os.path.join(HERE, 'officetel', 'ot_addr.json')


def one(pid):
    raw = bp.get(f'https://m.richgo.ai/realty/officetel/{pid}')
    if not raw: return pid, None
    try: d = bp.next_data(raw).get('data') or {}
    except Exception: return pid, None
    b = d.get('basic') or {}; a = b.get('address') or {}
    try: ch = {x['date'][:7]: x.get('averagePrice') for x in d['analyze']['invest']['invest']['chart']['data'] if x.get('averagePrice')}
    except Exception: ch = {}
    return pid, dict(chart=ch, name=d.get('name'), jibun=a.get('jibun'), road=a.get('road'),
                     built=((b.get('construction') or {}).get('date')), bjd=d.get('bjdInfo'))


if __name__ == '__main__':
    ids = sorted(pd.read_csv(os.path.join(HERE, 'officetel', 'ot_train.csv')).danji.unique())
    old = json.load(open(OUT)) if os.path.exists(OUT) else {}
    todo = [i for i in ids if not (old.get(i) or {}).get('chart')]
    with ThreadPoolExecutor(12) as ex:
        for pid, v in ex.map(one, todo): old[pid] = v
    json.dump(old, open(OUT, 'w'), ensure_ascii=False, indent=1)
    print(len(ids), 'ok', sum(1 for i in ids if old.get(i)))
