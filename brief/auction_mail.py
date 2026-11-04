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


def summary_row(v, today, new=False):
    bb = v.get('by_bidders') or {}
    n = bb.get('expected_bidders'); ex = cp.exp_row(v['category'], n)
    p50 = ((bb.get('bid_by_prob_eok') or {}).get(ex) or v['bid_by_prob_eok'])['50%']
    st = v.get('station') or {}
    gu = (v.get('region') or '').split(' ', 1)[-1]
    case = v['key'].replace('[1]', '')
    line2 = (f"{md(v['bidding_date'])} {dday(v['bidding_date'], today)} · 최저 {v['low_manwon'] / 1e4:.2f}억 · "
             f"50% {p50:.2f}억" + (f' ({n}명)' if n else '') + (f" · 🚇 {E(st['name'])} {st['walk_min']}분" if st.get('name') else '')
             + f' · <a style="color:#1a73e8" href="https://m.richgo.ai/auctionMobile/{E(v["auction_id"])}">상세</a>')
    tag = '<span style="color:#d93025;font-weight:bold;font-size:12px">New</span> ' if new else ''
    h = (f'<div style="border-bottom:1px solid #ddd;padding:6px 0">{tag}<b>{E(v.get("danji_name") or "")}</b> '
         f'<span style="{GRAY}">{v.get("area")}㎡ · {E(gu)} {E(case)}</span>'
         + f'<br>{line2}</div>')
    t = (('[New] ' if new else '') + f"{v.get('danji_name')} {v.get('area')}㎡ · {gu} {case}\n  {md(v['bidding_date'])} {dday(v['bidding_date'], today)} · 최저 {v['low_manwon'] / 1e4:.2f}억 · 50% {p50:.2f}억"
         + (f' ({n}명)' if n else ''))
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
        if r.get('status') == '매각' and r.get('actual_manwon'):
            act = f'<b>{r["actual_manwon"] / 1e4:.2f}</b>'
            df = r.get('diff_pct') or 0
            diff = f'<span style="color:{"#FF6B6B" if df > 0 else "#6FA8FF"}">{df:+.1f}%</span><br><span style="font-size:11px;color:#BBBBBB">{E(r.get("band") or "")}</span>'
            T.append(f"{dd} {r['danji_name']} — 예상 {p50:.2f}억 → 실제 {r['actual_manwon'] / 1e4:.2f}억 ({df:+.1f}%, {r.get('band') or ''})")
        else:
            act = f'<span style="color:#BBBBBB">{E(r.get("status") or "결과대기")}</span>'; diff = '-'
            T.append(f"{dd} {r['danji_name']} — 예상 {p50:.2f}억 → {r.get('status')}")
        ppl = f'<b>{r["bidders"] if r.get("bidders") is not None else "-"}</b>/{r["expected_bidders"] if r.get("expected_bidders") is not None else "-"}'
        name = f'{E(r["danji_name"] or "")}<br><span style="font-size:11px;color:#BBBBBB">{E(r["key"].replace("[1]", ""))}<br>{r.get("area")}㎡</span>'
        tr.append('<tr>' + ''.join(f'<td style="{c};font-size:12px">{x}</td>' for x in (name, dd, f'{p50:.2f}', act, diff, ppl)) + '</tr>')
    h = (f'<div style="{GRAY}">{sm}</div>' if sm else '') + (
        f'<table style="{TABLE};font-size:12px"><col style="width:28%"><col style="width:11%"><col><col><col><col style="width:14%">'
        f'<tr>{th}</tr>{"".join(tr)}</table><div style="{GRAY}">예상 = 기일 전에 기록한 앙상블 낙찰확률 50% 가격 · 인원 = 실제 응찰자 수 / 기일 전 모델이 예상한 인원 · '
        '구간 = 실제 낙찰가가 확률표의 어디에 있었는지 (40~60% 안이면 모델 범위 안)</div>')
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
    items = [v for v in L['items'].values() if cp.keep(v) and (v.get('bidding_date') or '') >= lo and v['key'] not in sold]
    pk = prev_keys(today)
    H = [f'<div style="font-weight:bold;font-size:17px">🏠 경매 알림</div>']
    H += [f'<div style="color:#d93025;font-size:13px">{E(n)}</div>' for n in notes]
    H.append(f'<p style="text-align:center;margin:12px 0"><a href="{PAGE}" style="display:inline-block;background:#1F1D1A;color:#ffffff;'
             'text-decoration:none;font-weight:bold;padding:12px 20px;border-radius:10px">📄 경매 전체 카드 보기 (모든 물건 상세)</a></p>')
    T = ['🏠 경매 알림'] + notes + [f'📄 경매 전체 카드: {PAGE}']
    rt = retrain_line(today)
    try:
        res = results_14d(today)
    except Exception:
        res = None
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
            h, t = summary_row(v, today, is_new(v, pk)); H.append(h); T.append(t)
        H.append(f'<div style="font-weight:bold;margin:16px 0 6px">📊 모델 성적표 (최근 14일)</div>')
        T.append('▶ 📊 모델 성적표 (최근 14일)')
        if rt:
            H.append(f'<div style="{GRAY}">{rt}</div>'); T.append(rt)
        if res is None:
            H.append(f'<div style="{GRAY}">성적표를 만들지 못했습니다</div>')
        else:
            h, t = scorecard(res, cat, today); H.append(h); T.append(t)
    foot = ['🛡 안전 = 법원 매각물건명세서로 인수 금액 0원 확인 · 보통 = 리치고 기준 권리 문제 없음(명세서 미확인) · 주의·위험은 숨김',
            '📈 회수기간(오피스텔) = 낙찰확률 50% 가격 ÷ (추정 월세 × 12) · 대출·세금·비용 제외 단순 계산',
            '검색 지역: 서울 강남·서초·강동·광진·송파 / 성남 수정·분당·중원 / 남양주·구리(8호선역 도보 15분 이내)',
            '🏢 아파트 입찰가 = 앙상블 모델(부스팅+군집별 회귀) · 가격 오차 약 ±6% · 확률 오차 약 ±5%p',
            '🏬 오피스텔 입찰가 = 오피스텔 전용 모델(랜덤포레스트+부스팅) · 월세는 전세 시세 × 전월세전환율로 추정',
            '🏷 매매 시세(종합) = 최근 12개월 실거래(추세 보정) · 6개월 이내 KB · 리치고 추정시세의 중앙값 (호가 제외)',
            '🎲 유찰 확률 = 회차별 낙찰·유찰 이력으로 학습한 모델',
            '⚠️ 주거용 오피스텔은 세법상 주택 수에 들어갈 수 있어요 — 세무사·은행에 확인',
            f'<a style="color:#1a73e8" href="https://docs.google.com/document/d/{TRACKER}/edit">경매 트래커 열기</a>',
            '권리분석은 등기 기준 자동요약을 바탕으로 한 1차 추정입니다. 점유자·대항력은 매각물건명세서에서, 대출 한도는 은행에서 직접 확인하세요. 역 도보시간은 직선거리 기준 추정입니다.']
    H.append(f'<div style="{GRAY};margin-top:18px;line-height:1.6">' + '<br>'.join(foot) + '</div>')
    T.append('\n' + '\n'.join(re.sub(r'<[^>]+>', '', f) for f in foot))
    return '\n'.join(H), '\n'.join(T), cnt
