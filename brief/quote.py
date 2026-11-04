"""STEP 0 오늘의 문장 (구글 시트 'JM's 말모음' / 탭 '오늘의 문장')."""
import datetime as dt, html, re
import google_api as g

SHEET = '1yxgV3lZTubJNz5z-X-C2-Y76cytUH-vFTnYkckm7rVQ'
TOTAL = 902


def today_quote(today):
    n = ((today - dt.date(2026, 10, 3)).days - 1) % TOTAL + 1
    row = g.sheet_values(SHEET, f"'오늘의 문장'!A{n + 1}:C{n + 1}")[0]
    if str(row[0]).strip() != str(n):
        raise ValueError(f'순번 불일치: {row[0]} != {n}')
    text = re.sub(r'^#\s*', '', row[2].strip())
    src = ''
    m = re.search(r'\s-\s([^\n]+)$', text)
    if m:
        text, src = text[:m.start()].rstrip(), m.group(1).strip()
    return dict(n=n, text=text, source=src)


def render(q):
    """(html, text). q=None 이면 실패 문구."""
    if not q:
        msg = '오늘의 문장을 불러오지 못했습니다'
        return f'<p style="color:#777">{msg}</p>', msg
    body = html.escape(q['text']).replace('\n', '<br>')
    src = f'<div style="color:#777;font-size:12px;margin-top:6px">{html.escape(q["source"])}</div>' if q['source'] else ''
    h = (f'<div style="font-size:12px;color:#777">📖 오늘의 문장 ({q["n"]}/{TOTAL})</div>'
         f'<div style="border-left:3px solid #888888;padding:6px 12px;margin:6px 0;font-size:16px;line-height:1.6">{body}{src}</div>')
    t = f'📖 오늘의 문장 ({q["n"]}/{TOTAL})\n{q["text"]}' + (f'\n{q["source"]}' if q['source'] else '')
    return h, t
