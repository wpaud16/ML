"""이벤트 때문에 한 구독을 당첨자 발표 뒤에 해지 (2026-11-28 사용자: '구독했던 것들은 응모 기간이 끝나면 취소해줘').
발표 전에 끊으면 당첨 확인에서 빠질 수 있어서, 해지일 = 발표일 + 3일 (발표일을 모르면 마감 + 14일, 둘 다 모르면 응모일 + 30일).
장부: C:\\auction_pc\\entry\\subs.json (저장소 밖: 해지할 때 이름·이메일을 쓰는 항목이 있어서).
  kind: youtube (채널 URL) | korea_nl (정책브리핑 뉴스레터) | manual (카카오 채널·인스타·메일 링크 등 — 직접 해지, 페이지에 안내만)
매일 06:00 run_all s_outfit 에서 entry_submit 다음에 돈다. 원래 사용자가 구독하던 채널은 장부에 없으니 건드리지 않는다.
사용: python unsub.py [--dry] [--list]"""
import argparse, datetime as dt, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(os.path.dirname(HERE))
LEDGER = os.path.join(BASE, 'entry', 'subs.json')
sys.path.insert(0, HERE)


def load():
    try:
        return json.load(open(LEDGER, encoding='utf-8'))
    except Exception:
        return []


def save(L):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    json.dump(L, open(LEDGER, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def _d(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def cancel_on(announce=None, deadline=None, entered=None):
    a, d, e = _d(announce), _d(deadline), _d(entered) or dt.date.today()
    if a: return (a + dt.timedelta(days=3)).isoformat()
    if d: return (d + dt.timedelta(days=14)).isoformat()
    return (e + dt.timedelta(days=30)).isoformat()


def norm(kind, target):
    if kind == 'youtube':
        return target.split('?')[0].rstrip('/').lower()
    return target


def add(kind, target, event, announce=None, deadline=None, entered=None, note=''):
    """구독할 때 부른다. 같은 대상이 이미 있으면 해지일을 더 늦은 쪽으로 (여러 이벤트에 걸친 채널)."""
    L = load(); key = norm(kind, target); when = cancel_on(announce, deadline, entered)
    for x in L:
        if x['kind'] == kind and norm(kind, x['target']) == key and x['status'] == 'active':
            if when > x['cancel_on']:
                x['cancel_on'] = when
            if event not in x['events']:
                x['events'].append(event)
            save(L); return x
    x = dict(kind=kind, target=target, events=[event], subscribed=(entered or dt.date.today().isoformat()),
             cancel_on=when, status='active', note=note)
    L.append(x); save(L); return x


def yt_channel(pg):
    """지금 열린 유튜브 영상 페이지의 채널 URL."""
    return pg.evaluate("""(()=>{const a=document.querySelector('ytd-video-owner-renderer a[href*="/@"], ytd-video-owner-renderer a');return a?a.href:''})()""")


def yt_unsub(pg, url):
    pg.goto(url, wait_until='domcontentloaded', timeout=40000); pg.wait_for_timeout(5000)
    b = pg.locator('#page-header yt-subscribe-button-view-model button, ytd-subscribe-button-renderer button, #subscribe-button button').first
    t = (b.inner_text() or '').replace(' ', '')
    if '구독중' not in t:
        return 'already' if '구독' in t else f'버튼 못 찾음({t[:10]})'
    b.click(); pg.wait_for_timeout(1500)
    pg.locator('tp-yt-paper-listbox yt-list-item-view-model, ytd-menu-service-item-renderer, yt-list-item-view-model').filter(has_text='구독 취소').first.click()
    pg.wait_for_timeout(1500)
    c = pg.locator('yt-confirm-dialog-renderer #confirm-button button, yt-confirm-dialog-renderer #confirm-button, button[aria-label="구독 취소"]').filter(visible=True)
    if c.count():
        c.first.click(); pg.wait_for_timeout(2500)
    t = (b.inner_text() or '').replace(' ', '')
    return 'done' if '구독중' not in t else '해지 확인 안 됨'


def korea_nl_unsub(pg):
    import nform
    e = nform.env()
    msgs = []
    pg.on('dialog', lambda d: (msgs.append(d.message), d.accept()))
    pg.goto('https://www.korea.kr/etc/newsLetterMain.do?tabGubun=cancle', wait_until='domcontentloaded', timeout=40000)
    pg.wait_for_timeout(3000)
    pg.locator('#cancelName').fill(e['ENTRY_NAME']); pg.locator('#cancelEmail').fill(e['ENTRY_EMAIL'])
    pg.locator('[onclick^="cancelNewsLetter"]').first.click(); pg.wait_for_timeout(2000)
    ok = pg.locator('text=확인').filter(visible=True)   # 사이트 자체 확인 창이 뜨는 경우
    if ok.count():
        ok.first.click(); pg.wait_for_timeout(2500)
    txt = ' '.join(msgs) + ' ' + pg.evaluate("document.body.innerText").replace('\n', ' ')[-3000:]
    m = re.search(r'[^.。\s]{0,20}(해지|수신거부|취소)[^.。]{0,30}(되었|완료|처리)[^.。]{0,15}', txt)
    return ('done', m.group(0)) if m else ('해지 확인 안 됨', ' '.join(msgs)[:80])


def due(today=None):
    t = (today or dt.date.today()).isoformat()
    return [x for x in load() if x['status'] == 'active' and x['cancel_on'] <= t]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args()
    L = load(); today = dt.date.today().isoformat()
    if a.list:
        for x in L:
            print(f"{x['status']:9} {x['cancel_on']} {x['kind']:8} {x['target'][:50]} ← {' / '.join(x['events'])[:60]}")
        return
    todo = [x for x in L if x['status'] == 'active' and x['cancel_on'] <= today and x['kind'] != 'manual']
    print(f'해지할 것 {len(todo)}건 (장부 {len(L)}건)', flush=True)
    if not todo or a.dry:
        for x in todo: print('  (dry)', x['kind'], x['target'])
        return
    import entry_login as el
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = el.open_profile(pw, headless=True)
        for x in todo:
            pg = ctx.new_page()
            try:
                if x['kind'] == 'youtube':
                    st = yt_unsub(pg, x['target']); msg = ''
                else:
                    st, msg = korea_nl_unsub(pg)
            except Exception as e:
                st, msg = 'error', str(e)[:120]
            if st in ('done', 'already'):
                x.update(status='cancelled', cancelled=today)
            else:
                x['last_error'] = f'{today} {st} {msg}'.strip()
            print(f"[{st}] {x['kind']} {x['target']} {msg}", flush=True)
            pg.close(); save(L)
        ctx.close()
    save(L)


if __name__ == '__main__':
    main()
