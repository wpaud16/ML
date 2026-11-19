"""이벤트 대신 응모용 브라우저 프로필에 로그인해 두는 창 (2026-11-19 사용자 요청).

사용자가 직접 네이버·카카오·구글에 로그인 → 창을 닫으면 로그인 상태가 C:\\auction_pc\\entry_profile 에 남음.
Claude 는 비밀번호를 다루지 않고, 이후 응모 스크립트가 같은 프로필을 씀 (open_profile()).
"""
import os
from playwright.sync_api import sync_playwright

PROFILE = r'C:\auction_pc\entry_profile'
SITES = ['https://nid.naver.com/nidlogin.login', 'https://accounts.kakao.com/login/', 'https://accounts.google.com/']


def open_profile(p, headless=False):
    os.makedirs(PROFILE, exist_ok=True)
    kw = dict(headless=headless, viewport=None, locale='ko-KR',
              args=['--disable-blink-features=AutomationControlled', '--start-maximized'],
              ignore_default_args=['--enable-automation'])
    try:
        return p.chromium.launch_persistent_context(PROFILE, channel='chrome', **kw)   # 설치된 크롬 (구글 로그인 차단 덜함)
    except Exception:
        return p.chromium.launch_persistent_context(PROFILE, **kw)


if __name__ == '__main__':
    with sync_playwright() as p:
        ctx = open_profile(p)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto(SITES[0])
        for u in SITES[1:]:
            ctx.new_page().goto(u)
        try:
            while ctx.pages:
                ctx.pages[0].wait_for_timeout(1000)
        except Exception:
            pass
        try:
            ctx.close()
        except Exception:
            pass
    print('closed')
