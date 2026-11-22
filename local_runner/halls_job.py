"""법원 부동산매각공고에서 물건별 담당계·입찰법정·입찰시간·전화 수집 (2026-11-22 사용자 요청: 카드에 '경매1계 · 101호 · 10시').
법원경매정보 > 경매공고 > 부동산매각공고 화면을 사람처럼 연다: 법원 고르고 검색 → 달력의 '경매N계' 링크를 하나씩 눌러,
사이트가 스스로 부르는 응답(JSON)을 읽는다. 직접 API 호출은 하지 않는다 (예전에 IP 차단됨).
클릭마다 6~10초, 법원마다 15초 쉰다. '차단' 응답이면 즉시 멈춘다. 공고는 매각기일 14일 전부터 올라온다.
결과: auction_model/predictions/halls.json {updated, items: {키: {date, court, jdbn, tel, place, time, changed}}}
사용: python halls_job.py [--budget-min 25] [--court 서울동부지방법원] [--days 14]"""
import argparse, datetime as dt, json, os, random, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PRED = os.path.join(REPO, 'auction_model', 'predictions')
OUT = os.path.join(PRED, 'halls.json')
URL = 'https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ141M00.xml&pgjId=143M01'
SEL = '#mf_wfm_mainFrame_sbx_cortOfcNm'
KST = dt.timezone(dt.timedelta(hours=9))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, 'auction_model'))


def log(m):
    print(f'[{dt.datetime.now(KST):%Y-%m-%d %H:%M:%S}] {m}', flush=True)


def targets(today, days):
    """카드에 나오는 물건(아파트·오피스텔 예측 + 상가·건물) 중 오늘~days일 안 기일 → {법원: {날짜: [키]}}."""
    import cards_page as cp
    rows = [v for v in json.load(open(os.path.join(PRED, 'latest.json'), encoding='utf-8'))['items'].values() if cp.keep(v)]
    try:
        rows += list((json.load(open(os.path.join(PRED, 'others.json'), encoding='utf-8')).get('items') or {}).values())
    except Exception:
        pass
    end = (today + dt.timedelta(days=days)).isoformat()
    out = {}
    for v in rows:
        bd = v.get('bidding_date') or ''
        if today.isoformat() <= bd <= end and v.get('court') and re.fullmatch(r'\d{4}타경\d+\[\d+\]', v.get('key') or ''):
            out.setdefault(v['court'], {}).setdefault(bd, []).append(v['key'])
    return out


def hm(s):
    s = re.sub(r'\D', '', s or '')
    return f'{int(s[:-2])}:{s[-2:]}' if len(s) in (3, 4) else ''


def walk(o, path=''):
    """응답 JSON 안의 물건(csNo·dspslSeq 가 있는 dict)과 그 물건이 들어 있던 위치(예: result.dspslPbanc.pbancInfo.lst)."""
    if isinstance(o, dict):
        if o.get('csNo') and o.get('dspslSeq') is not None:
            yield path, o
            return
        for k, v in o.items():
            if isinstance(v, (dict, list)):
                yield from walk(v, f'{path}.{k}' if path else k)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v, path)


NORMAL = 'result.dspslPbanc.pbancInfo.lst'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--budget-min', type=float, default=25)
    ap.add_argument('--court')
    ap.add_argument('--days', type=int, default=14)
    a = ap.parse_args()
    import tenants_job as tj
    from playwright.sync_api import sync_playwright
    now = dt.datetime.now(KST); today = now.date()
    T = targets(today, a.days)
    if a.court: T = {k: v for k, v in T.items() if k == a.court}
    log(f'대상 법원 {len(T)}곳 · 물건 {sum(len(x) for d in T.values() for x in d.values())}건')
    try:
        items = json.load(open(OUT, encoding='utf-8')).get('items') or {}
    except Exception:
        items = {}
    t0 = time.time(); ok = 0; blocked = False; secs = set()
    with sync_playwright() as pw:
        s = tj.Scraper(pw); pg = s.page

        def open_cal(court, ym):
            """공고 화면을 새로 열어 법원·달을 고르고 그 달 공고 목록(JSON)을 받는다. 차단이면 None."""
            pg.goto(URL, wait_until='networkidle'); time.sleep(3)
            opts = pg.eval_on_selector_all(SEL + ' option', 'os=>os.map(o=>o.text.trim())')
            label = tj.resolve_court(court, opts)
            if not label:
                raise RuntimeError(f'법원 이름 못 찾음 {court}')
            pg.select_option(SEL, label=label); pg.wait_for_timeout(1000)
            with pg.expect_response(lambda r: 'selectRletDspslPbanc.on' in r.url, timeout=25000) as ri:
                if ym == today.isoformat()[:7]:
                    pg.click('#mf_wfm_mainFrame_btn_srchDspslPbanc')
                else:
                    if ym[:4] != str(today.year):
                        pg.click('#mf_wfm_mainFrame_btn_nextYear'); pg.wait_for_timeout(1500)
                    pg.click(f'label[for="mf_wfm_mainFrame_rad_mm_input_{int(ym[5:]) - 1}"]')
            j = json.loads(ri.value.text())
            if '차단' in (j.get('message') or ''):
                log(f'차단 응답 → 중단: {j.get("message")}'); return None
            pg.wait_for_timeout(random.uniform(4000, 7000))
            return (j.get('data') or {}).get('dlt_rletDspslPbancLst') or []

        def back_to_cal(court, ym):
            """상세 → 달력. 이전 버튼이 없거나 달력이 안 보이면 화면을 새로 연다."""
            try:
                pg.click('#mf_wfm_mainFrame_btn_prevBtn', timeout=8000); pg.wait_for_timeout(random.uniform(3000, 5000))
                if pg.evaluate("[...document.querySelectorAll('td a')].some(a => /경매\\d+계/.test(a.textContent))"):
                    return True
            except Exception:
                pass
            log('달력 다시 열기'); time.sleep(10)
            return open_cal(court, ym) is not None

        try:
            for ci, (court, by_day) in enumerate(sorted(T.items())):
                if time.time() - t0 > a.budget_min * 60:
                    log(f'시간 한도 → {court} 등 나머지 생략'); break
                if ci: time.sleep(15)
                for ym in sorted({d[:7] for d in by_day}):
                    try:
                        days = open_cal(court, ym)
                    except Exception as e:
                        log(f'{court} {ym}: 공고 화면 실패 {str(e)[:120]}'); continue
                    if days is None:
                        blocked = True; break
                    log(f'{court} {ym}: 공고 {len(days)}개 ' + ', '.join(f"{x['dspslDxdyYmd'][4:]} {x['cortAuctnJdbnNm']}" for x in days))
                    for x in days:
                        d = f"{x['dspslDxdyYmd'][:4]}-{x['dspslDxdyYmd'][4:6]}-{x['dspslDxdyYmd'][6:]}"
                        if d not in by_day: continue
                        if time.time() - t0 > a.budget_min * 60: break
                        # 달력에서 그 날짜 칸의 'N계' 링크를 표시해 두고 실제로 클릭
                        mark = pg.evaluate("""([day, nm]) => { document.querySelectorAll('[data-hj]').forEach(e => e.removeAttribute('data-hj'));
                            for (const a of document.querySelectorAll('td a')) { const td = a.closest('td');
                              if (a.textContent.trim() === nm && td && parseInt(td.textContent.trim(), 10) === day) { a.setAttribute('data-hj', '1'); return true; } }
                            return false; }""", [int(d[8:]), x['cortAuctnJdbnNm']])
                        if not mark:
                            log(f'{d} {x["cortAuctnJdbnNm"]}: 달력 링크 못 찾음'); continue
                        try:
                            with pg.expect_response(lambda r: 'selectRletDspslPbancDtl.on' in r.url, timeout=25000) as rd:
                                pg.click('a[data-hj="1"]')
                            dj = json.loads(rd.value.text())
                        except Exception as e:
                            log(f'{d} {x["cortAuctnJdbnNm"]}: 상세 실패 {str(e)[:100]}')
                            if not back_to_cal(court, ym): blocked = True; break
                            continue
                        if '차단' in (dj.get('message') or ''):
                            blocked = True; log(f'차단 응답 → 중단: {dj.get("message")}'); break
                        want = set(by_day[d]); seen = {}
                        for sec, o in walk(dj.get('data')):
                            secs.add(sec)
                            key = f"{o['csNo']}[{o['dspslSeq']}]"
                            if key not in want: continue
                            r = seen.setdefault(key, dict(date=d, court=court, jdbn=x['cortAuctnJdbnNm'], tel=x.get('jdbnTelno') or '',
                                                          place=x.get('dspslPlcNm') or '', time=hm(x.get('fstDspslHm')), notes=[],
                                                          at=now.isoformat(timespec='seconds')))
                            t = re.search(r'입찰시간\s*\((\d{1,2}):?(\d{2})\)', o.get('lwsDspslPrc') or '')
                            if t: r['time'] = f'{int(t.group(1))}:{t.group(2)}'
                            if sec != NORMAL:   # 정정공고(crrct) · 기일변경/취하/취소공고(rtrcn) → 카드에 경고로
                                kind = '정정' if 'crrct' in sec else '변경·취하' if 'rtrcn' in sec else '기타'
                                txt = next((re.sub(r'\s+', ' ', v).strip() for k, v in o.items() if isinstance(v, str) and k not in ('st', 'lwsDspslPrc', 'dspslRmk')
                                            and re.search(r'변경|취하|취소|정지|추가|정정|유치권', v)), '')
                                r['notes'].append(dict(kind=kind, text=txt[:200]))
                        items.update(seen); got = len(seen)
                        ok += got
                        log(f'{d} {x["cortAuctnJdbnNm"]}: 우리 물건 {got}/{len(want)}건')
                        pg.wait_for_timeout(random.uniform(6000, 10000))
                        if not back_to_cal(court, ym): blocked = True; break
                    if blocked: break
                if blocked: break
        except Exception as e:
            log(f'중간 오류 → 모은 것까지 저장: {str(e)[:200]}')
        finally:
            s.close()
    log(f'응답 묶음 이름: {sorted(x for x in secs if x)}')
    cut = (today - dt.timedelta(days=30)).isoformat()
    items = {k: v for k, v in items.items() if (v.get('date') or '9') >= cut}
    json.dump(dict(updated=now.isoformat(timespec='seconds'), items=items), open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    log(f'저장 {OUT}: 이번에 {ok}건' + (' (차단으로 중단)' if blocked else ''))
    if blocked: sys.exit(1)


if __name__ == '__main__':
    main()
