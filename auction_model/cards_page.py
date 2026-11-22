#!/usr/bin/env python3
"""경매 전체 카드 웹페이지 (2026-11-04 사용자 요청: 메일 용량 때문에 요약된 추적 물건도 물건별 전체 정보로 보기).

predictions/latest.json → page/index.html (GitHub Pages: https://wpaud16.github.io/ML/auction_model/page/)
메일 카드(브리핑 v24 CARD)와 같은 내용·같은 표 색을 코드로 만든다. 표시 기준도 메일과 같다:
  - risk.decision == show, safety 안전/보통만, 모델 예측 있는 물건만
  - 아파트는 전용 50㎡ 이상만 (2026-11-13)
  - 구리 아파트는 8호선역 도보 15분(직선 920m) 이내만 (남양주는 2026-11-12 사용자 요청으로 제외)
  python3 cards_page.py [latest.json] [출력 html]
"""
import json, os, re, sys, html
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
KST = timezone(timedelta(hours=9))
WD = '월화수목금토일'
E = html.escape


def day_label(d):
    """'2026-11-12' → '11/12(목)'."""
    try:
        t = datetime.strptime(d, '%Y-%m-%d'); return f'{t.month}/{t.day}({WD[t.weekday()]})'
    except Exception:
        return d or '기일 미정'


def eok(x, nd=2):
    return f'{x:.{nd}f}' if x is not None else '-'


def md(d):
    t = datetime.strptime(d[:10], '%Y-%m-%d')
    return f'{t.month}/{t.day}({WD[t.weekday()]})'


def m_line(v):
    """모델 시세(M) 한 줄 (2026-11-05: 아파트 예측에 쓰는 시세 = 리치고 + 국토부 실거래 가중)."""
    m = v.get('m_sise') or {}
    if not m or not v.get('model_sise_eok'): return []
    if m.get('no_trade') is True:
        why = '1년 실거래 없음 · 리치고' + (f' × 층 보정({m.get("floor_bin")})' if m.get('fprem') and m['fprem'] != 1 else '')
    elif m.get('no_trade') is None:
        why = '리치고' + (f' · {E(m.get("note") or "")}' if m.get('note') else '')
    else:
        why = f'리치고 {m.get("richgo_floor") or m.get("richgo"):.2f}억 · 1년 실거래 {m.get("n12")}건 {m.get("trade_w"):.2f}억 · 실거래 비중 {m.get("w", 0) * 100:.0f}%'
    return [f'🎯 모델 시세 <b>{v["model_sise_eok"]:.2f}억</b> <span class="g">({why})</span>']


def station_text(v, short=False):
    """가까운 역 (2개 이상이면 2개, 2026-11-05). short=True: '교대 7분 · 서초 9분'."""
    sl = v.get('stations') or ([v['station']] if (v.get('station') or {}).get('name') else [])
    if short:
        return ' · '.join(f"{E(x['name'])} {x['walk_min']}분" for x in sl)
    return ' · '.join(f"{E(x['name'])}역 도보 약 {x['walk_min']}분 ({x['distance_m']}m)" for x in sl)


def keep(v):
    if v.get('category') not in ('아파트', '오피스텔'): return False
    if (v.get('risk') or {}).get('decision', 'show') != 'show': return False
    if (v.get('safety') or {}).get('grade', '보통') not in ('안전', '보통'): return False
    if not v.get('bid_by_prob_eok'): return False
    reg = v.get('region') or ''
    if v.get('category') == '아파트' and (v.get('area') or 0) < 50: return False   # 2026-11-13 사용자 요청: 아파트 전용 50㎡ 이상만
    if '남양주' in reg: return False   # 2026-11-12 사용자 요청: 남양주 제외, 구리만 유지
    if v.get('category') == '아파트' and '구리' in reg:
        s8 = v.get('station8')
        if not s8 or s8['distance_m'] > 920: return False
    if v.get('category') == '아파트' and '하남' in reg:   # 하남은 5호선역 도보 15분(직선 920m) 이내만
        s5 = v.get('station5')
        if not s5 or s5['distance_m'] > 920: return False
    return True


def kb_line(v, low):
    """KB 시세 한 줄 (2026-11-17 사용자 요청, kb_sise.py — KB부동산 매매 일반가)."""
    k = v.get('kb') or {}
    if not k.get('eok'): return []
    return [f'🏦 KB 시세 <b>{k["eok"]:.2f}억</b>']   # 2026-11-19 사용자 요청: 뒤 괄호(하한~상한·%·기준일) 제거


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
        if s.get('richgo_eok') and s.get('richgo_source') not in ('OFFER', 'MOLIT', 'BLDG', 'NEARBY'): src.append(f"리치고 {s['richgo_eok']:.2f}억")
        nb = s.get('nearby')
        if nb: src.append(f"주변 {nb['eok']:.2f}억({nb['n_danji']}개 단지)")
        if src: out.append(f'<span class="g s">{" · ".join(src)}</span>')
        out += m_line(v)
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
        lab = {'OFFER': '리치고 · 매물 호가 기반 · 최근 실거래·KB 없음', 'MOLIT': '리치고 시세 없음 → 최근 실거래 기준', 'BLDG': '추정: 같은 건물 다른 면적 ㎡당 가격 × 면적', 'NEARBY': '추정: 주변 오피스텔 ㎡당 실거래 × 면적'}.get(s.get('richgo_source'), '리치고')
        return [f'매매 시세 {rs:.2f}억 <span class="g">({lab} · 감정가는 시세의 {appr / rs * 100:.0f}% · 최저가는 {low / rs * 100:.0f}%)</span>'] + m_line(v)
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


def base_sise(v):
    """입찰가 % 기준 시세(억): 예측에 쓴 모델 시세 (아파트 M, 오피스텔 리치고)."""
    return v.get('model_sise_eok') or v.get('richgo_sise_eok')


GOOD_PCT = 0.88   # 2026-11-10 사용자 요청: 시세 88% 이하 입찰가 칸 초록 표시 (매매 대비 확실한 이득선)


def is_good(v, x):
    b = base_sise(v)
    return bool(b and x and x / b <= GOOD_PCT)


def pct_of(v, x):
    b = base_sise(v)
    if not (b and x): return ''
    return f'{x / b * 100:.1f}%'   # 카드는 M(모델 시세) 기준만 — 실거래 기준은 성적표에만 (2026-11-10 사용자 결정)


def bidder_table(v, seoul):
    bb = v.get('by_bidders') or {}
    probs = ['40%', '45%', '50%', '55%', '60%']
    head = '<b>👥 입찰 인원별 낙찰확률 입찰가</b>'
    if bb.get('bid_by_prob_eok') and not bb.get('error'):
        n = bb.get('expected_bidders'); r = bb.get('expected_range') or []
        if n is not None:
            head += f' <span class="n">· 예상 약 {n}명' + (f' (보통 {r[0]}~{r[1]}명)' if len(r) == 2 else '') + '</span>'
        rows = list(bb['bid_by_prob_eok'].items()); ex = exp_row(v.get('category'), n)
        if v.get('bid_by_prob_eok'):   # 인원 가정 없는 종합 예측 = 성적표 '예상(50%)' 기준 (2026-11-08 사용자 요청)
            rows = [('종합', v['bid_by_prob_eok'])] + rows
    else:
        rows = [('예측', v['bid_by_prob_eok'])]; ex = None
    t = ['<table><col style="width:19%"><col><col><col><col><col>', '<tr><th>인원</th>' + ''.join(f'<th>{p}</th>' for p in probs) + '</tr>']
    for lab, vals in rows:
        hi = lab == ex
        cells = [f'<td class="lab{" hi" if hi else ""}">{"▶ " if hi else ""}{E(lab)}</td>']
        for p in probs:
            cls = ' hi' if (hi or p == '50%') else ''   # 2026-11-11 사용자 요청: 88% 이하 초록 칸 제거
            pc = pct_of(v, vals.get(p))   # 2026-11-05 사용자 요청: 입찰가마다 시세 대비 %
            cells.append(f'<td class="{cls.strip()}">{eok(vals.get(p))}' + (f'<br><span class="sub">{pc}</span>' if pc else '') + '</td>')
        t.append('<tr>' + ''.join(cells) + '</tr>')
    t.append('</table>')
    note = '단위 억 · 아래 % = 모델 시세' + (f' {base_sise(v):.2f}억' if base_sise(v) else '') + ' 대비 · 종합 = 인원 가정 없는 전체 예측(성적표 기준) · ▶ 예상 인원 · 모델 오차 약 ±6% · 확률 ±5%p'
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
        ck = tn.get('checks')
        if ck and tn.get('opposing_tenants'):   # 2026-11-12 대항력 임차인 5가지 안전 조건
            mk = lambda b: '미확인' if b is None else ('✅' if b else '❌')
            out.append('🛡 대항력 체크 ' + ' '.join(f'{c}{k} {mk(ck.get(k))}' for c, k in zip('①②③④⑤', ('배당요구', '확정일자', '순위', '재원', '전입유지'))))
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


COURT = {}   # 아침 브리핑이 법원경매정보에서 확인한 당일 진행 여부 (predictions/court_status.json, 2026-11-09)


def load_court():
    try:
        return json.load(open(os.path.join(HERE, 'predictions', 'court_status.json'), encoding='utf-8')).get('items') or {}
    except Exception:
        return {}


VIEWS = {}   # 법원경매정보 관심등록 수 (predictions/views.json, 새벽 수집, 2026-11-09)


def load_views():
    try:
        return json.load(open(os.path.join(HERE, 'predictions', 'views.json'), encoding='utf-8')).get('items') or {}
    except Exception:
        return {}


def views_text(key):
    """'⭐ 관심 18명 (어제 +3)' — 법원 사이트에 관심물건으로 등록한 사람 수 (입찰 경쟁 신호)."""
    v = VIEWS.get(key)
    if not v or v.get('gwans') is None: return ''
    h = v.get('hist') or {}
    ds = sorted(d for d in h if d < (v.get('date') or ''))
    ch = ''
    if ds:
        diff = v['gwans'] - h[ds[-1]][1]
        ch = f' (전일 대비 {diff:+d})' if diff else ' (변동 없음)'
    return f'⭐ 법원 관심 {v["gwans"]}명{ch}'


def court_line(key, bd):
    """카드용 법원 진행 여부 한 줄 (메일과 같은 표시). 그 기일에 확인한 것만."""
    c = COURT.get(key)
    if not c or c.get('date') != bd: return ''
    ok, msg, at = c.get('ok'), E(c.get('msg') or ''), E((c.get('at') or '')[11:16])
    when = f' <span class="g s">({at} 확인)</span>' if at else ''
    if ok is True: return f'<b style="color:#3FB950">✅ 법원 확인: {msg}</b>{when}'
    if ok is False: return f'<b style="color:#FF6B6B">❌ 진행 안 함: {msg}</b>{when}'
    return f'<span class="g">❔ 법원 {msg}</span>{when}'


def unmatched_card(f):
    appr, low = (f.get('appr_manwon') or 0) / 1e4, (f.get('low_manwon') or 0) / 1e4
    reg = (f.get('region') or '').split(' ', 1)[-1]
    rk = f.get('risk') or {}
    chk = ' · ⚠ 권리 확인 필요' if rk.get('decision') == 'check' else ''
    L = [f'<div class="t">{E((f.get("address") or "").split(" ", 2)[-1])}</div>',
         f'<div class="g s">{E(reg)} · {E(f["key"].replace("[1]", ""))} · {E(f.get("court") or "")}{chk}</div>',
         f'매각기일 {md(f["bidding_date"])} · <span class="dday" data-d="{f["bidding_date"]}"></span> · 전용 {f.get("area")}㎡',
         court_line(f['key'], f.get('bidding_date')),
         f'감정가 {appr:.2f}억 · 최저가 <b>{low:.2f}억</b> ({low / appr * 100:.0f}%) · 유찰 {f.get("fails") or 0}회' if appr else '',
         f'<span class="g s">🔍 예측 불가: {E(f.get("reason") or "")} — 리치고 단지 페이지가 없어 시세·모델 예측 없음</span>']
    if f.get('auction_id'):
        L.append(f'<a href="https://m.richgo.ai/auctionMobile/{E(f["auction_id"])}" target="_blank" rel="noopener">상세 보기 ↗</a>')
    return f'<div class="card">' + '<br>'.join(x for x in L if x) + '</div>'


def region_text():
    """검색 지역 문구 (search_regions.json, 2026-11-08 GUI 로 수정)."""
    try:
        rc = json.load(open(os.path.join(HERE, 'search_regions.json'), encoding='utf-8'))
    except Exception:
        return '-'
    by = {}
    for sd, sgg in rc.get('apt') or []:
        city, _, gu = sgg.partition(' ')
        name = f'{sd} {city}' if gu else sd
        by.setdefault(name, []).append((gu or city).removesuffix('구') if gu or sd == '서울' else city)
    note = {'구리시': '(8호선역 도보 15분 이내)', '하남시': '(5호선역 도보 15분 이내)'}
    apt = ' / '.join(f"{k} {'·'.join(v)}" if k != '경기' else '경기 ' + '·'.join(x + note.get(x, '') for x in v) for k, v in by.items())
    ot = rc.get('ot') or []
    ot_t = '서울 전체' if len(ot) >= 25 else '서울 ' + '·'.join(g.removesuffix('구') for g in ot)
    import search_cfg
    pa, po = search_cfg.price_text('아파트', rc), search_cfg.price_text('오피스텔', rc)
    return (f'아파트(전용 50㎡ 이상{", " + pa if pa else ""}) {apt} · '
            f'오피스텔 {ot_t}(역 도보 10분{", " + po if po else ""})')


def unit_text(v):
    """주소에서 동·호·층 (2026-11-08 사용자 요청: 상세 정보에 몇 동 몇 호). 법정동(역삼동 등)은 지번 뒤에서만 찾아 제외."""
    a = v.get('address') or ''
    m = re.search(r'\d+(?:-\d+)?,?\s', a)
    tail = a[m.end():] if m else a
    dong = re.search(r'(?:^|\s)(?:제)?([0-9A-Za-z]+|[가-힣])동(?=\s|제|\d|$)', tail)
    ho = re.findall(r'(?:제)?([0-9A-Za-z]+)호', tail)
    fl = re.findall(r'(?:제)?(?:지하)?(\d+)층', tail)
    parts = ([f'{dong.group(1)}동'] if dong else []) + ([f'{ho[-1]}호'] if ho else [])
    if not parts: return ''
    return ' '.join(parts) + (f' ({fl[-1]}층)' if fl else '')


def result_line(r):
    """기일 지난 카드의 실제 결과 한 줄 (2026-11-08)."""
    if not r: return '<b>📊 결과:</b> 확인 전'
    st = r.get('status') or '결과대기'
    if st != '매각' or not r.get('actual_manwon'):
        return f'<b>📊 결과:</b> {E(st)}'
    a = r['actual_manwon']; s = r.get('sise_manwon')
    out = f'<b>📊 결과: 매각 {a / 1e4:.2f}억</b>' + (f' (시세 대비 {a / s * 100:.1f}%)' if s else '')
    if r.get('bidders') is not None: out += f' · 응찰 {r["bidders"]}명'
    if r.get('diff_pct') is not None: out += f' · 예상(50%) 대비 {r["diff_pct"]:+.1f}%'
    return out


def card(v, today, cid=None, res=None):
    cat = v['category']; reg = v.get('region') or ''; seoul = reg.startswith('서울')
    gu = reg.split(' ', 1)[-1]
    appr, low = v['appr_manwon'] / 1e4, v['low_manwon'] / 1e4
    key = v['key']; no = key.split('[')[-1].rstrip(']')
    case = key.split('[')[0] + (f' [{no}]' if no != '1' else '')
    hh = f' <span class="hh">{v["households"]:,}세대</span>' if cat == '아파트' and v.get('households') else ''
    grade = (v.get('safety') or {}).get('grade', '보통')
    new = '<span class="new">New</span> ' if v.get('_new') else ''   # 어제 예측 파일에 없던 물건 (2026-11-05)
    L = [f'<div class="t">{new}{E(v.get("danji_name") or "")}{hh} · 전용 {v.get("area")}㎡ · 🛡 {grade}</div>',
         f'<div class="g s">{E(gu)} · {E(case)} · {E(v.get("court") or "")}</div>', '<b>📋 기본 정보</b>']
    bd = v.get('bidding_date') or ''
    L.append(f'매각기일 {md(bd)} · <span class="dday" data-d="{bd}"></span>' if bd else '매각기일 미정')
    cl = court_line(key, bd)
    if cl: L.append(cl)
    ut = unit_text(v)
    if ut: L.append(f'🏠 {E(ut)}')
    if cid: L.append(result_line(res))
    # 순서 (2026-11-05 사용자 지정): 매매 시세 → 감정가·최저가 → 유찰 → 가까운 역
    bs = base_sise(v)   # 모델 시세 (아파트 M, 오피스텔 리치고)
    if bs:
        L.append(f'🎯 매매 시세 <b>{bs:.2f}억</b>')
    L += kb_line(v, low)   # KB 시세 (2026-11-17)
    if v.get('within3_pct') is not None:   # 2026-11-15: 예측이 실제 ±3% 안에 들 확률, 상위 20% = 정밀 (acc_model.py)
        L.append(('<b>✅ 정밀</b> · ' if v.get('precise') else '') + f"📐 3% 안 확률 {v['within3_pct']}%"
                 + ('' if v.get('precise') else ' <span class="g">(정밀 기준 상위 20%)</span>'))
    L.append(f'💰 감정가 {appr:.2f}억 · 최저가 <b>{low:.2f}억</b>' + (f' (시세 대비 {low / bs * 100:.0f}%)' if bs else '')
             + f' · 보증금 {v["low_manwon"] * 0.1:,.0f}만')
    f = v.get('fail') or {}
    line = f"🔁 유찰 {v.get('fails') or 0}회"
    if f.get('prob_pct') is not None and not f.get('error'): line += f" · 유찰 확률(이번 회차) {f['prob_pct']}% · {f.get('level', '')}"
    L.append(line)
    stt = station_text(v)
    if stt:
        L.append(f"🚇 {stt}")
    s8 = v.get('station8'); s5 = v.get('station5')
    names = {x['name'] for x in (v.get('stations') or [])} | {(v.get('station') or {}).get('name')}
    if cat == '아파트' and s5 and s5['name'].removesuffix('역') not in names and s5['name'] not in names and s5['distance_m'] <= 920:
        L.append(f"🚇 5호선 {E(s5['name'])}역 도보 약 {s5['walk_min']}분 ({s5['distance_m']}m)")
    if cat == '아파트' and s8 and s8['name'].removesuffix('역') not in names and s8['name'] not in names and s8['distance_m'] <= 920:
        L.append(f"🚇 8호선 {E(s8['name'])}역 도보 약 {s8['walk_min']}분 ({s8['distance_m']}m)")
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
        body += f'<div class="sec"><a href="https://m.richgo.ai/auctionMobile/{E(v["auction_id"])}" target="_blank" rel="noopener">상세 보기 ↗</a></div>'
    idattr = f' id="{cid}"' if cid else ''
    return f'<div class="card"{idattr} data-d="{bd}" data-gu="{E(gu)}">{body}</div>'


def tracked_past(today, pred_dir, days=14):
    """추적했던 물건 = 기일 전 예측 파일에서 웹페이지에 표시됐던(keep) 물건, 기일이 최근 days일 안에 지난 것 (2026-11-08 사용자 요청).
    반환 {'키|기일': 기일 전 마지막 예측 항목}."""
    lo = (datetime.strptime(today, '%Y-%m-%d') - timedelta(days=days)).strftime('%Y-%m-%d')
    out, shown = {}, set()
    try:
        fs = sorted(f for f in os.listdir(pred_dir) if re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json', f))
    except Exception:
        return {}
    for fn in fs:
        if fn[:10] < (datetime.strptime(lo, '%Y-%m-%d') - timedelta(days=21)).strftime('%Y-%m-%d'): continue
        try:
            items = json.load(open(os.path.join(pred_dir, fn), encoding='utf-8'))['items']
        except Exception:
            continue
        for k, it in items.items():
            bd = it.get('bidding_date') or ''
            if not (lo <= bd < today) or fn[:10] > bd: continue
            rid = f'{k}|{bd}'
            it = dict(it, category=it.get('category') or '아파트')   # 초기 예측 파일은 아파트에 category 없음
            if keep(it): shown.add(rid)
            out[rid] = dict(it, pred_date=fn[:10])
    # 2026-11-17: 권리 판정 전 파일(10/31~11/1)에서 한 번 표시됐어도, 기일 전 마지막 예측이 숨김(지분매각 등)이면 뺀다
    def hidden(v):
        return (v.get('risk') or {}).get('decision') == 'hide' or (v.get('appr_vs_sise') is not None and v['appr_vs_sise'] < 0.6)
    return {rid: v for rid, v in out.items() if rid in shown and not hidden(v)}


def card_id(aid, bd):
    return f'p-{aid}-{bd}'


def results_all():
    try:
        return json.load(open(os.path.join(HERE, 'predictions', 'results.json'), encoding='utf-8'))
    except Exception:
        return None


def results_14d(today, RS=None, tracked=None):
    """predictions/results.json 최근 14일 (같은 물건은 매각 우선·최신 기일 하나). tracked 가 있으면 추적했던 물건만."""
    if RS is None: RS = results_all()
    if RS is None:
        return None
    R = RS.values()
    t = datetime.strptime(today, '%Y-%m-%d')
    lo = (t - timedelta(days=14)).strftime('%Y-%m-%d')
    best = {}
    for r in R:
        if not (lo <= r['bidding_date'] < today): continue
        if tracked is not None and f"{r['key']}|{r['bidding_date']}" not in tracked: continue
        r = dict(r); r['category'] = r.get('category') or '아파트'
        b = best.get(r['key'])
        if b is None or (r['status'] == '매각', r['bidding_date']) > (b['status'] == '매각', b['bidding_date']):
            best[r['key']] = r
    # 추적했는데 결과가 아직 없는 물건(기일 변경·결과 미수집)도 성적표에 '결과 미확인'으로 (2026-11-08: 기일 지남 칸과 건수 맞춤)
    for rid, v in (tracked or {}).items():
        k, bd = rid.rsplit('|', 1)
        if k in best or not (lo <= bd < today): continue
        p = (v.get('bid_by_prob_eok') or {}).get('50%')
        if not isinstance(p, (int, float)): continue
        best[k] = dict(key=k, bidding_date=bd, category=v.get('category') or '아파트', status='결과 미확인',
                       bid_by_prob_manwon={'50%': p * 1e4}, danji_name=v.get('danji_name'), area=v.get('area'),
                       auction_id=v.get('auction_id'), expected_bidders=None)
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


def pct_sub(x, s, t=None):
    """시세 대비 % — 아파트는 M 과 실거래(t) 두 기준을 함께 (2026-11-10 사용자 요청)."""
    if not (x and s): return ''
    if not t: return f'<br><span class="sub">({x / s * 100:.1f}%)</span>'
    return f'<br><span class="sub">M {x / s * 100:.1f}%<br>실 {x / t * 100:.1f}%</span>'


def scorecard(rows, cat, tracked=None):
    tracked = tracked or {}
    rows = sorted([r for r in rows if r['category'] == cat], key=lambda r: r['bidding_date'], reverse=True)
    if not rows: return '<p class="g">최근 14일 추적 물건 결과 없음</p>'
    sold = [r for r in rows if r.get('status') == '매각' and r.get('diff_pct') is not None]
    out = []
    if sold:
        err = sum(abs(r['diff_pct']) for r in sold) / len(sold)
        w5 = sum(1 for r in sold if abs(r['diff_pct']) <= 5)
        mid = sum(1 for r in sold if (r.get('band') or '') not in ('', '60% 초과', '최저가 단일') and not (r.get('band') or '').startswith('40% 미만'))
        out.append(f'<div class="g s">낙찰 {len(sold)}건 · 평균 오차 {err:.1f}% · ±5% 안 {w5}건 · 40~60% 구간 안 {mid}건</div>')
        mt = [(r['actual_manwon'], r['sise_manwon'], r['trade_manwon'], r['bid_by_prob_manwon']['50%']) for r in sold if r.get('sise_manwon') and r.get('trade_manwon')]
        if mt:   # 2026-11-10 사용자 요청: M 시세 vs 실거래 기준 비교
            md_ = lambda xs: sorted(xs)[len(xs) // 2] if len(xs) % 2 else sum(sorted(xs)[len(xs) // 2 - 1:len(xs) // 2 + 1]) / 2
            out.append(f'<div class="g s">시세 대비 중앙값({len(mt)}건) · 실제 낙찰가 M {md_([a / s for a, s, t, p in mt]) * 100:.1f}% / 실거래 {md_([a / t for a, s, t, p in mt]) * 100:.1f}%'
                       f' · 예상(50%) M {md_([p / s for a, s, t, p in mt]) * 100:.1f}% / 실거래 {md_([p / t for a, s, t, p in mt]) * 100:.1f}%</div>')
        mk = [(r['actual_manwon'], r['kb_manwon'], r['bid_by_prob_manwon']['50%']) for r in sold if r.get('kb_manwon')]
        if mk:   # 2026-11-17 사용자 요청: KB 시세 기준도
            md_ = lambda xs: sorted(xs)[len(xs) // 2] if len(xs) % 2 else sum(sorted(xs)[len(xs) // 2 - 1:len(xs) // 2 + 1]) / 2
            out.append(f'<div class="g s">KB 시세 대비 중앙값({len(mk)}건) · 실제 낙찰가 {md_([a / k for a, k, p in mk]) * 100:.1f}% · 예상(50%) {md_([p / k for a, k, p in mk]) * 100:.1f}%</div>')
    # 2026-11-11 사용자 요청: 차이 두 값이 표를 넘침 + 가독성 → 물건마다 두 행(종합 / 인원 줄)으로 나누고, 물건·실제·인원 칸은 두 행을 합침
    t = ['<table class="sc"><col style="width:25%"><col style="width:12%"><col style="width:20%"><col style="width:15%"><col style="width:17%"><col style="width:11%">',
         '<tr><th>물건</th><th>기준</th><th>예측<br><span class="sub">50%</span></th><th>차이</th><th>실제<br><span class="sub">낙찰</span></th><th>인원<br><span class="sub">실제</span></th></tr>']

    def pc(x, s, tr, kb=None):   # 시세 대비 % (M · 실 · KB 각 한 줄, KB 는 2026-11-17)
        if not (x and s): return ''
        return f'<div class="sub">M {x / s * 100:.1f}%' + (f'<br>실 {x / tr * 100:.1f}%' if tr else '') + (f'<br>KB {x / kb * 100:.1f}%' if kb else '') + '</div>'

    def dcell(v):
        if v is None: return '<span class="sub">-</span>'
        c = '#FF6B6B' if v > 0 else '#6FA8FF'
        return f'<b style="color:{c}">{v:+.1f}%</b>'

    for i, r in enumerate(rows):
        rid = f"{r['key']}|{r['bidding_date']}"
        it = tracked.get(rid) or {}
        sise = r.get('sise_manwon') or (base_sise(it) or 0) * 1e4 or None
        tr_ = r.get('trade_manwon') if r['category'] == '아파트' else None
        kb_ = r.get('kb_manwon') or (it.get('kb') or {}).get('manwon')
        p50m = r['bid_by_prob_manwon']['50%']; p50 = p50m / 1e4
        star = '<sup>*</sup>' if r.get('rescored') else ''
        d = datetime.strptime(r['bidding_date'], '%Y-%m-%d')
        sold_ = r.get('status') == '매각' and r.get('actual_manwon')
        b = r.get('bidders'); x = r.get('expected_bidders')
        bb = ((r.get('rescored_pred') or {}).get('by_bidders') or it.get('by_bidders') or {})
        lab = exp_row(r['category'], x if x is not None else bb.get('expected_bidders'))
        e50 = ((bb.get('bid_by_prob_eok') or {}).get(lab) or {}).get('50%') if lab else None
        d1 = (r.get('diff_pct') or 0) if sold_ else None
        lines = [('종합', f'<b>{p50:.2f}</b>{star}' + pc(p50m, sise, tr_, kb_), dcell(d1))]
        if e50:
            d2 = (r['actual_manwon'] / (e50 * 1e4) - 1) * 100 if sold_ else None
            lines.append((E(lab), f'<b>{e50:.2f}</b>' + pc(e50 * 1e4, sise, tr_, kb_), dcell(d2)))
        act = (f'<b class="big">{r["actual_manwon"] / 1e4:.2f}</b>' + pc(r['actual_manwon'], sise, tr_, kb_)) if sold_ else f'<span class="sub">{E(r.get("status") or "결과대기")}</span>'
        if r.get('source') == '법원': act += '<div class="sub">(법원 확인)</div>'
        ppl = f'<b class="big">{b if b is not None else "-"}</b><div class="sub">예상<br>{f"{x}명" if x is not None else "-"}</div>'
        aid = r.get('auction_id') or it.get('auction_id')
        nm = E(r.get('danji_name') or '')
        nm = f'<a href="#{card_id(aid, r["bidding_date"])}">{nm}</a>' if aid and it else nm
        name = f'{nm}<div class="sub">{E(r["key"].replace("[1]", ""))}<br>{r.get("area")}㎡<br><b>{d.month}/{d.day}</b></div>'
        n = len(lines); z = ' z' if i % 2 else ''
        for j, (tg, pv, dv) in enumerate(lines):
            first = j == 0
            lead = (f'<td class="nm" rowspan="{n}">{name}</td>' if first else '')
            tail = (f'<td rowspan="{n}">{act}</td><td rowspan="{n}">{ppl}</td>' if first else '')
            cls = ('top' if first else 'mid') + (' end' if j == n - 1 else '') + z
            t.append(f'<tr class="{cls}">{lead}<td><span class="tg">{tg}</span></td><td>{pv}</td><td>{dv}</td>{tail}</tr>')
    t.append('</table>')
    out.append(''.join(t))
    out.append('<div class="g s">추적했던 물건(기일 전 웹페이지에 표시된 물건)만 · 물건 이름을 누르면 위 \'기일 지남\' 카드로 이동 · '
               '기준: 종합 = 인원 가정 없는 앙상블 낙찰확률 50% 가격, 8명 등 = 카드 ▶ 예상 인원 줄의 50% 가격 · 차이 = 실제 ÷ 예측 − 1 (빨강 = 실제가 더 높음, 파랑 = 더 낮음) · '
               'M = 모델 시세 대비, 실 = 예측 당시 층 보정 실거래 12개월 가중 평균 대비(오피스텔은 리치고), '
               'KB = KB부동산 매매 일반가 대비(예측 당시 값, 없으면 기일 달 KB 월별 시세) · '
               '<sup>*</sup> = 11/5 이전(리치고 시세) 예측을 11/8 현재 M 시세 모델로 다시 계산한 값(사후 계산)</div>')
    return ''.join(out)


CSS = """
:root{--bg:#ffffff;--fg:#1d1d1f;--mut:#777;--bd:#888}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#ececec;--mut:#9a9a9a;--bd:#666}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif;font-size:14px;line-height:1.55}
.wrap{max-width:600px;margin:0 auto;padding:12px 16px 40px}
h1{font-size:19px;margin:6px 0 2px} .meta{color:var(--mut);font-size:12px;margin-bottom:10px}
.nav{position:sticky;top:0;background:var(--bg);padding:8px 0 6px;z-index:2;border-bottom:1px solid var(--bd)}
.nav a{color:var(--fg);text-decoration:none;white-space:nowrap}
.nav b{font-weight:600;opacity:.75;font-size:12px}
.tabs{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tab{flex:1 0 auto;white-space:nowrap;text-align:center;border:1px solid var(--bd);border-radius:10px;padding:7px 4px;font-size:14px;font-weight:bold}
.tab.on{background:#1a73e8;border-color:#1a73e8;color:#fff!important}
.tab.on b{opacity:.9}
.subs{display:flex;gap:6px;overflow-x:auto;padding-top:7px;scrollbar-width:none}
.subs::-webkit-scrollbar{display:none}
.sub-t{border:1px solid var(--bd);border-radius:16px;padding:4px 11px;font-size:13px}
.sub-t.on{border-color:#1a73e8;color:#1a73e8!important;font-weight:bold}
.js .subs{display:none} .js .subs.on{display:flex}
.js .pane,.js .mainh,.js .pane-note{display:none} .js .pane.on,.js .pane-note.on{display:block}
.dchips{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;margin:0 0 10px;padding:7px 0;
 position:sticky;top:var(--navh,88px);z-index:1;background:var(--bg);border-bottom:1px solid var(--bd)}
.dchips::-webkit-scrollbar{display:none}
.dchips a{border:1px dashed var(--bd);border-radius:12px;padding:2px 9px;font-size:12px;color:var(--fg);text-decoration:none;white-space:nowrap}
.dchips a.on{border-style:solid;border-color:#1a73e8;color:#1a73e8;font-weight:bold}
.dh{font-size:13px;color:var(--mut);margin:14px 0 6px;scroll-margin-top:calc(var(--stk,130px) + 6px);border-left:3px solid #1a73e8;padding-left:7px}
.pane{scroll-margin-top:110px}
h2{font-size:19px;margin:22px 0 6px;padding-bottom:4px;border-bottom:2px solid var(--bd)}
h3{font-size:15px;margin:16px 0 8px}
.card{border:1px solid var(--bd);border-radius:10px;padding:12px 14px;margin-bottom:12px;overflow:hidden;scroll-margin-top:calc(var(--stk,130px) + 6px)}
.card:target{outline:3px solid #1a73e8}
.t{font-weight:bold;font-size:15px} .hh{font-weight:normal;color:var(--mut);font-size:12px}
.g{color:var(--mut)} .s{font-size:12px} .n{font-weight:normal;font-size:13px}
.warn{color:#d93025;font-size:12px}
.sec{margin-top:10px}
table{border-collapse:collapse;width:100%;max-width:560px;table-layout:fixed;margin:8px 0;font-size:14px;text-align:center;background:#000;color:#fff;border:2px solid #fff}
th,td{background:#000;color:#fff;border:1px solid #fff;padding:9px 2px}
td.lab,th:first-child{white-space:nowrap} td.hi{font-weight:bold;background:#333} td.good,td.hi.good{background:rgba(46,204,113,0.35)}
a{color:#1a73e8}
.sub{font-size:11px;color:#BBBBBB}
table.sc{font-size:12.5px;border:1px solid #555;line-height:1.35}
table.sc th{background:#1f2a36;border:0;border-bottom:2px solid #6FA8FF;padding:8px 3px;font-size:12.5px;white-space:normal}
table.sc td{border:0;padding:7px 3px;vertical-align:middle;overflow-wrap:anywhere}
table.sc tr.end td,table.sc td[rowspan]{border-bottom:1px solid #444}
table.sc tr.mid td{border-top:1px dashed #333}
table.sc tr.z td{background:#161616}
table.sc td.nm{text-align:left;padding-left:6px}
table.sc td.nm a{font-weight:bold;color:#8AB4F8;text-decoration:none}
table.sc .tg{display:inline-block;font-size:10.5px;color:#ddd;background:#2b2b2b;border-radius:4px;padding:1px 5px;white-space:nowrap}
table.sc .big{font-size:14.5px}
.foot{color:var(--mut);font-size:12px;margin-top:24px;line-height:1.7}
.new{color:#d93025;font-size:12px;font-weight:bold}
.fbar{display:flex;gap:8px;align-items:center;padding:10px 0 4px}
.ctag{font-size:11px;color:var(--mut);margin-bottom:2px}
.fbar button,.fact button{border:1px solid var(--bd);background:var(--bg);color:var(--fg);border-radius:16px;padding:4px 11px;font-size:13px;cursor:pointer}
.fbar button.on{border-color:#1a73e8;background:#1a73e8;color:#fff}
#fsum{flex:1;min-width:0;font-weight:bold}
#fpanel{border:1px solid var(--bd);border-radius:10px;padding:8px 10px;margin:4px 0 10px}
.fl{font-size:12px;font-weight:bold;margin:6px 0 4px}
.fchips{display:flex;flex-wrap:wrap;gap:6px}
.fchips button{border:1px dashed var(--bd);background:var(--bg);color:var(--fg);border-radius:14px;padding:3px 10px;font-size:13px;cursor:pointer}
.fchips button.on{border-style:solid;border-color:#1a73e8;color:#1a73e8;font-weight:bold}
.fchips button i{font-style:normal;opacity:.6;font-size:11px;margin-left:3px}
.fact{display:flex;gap:8px;margin-top:10px} #fok{border-color:#1a73e8;background:#1a73e8;color:#fff}
.fempty{color:var(--mut);padding:10px 0}
.cal{margin:4px 0 16px}
.cal-hd{display:flex;align-items:center;justify-content:center;gap:18px;margin:6px 0 10px}
.cal-hd b{font-size:22px;letter-spacing:1px}
.cal-hd button{width:32px;height:32px;border-radius:50%;border:0;background:#1a73e8;color:#fff;font-size:18px;cursor:pointer}
.cal-hd button:disabled{background:#c9c9c9;opacity:.5;cursor:default}
.cal-past{display:block;width:100%;border:1px dashed var(--bd);background:var(--bg);color:var(--mut);border-radius:8px;padding:6px;font-size:13px;margin-bottom:8px;cursor:pointer}
.cal-wk{display:grid;grid-template-columns:repeat(5,1fr);text-align:center;background:rgba(128,128,128,.12);padding:9px 0;font-size:14px;color:var(--mut)}
.cal-row{display:grid;grid-template-columns:repeat(5,1fr);text-align:center}
.cal-d{padding:10px 0 8px;cursor:pointer;border:1px solid transparent;border-bottom:0;border-radius:6px 6px 0 0;user-select:none}
.cal-d .dn{font-size:19px}
.cal-d .dc{font-size:12.5px;color:var(--mut);margin-top:2px}
.cal-d.has .dc b{color:#1a73e8}
.cal-d.past{opacity:.45}
.cal-d.empty{cursor:default}
.cal-d.today .dn{color:#1a73e8;font-weight:bold}
.cal-d.sel{border-color:var(--bd);background:var(--bg);position:relative;top:1px;z-index:1;opacity:1}
.cal-d.sel .dn,.cal-d.sel .dc{font-weight:bold;color:var(--fg)}
.cal-open{border:1px solid var(--bd);border-radius:0 0 8px 8px;padding:12px 10px 4px;margin-bottom:8px}
.cal-open h4{margin:0 0 6px;font-size:15px}
.cal-sum{display:flex;align-items:center;gap:8px;padding:10px 2px;border-top:1px solid rgba(128,128,128,.25);cursor:pointer;font-size:15px}
.cal-open h4+.cal-sum{border-top:0}
.cal-sum .ic{font-size:16px}
.cal-sum .nm{flex:1;min-width:0;overflow-wrap:anywhere;line-height:1.35}
.cal-sum .sb{display:block;color:var(--mut);font-size:12px;font-weight:normal}
.cal-sum .pr{font-size:13px;white-space:nowrap;text-align:right}
.cal-sum .pr small{display:block;color:var(--mut);font-size:11.5px}
.cal-sum .ar{color:var(--mut);transition:transform .15s}
.cal-sum.on .ar{transform:rotate(180deg)}
.cal-sum.on .nm{font-weight:bold}
.cal-sum .nw{font-style:normal;background:#e8453c;color:#fff;font-size:10px;border-radius:4px;padding:1px 4px;margin-right:5px;vertical-align:2px}
.cal-open .card{margin:0 0 12px}
"""

JS = """
(function(){var t=new Date();var k=new Date(t.getTime()+9*3600e3);var today=Date.UTC(k.getUTCFullYear(),k.getUTCMonth(),k.getUTCDate());
document.querySelectorAll('.dday').forEach(function(e){var p=e.getAttribute('data-d').split('-');var d=Date.UTC(+p[0],+p[1]-1,+p[2]);
var n=Math.round((d-today)/864e5);e.textContent=n>0?('D-'+n):(n==0?'D-day':'기일 지남');});})();
(function(){ /* 탭: 아파트·오피스텔·성적표 → 하위 칸 (2026-11-12) */
var D=document,R=D.documentElement;R.classList.add('js');
function $$(s){return Array.prototype.slice.call(D.querySelectorAll(s));}
function save(k,v){try{localStorage.setItem(k,v);}catch(e){}}
function load(k){try{return localStorage.getItem(k);}catch(e){return null;}}
function showPane(pid,noSave){var p=D.getElementById(pid);if(!p)return;var m=p.getAttribute('data-main');
 $$('.tab').forEach(function(t){t.classList.toggle('on',t.getAttribute('data-main')==m);});
 $$('.subs').forEach(function(s){s.classList.toggle('on',s.getAttribute('data-main')==m);});
 $$('.pane').forEach(function(x){x.classList.toggle('on',x===p);});
 $$('.pane-note').forEach(function(x){x.classList.toggle('on',x.getAttribute('data-main')==m);});
 $$('.sub-t').forEach(function(s){s.classList.toggle('on',s.getAttribute('data-pane')==pid);});
 if(!noSave){save('pane-'+m,pid);save('main',m);}setH();}
/* 날짜 칸 고정 (2026-11-12): 메뉴 높이 → --navh, 메뉴+날짜칸 → --stk, 지금 보는 날짜 칩 강조 */
function setH(){var n=D.querySelector('.nav');var nh=n?n.offsetHeight:0;R.style.setProperty('--navh',nh+'px');
 var c=D.querySelector('.pane.on .dchips');R.style.setProperty('--stk',(nh+(c?c.offsetHeight:0))+'px');spy();}
function spy(){var c=D.querySelector('.pane.on .dchips');if(!c)return;var lim=c.getBoundingClientRect().bottom+12,cur=null;
 $$('.pane.on .dh').forEach(function(h){if(h.getBoundingClientRect().top<=lim)cur=h.id;});
 c.querySelectorAll('a').forEach(function(a){var on=a.getAttribute('href')=='#'+cur;if(on!=a.classList.contains('on')){a.classList.toggle('on',on);
  if(on&&a.scrollIntoView&&c.scrollWidth>c.clientWidth)c.scrollLeft=a.offsetLeft-c.clientWidth/2+a.offsetWidth/2;}});}
var tk=0;window.addEventListener('scroll',function(){if(!tk){tk=1;requestAnimationFrame(function(){tk=0;spy();});}},{passive:true});
window.addEventListener('resize',setH);
function firstPane(m){var k=load('pane-'+m);if(k&&D.getElementById(k))return k;var p=D.querySelector('.pane[id][data-main="'+m+'"]');return p&&p.id;}
function go(h,scroll){if(!h)return false;var el=D.getElementById(h);if(!el)return false;
 if(el.classList.contains('tab')||el.classList.contains('mainh')){var pid=firstPane(el.getAttribute('data-main')||h);if(pid)showPane(pid);window.scrollTo(0,0);return true;}
 var p=el.closest?el.closest('.pane[id]'):null;if(!p)return false;showPane(p.id);
 if(scroll){if(el===p)window.scrollTo(0,0);else setTimeout(function(){el.scrollIntoView();},0);}return true;}
$$('.tab').forEach(function(t){t.addEventListener('click',function(e){e.preventDefault();var pid=firstPane(t.getAttribute('data-main'));if(pid){showPane(pid);history.replaceState(null,'','#'+pid);}window.scrollTo(0,0);});});
$$('.sub-t').forEach(function(t){t.addEventListener('click',function(e){e.preventDefault();var pid=t.getAttribute('data-pane');showPane(pid);history.replaceState(null,'','#'+pid);window.scrollTo(0,0);});});
window.addEventListener('hashchange',function(){go(location.hash.slice(1),true);});
/* 캘린더 탭 (2026-11-22, 예전 '내 조건'): 고른 종류·구의 물건을 매각기일 달력으로 → 날짜 누르면 한 줄 요약 → 요약 누르면 카드 */
var CATS=[['apt','🏢 아파트'],['ot','🏬 오피스텔'],['shop','🏪 상가'],['bldg','🏙 건물']];
var TD=new Date(Date.now()+9*3600e3).toISOString().slice(0,10);
function p2(n){return ('0'+n).slice(-2);}
var F={cats:['apt','ot'],gus:[]};try{var s=JSON.parse(load('myf')||'null');if(s&&s.cats)F=s;}catch(e){}
var SRC=[];CATS.forEach(function(c){$$('#'+c[0]+'-soon .card,#'+c[0]+'-later .card,#past-'+c[0]+' .card').forEach(function(e){SRC.push({c:c[0],lab:c[1],e:e,d:e.getAttribute('data-d')||'',g:e.getAttribute('data-gu')||''});});});
var gcnt={};SRC.forEach(function(x){if(x.g&&x.d>=TD)gcnt[x.g]=(gcnt[x.g]||0)+1;});F.gus.forEach(function(g){if(!(g in gcnt))gcnt[g]=0;});var GUS=Object.keys(gcnt).sort();var tmp=null;
function chip(box,val,lab,n,sel){var b=D.createElement('button');b.type='button';b.innerHTML=lab+(n!=null?'<i>'+n+'</i>':'');
 b.classList.toggle('on',sel.indexOf(val)>=0);b.onclick=function(){var i=sel.indexOf(val);if(i>=0)sel.splice(i,1);else sel.push(val);b.classList.toggle('on',i<0);};box.appendChild(b);}
function openP(){tmp={cats:F.cats.slice(),gus:F.gus.slice()};var a=D.getElementById('fcat'),b=D.getElementById('fgu');a.innerHTML='';b.innerHTML='';
 CATS.forEach(function(c){chip(a,c[0],c[1],SRC.filter(function(x){return x.c==c[0]&&x.d>=TD;}).length,tmp.cats);});
 GUS.forEach(function(g){chip(b,g,g,gcnt[g],tmp.gus);});D.getElementById('fpanel').hidden=false;setH();}
function dl(d){var p=d.split('-');if(p.length<3)return '미정';var w='일월화수목금토'[new Date(Date.UTC(+p[0],+p[1]-1,+p[2])).getUTCDay()];return (+p[1])+'/'+(+p[2])+'('+w+')';}
var BY={},YM=null,SEL=null,SHOWPAST=false;
function esc(s){return s.replace(/[&<>"]/g,function(x){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[x];});}
function sumOf(x){var c=x.e,t=c.querySelector('.t'),tx=c.textContent,nm='',tags=[];
 if(t){var q=t.cloneNode(true);q.querySelectorAll('.hh,.new').forEach(function(e){e.remove();});nm=q.textContent.split('·')[0].trim();}
 var sz=t&&(t.textContent.match(/전용 ([0-9.]+)㎡/)||t.textContent.match(/([0-9.]+)㎡/));
 if(tx.indexOf('✅ 정밀')>=0)tags.push('✅정밀');if(t&&t.textContent.indexOf('🛡 안전')>=0)tags.push('🛡안전');
 var sub=[x.g].concat(sz?[Math.round(+sz[1]/3.3058)+'평']:[]).concat(tags).filter(Boolean).join(' · ');
 var lo=tx.match(/최저가? ([0-9.]+억)/),pc=tx.match(/최저가 [0-9.]+억 [(]시세 대비 ([0-9]+)%/),pa=tx.match(/최저 [0-9.]+억 [(]([0-9]+)%[)]/);
 var rs=tx.match(/📊 결과: 매각 ([0-9.]+억)/),rd=tx.match(/예상[(]50%[)] 대비 ([-+][0-9.]+%)/),rx=tx.match(/📊 결과: *([가-힣]+(?: 전)?)/),R;
 if(rs)R='<b>매각 '+rs[1]+'</b>'+(rd?'<small>예상 대비 '+rd[1]+'</small>':'');
 else if(rx)R='<b>'+esc(rx[1])+'</b><small>결과</small>';
 else R=(lo?'최저 <b>'+lo[1]+'</b>':'')+(pc?'<small>시세 '+pc[1]+'%</small>':pa?'<small>감정 '+pa[1]+'%</small>':'');
 return '<span class="ic">'+x.lab.split(' ')[0]+'</span><span class="nm">'+(c.querySelector('.new')?'<i class="nw">N</i>':'')+esc(nm)
  +'<span class="sb">'+esc(sub)+'</span></span><span class="pr">'+R+'</span><span class="ar">▾</span>';}
function cal(){var box=D.getElementById('cal');box.innerHTML='';var y=YM[0],m=YM[1],cur=y+'-'+p2(m+1),tm=TD.slice(0,7),ks=Object.keys(BY).sort();
 var MS=ks.map(function(k){return k.slice(0,7);}).concat([tm]).filter(function(v,i,a){return a.indexOf(v)==i;}).sort(),mi=MS.indexOf(cur);
 function goM(s){if(s){YM=[+s.slice(0,4),+s.slice(5,7)-1];cal();setH();}}
 var hd=D.createElement('div');hd.className='cal-hd';
 var pv=D.createElement('button');pv.type='button';pv.textContent='‹';pv.disabled=mi<=0;pv.onclick=function(){goM(MS[mi-1]);};
 var nx=D.createElement('button');nx.type='button';nx.textContent='›';nx.disabled=mi<0||mi>=MS.length-1;nx.onclick=function(){goM(MS[mi+1]);};
 var tt=D.createElement('b');tt.textContent=y+'.'+(m+1);hd.appendChild(pv);hd.appendChild(tt);hd.appendChild(nx);box.appendChild(hd);
 /* 주말 기일 물건이 있는 달만 토·일 칸도 (보통 법원 경매는 평일) */
 var wk=[],w=null,last=new Date(Date.UTC(y,m+1,0)).getUTCDate(),C7=ks.some(function(k){var g=new Date(k+'T00:00:00Z').getUTCDay();return k.slice(0,7)==cur&&(g==0||g==6)&&(SHOWPAST||cur!=tm||k>=TD);});
 for(var d=1;d<=last;d++){var ix=(new Date(Date.UTC(y,m,d)).getUTCDay()+6)%7;if(!C7&&ix>4)continue;
  if(!w){w=[];wk.push(w);for(var i=0;i<ix;i++)w.push(null);}else if(ix==0){w=[];wk.push(w);}w.push(y+'-'+p2(m+1)+'-'+p2(d));}
 var pastW=wk.filter(function(w){return !w.some(function(k){if(!k||k<TD)return false;var g=new Date(k+'T00:00:00Z').getUTCDay();return (g>0&&g<6)||BY[k];});}),fold=cur==tm&&pastW.length>0;
 if(fold){var pn=0;pastW.forEach(function(w){w.forEach(function(k){if(k&&BY[k])pn+=BY[k].length;});});
  var pb=D.createElement('button');pb.type='button';pb.className='cal-past';pb.textContent=(SHOWPAST?'▾ 지난 주 접기':'▸ 지난 주 보기')+(pn?' · 결과 '+pn+'건':'');
  pb.onclick=function(){SHOWPAST=!SHOWPAST;cal();setH();};box.appendChild(pb);}
 var GT='repeat('+(C7?7:5)+',1fr)';
 var wh=D.createElement('div');wh.className='cal-wk';wh.style.gridTemplateColumns=GT;wh.innerHTML='<div>월</div><div>화</div><div>수</div><div>목</div><div>금</div>'+(C7?'<div>토</div><div>일</div>':'');box.appendChild(wh);
 wk.forEach(function(w){if(fold&&!SHOWPAST&&pastW.indexOf(w)>=0)return;var row=D.createElement('div');row.className='cal-row';row.style.gridTemplateColumns=GT;box.appendChild(row);var hit=false;
  w.forEach(function(k){var c=D.createElement('div');if(!k){c.className='cal-d empty';row.appendChild(c);return;}
   var n=(BY[k]||[]).length;c.className='cal-d'+(n?' has':'')+(k<TD?' past':'')+(k==TD?' today':'')+(k==SEL?' sel':'');
   c.innerHTML='<div class="dn">'+k.slice(8)+'</div><div class="dc">('+(n?'<b>'+n+'</b>':'0')+'건)</div>';
   c.onclick=function(){SEL=k;cal();setH();};if(k==SEL)hit=true;row.appendChild(c);});
  if(hit)box.appendChild(openDay());});}
function openDay(){var o=D.createElement('div');o.className='cal-open';var xs=BY[SEL]||[];
 var h=D.createElement('h4');h.textContent=dl(SEL)+' · '+xs.length+'건'+(SEL<TD?' · 지난 기일':'');o.appendChild(h);
 if(!xs.length){var p=D.createElement('div');p.className='fempty';p.textContent='이 날은 조건에 맞는 경매가 없어요';o.appendChild(p);}
 xs.forEach(function(x){var r=D.createElement('div');r.className='cal-sum';r.innerHTML=sumOf(x);var k=x.e.cloneNode(true);k.removeAttribute('id');k.hidden=true;
  r.onclick=function(){k.hidden=!k.hidden;r.classList.toggle('on',!k.hidden);setH();};o.appendChild(r);o.appendChild(k);});return o;}
function build(){var xs=SRC.filter(function(x){return (!F.cats.length||F.cats.indexOf(x.c)>=0)&&(!F.gus.length||F.gus.indexOf(x.g)>=0);});
 xs.sort(function(a,b){return a.d<b.d?-1:a.d>b.d?1:0;});BY={};xs.forEach(function(x){if(x.d)(BY[x.d]=BY[x.d]||[]).push(x);});
 if(!SEL||!BY[SEL]){var up=Object.keys(BY).filter(function(d){return d>=TD;}).sort();SEL=BY[TD]?TD:(up[0]||TD);}
 YM=[+SEL.slice(0,4),+SEL.slice(5,7)-1];cal();
 xs=xs.filter(function(x){return x.d>=TD;});
 var nm=CATS.filter(function(c){return F.cats.indexOf(c[0])>=0;}).map(function(c){return c[1].split(' ')[1];});
 var gs=F.gus.length?(F.gus.length>3?F.gus.slice(0,3).join('·')+' 외 '+(F.gus.length-3)+'곳':F.gus.join('·')):'모든 지역';
 D.getElementById('fsum').textContent=(nm.length?nm.join('·'):'모든 종류')+' · '+gs+' · 다가오는 '+xs.length+'건';
 var tb=D.querySelector('.tab[data-main="my"]');if(tb){var b=tb.querySelector('b');if(!b){b=D.createElement('b');tb.appendChild(D.createTextNode(' '));tb.appendChild(b);}b.textContent=xs.length;}
 save('myf',JSON.stringify(F));setH();}
D.getElementById('fbtn').onclick=function(){var p=D.getElementById('fpanel');if(!p.hidden){p.hidden=true;setH();}else openP();};
D.getElementById('fcancel').onclick=function(){D.getElementById('fpanel').hidden=true;setH();};
D.getElementById('fok').onclick=function(){F.cats=tmp.cats;F.gus=tmp.gus;D.getElementById('fpanel').hidden=true;build();window.scrollTo(0,0);};
D.getElementById('gclr').onclick=function(e){e.preventDefault();tmp.gus.length=0;$$('#fgu button').forEach(function(b){b.classList.remove('on');});};
build();
/* 2026-11-22: 첫 화면은 항상 캘린더 (주소에 #이 있으면 그 칸) */
if(!go(location.hash.slice(1),true))showPane('my-list',true);
})();
"""


# 빌라 탭은 2026-11-17 사용자 요청으로 뺌
def _other_cond(cat, base):
    """2026-11-18: 지역·최저가 범위는 search_regions.json (경매 지역 GUI)."""
    import search_cfg
    g = search_cfg.gus(cat)
    where = '서울' if len(g) >= 25 else '서울 ' + '·'.join(x.removesuffix('구') for x in g)
    return ' · '.join(x for x in (where, base, search_cfg.price_text(cat)) if x)


OTHER_CATS = (('상가', '🏪 상가', 'shop', _other_cond('상가', '구분상가 1칸 · 역 도보 15분')),
              ('건물', '🏙 건물', 'bldg', _other_cond('건물', '꼬마빌딩·상가주택·다가구 · 역 도보 15분')))


def load_others(pred_dir):
    """other_items.py 결과 (빌라·상가·건물, 2026-11-16). 없으면 None."""
    try:
        return json.load(open(os.path.join(pred_dir, 'others.json'), encoding='utf-8'))
    except Exception:
        return None


def other_card(v):
    """빌라·상가·건물 카드 — 예측 없이 사실만 (2026-11-16)."""
    addr = re.sub(r'^서울특별시\s+\S+구\s+', '', v.get('address') or '').strip()
    bd = v.get('bidding_date') or ''
    appr, low = (v.get('appr_manwon') or 0) / 1e4, (v.get('low_manwon') or 0) / 1e4
    head = ' · '.join(x for x in [f"{v['area']:.1f}㎡" if v.get('area') else '', (v.get('region') or '').replace('서울 ', ''), v['key'].replace('[1]', '')] if x)
    L = [f'<div class="t">{E(addr)} <span class="hh">{E(head)}</span></div>',
         f'<div>📅 {day_label(bd)} <span class="dday" data-d="{E(bd)}"></span> · 유찰 {v.get("fails") or 0}회'
         + (f' <span class="g s">· {E(v["court"])}</span>' if v.get('court') else '') + '</div>',
         f'<div>💰 감정 {appr:.2f}억 → 최저 <b>{low:.2f}억</b> <span class="g">({low / appr * 100:.0f}%)</span></div>' if appr else '']
    sz = []
    if v['category'] == '건물' and v.get('land_area'):
        sz.append(f"토지 {v['land_area']:.0f}㎡({v['land_area'] / 3.3058:.0f}평)")
    if v.get('area'):
        sz.append(f"건물 {v['area']:.1f}㎡({v['area'] / 3.3058:.1f}평)")
    if v.get('construct_year'):
        sz.append(f"{v['construct_year']}년")
    td = [t for t in (v.get('type_details') or []) if t not in ('대지', '도로')]
    if td:
        sz.append('·'.join(td))
    if sz:
        L.append(f'<div class="g s">📐 {E(" · ".join(sz))}</div>')
    st = station_text(v)
    if st:
        L.append(f'<div>🚇 {st}</div>')
    r = v.get('rights') or {}
    L.append('<div>🛡 등기 기준 인수 권리·대항력 임차인 없음'
             + (f' <span class="g s">(말소기준 {E(r.get("base_right") or "")} {E(r.get("base_date") or "")})</span>' if r.get('base_right') else '') + '</div>')
    if v.get('traffic'):
        L.append(f'<div class="g s">🚌 감정평가서 교통: {E(v["traffic"][:120])}</div>')
    L.append(f'<div class="s"><a href="https://m.richgo.ai/auctionMobile/{E(v.get("auction_id") or "")}">상세 보기 →</a></div>')
    gu = (v.get('region') or '').split(' ', 1)[-1]
    return f'<div class="card" data-d="{E(bd)}" data-gu="{E(gu)}">' + ''.join(x for x in L if x) + '</div>'


def prev_keys(day, pred_dir):
    """이 예측 날짜 이전 가장 최근 예측 파일의 물건 키 (New 판정, 메일과 같은 기준). 없으면 None."""
    try:
        fs = sorted(f for f in os.listdir(pred_dir) if re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json', f) and f[:10] < day)
        return set(json.load(open(os.path.join(pred_dir, fs[-1])))['items']) if fs else None
    except Exception:
        return None


def build(src, dst):
    d = json.load(open(src))
    COURT.clear(); COURT.update(load_court())
    VIEWS.clear(); VIEWS.update(load_views())
    now = datetime.now(KST); today = now.strftime('%Y-%m-%d')
    items = [v for v in d['items'].values() if keep(v)]
    pk = prev_keys(d.get('date') or today, os.path.dirname(src))
    for v in items: v['_new'] = pk is not None and v['key'] not in pk
    soon = (now + timedelta(days=7)).strftime('%Y-%m-%d')
    # 기일 지난 추적 물건 2주 (2026-11-08 사용자 요청: 성적표 물건을 기일 지남 칸에서 2주 동안 관리)
    RS = results_all() or {}
    tracked = tracked_past(today, os.path.dirname(src))
    for v in items:
        bd = v.get('bidding_date') or ''
        if bd and bd < today: tracked.setdefault(f"{v['key']}|{bd}", v)
    for rid, v in list(tracked.items()):
        rp = (RS.get(rid) or {}).get('rescored_pred')
        if rp: tracked[rid] = dict(v, **rp)   # M 시세로 다시 계산한 예측으로 카드 표시
    # 기일 변경으로 같은 물건이 여러 기일로 잡히면 하나만 (매각 결과 우선 → 최신 기일) — 성적표와 같은 기준 (2026-11-08)
    one = {}
    for rid, v in tracked.items():
        k, bd = rid.rsplit('|', 1)
        s = ((RS.get(rid) or {}).get('status') == '매각', rid in RS, bd)
        if k not in one or s > one[k][0]: one[k] = (s, rid)
    tracked = {rid: tracked[rid] for _, rid in one.values()}
    # 2026-11-22: 리치고 기일이 비어 예측일(주말 포함)이 기일로 잘못 들어갔던 기록 → 주말 기일은 빼기 (법원 경매는 평일)
    tracked = {rid: v for rid, v in tracked.items() if datetime.strptime(rid.rsplit('|', 1)[1], '%Y-%m-%d').weekday() < 5}
    # 2026-11-12 사용자 요청: 아파트·오피스텔·성적표를 탭으로, 그 안을 7일 이내·그 이후·기일 지남 등으로 나누고 날짜별로 바로 이동
    parts, nav, total = [], [], {}
    subnav = {}   # main -> [(pane_id, label, n)]

    def pane(main, pid, label, n, inner, dates=None):
        subnav.setdefault(main, []).append((pid, label.split(' · ')[0].replace(' (참고)', ''), n))
        chips = ''
        if dates and len(dates) > 1:
            chips = '<div class="dchips">' + ''.join(f'<a href="#{pid}-{d}">{day_label(d)} <b>{c}</b></a>' for d, c in dates) + '</div>'
        parts.append(f'<section class="pane" id="{pid}" data-main="{main}"><h3>{label} ({n}건)</h3>{chips}{inner}</section>')

    def by_date(pid, rows, render):
        """같은 날짜끼리 묶어 날짜 제목(id={pid}-YYYY-MM-DD)을 달고 카드 출력 → (html, [(날짜, 건수)])."""
        out, dates, cur = [], [], None
        for x in rows:
            bd = (x[1] if isinstance(x, tuple) else x).get('bidding_date') or ''
            if bd != cur:
                cur = bd; dates.append([bd, 0])
                out.append(f'<h4 class="dh" id="{pid}-{bd}">{day_label(bd)}</h4>')
            dates[-1][1] += 1
            out.append(render(x))
        html = ''.join(out)
        for d, c in dates:
            html = html.replace(f'id="{pid}-{d}">{day_label(d)}</h4>', f'id="{pid}-{d}">{day_label(d)} · {c}건</h4>', 1)
        return html, dates

    for cat, title, anchor in (('아파트', '🏢 아파트', 'apt'), ('오피스텔', '🏬 오피스텔 (서울 · 역 도보 10분)', 'ot')):
        xs = sorted((v for v in items if v['category'] == cat), key=lambda v: (v.get('bidding_date') or '9999', v.get('danji_name') or ''))
        nt = [v for v in xs if v.get('no_trade_12m') is True]   # 1년 실거래 0건 → 따로 (2026-11-05 사용자 결정: 예측 오차 큼)
        xs = [v for v in xs if v.get('no_trade_12m') is not True]
        total[cat] = len(xs)
        nav.append((anchor, title.split(' (')[0], len(xs)))
        parts.append(f'<h2 class="mainh" id="{anchor}" data-main="{anchor}">{title} · {len(xs)}건</h2>')
        groups = (('soon', '🔔 7일 이내', [v for v in xs if today <= (v.get('bidding_date') or '') <= soon]),
                  ('later', '📅 그 이후', [v for v in xs if (v.get('bidding_date') or '9999') > soon]))
        for sid, lab, g in groups:
            if not g: continue
            html, dates = by_date(f'{anchor}-{sid}', g, lambda v: card(v, today))
            pane(anchor, f'{anchor}-{sid}', lab, len(g), html, dates)
        past = sorted(((rid, v) for rid, v in tracked.items() if (v.get('category') or '아파트') == cat),
                      key=lambda x: (x[1].get('bidding_date') or '', x[1].get('danji_name') or ''), reverse=True)
        if past:
            html, dates = by_date(f'past-{anchor}', past, lambda x: card(x[1], today, cid=card_id(x[1].get('auction_id'), x[1].get('bidding_date')), res=RS.get(x[0])))
            pane(anchor, f'past-{anchor}', '⏳ 기일 지남 · 최근 2주', len(past), html, dates)
        if not xs and not past: parts.append(f'<p class="g pane" data-main="{anchor}">표시할 물건 없음</p>')
        if nt:
            pane(anchor, f'{anchor}-nt', '🔍 실거래 없음 (참고)', len(nt),
                 '<p class="g s">최근 1년 같은 평형 실거래가 없어 시세가 불확실한 물건 — 백테스트에서 이런 물건은 평균 오차 약 6.1% (다른 물건 4.6%), 메일에는 넣지 않음</p>'
                 + ''.join(card(v, today) for v in nt))
        # 예측 불가(단지 못 찾음) 물건은 표시하지 않음 (2026-11-05 사용자 요청: 이상한 물건이 많음)
    # 빌라·상가·건물 탭 (2026-11-16 사용자 요청) — 예측 없이 사실만, other_items.py 결과
    oth = load_others(os.path.dirname(src))
    for cat, title, anchor, cond in OTHER_CATS:
        xs = sorted((v for v in ((oth or {}).get('items') or {}).values()
                     if v.get('category') == cat and (v.get('bidding_date') or '') >= today),
                    key=lambda v: (v.get('bidding_date') or '9999', v.get('address') or ''))
        total[cat] = len(xs)
        nav.append((anchor, title, len(xs)))
        parts.append(f'<h2 class="mainh" id="{anchor}" data-main="{anchor}">{title} ({E(cond)}) · {len(xs)}건</h2>')
        parts.append(f'<div class="g s pane-note" data-main="{anchor}">{E(cond)} · 권리 깨끗한 물건만 · 낙찰가 예측 없음(시세 자료 없음)</div>')
        if oth is None or (not xs and not (oth or {}).get('station_source')):
            msg = '아직 수집 전입니다' if oth is None else '역 거리 확인용 카카오 키가 없어 표시할 수 없어요 (.env KAKAO_REST_KEY)'
            parts.append(f'<section class="pane" id="{anchor}-none" data-main="{anchor}"><p class="g">{msg}</p></section>')
            subnav.setdefault(anchor, []).append((f'{anchor}-none', '안내', None))
            continue
        groups = (('soon', '🔔 7일 이내', [v for v in xs if (v.get('bidding_date') or '') <= soon]),
                  ('later', '📅 그 이후', [v for v in xs if (v.get('bidding_date') or '9999') > soon]))
        for sid, lab, g in groups:
            if not g: continue
            html, dates = by_date(f'{anchor}-{sid}', g, other_card)
            pane(anchor, f'{anchor}-{sid}', lab, len(g), html, dates)
        if not xs:
            parts.append(f'<section class="pane" id="{anchor}-none" data-main="{anchor}"><p class="g">표시할 물건 없음</p></section>')
            subnav.setdefault(anchor, []).append((f'{anchor}-none', '없음', None))
    # 2026-11-19 사용자 요청: '내 조건' 탭 — 고른 종류·구의 물건만 한데 모아 날짜순 (카드는 각 탭에서 JS 로 복사, 선택은 기기에 저장)
    # 2026-11-22 사용자 요청: '내 조건' → '📅 캘린더' (매각기일 달력, 날짜 → 한 줄 요약 → 카드), 첫 화면
    nav.insert(0, ('my', '📅 캘린더', None))
    parts.insert(0, '<h2 class="mainh" id="my" data-main="my">📅 캘린더</h2><section class="pane" id="my-list" data-main="my">'
                    '<div class="fbar"><span id="fsum" class="s"></span><button type="button" id="fbtn">⚙️ 조건 바꾸기</button></div>'
                    '<div id="fpanel" hidden><div class="fl">종류 <span class="g">(안 고르면 전체)</span></div><div class="fchips" id="fcat"></div>'
                    '<div class="fl">지역 (구) <span class="g">(안 고르면 전체)</span> <a href="#" id="gclr">모두 해제</a></div><div class="fchips" id="fgu"></div>'
                    '<div class="fact"><button type="button" id="fok">적용</button><button type="button" id="fcancel">닫기</button></div></div>'
                    '<div class="cal" id="cal"></div></section>')
    res = results_14d(today, RS, tracked)
    nav.append(('score', '📊 성적표', None))
    parts.append('<h2 class="mainh" id="score" data-main="score">📊 모델 성적표 (최근 14일)</h2>')
    rt = retrain_line(today)
    if rt: parts.append(f'<div class="g s pane-note" data-main="score">{rt}</div>')
    if res is None:
        parts.append('<p class="g pane" data-main="score">성적표를 만들지 못했습니다</p>')
    else:
        for cat, title, sid in (('아파트', '🏢 아파트', 'apt'), ('오피스텔', '🏬 오피스텔', 'ot')):
            n = sum(1 for r in res if (r.get('category') or '아파트') == cat) if isinstance(res, list) else 0
            subnav.setdefault('score', []).append((f'score-{sid}', title, n or None))
            parts.append(f'<section class="pane" id="score-{sid}" data-main="score"><h3>{title}</h3>{scorecard(res, cat, tracked)}</section>')
    navhtml = '<div class="tabs">' + ''.join(
        f'<a class="tab" href="#{a}" data-main="{a}">{t}' + (f' <b>{n}</b>' if n is not None else '') + '</a>' for a, t, n in nav) + '</div>'
    navhtml += ''.join(f'<div class="subs" data-main="{m}">' + ''.join(
        f'<a class="sub-t" href="#{pid}" data-pane="{pid}">{lab}' + (f' <b>{n}</b>' if n else '') + '</a>' for pid, lab, n in L) + '</div>'
        for m, L in subnav.items())
    nav = [navhtml]
    gen = d.get('generated_at', '')[:16].replace('T', ' ')
    foot = ('표시 기준: 권리 위험·주의 물건과 모델 예측이 없는 물건은 숨김 · 1년 실거래 없는 아파트는 \'실거래 없음(참고)\'에 따로<br>'
            f'검색 지역: {E(region_text())}<br>'
            '🛡 안전 = 법원 매각물건명세서로 인수 금액 0원 확인 · 보통 = 리치고 기준 권리 문제 없음(명세서 미확인) · 주의·위험은 숨김<br>'
            '🎯 모델 시세(아파트) = 리치고 시세와 국토부 실거래(최근 12개월, 최근일수록 가중, 층 보정)를 거래 수·흩어진 정도에 따라 섞은 값 — 입찰가와 % 의 기준<br>'
            '🏢 아파트 입찰가 = 앙상블 모델(부스팅+군집별 회귀) + 랜덤포레스트·LightGBM 8개 평균, 최저가 +1% 아래는 올림 (2026-11-15~, 백테스트 평균 오차 4.6→4.3%) · 🏬 오피스텔 = 랜덤포레스트+부스팅(시세는 리치고) · 확률 오차 약 ±5%p<br>'
            '📐 3% 안 확률 = 예상 낙찰가(50%)가 실제 낙찰가 ±3% 안에 들 확률 · ✅ 정밀 = 그 확률 상위 20%(백테스트 평균 오차 약 2.8%), 정밀 물건 입찰가표는 정밀 물건끼리의 오차로 계산<br>'
            '🏷 매매 시세(종합) = 최근 12개월 실거래(추세 보정) · 리치고 추정시세 · 주변 단지 시세(같은 동)의 중앙값 (호가 제외) — 참고용<br>'
            '🏦 KB 시세 = KB부동산 매매 일반가(전용면적이 가장 가까운 평형, ±2㎡) · 하한~상한 = KB 하위·상위 평균가 · 모델 입력 아님, 참고·성적표 비교용<br>'
            '⚖ 가중 시세 = 최근 3개월 같은 평형 실거래 60% · 층 보정 실거래 20% · 매물 최저 호가 15%(상한) · 감정가 시차 보정 5% (직거래 제외) — 참고용<br>'
            '🎲 유찰 확률 = 회차별 낙찰·유찰 이력으로 학습한 모델 · 📈 회수기간(오피스텔) = 낙찰확률 50% 가격 ÷ (추정 월세 × 12), 대출·세금·비용 제외 단순 계산<br>'
            '⚠️ 주거용 오피스텔은 세법상 주택 수에 들어갈 수 있어요 — 세무사·은행에 확인<br>'
            '🏪 상가·🏙 건물 =리치고 경매 목록 중 등기 요약상 인수 권리·대항력 임차인 없는 물건 · 역 거리 = 카카오 지도 주소 좌표 기준 직선거리 · 낙찰가 예측 없음, 법원 명세서 미확인<br>'
            '👤 임차인·⚖️ 문건 = 법원경매정보(매각물건명세서·현황조사서·문건송달내역) 수집분 · 역 도보시간은 직선거리 기준 추정<br>'
            '권리분석은 등기 기준 자동요약을 바탕으로 한 1차 추정입니다. 점유자·대항력은 매각물건명세서에서, 대출 한도는 은행에서 직접 확인하세요. 입찰 권유가 아닙니다.')
    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>경매 전체 카드</title><script>document.documentElement.classList.add('js')</script><style>{CSS}</style></head><body><div class="wrap">
<h1>🏠 경매 전체 카드</h1><div class="meta">예측 {E(gen)} 기준 · 아파트 {total['아파트']}건 · 오피스텔 {total['오피스텔']}건 · 상가 {total.get('상가', 0)} · 건물 {total.get('건물', 0)}건 · 매각기일 순</div>
<div class="nav">{''.join(nav)}</div>
{''.join(parts)}
<div class="foot" id="foot">{foot}</div></div><script>{JS}</script></body></html>"""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'w').write(doc)
    print('page', dst, total, f'{len(doc.encode()) / 1024:.0f}KB')


if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'predictions', 'latest.json')
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'page', 'index.html')
    build(src, dst)
