"""STEP 3 경매 알림 — latest.json + 트래커(읽기) → 메일 섹션.
카드 본문은 auction_model/cards_page.py(웹페이지)와 같은 코드를 쓰고, 메일용으로 스타일을 인라인으로 바꾼다.
"""
import datetime as dt, html, json, os, re, sys
import google_api as g

HERE = os.path.dirname(os.path.abspath(__file__))
AM = os.path.join(HERE, '..', 'auction_model')
sys.path.insert(0, AM)
import cards_page as cp  # noqa: E402

TRACKER = '1Ot5SNpmYdKpFGC8QSxgXdt8cfvFQn57VrqEeCFTMu_8'
PAGE = 'https://wpaud16.github.io/ML/auction_model/page/'
CAP = 10  # 카테고리별 새 물건 전체 카드 최대 개수
E = html.escape
WD = '월화수목금토일'
GRAY = 'color:#777;font-size:12px'
CELL = 'background:#000000;color:#FFFFFF;border:1px solid #FFFFFF;padding:9px 2px'
HL = CELL + ';font-weight:bold;background:#333333'
GOOD_BG = 'background:#104728'   # 시세 88% 이하 칸 = 초록 35% 를 검은 배경에 섞은 단색 (메일 앱 rgba 미지원 대비)
TABLE = ('border-collapse:collapse;width:100%;max-width:560px;table-layout:fixed;margin:8px 0;font-size:14px;'
         'text-align:center;background:#000000;color:#FFFFFF;border:2px solid #FFFFFF')
CLS = {'card': 'border:1px solid #888888;border-radius:10px;padding:12px 14px;margin-bottom:12px',
       't': 'font-weight:bold;font-size:15px', 'hh': 'font-weight:normal;color:#777;font-size:12px',
       'g': 'color:#777', 's': 'font-size:12px', 'n': 'font-weight:normal;font-size:13px',
       'warn': 'color:#d93025;font-size:12px', 'sec': 'margin-top:10px'}
HEADS = ['사건번호', '법원', '구', '주소/단지명', '전용㎡', '감정가(만원)', '최저가(만원)', '최저가율', '매각기일', '유찰',
         '상태', '권리판정', '추정시세(만원)', '상세URL', '처음알림일', '마지막확인일', '비고']


def md(d):
    t = dt.date.fromisoformat(d[:10]); return f'{t.month}/{t.day}({WD[t.weekday()]})'


def dday(d, today):
    n = (dt.date.fromisoformat(d[:10]) - today).days
    return f'D-{n}' if n > 0 else 'D-day' if n == 0 else '기일 지남'


def inline(h, today):
    """cards_page 카드 HTML → 메일용 인라인 스타일."""
    h = re.sub(r'<span class="dday" data-d="([^"]*)"></span>', lambda m: dday(m.group(1), today) if m.group(1) else '', h)
    h = h.replace('<table>', f'<table style="{TABLE}">').replace('<th>', f'<th style="{CELL};white-space:nowrap">')
    def td(m):
        c = m.group(1).split()
        st = HL if 'hi' in c else CELL
        if 'good' in c: st += ';' + GOOD_BG
        return f'<td style="{st}{";white-space:nowrap" if "lab" in c else ""}">'
    h = re.sub(r'<td class="([^"]*)">', td, h)
    h = re.sub(r' data-d="[^"]*"', '', h)
    h = re.sub(r'class="([^"]*)"', lambda m: 'style="' + ';'.join(CLS.get(c, '') for c in m.group(1).split()) + '"', h)
    return h.replace('<a href', '<a style="color:#1a73e8" href')


def tracker_rows():
    mdtxt = g.drive_export(TRACKER)
    rows = {}
    for ln in mdtxt.splitlines()[2:]:
        f = [x.strip() for x in re.sub(r'\\(.)', r'\1', ln).split(' | ')]
        if len(f) == len(HEADS):
            rows[f[0]] = dict(zip(HEADS, f))
    return rows


def court_tag(st):
    """법원 진행 확인 결과 → (html, text) (2026-11-08 사용자 요청: 당일 실제 진행 여부)."""
    if not st:
        return '', ''
    ok, msg = st
    if ok is True:
        return f' · <b style="color:#188038">✅ 법원 확인: {E(msg)}</b>', f' · ✅ 법원 확인: {msg}'
    if ok is False:
        return f' · <b style="color:#d93025">❌ 진행 안 함: {E(msg)}</b>', f' · ❌ 진행 안 함: {msg}'
    return f' · <span style="color:#777">❔ 법원 {E(msg)}</span>', f' · ❔ 법원 {msg}'


def summary_row(v, today, new=False, court=None):
    """물건 한 개 (2026-11-05 사용자 지정 형식):
    11/10(화) D-4 · 최저 입찰 27.69억
    🔁 유찰 0회 · 이번 회차 유찰 확률 n% · 🚇 교대 7분
    🎯 예상 낙찰가 50%: 29.38억 (시세 대비 93.5%) · 👥 2명 입찰 예상"""
    gw = cp.gap_warn(v)
    bb = v.get('by_bidders') or {}
    n = bb.get('expected_bidders'); ex = cp.exp_row(v['category'], n)
    p50 = ((bb.get('bid_by_prob_eok') or {}).get(ex) or v['bid_by_prob_eok'])['50%']
    st = v.get('station') or {}
    f = v.get('fail') or {}
    gu = (v.get('region') or '').split(' ', 1)[-1]
    case = v['key'].replace('[1]', '')
    bs = cp.base_sise(v)
    ch, _ = court_tag(court)
    l1 = f"{md(v['bidding_date'])} {dday(v['bidding_date'], today)} · 최저 입찰 <b>{v['low_manwon'] / 1e4:.2f}억</b>{ch}"
    l2 = f"🔁 유찰 {v.get('fails') or 0}회" + (f" · 이번 회차 유찰 확률 {f['prob_pct']}%" if f.get('prob_pct') is not None and not f.get('error') else '') \
         + (f" · 🚇 {cp.station_text(v, short=True)}" if cp.station_text(v, short=True) else '')
    l3 = f"🎯 예상 낙찰가 50%: <b>{p50:.2f}억</b>" + (f' (시세 대비 {p50 / bs * 100:.1f}%)' if bs else '') + (f' · 👥 {n}명 입찰 예상' if n else '') \
         + f' · <a style="color:#1a73e8" href="https://m.richgo.ai/auctionMobile/{E(v["auction_id"])}">상세</a>'
    warn = '<br><span style="color:#d93025;font-size:12px">⚠ 감정 후 시세 상승 — 실제가가 예측보다 높을 수 있음</span>' if gw else ''
    tag = '<span style="color:#d93025;font-weight:bold;font-size:12px">New</span> ' if new else ''
    h = (f'<div style="border-bottom:1px solid #ddd;padding:8px 0;line-height:1.6">{tag}<b>{E(v.get("danji_name") or "")}</b> '
         f'<span style="{GRAY}">{v.get("area")}㎡ · {E(gu)} {E(case)}</span>'
         f'<br>{l1}<br>{l2}<br>{l3}{warn}</div>')
    strip = lambda x: re.sub(r'<[^>]+>', '', x.replace('<br>', '\n  ')).replace(' · 상세', '')
    t = ('[New] ' if new else '') + f"{v.get('danji_name')} {v.get('area')}㎡ · {gu} {case}\n  {strip(l1)}\n  {strip(l2)}\n  {strip(l3)}"
    return h, t


def scorecard(rows, cat, today):
    rows = sorted([r for r in rows if r.get('category') == cat], key=lambda r: r['bidding_date'], reverse=True)[:30]
    if not rows:
        return f'<div style="{GRAY}">최근 14일 결과 없음 (예측 기록은 10/31부터 쌓는 중)</div>', '최근 14일 결과 없음'
    sold = [r for r in rows if r.get('status') == '매각' and r.get('diff_pct') is not None]
    sm = ''
    if sold:
        err = sum(abs(r['diff_pct']) for r in sold) / len(sold)
        w5 = sum(1 for r in sold if abs(r['diff_pct']) <= 5)
        mid = sum(1 for r in sold if r.get('band') and r['band'][0].isdigit() and r['band'] not in ('60% 초과',) and not r['band'].startswith('40% 미만'))
        sm = f'낙찰 {len(sold)}건 · 평균 오차 {err:.1f}% · ±5% 안 {w5}건 · 40~60% 구간 안 {mid}건'
    c = CELL.replace('9px 2px', '8px 2px')
    th = ''.join(f'<th style="{c}">{x}</th>' for x in ('물건', '기일', '예상(50%)', '실제', '차이', '인원<br><span style="font-size:10px;color:#BBBBBB">실제/예상</span>'))
    tr, T = [], []
    for r in rows:
        p50 = r['bid_by_prob_manwon']['50%'] / 1e4
        d = dt.date.fromisoformat(r['bidding_date']); dd = f'{d.month}/{d.day}'
        sv, tv = r.get('sise_manwon'), (r.get('trade_manwon') if cat == '아파트' else None)
        def pc(x):   # 2026-11-10 사용자 요청: 시세 대비 % (아파트 M / 실거래 함께)
            if not (x and sv): return ''
            t = f'M {x / sv * 100:.0f}%' + (f'<br>실 {x / tv * 100:.0f}%' if tv else '')
            return f'<br><span style="font-size:10px;color:#BBBBBB">{t}</span>'
        if r.get('status') == '매각' and r.get('actual_manwon'):
            act = f'<b>{r["actual_manwon"] / 1e4:.2f}</b>' + pc(r['actual_manwon'])
            df = r.get('diff_pct') or 0
            diff = f'<span style="color:{"#FF6B6B" if df > 0 else "#6FA8FF"}">{df:+.1f}%</span><br><span style="font-size:11px;color:#BBBBBB">{E(r.get("band") or "")}</span>'
            T.append(f"{dd} {r['danji_name']} — 예상 {p50:.2f}억 → 실제 {r['actual_manwon'] / 1e4:.2f}억 ({df:+.1f}%, {r.get('band') or ''})")
        else:
            act = f'<span style="color:#BBBBBB">{E(r.get("status") or "결과대기")}</span>'; diff = '-'
            T.append(f"{dd} {r['danji_name']} — 예상 {p50:.2f}억 → {r.get('status')}")
        ppl = f'<b>{r["bidders"] if r.get("bidders") is not None else "-"}</b>/{r["expected_bidders"] if r.get("expected_bidders") is not None else "-"}'
        name = f'{E(r["danji_name"] or "")}<br><span style="font-size:11px;color:#BBBBBB">{E(r["key"].replace("[1]", ""))}<br>{r.get("area")}㎡</span>'
        tr.append('<tr>' + ''.join(f'<td style="{c};font-size:12px">{x}</td>' for x in (name, dd, f'{p50:.2f}' + pc(r['bid_by_prob_manwon']['50%']), act, diff, ppl)) + '</tr>')
    h = (f'<div style="{GRAY}">{sm}</div>' if sm else '') + (
        f'<table style="{TABLE};font-size:12px"><col style="width:28%"><col style="width:11%"><col><col><col><col style="width:14%">'
        f'<tr>{th}</tr>{"".join(tr)}</table><div style="{GRAY}">예상 = 기일 전에 기록한 앙상블 낙찰확률 50% 가격 · 인원 = 실제 응찰자 수 / 기일 전 모델이 예상한 인원 · '
        '구간 = 실제 낙찰가가 확률표의 어디에 있었는지 (40~60% 안이면 모델 범위 안) · M = 모델 시세 대비, 실 = 실거래 시세 대비</div>')
    return h, (sm + '\n' if sm else '') + '\n'.join(T)


def retrain_line(today):
    try:
        x = json.load(open(os.path.join(AM, 'predictions', 'retrain_log.json')))[-1]
        d = dt.date.fromisoformat(x['date'])
    except Exception:
        return ''
    if (today - d).days > 7:
        return ''
    if not x.get('apt_added') and not x.get('ot_added'):
        return f'🔄 {d.month}/{d.day} 재학습 확인 · 새 낙찰 사례 없음 (모델 그대로)'
    return (f"🔄 {d.month}/{d.day} 모델 재학습 · 아파트 +{x['apt_added']}건 (오차 {x['apt_mape_before']}% → {x['apt_mape_after']}%) · "
            f"오피스텔 +{x['ot_added']}건 (오차 {x['ot_mape_before']}% → {x['ot_mape_after']}%)")


def is_new(v, prev_keys):
    return prev_keys is not None and v['key'] not in prev_keys


def prev_keys(today):
    """어제 이전 가장 최근 예측 파일의 물건 키 (New 판정). 없으면 None."""
    d = os.path.join(AM, 'predictions')
    fs = sorted(f for f in os.listdir(d) if re.match(r'\d{4}-\d{2}-\d{2}\.json$', f) and f[:10] < today.isoformat())
    if not fs:
        return None
    return set(json.load(open(os.path.join(d, fs[-1])))['items'])


def results_14d(today):
    R = json.load(open(os.path.join(AM, 'predictions', 'results.json'))).values()
    lo = (today - dt.timedelta(days=14)).isoformat()
    out = []
    for r in R:
        if lo <= r['bidding_date'] < today.isoformat():
            r = dict(r); r.setdefault('category', '아파트')
            r['category'] = r['category'] or '아파트'
            out.append(r)
    # 같은 물건이 여러 기일로 기록된 경우 하나만 (매각 우선, 그다음 최신 기일)
    best = {}
    for r in out:
        b = best.get(r['key'])
        if b is None or (r['status'] == '매각', r['bidding_date']) > (b['status'] == '매각', b['bidding_date']):
            best[r['key']] = r
    return list(best.values())


def sold_keys():
    try:
        R = json.load(open(os.path.join(AM, 'predictions', 'results.json'))).values()
        return {r['key'] for r in R if r.get('status') == '매각'}
    except Exception:
        return set()


def build(today, now_hour=None):
    """(html, text, counts)."""
    notes = []
    L = json.load(open(os.path.join(AM, 'predictions', 'latest.json')))
    if L.get('date') != today.isoformat():
        notes.append(f"예측 결과가 {L.get('date')} 기준입니다 (오늘 자동 계산 미실행)")
    # 오늘 기일 물건은 입찰 시작(10시) 전에만 보여준다
    hour = now_hour if now_hour is not None else dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).hour
    lo = today.isoformat() if hour < 10 else (today + dt.timedelta(days=1)).isoformat()
    sold = sold_keys()  # 이미 낙찰된 물건은 목록에서 뺀다 (성적표에만)
    items = [v for v in L['items'].values() if cp.keep(v) and (v.get('bidding_date') or '') >= lo and v['key'] not in sold
             and v.get('no_trade_12m') is not True]   # 1년 실거래 0건 아파트는 메일에서 숨김 (웹페이지 '실거래 없음(참고)', 2026-11-05)
    pk = prev_keys(today)
    cp.VIEWS.clear(); cp.VIEWS.update(cp.load_views())
    # 오늘 기일 물건은 법원경매정보에서 실제 진행 여부 확인 (노트북에서만, 실패해도 메일은 발송)
    court = {}
    try:
        import court_status
        court = court_status.check([v for v in items if v['bidding_date'] == today.isoformat()])
        court_status.save(court, today.isoformat(), os.path.join(AM, 'predictions', 'court_status.json'))   # 웹카드에도 표시 (2026-11-09)
    except Exception as e:
        print('법원 확인 실패', e)
    H = [f'<div style="font-weight:bold;font-size:17px">🏠 경매 알림</div>']
    H += [f'<div style="color:#d93025;font-size:13px">{E(n)}</div>' for n in notes]
    # 버튼이 일부 메일 앱에서 눌리지 않는다는 보고(2026-11-05) → 새 창 열기 + 아래에 일반 링크도
    H.append(f'<p style="text-align:center;margin:12px 0 4px"><a href="{PAGE}" target="_blank" rel="noopener" style="display:inline-block;background:#1F1D1A;color:#ffffff;'
             'text-decoration:none;font-weight:bold;padding:12px 20px;border-radius:10px">📄 경매 전체 카드 · 모델 성적표 보기</a></p>'
             f'<p style="text-align:center;margin:0 0 12px;font-size:12px"><a href="{PAGE}" target="_blank" rel="noopener" style="color:#1a73e8">{PAGE}</a></p>')
    T = ['🏠 경매 알림'] + notes + [f'📄 경매 전체 카드: {PAGE}']
    cnt = dict(new=0, total=0)
    for cat, title in (('아파트', '🏢 아파트'), ('오피스텔', '🏬 오피스텔 (서울 · 역 도보 10분)')):
        xs = sorted((v for v in items if v['category'] == cat), key=lambda v: (v['bidding_date'], v.get('danji_name') or ''))
        nn = sum(1 for v in xs if is_new(v, pk))
        cnt['new'] += nn; cnt['total'] += len(xs)
        H.append(f'<div style="font-weight:bold;font-size:19px;margin-top:22px;padding-bottom:4px;border-bottom:2px solid #888888">{title}</div>')
        T.append(f'\n▶ {title}')
        H.append(f'<div style="font-weight:bold;margin:12px 0 6px">📋 경매 물건 ({len(xs)}건' + (f' · New {nn}' if nn else '') + ')</div>')
        T.append(f'▶ 📋 경매 물건 ({len(xs)}건' + (f' · New {nn}' if nn else '') + ')')
        if not xs:
            H.append(f'<div style="{GRAY}">진행 중인 물건 없음</div>')
        for v in xs:
            h, t = summary_row(v, today, is_new(v, pk), court.get(v['key'])); H.append(h); T.append(t)
    # 안내문(모델·시세·지역 설명)은 웹페이지 맨 아래로 옮김 (2026-11-05 사용자 요청)
    H.append(f'<div style="{GRAY};margin-top:18px">모델·시세 설명과 검색 지역은 <a style="color:#1a73e8" href="{PAGE}#foot">웹페이지 맨 아래</a>에 있어요 · 입찰 권유가 아닙니다</div>')
    T.append(f'\n모델·시세 설명: {PAGE}')
    return '\n'.join(H), '\n'.join(T), cnt
