"""오늘 매각기일 물건이 법원경매정보(courtauction.go.kr)에서 실제로 진행되는지 확인 (2026-11-08 사용자 요청).
사건 조회 화면의 '물건상태'(매각준비 -> 매각공고 …), '기일정보'(다음 매각기일), '사건항고/정지여부', '종국결과'로 판정.
법원 수집기(local_runner/tenants_job.py, 환경변수 TENANT_JOB)의 조회 코드를 그대로 쓴다.
GitHub Actions(COURT_CHECK=0)이거나 조회에 실패하면 표시하지 않는다(메일은 그대로 발송)."""
import os, re, sys, time

BUDGET_SEC = int(os.environ.get('COURT_CHECK_SEC', '720'))   # 물건당 약 10초, 오늘 물건 30~60건
STOP_WORDS = ('변경', '연기', '정지', '취하', '취소', '기각', '각하', '중지')


def _tj():
    p = os.environ.get('TENANT_JOB') or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'local_runner', 'tenants_job.py')
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
    if os.environ.get('COURT_CHECK') == '0' or os.environ.get('GITHUB_ACTIONS'):
        log('법원 확인 건너뜀 (Actions)'); return {}
    try:
        tj = _tj()
    except Exception as e:
        log(f'법원 확인 건너뜀: 수집기 불러오기 실패 {e}'); return {}
    if tj is None:
        log('법원 확인 건너뜀: 수집기 없음'); return {}
    from playwright.sync_api import sync_playwright
    out, t0 = {}, time.time()

    def one(s, v):
        """(ok, 문구, 기일 상세{time, place}) — 진행이면 물건상세조회의 기일내역에서 시각·법정을 읽는다 (2026-11-11 사용자 요청)."""
        m = re.fullmatch(r'(\d{4})타경(\d+)\[(\d+)\]', v['key'])
        if not m: return None
        y, no, item_no = m.groups()
        _, tbls = s.search(v.get('court'), y, no)
        basic = tj.table_by_cap(tbls, '사건번호,사건명') or {'rows': []}
        info = {r[i]: r[i + 1] for r in basic['rows'] for i in range(0, len(r) - 1, 2)}
        rows, gi = None, None
        for tb in tbls:
            mm = re.match(r'mf_wfm_mainFrame_gen_gdsDts_(\d+)_grp_gdsDtsTbl', tb['id'] or '')
            if mm and tb['rows'] and tb['rows'][0][0] == '물건번호' and tb['rows'][0][1].strip() == item_no:
                rows, gi = tb['rows'], mm.group(1)
        if not rows:
            return (None, f'물건번호 {item_no} 없음', {})
        ok, msg = judge(info, rows, v['bidding_date'])
        det = {}
        if ok is not False:
            try:
                pg = s.page
                b = pg.locator(f'#mf_wfm_mainFrame_gen_gdsDts_{gi}_btn_gdsDtlInq')
                if b.count() and b.is_enabled():
                    b.click(); pg.wait_for_load_state('networkidle'); pg.wait_for_timeout(1500)
                    want = v['bidding_date'].replace('-', '.')
                    for r in tj.body_rows(tj.table_by_cap(tj.tables(pg), '기일,기일종류,기일장소,최저매각가격,기일결과')):
                        if len(r) >= 3 and r[0].startswith(want) and '매각' in (r[1] or '') and '결정' not in (r[1] or ''):
                            tm = re.search(r'\d{1,2}:\d{2}', r[0])
                            det = dict(time=tm.group(0) if tm else None, place=(r[2] or '').strip() or None, kind=r[1], result=(r[4] if len(r) > 4 else '') or None)
                            break
            except Exception as e:
                log(f"기일내역 읽기 실패 {v['key']}: {str(e)[:100]}")
        if ok is True and det:
            msg = '오늘 진행' + (f" · {det['time']}" if det.get('time') else '') + (f" · {det['place']}" if det.get('place') else '')
        return (ok, msg, det)

    with sync_playwright() as pw:
        s = tj.Scraper(pw)
        try:
            todo = list(items)
            for rnd in range(3):   # 2026-11-11: 첫 조회 시간초과로 '확인 못 함' → 실패한 물건은 최대 3번까지 다시
                retry = []
                for v in todo:
                    if time.time() - t0 > BUDGET_SEC:
                        log('법원 확인 시간 초과 — 나머지 생략'); break
                    try:
                        r = one(s, v)
                        if r is None: continue
                        out[v['key']] = r
                    except Exception as e:
                        out[v['key']] = (None, '확인 못 함', {})
                        retry.append(v)
                        log(f"법원 확인 실패({rnd + 1}회) {v['key']}: {str(e)[:120]}")
                        try:
                            s.close()
                        except Exception:
                            pass
                        s = tj.Scraper(pw)   # 브라우저를 새로 열어 다시
                    log(f"법원 확인 {v['key']}: {out.get(v['key'])}")
                if not retry or time.time() - t0 > BUDGET_SEC: break
                time.sleep(10); todo = retry
        finally:
            s.close()
    return out


def parse_result(info, item_rows, bidding_date):
    """사건 조회 화면에서 그 기일의 결과 (2026-11-11: 성적표 결과를 법원에서 바로 확인 — 리치고는 하루 이상 늦음).
    → dict(status='매각'|'유찰'|'변경'|'취하'|..., actual_manwon) 또는 None(아직 결과 없음)."""
    kv = {}
    for r in item_rows or []:
        for i in range(0, len(r) - 1, 2):
            kv.setdefault(r[i].strip(), r[i + 1].strip())
    end = (info.get('종국결과') or '').strip()
    last = kv.get('최근입찰결과') or ''
    want = bidding_date.replace('-', '.')
    if last.startswith(want):
        m = re.search(r'매각\(\s*([\d,]+)\s*원', last)
        if m:
            return dict(status='매각', actual_manwon=int(int(m.group(1).replace(',', '')) / 1e4), text=last)
        for w in ('유찰', '변경', '연기', '취하', '정지', '기각', '불허'):
            if w in last:
                return dict(status=w if w != '연기' else '변경', text=last)
        return None
    stage = (kv.get('물건상태') or '').split('->')[-1].strip()
    if stage == '유찰' and not last:   # 최근입찰결과가 비어 있고 물건상태만 '유찰' (예: 2026타경50257, 11/10)
        return dict(status='유찰', text=f'물건상태 {stage}')
    for w in ('취하', '기각', '정지', '변경', '연기', '취소'):
        if w in stage or w in end:
            return dict(status={'연기': '변경', '취소': '취하'}.get(w, w), text=f'물건상태 {stage} {end}'.strip())
    nd = re.sub(r'\D', '', kv.get('기일정보') or '')
    if nd and nd > bidding_date.replace('-', '') and not last.startswith(want):
        return dict(status='변경', text=f'기일 변경 → {nd[4:6]}/{nd[6:8]}')
    lm = re.match(r'(\d{4})\.(\d{2})\.(\d{2})', last)
    if lm and ''.join(lm.groups()) < bidding_date.replace('-', '') and not nd:
        return dict(status='변경', text=f'그 기일 진행 안 함 (최근 {last})')   # 기일이 열리지 않음 (예: 2025타경104590)
    return None


def fetch_results(items, log=print, budget_sec=1500):
    """items: dict(rid, key, court, bidding_date) → {rid: 결과 dict}. 사건별로 한 번만 조회, 조회 사이 4~6초 쉼."""
    import random
    tj = _tj()
    if tj is None: return {}
    from playwright.sync_api import sync_playwright
    by_case = {}
    for v in items:
        m = re.fullmatch(r'(\d{4})타경(\d+)\[(\d+)\]', v['key'])
        if m: by_case.setdefault((v.get('court'), m.group(1), m.group(2)), []).append((v, m.group(3)))
    out, t0 = {}, time.time()
    with sync_playwright() as pw:
        s = tj.Scraper(pw)
        try:
            for (court, y, no), vs in by_case.items():
                if time.time() - t0 > budget_sec:
                    log('법원 결과 확인 시간 초과 — 나머지 생략'); break
                for attempt in range(2):
                    try:
                        _, tbls = s.search(court, y, no)
                        basic = tj.table_by_cap(tbls, '사건번호,사건명') or {'rows': []}
                        info = {r[i]: r[i + 1] for r in basic['rows'] for i in range(0, len(r) - 1, 2)}
                        for v, item_no in vs:
                            rows = None
                            for tb in tbls:
                                if re.match(r'mf_wfm_mainFrame_gen_gdsDts_\d+_grp_gdsDtsTbl', tb['id'] or '') and tb['rows'] \
                                        and tb['rows'][0][0] == '물건번호' and tb['rows'][0][1].strip() == item_no:
                                    rows = tb['rows']
                            r = parse_result(info, rows, v['bidding_date']) if rows else None
                            if r: out[v['rid']] = r
                            log(f"법원 결과 {v['rid']}: {r}")
                        break
                    except Exception as e:
                        log(f'법원 결과 조회 실패({attempt + 1}) {y}타경{no}: {str(e)[:100]}')
                        try: s.close()
                        except Exception: pass
                        s = tj.Scraper(pw)
                time.sleep(random.uniform(4, 6))
        finally:
            s.close()
    return out


def save(res, day, path):
    """확인 결과를 웹카드용 파일에 합쳐 저장 (2026-11-09 사용자 요청: 웹카드·메일 둘 다 표시). 30일 지난 것은 지움."""
    import json, datetime as dt
    if not res: return
    try:
        d = json.load(open(path, encoding='utf-8'))
    except Exception:
        d = {}
    it = d.get('items') or {}
    at = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec='seconds')
    for k, r in res.items():
        ok, msg = r[0], r[1]
        det = r[2] if len(r) > 2 else {}
        it[k] = dict(date=day, ok=ok, msg=msg, at=at, time=(det or {}).get('time'), place=(det or {}).get('place'))
    cut = (dt.date.fromisoformat(day) - dt.timedelta(days=30)).isoformat()
    it = {k: v for k, v in it.items() if (v.get('date') or '') >= cut}
    json.dump(dict(updated=at, items=it), open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':   # 시험: python court_status.py 남양주지원 2025타경72200[1] 2026-11-11
    print(check([dict(court=sys.argv[1], key=sys.argv[2], bidding_date=sys.argv[3])]))
