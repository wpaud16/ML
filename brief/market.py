"""STEP 2 증시 숫자 (AI 요약 없음). 야후 파이낸스 차트 API, 국내 지수는 네이버 증권으로 보조."""
import datetime as dt, html, json, urllib.request

UA = {'User-Agent': 'Mozilla/5.0'}
KR = [('KOSPI', '^KS11', 'KOSPI'), ('KOSDAQ', '^KQ11', 'KOSDAQ'), ('원/달러', 'KRW=X', None)]
US = [('다우', '^DJI', None), ('S&P 500', '^GSPC', None), ('나스닥', '^IXIC', None),
      ('美10년물', '^TNX', None), ('WTI', 'CL=F', None)]
RED, BLUE, GRAY = '#D93025', '#1A73E8', '#777'


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return json.load(r)


def yahoo(sym):
    d = _get('https://query1.finance.yahoo.com/v8/finance/chart/' + urllib.request.quote(sym) + '?range=10d&interval=1d')
    r = d['chart']['result'][0]
    ts, cl = r['timestamp'], r['indicators']['quote'][0]['close']
    pts = [(t, c) for t, c in zip(ts, cl) if c is not None]
    (t1, c1), (_, c0) = pts[-1], pts[-2]
    off = r['meta'].get('gmtoffset', 0)
    day = dt.datetime.fromtimestamp(t1 + off, dt.timezone.utc).date()
    return dict(value=c1, prev=c0, date=day)


def naver(code):
    d = _get(f'https://m.stock.naver.com/api/index/{code}/basic')
    v = float(d['closePrice'].replace(',', ''))
    ch = float(d['compareToPreviousClosePrice'].replace(',', ''))
    return dict(value=v, prev=v - ch, date=dt.date.fromisoformat(d['localTradedAt'][:10]))


def fetch():
    out, errs = {}, []
    for name, sym, nv in KR + US:
        x = None
        try:
            x = yahoo(sym)
        except Exception as e:
            errs.append(f'{name}: {type(e).__name__}')
            if nv:
                try:
                    x = naver(nv)
                except Exception:
                    pass
        out[name] = x
    return out, errs


def _line(name, x):
    if not x:
        return f'<tr><td style="padding:2px 12px 2px 0">{name}</td><td colspan="3"><font color="{GRAY}">확인 못함</font></td></tr>', f'{name} 확인 못함'
    v, p = x['value'], x['prev']
    if name == '美10년물':
        diff = (v - p) * 100  # bp
        val, chg = f'{v:.2f}%', f'{abs(diff):.0f}bp'
        up = diff
    else:
        pct = (v / p - 1) * 100
        val = f'{v:,.2f}' if name != '원/달러' else f'{v:,.1f}원'
        if name == 'WTI':
            val = f'${v:,.2f}'
        chg, up = f'{abs(pct):.2f}%', pct
    if abs(up) < 0.005:
        mark, col, chg = '–', GRAY, '보합'
    else:
        mark, col = ('▲', RED) if up > 0 else ('▼', BLUE)
    d = f'{x["date"].month}/{x["date"].day}'
    h = (f'<tr><td style="padding:2px 12px 2px 0">{name}</td><td style="padding:2px 8px 2px 0;text-align:right"><b>{val}</b></td>'
         f'<td style="padding:2px 8px 2px 0;color:{col}"><font color="{col}">{mark}{chg}</font></td>'
         f'<td style="color:{GRAY};font-size:11px"><font color="{GRAY}">{d}</font></td></tr>')
    return h, f'{name} {val} {mark}{chg} ({d})'


def render(data, errs, ai=None):
    box = 'border:1px solid #888888;border-radius:10px;padding:12px 14px;margin-bottom:16px;line-height:1.8'
    H = ['<div style="font-weight:bold;font-size:17px;margin-bottom:8px">📈 증시 시황</div>']
    T = ['📈 증시 시황']
    for title, rows in (('🇰🇷 국내', KR), ('🇺🇸 미국', US)):
        lines = [_line(n, data.get(n)) for n, _, _ in rows]
        key = 'kr' if title.endswith('국내') else 'us'
        ah, at = ai_block(ai, key) if ai else ('', '')
        H.append(f'<div style="{box}"><div style="font-weight:bold;margin-bottom:4px">{title}</div>'
                 f'<table style="border-collapse:collapse;font-size:14px">' + ''.join(h for h, _ in lines) + '</table>' + ah + '</div>')
        T.append(f'\n▶ {title}\n' + '\n'.join(t for _, t in lines) + at)
    if ai:
        ah, at = ai_watch(ai)
        H.append(f'<div style="{box}"><div style="font-weight:bold;margin-bottom:4px">👀 앞으로 주목할 것</div>{ah}</div>'); T.append('\n▶ 👀 앞으로 주목할 것' + at)
    src = 'Yahoo Finance (국내 지수 보조: 네이버 증권)'
    if ai and ai.get('sources'):
        src += ' · 해설: Gemini + Google 검색 (' + ', '.join(ai['sources'][:5]) + ')'
    H.append(f'<div style="color:{GRAY};font-size:11px"><font color="{GRAY}">출처: {html.escape(src)} · 날짜 = 마지막 거래일 종가 · 상승 빨강 ▲ / 하락 파랑 ▼</font></div>')
    T.append('출처: ' + src)
    return ''.join(H), '\n'.join(T)


if __name__ == '__main__':
    d, e = fetch()
    print(json.dumps({k: (v and dict(v, date=str(v['date']))) for k, v in d.items()}, ensure_ascii=False, indent=1), e)
    print(render(d, e)[1])


UL = '<ul style="margin:4px 0 10px;padding-left:18px">'
LI = '<li style="line-height:1.6;margin-bottom:4px">'
LAB = '<div style="font-weight:bold;font-size:13px;margin-top:10px">'


def _themes(xs):
    return ''.join(f'{LI}<b>{html.escape(x.get("theme", ""))}</b> — {html.escape(x.get("stocks", ""))}'
                   + (f' · {html.escape(x["reason"])}' if x.get('reason') else '') + '</li>' for x in xs)


def ai_block(ai, k):
    m = ai.get(k) or {}
    if not m:
        return '', ''
    word = m.get('direction') or '움직였나'
    h = f'{LAB}📌 왜 {html.escape(word)}</div>{UL}' + ''.join(f'{LI}{html.escape(r)}</li>' for r in m.get('reasons', [])) + '</ul>'
    if m.get('up'):
        h += f'{LAB}🔺 강세</div>{UL}{_themes(m["up"])}</ul>'
    if m.get('down'):
        h += f'{LAB}🔻 약세</div>{UL}{_themes(m["down"])}</ul>'
    t = f'\n\n▶ 📌 왜 {word}\n' + '\n'.join('- ' + r for r in m.get('reasons', []))
    for lab, key in (('🔺 강세', 'up'), ('🔻 약세', 'down')):
        if m.get(key):
            t += f'\n\n▶ {lab}\n' + '\n'.join(f"- {x.get('theme')} — {x.get('stocks')} · {x.get('reason', '')}" for x in m[key])
    return h, t


def ai_watch(ai):
    ev, th = ai.get('week') or [], ai.get('themes') or []
    h = (f'{LAB}🗓 이번 주 일정</div>{UL}' + ''.join(f'{LI}<b>{html.escape(e.get("day", ""))}</b> {html.escape(e.get("event", ""))}</li>' for e in ev) + '</ul>'
         f'{LAB}🔍 볼 만한 테마</div>{UL}' + ''.join(f'{LI}<b>{html.escape(x.get("theme", ""))}</b> — {html.escape(x.get("reason", ""))}</li>' for x in th) + '</ul>')
    t = '\n▶ 🗓 이번 주 일정\n' + '\n'.join(f"- {e.get('day')} {e.get('event')}" for e in ev) + '\n\n▶ 🔍 볼 만한 테마\n' + '\n'.join(f"- {x.get('theme')} — {x.get('reason')}" for x in th)
    return h, t
