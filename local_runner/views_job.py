"""법원경매정보 물건별 관심등록 수·조회수 수집 (2026-11-09 사용자 요청: 경쟁 신호를 브리핑에 표시, 나중에 입찰 인원 예측에 사용).
물건상세검색 화면에서 법원·사건번호로 검색하고, 사이트가 스스로 부르는 검색 결과(JSON)에서 inqCnt(조회수)·gwansMulRegCnt(관심등록)를 읽는다.
사이트 차단을 피하려고 검색마다 6~10초 쉬고, 30건마다 화면을 다시 열고 20초 쉰다. '차단' 응답이 오면 즉시 멈춘다.
결과: auction_model/predictions/views.json  {updated, items: {key: {date, inq, gwans, bidding_date, hist: {날짜: [조회, 관심]}}}}
사용: python views_job.py [--budget-min 20] [--limit N] [--days 14]"""
import argparse, datetime as dt, json, os, random, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PRED = os.path.join(REPO, 'auction_model', 'predictions')
OUT = os.path.join(PRED, 'views.json')
URL = 'https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml'
KST = dt.timezone(dt.timedelta(hours=9))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, 'auction_model'))


def log(m):
    print(f'[{dt.datetime.now(KST):%Y-%m-%d %H:%M:%S}] {m}', flush=True)


def targets(today, days):
    """예측 목록에서 오늘~days일 안에 기일인 물건 (카드·메일에 나오는 것) → {(법원, 사건): [키,...]}."""
    import cards_page as cp
    L = json.load(open(os.path.join(PRED, 'latest.json'), encoding='utf-8'))
    end = (today + dt.timedelta(days=days)).isoformat()
    rows = [v for v in L['items'].values() if cp.keep(v)]
    rows += [f for f in L.get('failed') or [] if (f.get('risk') or {}).get('decision') == 'show']
    out = {}
    for v in rows:
        bd = v.get('bidding_date') or ''
        if not (today.isoformat() <= bd <= end) or not v.get('court'): continue
        m = re.fullmatch(r'(\d{4})타경(\d+)\[(\d+)\]', v['key'])
        if not m: continue
        out.setdefault((v['court'], m.group(1), m.group(2)), []).append((v['key'], m.group(3), bd))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--budget-min', type=float, default=20)
    ap.add_argument('--limit', type=int)
    ap.add_argument('--days', type=int, default=14)
    a = ap.parse_args()
    import tenants_job as tj
    from playwright.sync_api import sync_playwright
    now = dt.datetime.now(KST); today = now.date()
    T = targets(today, a.days)
    keys = sorted(T, key=lambda k: (k[0], k[1], k[2]))
    if a.limit: keys = keys[:a.limit]
    log(f'대상 사건 {len(keys)}건 (물건 {sum(len(T[k]) for k in keys)}건)')
    try:
        D = json.load(open(OUT, encoding='utf-8'))
    except Exception:
        D = {}
    items = D.get('items') or {}
    t0 = time.time(); ok = fail = 0; blocked = False
    with sync_playwright() as pw:
        s = tj.Scraper(pw)
        pg = s.page
        opts = None

        def open_form():
            nonlocal opts
            pg.goto(URL, wait_until='networkidle'); time.sleep(3)
            opts = pg.eval_on_selector_all('#mf_wfm_mainFrame_sbx_rletCortOfc option', 'os=>os.map(o=>o.text.trim())')
        try:
            open_form()
            for n, k in enumerate(keys):
                if time.time() - t0 > a.budget_min * 60:
                    log(f'시간 한도 {a.budget_min}분 → 나머지 {len(keys) - n}건 생략'); break
                court, y, no = k
                if n and n % 30 == 0:
                    time.sleep(20); open_form()
                try:
                    label = tj.resolve_court(court, opts)
                    if not label: raise RuntimeError(f'법원 이름 못 찾음 {court}')
                    if not pg.locator('#mf_wfm_mainFrame_ibx_rletCsNo').is_visible():
                        open_form()
                    pg.select_option('#mf_wfm_mainFrame_sbx_rletCortOfc', label=label); pg.wait_for_timeout(1000)
                    pg.select_option('#mf_wfm_mainFrame_sbx_rletCsYear', label=y)
                    pg.fill('#mf_wfm_mainFrame_ibx_rletCsNo', no); pg.wait_for_timeout(500)
                    # 이벤트는 playwright 호출 중에만 처리되므로 expect_response 로 기다린다
                    with pg.expect_response(lambda r: 'searchControllerMain' in r.url, timeout=25000) as ri:
                        pg.click('#mf_wfm_mainFrame_btn_gdsDtlSrch')
                    j = json.loads(ri.value.text())
                    msg = j.get('message') or ''
                    if '차단' in msg:
                        blocked = True; log(f'사이트 차단 응답 → 즉시 중단: {msg}'); break
                    res = (j.get('data') or {}).get('dlt_srchResult') or []
                    by = {}
                    for x in res:
                        if x.get('srnSaNo') == f'{y}타경{no}':
                            by[str(x.get('maemulSer'))] = x
                    for key, item_no, bd in T[k]:
                        x = by.get(item_no) or (next(iter(by.values())) if len(by) == 1 else None)
                        if not x:
                            log(f'{key}: 결과에 없음 (검색 {len(res)}건)'); fail += 1; continue
                        inq, gw = int(x.get('inqCnt') or 0), int(x.get('gwansMulRegCnt') or 0)
                        e = items.get(key) or {}
                        h = e.get('hist') or {}
                        h[today.isoformat()] = [inq, gw]
                        items[key] = dict(date=today.isoformat(), at=now.isoformat(timespec='seconds'), inq=inq, gwans=gw, bidding_date=bd, hist=h)
                        ok += 1
                        log(f'{key}: 관심 {gw} · 조회 {inq}')
                except Exception as e:
                    fail += 1; log(f'{y}타경{no}: 실패 {str(e)[:150]}')
                    try: open_form()
                    except Exception: pass
                pg.wait_for_timeout(random.uniform(6000, 10000))
        finally:
            s.close()
    cut = (today - dt.timedelta(days=45)).isoformat()
    items = {k: v for k, v in items.items() if (v.get('bidding_date') or '9') >= cut}
    json.dump(dict(updated=now.isoformat(timespec='seconds'), items=items), open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    log(f'저장 {OUT}: 성공 {ok}, 실패 {fail}' + (' (차단으로 중단)' if blocked else ''))
    if blocked or (ok == 0 and keys):
        sys.exit(1)


if __name__ == '__main__':
    main()
