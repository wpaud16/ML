"""아파트 학습 행(auction_train.csv) ↔ 경매 사건(auction_id·사건번호) 매핑 → court_backfill/apt_case_map.csv
학습 행에는 사건번호가 없어서, 리치고 공개 단지 페이지의 과거 경매 목록에서 (단지, 매각일, 낙찰가)로 찾는다."""
import sys, os, json
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import batch_predict as bp
import retrain as rt

OUT = os.path.join(HERE, 'court_backfill', 'apt_case_map.csv')


def one(dj):
    d, _ = rt.page('danji', dj)
    if not d: return []
    return [dict(danji=dj, date=(a.get('sellingDate') or '')[:10], sell=a.get('sellingPrice'),
                 auction_id=a.get('auctionId'), case=a.get('caseName'), item_no=a.get('itemNumber') or 1)
            for a in rt.flat_auctions(d) if a.get('sellingPrice')]


if __name__ == '__main__':
    tr = pd.read_csv(os.path.join(HERE, 'auction_train.csv'))
    rows = []
    with ThreadPoolExecutor(12) as ex:
        for r in ex.map(one, sorted(tr.danji.unique())): rows += r
    au = pd.DataFrame(rows)
    m = tr.reset_index().merge(au, on=['danji', 'date'], how='left')
    m = m[(m.sell_y.isna()) | ((m.sell_x - m.sell_y).abs() <= m.sell_x * 0.001)]
    m = m.drop_duplicates('index')[['index', 'danji', 'date', 'auction_id', 'case', 'item_no']]
    m.to_csv(OUT, index=False)
    print('train', len(tr), 'mapped', m.auction_id.notna().sum())
