"""JM's Schedule 아침 브리핑 — Claude 없이 GitHub Actions에서 실행.
TEST_MODE=1 (기본): 제목에 [테스트], 구글 문서·트래커는 읽기만 한다.
"""
import datetime as dt, os, traceback
import google_api as g
import quote

TO = os.environ.get('BRIEF_TO', 'wpaud16@naver.com')
TEST = os.environ.get('TEST_MODE', '1') == '1'
WD = '월화수목금토일'
DIV = '<hr style="border:none;border-top:1px solid #888888;margin:24px 0">'


def main():
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    label = f'{today.month}월 {today.day}일 ({WD[today.weekday()]})'
    fails, H, T = [], [], []

    try:
        q = quote.today_quote(today)
    except Exception:
        traceback.print_exc(); q = None; fails.append('오늘의 문장')
    h, t = quote.render(q); H.append(h); T.append(t)

    # TODO: STEP 1 할 일 / 1b 식사 / 2 증시 / 3 경매

    top_h = top_t = ''
    if TEST:
        top_h += '<p style="color:#777;font-size:12px">테스트 메일입니다 (Python 버전 · 문서·트래커는 변경하지 않음)</p>'
        top_t += '테스트 메일입니다 (Python 버전)\n\n'
    if fails:
        top_h += f'<p style="color:#d93025">⚠️ 실패: {", ".join(fails)}</p>'
        top_t += f'⚠️ 실패: {", ".join(fails)}\n\n'
    html_body = ('<div style="font-family:-apple-system,Segoe UI,Malgun Gothic,sans-serif;max-width:600px;'
                 'margin:auto;padding:8px;line-height:1.5;color:#222">' + top_h + DIV.join(H) + '</div>')
    subject = ('[테스트] ' if TEST else '') + f"[JM's Schedule] {label} 오늘의 할 일"
    g.send_mail(TO, subject, html_body, top_t + '\n\n'.join(T))
    print('sent:', subject)


if __name__ == '__main__':
    main()
