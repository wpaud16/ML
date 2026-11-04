#!/usr/bin/env python3
"""경매 전체 카드 웹페이지 (2026-11-04 사용자 요청: 메일 용량 때문에 요약된 추적 물건도 물건별 전체 정보로 보기).

predictions/latest.json → page/index.html (GitHub Pages: https://wpaud16.github.io/ML/auction_model/page/)
메일 카드(브리핑 v24 CARD)와 같은 내용·같은 표 색을 코드로 만든다. 표시 기준도 메일과 같다:
  - risk.decision == show, safety 안전/보통만, 모델 예측 있는 물건만
  - 남양주·구리 아파트는 8호선역 도보 15분(직선 920m) 이내만
  python3 cards_page.py [latest.json] [출력 html]
"""
import json, os, sys, html
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
KST = timezone(timedelta(hours=9))
WD = '월화수목금토일'
E = html.escape


def eok(x, nd=2):
    return f'{x:.{nd}f}' if x is not None else '-'


def md(d):
    t = datetime.strptime(d[:10], '%Y-%m-%d')
    return f'{t.month}/{t.day}({WD[t.weekday()]})'


def keep(v):
    if v.get('category') not in ('아파트', '오피스텔'): return False
    if (v.get('risk') or {}).get('decision', 'show') != 'show': return False
    if (v.get('safety') or {}).get('grade', '보통') not in ('안전', '보통'): return False
    if not v.get('bid_by_prob_eok'): return False
    reg = v.get('region') or ''
    if v.get('category') == '아파트' and ('남양주' in reg or '구리' in reg):
        s8 = v.get('station8')
        if not s8 or s8['distance_m'] > 920: return False
    if v.get('category') == '아파트' and '하남' in reg:   # 하남은 5호선역 도보 15분(직선 920m) 이내만
        s5 = v.get('station5')
        if not s5 or s5['distance_m'] > 920: return False
    return True


def sise_lines(v, appr, low):
    s = v.get('sise') or {}
    if s.get('est_eok') and not s.get('error'):
        est = s['est_eok']; a, b = (s.get('range_eok') or [est, est])
        rng = f'범위 {a:.2f}~{b:.2f}억 · ' if abs(a - b) > 0.005 else ''
        out = [f'매매 시세(종합) <b>{est:.2f}억</b> <span class="g">({rng}감정가는 {appr / est * 100:.0f}% · 최저가는 {low / est * 100:.0f}%)</span>']
        src = []
        t = s.get('trade')
        if t: src.append(f"실거래 {t['eok']:.2f}억({md(t['date']).split('(')[0]} → 추세 반영 {t['adj_eok']:.2f})")
        if s.get('kb'): src.append(f"KB {s['kb']['eok']:.2f}억")
        if s.get('richgo_eok') and s.get('richgo_source') not in ('OFFER', 'MOLIT'): src.append(f"리치고 {s['richgo_eok']:.2f}억")
        nb = s.get('nearby')
        if nb: src.append(f"주변 {nb['eok']:.2f}억({nb['n_danji']}개 단지)")
        if src: out.append(f'<span class="g s">{" · ".join(src)}</span>')
        tr = s.get('trend') or {}
        tt = [f'{lab} {tr[k]:+.1f}%' for k, lab in (('3m_pct', '3개월'), ('12m_pct', '1년')) if tr.get(k) is not None]
        if tt: out.append(f'<span class="g s">단지 시세 추세 {" · ".join(tt)}</span>')
        ws = s.get('weighted')
        if ws:
            NM = dict(trade3='3개월 실거래', floor='층 보정', offer='최저 호가', appr='감정 시차')
            out.append(f'⚖ 가중 시세 <b>{ws["eok"]:.2f}억</b> <span class="g">(최저가는 {low / ws["eok"] * 100:.0f}%' + (' · 최저 호가 상한 적용' if ws.get('cap_by_offer') else '') + ')</span>')
            out.append('<span class="g s">' + ' · '.join(f"{NM[x['key']]} {x['eok']:.2f}억×{int(x['weight'] * 100)}%" for x in ws['parts']) + '</span>')
        if nb and nb.get('detail'):
            unit = '평당' if 'per_pyeong' in nb['detail'][0] else '㎡당'
            out.append('<span class="g s">🏘 ' + E(nb.get('basis') or '') + ' · ' + ' · '.join(
                f"{E(d['name'] or '')} {unit} {(d.get('per_pyeong') or d.get('per_m2')):,}만" for d in nb['detail'][:4]) + '</span>')
        if s.get('flags'): out.append(f'<span class="warn">⚠ {E(" · ".join(s["flags"]))}</span>')
        return out
    rs = v.get('richgo_sise_eok')
    if rs:
        lab = {'OFFER': '리치고 · 매물 호가 기반 · 최근 실거래·KB 없음', 'MOLIT': '리치고 시세 없음 → 최근 실거래 기준'}.get(s.get('richgo_source'), '리치고')
        return [f'매매 시세 {rs:.2f}억 <span class="g">({lab} · 감정가는 시세의 {appr / rs * 100:.0f}% · 최저가는 {low / rs * 100:.0f}%)</span>']
    return []


def exp_row(cat, n):
    if n is None: return None
    if cat == '오피스텔':
        return '1명' if n <= 1 else '2명' if n <= 2 else '3명' if n <= 4 else '5명' if n <= 7 else '8명 이상'
    return '1명' if n <= 1 else '2명' if n <= 2 else '3명' if n <= 4 else '5명' if n <= 7 else '8명' if n <= 12 else '13명'


def gap_warn(v):
    """감정 후 시세가 많이 오른 물건 (2026-11-05 백테스트: 감정가<시세 85% & 1년 +8%↑ 76건, 실제가가 예측보다 평균 +2.2%,
    3건 중 1건은 5% 넘게 높음 — 2024타경3470 +15%). 모델 입력으로는 개선이 없어 경고로만 표시."""
    avs = v.get('appr_vs_sise'); m12 = ((v.get('sise') or {}).get('trend') or {}).get('12m_pct')
    if avs and m12 is not None and avs < 0.85 and m12 > 8:
        return f'⚠ 감정 후 시세 상승(감정가는 시세의 {avs * 100:.0f}% · 1년 {m12:+.0f}%) — 과거 이런 물건은 실제가가 예측보다 높은 경우가 많았어요(3건 중 1건 +5% 넘게)'
    return ''


def bidder_table(v, seoul):
    bb = v.get('by_bidders') or {}
    probs = ['40%', '45%', '50%', '55%', '60%']
    head = '<b>👥 입찰 인원별 낙찰확률 입찰가</b>'
    if bb.get('bid_by_prob_eok') and not bb.get('error'):
        n = bb.get('expected_bidders'); r = bb.get('expected_range') or []
        if n is not None:
            head += f' <span class="n">· 예상 약 {n}명' + (f' (보통 {r[0]}~{r[1]}명)' if len(r) == 2 else '') + '</span>'
        rows = list(bb['bid_by_prob_eok'].items()); ex = exp_row(v.get('category'), n)
    else:
        rows = [('예측', v['bid_by_prob_eok'])]; ex = None
    t = ['<table><col style="width:19%"><col><col><col><col><col>', '<tr><th>인원</th>' + ''.join(f'<th>{p}</th>' for p in probs) + '</tr>']
    for lab, vals in rows:
        hi = lab == ex
        cells = [f'<td class="lab{" hi" if hi else ""}">{"▶ " if hi else ""}{E(lab)}</td>']
        for p in probs:
            cls = ' hi' if (hi or p == '50%') else ''
            cells.append(f'<td class="{cls.strip()}">{eok(vals.get(p))}</td>')
        t.append('<tr>' + ''.join(cells) + '</tr>')
    t.append('</table>')
    note = '단위 억 · ▶ 예상 인원 · 모델 오차 약 ±6% · 확률 ±5%p'
    f = v.get('fail') or {}
    if seoul and f.get('level') in ('보통', '높음'):
        note += f" · 유찰 시 다음 최저가 {v['low_manwon'] * 0.8 / 1e4:.2f}억"
    return head + ''.join(t) + f'<div class="g s">{note}</div>'


def rights(v, seoul):
    out = ['<b>⚖️ 권리분석</b>']
    sm = (v.get('risk') or {}).get('summary') or {}
    if sm.get('base_right'):
        out.append(f"말소기준: {E(sm['base_right'])}" + (f" ({sm['base_date']})" if sm.get('base_date') else '') + ' · 이후 소멸')
    out.append('인수 권리(등기 기준): ' + ('있음 — 확인 필요' if sm.get('right_risk') else '없음'))
    tn = v.get('tenant')
    if tn:
        ck = tn.get('checked') or ''
        out.append(f'👤 법원 명세서({md(ck).split("(")[0] if ck else "-"})')
        out += [E(x) for x in (tn.get('lines') or [])]
        am = tn.get('assumed_manwon') or 0
        out.append('인수 예상 <b>' + ('0원 (배당으로 전액 변제 예상)' if am == 0 else f'{am:,}만') + '</b>')
        if tn.get('caution'): out.append(f'<span class="g s">{E(tn["caution"])}</span>')
    else:
        out.append('점유자(대항력): 매각물건명세서 확인 필요')
    ci = v.get('court_info')
    if ci:
        if ci.get('occupant'):
            out.append(f"🏠 점유: {E(ci['occupant'])}" + (' · 폐문부재' if ci.get('closed_absent') else ''))
        for w in (ci.get('withdraw_signal') or [])[:2]:
            out.append(f"<b>⚖️ 취하·변경 주의: {md(w['date']).split('(')[0]} {E(w.get('label') or '')} — {E(w.get('text') or '')}</b>")
        if ci.get('notes'):
            out.append('<span class="g s">📂 ' + ' · '.join(E(n.get('label') or '') for n in ci['notes']) + '</span>')
        if ci.get('spec_published') is False:
            out.append('<span class="g s">명세서는 보통 매각기일 1주 전 공개 — 공개 후 자동 반영</span>')
    if seoul and v.get('category') == '아파트':
        out.append('토지거래허가: 경매 취득은 허가 대상 아님')
    out.append('<span class="g s">입찰 전 직접 확인: 배당요구종기 · 관리비 체납</span>')
    return out


def unmatched(d, today):
    """단지를 못 찾아 예측이 없는 아파트 (2026-11-05: 숨기지 말고 표시·추적)."""
    out = []
    for f in d.get('failed') or []:
        if f.get('category') != '아파트' or (f.get('bidding_date') or '') < today: continue
        if any(x in (f.get('region') or '') for x in ('남양주', '구리', '하남')): continue   # 역세권 판정 불가 지역은 제외
        if (f.get('risk') or {}).get('decision', 'show') == 'hide': continue
        out.append(f)
    return sorted(out, key=lambda f: f.get('bidding_date') or '9999')


def unmatched_card(f):
    appr, low = (f.get('appr_manwon') or 0) / 1e4, (f.get('low_manwon') or 0) / 1e4
    reg = (f.get('region') or '').split(' ', 1)[-1]
    rk = f.get('risk') or {}
    chk = ' · ⚠ 권리 확인 필요' if rk.get('decision') == 'check' else ''
    L = [f'<div class="t">{E((f.get("address") or "").split(" ", 2)[-1])}</div>',
         f'<div class="g s">{E(reg)} · {E(f["key"].replace("[1]", ""))} · {E(f.get("court") or "")}{chk}</div>',
         f'매각기일 {md(f["bidding_date"])} · <span class="dday" data-d="{f["bidding_date"]}"></span> · 전용 {f.get("area")}㎡',
         f'감정가 {appr:.2f}억 · 최저가 <b>{low:.2f}억</b> ({low / appr * 100:.0f}%) · 유찰 {f.get("fails") or 0}회' if appr else '',
         f'<span class="g s">🔍 예측 불가: {E(f.get("reason") or "")} — 리치고 단지 페이지가 없어 시세·모델 예측 없음</span>']
    if f.get('auction_id'):
        L.append(f'<a href="https://m.richgo.ai/auctionMobile/{E(f["auction_id"])}">상세 보기 →</a>')
    return f'<div class="card">' + '<br>'.join(x for x in L if x) + '</div>'


def card(v, today):
    cat = v['category']; reg = v.get('region') or ''; seoul = reg.startswith('서울')
    gu = reg.split(' ', 1)[-1]
    appr, low = v['appr_manwon'] / 1e4, v['low_manwon'] / 1e4
    key = v['key']; no = key.split('[')[-1].rstrip(']')
    case = key.split('[')[0] + (f' [{no}]' if no != '1' else '')
    hh = f' <span class="hh">{v["households"]:,}세대</span>' if cat == '아파트' and v.get('households') else ''
    grade = (v.get('safety') or {}).get('grade', '보통')
    L = [f'<div class="t">{E(v.get("danji_name") or "")}{hh} · 전용 {v.get("area")}㎡ · 🛡 {grade}</div>',
         f'<div class="g s">{E(gu)} · {E(case)} · {E(v.get("court") or "")}</div>', '<b>📋 기본 정보</b>']
    bd = v.get('bidding_date') or ''
    L.append(f'매각기일 {md(bd)} · <span class="dday" data-d="{bd}"></span>' if bd else '매각기일 미정')
    f = v.get('fail') or {}
    line = f"유찰 {v.get('fails') or 0}회"
    if f.get('prob_pct') is not None and not f.get('error'): line += f" · 유찰 확률(이번 회차) {f['prob_pct']}% · {f.get('level', '')}"
    L.append(line)
    L.append(f'감정가 {appr:.2f}억 · 최저가 <b>{low:.2f}억</b> ({low / appr * 100:.0f}%) · 보증금 {v["low_manwon"] * 0.1:,.0f}만')
    st = v.get('station')
    if st and st.get('name'):
        L.append(f"🚇 {E(st['name'])}역 도보 약 {st['walk_min']}분 ({st['distance_m']}m)")
    s8 = v.get('station8')
    s5 = v.get('station5')
    if cat == '아파트' and s5 and st and s5['name'] != st['name'] and s5['distance_m'] <= 920:
        L.append(f"🚇 5호선 {E(s5['name'])}역 도보 약 {s5['walk_min']}분 ({s5['distance_m']}m)")
    if cat == '아파트' and s8 and st and s8['name'] != st['name'] and s8['distance_m'] <= 920:
        L.append(f"🚇 8호선 {E(s8['name'])}역 도보 약 {s8['walk_min']}분 ({s8['distance_m']}m)")
    L += sise_lines(v, appr, low)
    if cat == '오피스텔':
        inc = v.get('income') or {}
        if inc.get('est_monthly_rent_manwon'):
            b = ' · 같은 건물 다른 평형 기준' if '같은 건물' in (inc.get('rent_basis') or '') else ''
            L.append(f"월세 시세 약 {inc['est_monthly_rent_manwon']}만원 <span class=\"g\">(보증금 1,000만 기준 추정{b})</span>")
        pb = v.get('payback')
        if pb and not pb.get('error') and pb.get('years'):
            L.append(f"📈 월세 {pb['monthly_rent_manwon']}만 × 약 {pb['years']:.1f}년({pb['months']}개월)이면 50% 가격 {pb['price_manwon'] / 1e4:.2f}억 <span class=\"g\">(대출·세금·비용 제외 단순 계산)</span>")
    gw = gap_warn(v)
    if gw: L.append(f'<span class="warn">{gw}</span>')
    sa = v.get('small_danji_adj') or {}
    if sa.get('applied'):
        L.append('<span class="g s">🏘 소규모 단지(300세대 미만) −3% 보정 적용</span>')
    if (v.get('risk') or {}).get('resale'):
        L.append('<span class="s">🔁 재매각 물건 — 이전 낙찰자 잔금 미납 · 보증금(보통 20%)·사유 확인 · 모델은 일반 물건 기준이라 참고용</span>')
    body = '<br>'.join(L)
    body += '<div class="sec">' + bidder_table(v, seoul) + '</div>'
    body += '<div class="sec">' + '<br>'.join(rights(v, seoul)) + '</div>'
    if v.get('auction_id'):
        body += f'<div class="sec"><a href="https://m.richgo.ai/auctionMobile/{E(v["auction_id"])}">상세 보기 →</a></div>'
    return f'<div class="card" data-d="{bd}">{body}</div>'


def results_14d(today):
    """predictions/results.json 최근 14일 (같은 물건은 매각 우선·최신 기일 하나)."""
    try:
        R = json.load(open(os.path.join(HERE, 'predictions', 'results.json'))).values()
    except Exception:
        return None
    t = datetime.strptime(today, '%Y-%m-%d')
    lo = (t - timedelta(days=14)).strftime('%Y-%m-%d')
    best = {}
    for r in R:
        if not (lo <= r['bidding_date'] < today): continue
        r = dict(r); r['category'] = r.get('category') or '아파트'
        b = best.get(r['key'])
        if b is None or (r['status'] == '매각', r['bidding_date']) > (b['status'] == '매각', b['bidding_date']):
            best[r['key']] = r
    return list(best.values())


def retrain_line(today):
    try:
        x = json.load(open(os.path.join(HERE, 'predictions', 'retrain_log.json')))[-1]
        d = datetime.strptime(x['date'], '%Y-%m-%d')
    except Exception:
        return ''
    if (datetime.strptime(today, '%Y-%m-%d') - d).days > 14: return ''
    if not x.get('apt_added') and not x.get('ot_added'):
        return f'🔄 {d.month}/{d.day} 재학습 확인 · 새 낙찰 사례 없음 (모델 그대로)'
    return (f"🔄 {d.month}/{d.day} 모델 재학습 · 아파트 +{x['apt_added']}건 (오차 {x['apt_mape_before']}% → {x['apt_mape_after']}%) · "
            f"오피스텔 +{x['ot_added']}건 (오차 {x['ot_mape_before']}% → {x['ot_mape_after']}%)")


def scorecard(rows, cat):
    rows = sorted([r for r in rows if r['category'] == cat], key=lambda r: r['bidding_date'], reverse=True)
    if not rows: return '<p class="g">최근 14일 결과 없음 (예측 기록은 10/31부터 쌓는 중)</p>'
    sold = [r for r in rows if r.get('status') == '매각' and r.get('diff_pct') is not None]
    out = []
    if sold:
        err = sum(abs(r['diff_pct']) for r in sold) / len(sold)
        w5 = sum(1 for r in sold if abs(r['diff_pct']) <= 5)
        mid = sum(1 for r in sold if (r.get('band') or '') not in ('', '60% 초과', '최저가 단일') and not (r.get('band') or '').startswith('40% 미만'))
        out.append(f'<div class="g s">낙찰 {len(sold)}건 · 평균 오차 {err:.1f}% · ±5% 안 {w5}건 · 40~60% 구간 안 {mid}건</div>')
    t = ['<table class="sc"><col style="width:28%"><col style="width:11%"><col><col><col><col style="width:14%">',
         '<tr><th>물건</th><th>기일</th><th>예상(50%)</th><th>실제</th><th>차이</th><th>인원<br><span class="sub">실제/예상</span></th></tr>']
    for r in rows:
        p50 = r['bid_by_prob_manwon']['50%'] / 1e4
        d = datetime.strptime(r['bidding_date'], '%Y-%m-%d'); dd = f'{d.month}/{d.day}'
        if r.get('status') == '매각' and r.get('actual_manwon'):
            act = f'<b>{r["actual_manwon"] / 1e4:.2f}</b>'; df = r.get('diff_pct') or 0
            bp = r.get('bid_by_prob_manwon') or {}
            if bp.get('40%') == bp.get('60%'): r = dict(r, band='최저가 단일')
            diff = f'<span style="color:{"#FF6B6B" if df > 0 else "#6FA8FF"}">{df:+.1f}%</span><br><span class="sub">{E(r.get("band") or "")}</span>'
        else:
            act = f'<span class="sub">{E(r.get("status") or "결과대기")}</span>'; diff = '-'
        b = r.get('bidders'); x = r.get('expected_bidders')
        ppl = f'<b>{b if b is not None else "-"}</b>/{x if x is not None else "-"}'
        name = f'{E(r.get("danji_name") or "")}<br><span class="sub">{E(r["key"].replace("[1]", ""))}<br>{r.get("area")}㎡</span>'
        t.append('<tr>' + ''.join(f'<td>{c}</td>' for c in (name, dd, f'{p50:.2f}', act, diff, ppl)) + '</tr>')
    t.append('</table>')
    out.append(''.join(t))
    out.append('<div class="g s">예상 = 기일 전에 기록한 앙상블 낙찰확률 50% 가격 · 인원 = 실제 응찰자 수 / 기일 전 모델이 예상한 인원 · '
               '구간 = 실제 낙찰가가 확률표의 어디에 있었는지 (40~60% 안이면 모델 범위 안)</div>')
    return ''.join(out)


CSS = """
:root{--bg:#ffffff;--fg:#1d1d1f;--mut:#777;--bd:#888}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#ececec;--mut:#9a9a9a;--bd:#666}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif;font-size:14px;line-height:1.55}
.wrap{max-width:600px;margin:0 auto;padding:12px 16px 40px}
h1{font-size:19px;margin:6px 0 2px} .meta{color:var(--mut);font-size:12px;margin-bottom:10px}
.nav{position:sticky;top:0;background:var(--bg);padding:8px 0;display:flex;gap:8px;flex-wrap:wrap;z-index:2;border-bottom:1px solid var(--bd)}
.nav a{border:1px solid var(--bd);border-radius:16px;padding:4px 12px;color:var(--fg);text-decoration:none;font-size:13px}
h2{font-size:19px;margin:22px 0 6px;padding-bottom:4px;border-bottom:2px solid var(--bd)}
h3{font-size:15px;margin:16px 0 8px}
.card{border:1px solid var(--bd);border-radius:10px;padding:12px 14px;margin-bottom:12px;overflow:hidden}
.t{font-weight:bold;font-size:15px} .hh{font-weight:normal;color:var(--mut);font-size:12px}
.g{color:var(--mut)} .s{font-size:12px} .n{font-weight:normal;font-size:13px}
.warn{color:#d93025;font-size:12px}
.sec{margin-top:10px}
table{border-collapse:collapse;width:100%;max-width:560px;table-layout:fixed;margin:8px 0;font-size:14px;text-align:center;background:#000;color:#fff;border:2px solid #fff}
th,td{background:#000;color:#fff;border:1px solid #fff;padding:9px 2px}
td.lab,th:first-child{white-space:nowrap} td.hi{font-weight:bold;background:#333}
a{color:#1a73e8}
table.sc{font-size:12px} table.sc td{padding:8px 2px} .sub{font-size:11px;color:#BBBBBB}
.foot{color:var(--mut);font-size:12px;margin-top:24px}
"""

JS = """
(function(){var t=new Date();var k=new Date(t.getTime()+9*3600e3);var today=Date.UTC(k.getUTCFullYear(),k.getUTCMonth(),k.getUTCDate());
document.querySelectorAll('.dday').forEach(function(e){var p=e.getAttribute('data-d').split('-');var d=Date.UTC(+p[0],+p[1]-1,+p[2]);
var n=Math.round((d-today)/864e5);e.textContent=n>0?('D-'+n):(n==0?'D-day':'기일 지남');});})();
"""


def build(src, dst):
    d = json.load(open(src))
    now = datetime.now(KST); today = now.strftime('%Y-%m-%d')
    items = [v for v in d['items'].values() if keep(v)]
    soon = (now + timedelta(days=7)).strftime('%Y-%m-%d')
    parts, nav, total = [], [], {}
    for cat, title, anchor in (('아파트', '🏢 아파트', 'apt'), ('오피스텔', '🏬 오피스텔 (서울 · 역 도보 10분)', 'ot')):
        xs = sorted((v for v in items if v['category'] == cat), key=lambda v: (v.get('bidding_date') or '9999', v.get('danji_name') or ''))
        total[cat] = len(xs)
        nav.append(f'<a href="#{anchor}">{title.split(" (")[0]} {len(xs)}</a>')
        parts.append(f'<h2 id="{anchor}">{title} · {len(xs)}건</h2>')
        groups = (('🔔 7일 이내', [v for v in xs if today <= (v.get('bidding_date') or '') <= soon]),
                  ('📅 그 이후', [v for v in xs if (v.get('bidding_date') or '9999') > soon]),
                  ('⏳ 기일 지남 · 결과 대기', [v for v in xs if (v.get('bidding_date') or '9999') < today]))
        for lab, g in groups:
            if not g: continue
            parts.append(f'<h3>{lab} ({len(g)}건)</h3>')
            parts += [card(v, today) for v in g]
        if not xs: parts.append('<p class="g">표시할 물건 없음</p>')
        if cat == '아파트':
            um = unmatched(d, today)
            if um:
                parts.append(f'<h3>🔍 예측 불가 (단지 못 찾음) · {len(um)}건</h3>')
                parts += [unmatched_card(f) for f in um]
    res = results_14d(today)
    nav.append('<a href="#score">📊 성적표</a>')
    parts.append('<h2 id="score">📊 모델 성적표 (최근 14일)</h2>')
    rt = retrain_line(today)
    if rt: parts.append(f'<div class="g s">{rt}</div>')
    if res is None:
        parts.append('<p class="g">성적표를 만들지 못했습니다</p>')
    else:
        for cat, title in (('아파트', '🏢 아파트'), ('오피스텔', '🏬 오피스텔')):
            parts.append(f'<h3>{title}</h3>' + scorecard(res, cat))
    gen = d.get('generated_at', '')[:16].replace('T', ' ')
    foot = ('표시 기준: 권리 위험·주의 물건과 모델 예측이 없는 물건은 숨김 · 남양주·구리 아파트는 8호선역 도보 15분 이내만 · 하남은 5호선역 도보 15분 이내만<br>'
            '🏢 아파트 입찰가 = 앙상블 모델(부스팅+군집별 회귀) · 🏬 오피스텔 = 랜덤포레스트+부스팅 · 가격 오차 약 ±6% · 확률 오차 약 ±5%p<br>'
            '⚖ 가중 시세 = 최근 3개월 같은 평형 실거래 60% · 층 보정 실거래 20% · 매물 최저 호가 15%(상한) · 감정가 시차 보정 5% (직거래 제외)<br>'
            '🏷 매매 시세(종합) = 최근 12개월 실거래(추세 보정) · 6개월 이내 KB · 리치고 추정시세 · 주변 단지 시세(같은 동)의 중앙값 (호가 제외) — 입찰가 모델은 리치고 시세 기준<br>'
            '👤 임차인·⚖️ 문건 = 법원경매정보(매각물건명세서·현황조사서·문건송달내역) 수집분 · 역 도보시간은 직선거리 기준 추정<br>'
            '권리분석은 등기 기준 자동요약을 바탕으로 한 1차 추정입니다. 점유자·대항력은 매각물건명세서에서, 대출 한도는 은행에서 직접 확인하세요. 입찰 권유가 아닙니다.')
    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>경매 전체 카드</title><style>{CSS}</style></head><body><div class="wrap">
<h1>🏠 경매 전체 카드</h1><div class="meta">예측 {E(gen)} 기준 · 아파트 {total['아파트']}건 · 오피스텔 {total['오피스텔']}건 · 매각기일 순</div>
<div class="nav">{''.join(nav)}</div>
{''.join(parts)}
<div class="foot">{foot}</div></div><script>{JS}</script></body></html>"""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'w').write(doc)
    print('page', dst, total, f'{len(doc.encode()) / 1024:.0f}KB')


if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'predictions', 'latest.json')
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'page', 'index.html')
    build(src, dst)
