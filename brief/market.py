"""STEP 2 증시 숫자 (AI 요약 없음). 야후 파이낸스 차트 API, 국내 지수는 네이버 증권으로 보조."""
import datetime as dt, json, urllib.request

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
        return f'<div>{name} <span style="color:{GRAY}">확인 못함</span></div>', f'{name} 확인 못함'
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
    h = (f'<div style="display:flex;justify-content:space-between;max-width:320px"><span>{name}</span>'
         f'<span><b>{val}</b> <span style="color:{col}">{mark}{chg}</span> <span style="color:{GRAY};font-size:11px">{d}</span></span></div>')
    return h, f'{name} {val} {mark}{chg} ({d})'


def render(data, errs):
    box = 'border:1px solid #888888;border-radius:10px;padding:12px 14px;margin-bottom:16px;line-height:1.8'
    H = ['<div style="font-weight:bold;font-size:17px;margin-bottom:8px">📈 증시 시황</div>']
    T = ['📈 증시 시황']
    for title, rows in (('🇰🇷 국내', KR), ('🇺🇸 미국', US)):
        lines = [_line(n, data.get(n)) for n, _, _ in rows]
        H.append(f'<div style="{box}"><div style="font-weight:bold;margin-bottom:4px">{title}</div>' + ''.join(h for h, _ in lines) + '</div>')
        T.append(f'\n▶ {title}\n' + '\n'.join(t for _, t in lines))
    H.append(f'<div style="color:{GRAY};font-size:11px">출처: Yahoo Finance (국내 지수 보조: 네이버 증권) · 날짜 = 마지막 거래일 종가 · 상승 빨강 ▲ / 하락 파랑 ▼</div>')
    return ''.join(H), '\n'.join(T)


if __name__ == '__main__':
    d, e = fetch()
    print(json.dumps({k: (v and dict(v, date=str(v['date']))) for k, v in d.items()}, ensure_ascii=False, indent=1), e)
    print(render(d, e)[1])
