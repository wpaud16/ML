"""오늘 매각기일 물건이 법원경매정보(courtauction.go.kr)에서 실제로 진행되는지 확인 (2026-11-08 사용자 요청).
사건 조회 화면의 '물건상태'(매각준비 -> 매각공고 …), '기일정보'(다음 매각기일), '사건항고/정지여부', '종국결과'로 판정.
노트북의 법원 수집기(C:\\auction_pc\\tenants_job.py, 환경변수 TENANT_JOB)의 조회 코드를 그대로 쓴다.
수집기가 없거나(GitHub Actions) 조회에 실패하면 표시하지 않는다(메일은 그대로 발송)."""
import os, re, sys, time

BUDGET_SEC = int(os.environ.get('COURT_CHECK_SEC', '420'))
STOP_WORDS = ('변경', '연기', '정지', '취하', '취소', '기각', '각하', '중지')


def _tj():
    p = os.environ.get('TENANT_JOB') or r'C:\auction_pc\tenants_job.py'
    if not os.path.exists(p):
        return None
    sys.path.insert(0, os.path.dirname(p))
    import importlib
    return importlib.import_module(os.path.splitext(os.path.basename(p))[0])


def judge(info, item_rows, bidding_date):
    """(ok, 표시 문구). ok: True 진행 / False 진행 안 함 / None 판단 못 함."""
    end = (info.get('종국결과') or '').strip()
    if end and end != '미종국':
        return False, f'사건 종국({end})'
    stop = (info.get('사건항고/정지여부') or '').strip()
    if stop:
        return False, f'사건 {stop}'
    kv = {}
    for r in item_rows:
        for i in range(0, len(r) - 1, 2):
            kv.setdefault(r[i].strip(), r[i + 1].strip())
    stage = (kv.get('물건상태') or '').split('->')[-1].strip()
    if any(w in stage for w in STOP_WORDS):
        return False, f'물건상태 {stage}'
    nd = re.sub(r'\D', '', kv.get('기일정보') or '')
    want = bidding_date.replace('-', '')
    if nd == want:
        return (True, '오늘 진행') if stage in ('매각공고', '') else (None, f'물건상태 {stage}')
    if nd:
        return False, f'기일 변경 → {int(nd[4:6])}/{int(nd[6:8])}'
    last = kv.get('최근입찰결과') or ''
    return False, '오늘 기일 없음' + (f' (최근 {last})' if last else '')


def check(items, log=print):
    """items: 예측 항목(dict: key, court, bidding_date) → {key: (ok, 문구)}."""
    if not items:
        return {}
    try:
        tj = _tj()
    except Exception as e:
        log(f'법원 확인 건너뜀: 수집기 불러오기 실패 {e}'); return {}
    if tj is None:
        log('법원 확인 건너뜀: 수집기 없음'); return {}
    from playwright.sync_api import sync_playwright
    out, t0 = {}, time.time()
    with sync_playwright() as pw:
        s = tj.Scraper(pw)
        try:
            for v in items:
                if time.time() - t0 > BUDGET_SEC:
                    log('법원 확인 시간 초과 — 나머지 생략'); break
                m = re.fullmatch(r'(\d{4})타경(\d+)\[(\d+)\]', v['key'])
                if not m: continue
                y, no, item_no = m.groups()
                try:
                    _, tbls = s.search(v.get('court'), y, no)
                    basic = tj.table_by_cap(tbls, '사건번호,사건명') or {'rows': []}
                    info = {r[i]: r[i + 1] for r in basic['rows'] for i in range(0, len(r) - 1, 2)}
                    rows = None
                    for tb in tbls:
                        if re.match(r'mf_wfm_mainFrame_gen_gdsDts_\d+_grp_gdsDtsTbl', tb['id'] or '') and tb['rows'] \
                                and tb['rows'][0][0] == '물건번호' and tb['rows'][0][1].strip() == item_no:
                            rows = tb['rows']
                    out[v['key']] = judge(info, rows, v['bidding_date']) if rows else (None, f'물건번호 {item_no} 없음')
                except Exception as e:
                    out[v['key']] = (None, '확인 못 함')
                    log(f"법원 확인 실패 {v['key']}: {str(e)[:120]}")
                log(f"법원 확인 {v['key']}: {out.get(v['key'])}")
        finally:
            s.close()
    return out


if __name__ == '__main__':   # 시험: python court_status.py 남양주지원 2025타경72200[1] 2026-11-11
    print(check([dict(court=sys.argv[1], key=sys.argv[2], bidding_date=sys.argv[3])]))
