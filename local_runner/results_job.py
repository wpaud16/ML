"""성적표 결과를 법원 사건 조회로 먼저 채운다 (2026-11-11 사용자 요청: 리치고 결과가 하루 이상 늦게 올라와 '결과대기'가 오래감).
최근 14일 안에 기일이 지난 추적 물건 중 결과가 없는 것 → 법원 '최근입찰결과'(매각가·유찰·변경) → predictions/court_results.json
→ batch_predict.update_results 로 results.json 갱신 (리치고 결과가 있으면 그것 우선, 응찰자 수는 리치고에서 나중에 채움).
사용: python results_job.py"""
import datetime as dt, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
AM = os.path.join(REPO, 'auction_model')
PRED = os.path.join(AM, 'predictions')
sys.path.insert(0, AM); sys.path.insert(0, os.path.join(REPO, 'brief'))
KST = dt.timezone(dt.timedelta(hours=9))
FINAL = ('매각', '유찰', '변경', '취하', '기각', '정지')


def log(m):
    print(f'[{dt.datetime.now(KST):%H:%M:%S}] {m}', flush=True)


def pending(today):
    res = json.load(open(os.path.join(PRED, 'results.json'), encoding='utf-8')) if os.path.exists(os.path.join(PRED, 'results.json')) else {}
    lo = (dt.date.fromisoformat(today) - dt.timedelta(days=14)).isoformat()
    last = {}
    for fn in sorted(f for f in os.listdir(PRED) if re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json', f)):
        if fn[:10] >= today or fn[:10] < (dt.date.fromisoformat(lo) - dt.timedelta(days=7)).isoformat(): continue
        for k, it in (json.load(open(os.path.join(PRED, fn), encoding='utf-8')).get('items') or {}).items():
            bd = it.get('bidding_date') or ''
            if lo <= bd < today and fn[:10] <= bd and it.get('court'):
                last[f'{k}|{bd}'] = dict(rid=f'{k}|{bd}', key=k, court=it['court'], bidding_date=bd)
    try:   # 법원에서 이미 결과를 받은 물건은 다시 조회하지 않음 (성적표 제외 물건이 매번 다시 조회되던 문제)
        C = json.load(open(os.path.join(PRED, 'court_results.json'), encoding='utf-8'))
    except Exception:
        C = {}
    out = [v for rid, v in last.items() if (res.get(rid) or {}).get('status') not in FINAL and rid not in C]
    return sorted(out, key=lambda v: v['bidding_date'], reverse=True)   # 최근 기일부터 (시간 한도에 걸려도 성적표 위쪽이 먼저 채워지게)


def main():
    import os as _os
    _os.chdir(AM)
    today = dt.datetime.now(KST).date().isoformat()
    todo = pending(today)
    log(f'결과 없는 지난 기일 물건 {len(todo)}건')
    p = os.path.join(PRED, 'court_results.json')
    try:
        C = json.load(open(p, encoding='utf-8'))
    except Exception:
        C = {}
    if todo:
        import court_status
        got = court_status.fetch_results(todo, log=log)
        for rid, r in got.items():
            C[rid] = dict(r, checked=today)
        cut = (dt.date.fromisoformat(today) - dt.timedelta(days=45)).isoformat()
        C = {k: v for k, v in C.items() if k.rsplit('|', 1)[1] >= cut}
        json.dump(dict(sorted(C.items())), open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        log(f'법원 결과 {len(got)}건 저장')
    import batch_predict as bp
    s = bp.update_results(today)
    log(f"results.json 갱신: {s.get('summary')}")


if __name__ == '__main__':
    main()
