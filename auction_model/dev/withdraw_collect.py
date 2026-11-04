"""취하 예측 백테스트용: 백필 사건(court_backfill/targets_all.json) 중 끝난 사건의 리치고 경매 상세 기본 정보 수집
→ court_backfill/richgo_detail.jsonl (한 줄에 한 건, 이미 받은 건은 건너뜀). 리치고 공개 경매 상세 페이지만 읽는다."""
import sys, os, json
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import batch_predict as bp

CB = os.path.join(HERE, 'court_backfill')
OUT = os.path.join(CB, 'richgo_detail.jsonl')
KEEP = ['auctionId', 'caseName', 'caseSite', 'itemType', 'itemNumber', 'sd', 'sgg', 'emd', 'appraisedPrice',
        'lowestSellingPrice', 'numberOfFailures', 'sellingDate', 'sellingPrice', 'bidders', 'registrationDate',
        'itemStatus', 'buildingTotalArea', 'constructYear', 'rights', 'historyList']


def one(aid):
    try:
        d = bp.auction_detail(aid) or {}
    except Exception as e:
        return dict(auctionId=aid, error=str(e)[:200])
    if not d: return dict(auctionId=aid, error='empty')
    return {k: d.get(k) for k in KEEP}


if __name__ == '__main__':
    t = json.load(open(os.path.join(CB, 'targets_all.json')))['items']
    ended = []
    for r in t:
        f = os.path.join(CB, 'data', f"{r['case']}_{int(r['item_no'])}.json")
        if not os.path.exists(f): continue
        er = ((json.load(open(f)).get('case_info') or {}).get('end_result'))
        if er and er != '미종국': ended.append(r['auction_id'])
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT):
            try:
                o = json.loads(line)
                if not o.get('error'): done.add(o['auctionId'])
            except Exception: pass
    todo = [a for a in dict.fromkeys(ended) if a not in done]
    print('ended', len(set(ended)), 'todo', len(todo), flush=True)
    with open(OUT, 'a') as fo, ThreadPoolExecutor(12) as ex:
        for i, o in enumerate(ex.map(one, todo)):
            fo.write(json.dumps(o, ensure_ascii=False) + '\n')
            if i % 500 == 0: print(i, flush=True)
    print('done')
