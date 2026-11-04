"""JM's Schedule 아침 브리핑 — Claude 없이 GitHub Actions에서 실행.
TEST_MODE=1 (기본): 제목에 [테스트], 구글 문서·트래커는 읽기만 한다.
"""
import datetime as dt, os, traceback
import google_api as g
import quote
import schedule_doc
import auction_mail

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

    try:
        r = schedule_doc.plan(today, write=not TEST)
        h, t = schedule_doc.render(r); H.append(h); T.append(t)
        fails += r['warnings']
    except Exception:
        traceback.print_exc(); fails.append('오늘의 할 일 (문서 읽기/쓰기)')

    # TODO: STEP 2 증시

    try:
        h, t, _ = auction_mail.build(today); H.append(h); T.append(t)
    except Exception:
        traceback.print_exc(); fails.append('경매 알림')

    top_h = top_t = ''
    if TEST:
        top_h += '<p style="color:#777;font-size:12px">테스트 메일입니다 (Python 버전 · 문서·트래커는 변경하지 않음)</p>'
        top_t += '테스트 메일입니다 (Python 버전)\n\n'
    if fails:
        top_h += f'<p style="color:#d93025">⚠️ 실패: {", ".join(fails)}</p>'
        top_t += f'⚠️ 실패: {", ".join(fails)}\n\n'
    H.append('<div style="color:#777;font-size:12px">📝 <a href="https://docs.google.com/document/d/16r3j5QD_VJZKxL9hOxbv-Aj58jNbp92nCM4szeKrq6Y/edit">JM\'s Schedule 문서 열기</a><br>'
             '끝낸 일(운동·큐티·독서 포함)은 문서에서 체크해 주세요. 내일 아침 자동 정리됩니다.</div>')
    T.append('📝 문서: https://docs.google.com/document/d/16r3j5QD_VJZKxL9hOxbv-Aj58jNbp92nCM4szeKrq6Y/edit')
    html_body = ('<div style="font-family:-apple-system,Segoe UI,Malgun Gothic,sans-serif;max-width:600px;'
                 'margin:auto;padding:8px;line-height:1.5;color:#222">' + top_h + DIV.join(H) + '</div>')
    subject = ('[테스트] ' if TEST else '') + f"[JM's Schedule] {label} 오늘의 할 일"
    g.send_mail(TO, subject, html_body, top_t + '\n\n'.join(T))
    print('sent:', subject)


if __name__ == '__main__':
    main()
