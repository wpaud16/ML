"""유튜브 이벤트용 동작 (2026-11-23 사용자: 응모용 창에 구글 로그인 → 구독·좋아요·댓글은 Claude 가).
응모용 프로필(entry_login) 로 연다. 댓글은 사용자가 대화창에서 승인한 문구만 쓴다.
python yt.py subscribe <채널URL> [shot.png]
python yt.py like <영상URL>
python yt.py comment <영상URL> <문구> [shot.png]
python yt.py handle"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import entry_login as el
from playwright.sync_api import sync_playwright


def subscribe(pg, url, shot=None):
    pg.goto(url, wait_until='domcontentloaded'); pg.wait_for_timeout(5000)
    b = pg.locator('#page-header yt-subscribe-button-view-model button, ytd-subscribe-button-renderer button, #subscribe-button button').first
    t = (b.inner_text() or '').strip()
    if '구독' in t and '구독중' not in t.replace(' ', ''):
        b.click(); pg.wait_for_timeout(2500)
        t = (b.inner_text() or '').strip()
    if shot: pg.screenshot(path=shot)
    return t


def like(pg, url):
    pg.goto(url, wait_until='domcontentloaded'); pg.wait_for_timeout(6000)
    b = pg.locator('ytd-watch-metadata like-button-view-model button, ytd-watch-metadata #segmented-like-button button').filter(visible=True).first
    if b.get_attribute('aria-pressed') != 'true':
        b.click(); pg.wait_for_timeout(1500)
    return b.get_attribute('aria-pressed')


def comment(pg, url, text, shot=None):
    if url not in pg.url:
        pg.goto(url, wait_until='domcontentloaded'); pg.wait_for_timeout(6000)
    for _ in range(4):
        pg.mouse.wheel(0, 700); pg.wait_for_timeout(1200)
    pg.locator('#simplebox-placeholder').first.click(); pg.wait_for_timeout(1200)
    box = pg.locator('#contenteditable-root').first
    box.click(); pg.keyboard.insert_text(text); pg.wait_for_timeout(800)
    pg.locator('#submit-button button, ytd-button-renderer#submit-button').first.click(); pg.wait_for_timeout(4000)
    mine = pg.locator('ytd-comment-thread-renderer', has_text=text[:15]).first
    ok = mine.count() > 0
    if shot:
        if ok: mine.scroll_into_view_if_needed()
        pg.wait_for_timeout(800); pg.screenshot(path=shot)
    return ok


def handle(pg):
    pg.goto('https://www.youtube.com/account', wait_until='domcontentloaded'); pg.wait_for_timeout(4000)
    return pg.evaluate("(document.body.innerText.match(/@[A-Za-z0-9._-]{3,}/)||[''])[0]")


if __name__ == '__main__':
    cmd = sys.argv[1]
    with sync_playwright() as p:
        c = el.open_profile(p, headless=True); pg = c.new_page()
        try:
            if cmd == 'subscribe': print(subscribe(pg, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
            elif cmd == 'like': print(like(pg, sys.argv[2]))
            elif cmd == 'comment': print(comment(pg, sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None))
            elif cmd == 'handle': print(handle(pg))
        finally:
            c.close()
