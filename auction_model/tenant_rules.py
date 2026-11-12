"""임차인 보증금 인수 판정 (2026-11-03 추가).

자료: auction_model/tenants/latest.json — 사용자 PC(LAPTOP-M47J0JTR)가 매일 새벽 법원경매정보 매각물건명세서에서 읽어 올리는 파일.
      형식은 tenants/README.md 참고. 파일이 없거나 오래되면(14일) 아무것도 바꾸지 않는다(리치고 판정 그대로).

규칙 (보수적으로):
- 대항력 = 전입일이 말소기준권리 접수일보다 빠른 임차인 (전입 다음날 0시 효력이라 같은 날이면 대항력 없음)
- 대항력 임차인이 배당요구(종기 안)를 했고 확정일자도 말소기준보다 빠르면 → 1순위로 낙찰금에서 배당받는다고 본다
  · 배당 재원 = 낙찰확률 40% 가격 × 95% − 집행비용 300만 (당해세 등 먼저 빠질 수 있는 몫을 남겨 둠)
- 그 외(배당요구 없음, 확정일자 없음/늦음) → 보증금 전액 인수로 본다
- 인수 예상액 > 0 → 숨김, 0 → 포함(대항력 임차인 문제는 해소)
- 대항력 임차인 보증금이 미상(null)이면 인수액을 알 수 없으므로 숨김 (2026-11-03)
- 5가지 안전 조건 체크 (2026-11-12): ①배당요구(종기 안) ②확정일자 ③순위(전입 다음날·확정일자가 말소기준보다 앞섬)
  ④재원(배당 재원으로 전액) ⑤전입유지(현황조사서 점유가 임차인인지, 자료 없으면 None=미확인·판정에 안 씀)
  → note['checks'] 로 저장, 카드에 한 줄 표시. ①~④ 중 하나라도 실패면 기존처럼 인수액이 생겨 숨김.
- 전세대출 양도로 같은 임차가 2줄로 나오는 경우 (2026-11-12, 304호 사례: 보증금 1.7억 · 한국주택금융공사만 배당요구):
  전입일·확정일자·보증금이 같은 행은 1건으로 합치고, 한쪽이라도 배당요구했으면 배당요구 O.
  배당요구가 엇갈리면(금융기관만 요구) flags 에 '대출 양도 금액 확인' → 안전 대신 보통 등급(표시는 함).
"""
import json, os, re
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, 'tenants', 'latest.json')
COST_MANWON = 300
POOL_RATE = 0.95


def load(today):
    if not os.path.exists(PATH): return {}
    try:
        d = json.load(open(PATH))
    except Exception:
        return {}
    lo = str((datetime.fromisoformat(today) - timedelta(days=14)).date())
    # error 가 있어도(예: 매각물건명세서 공개 전) 문건·점유 정보는 쓴다. 명세서 항목이 없으면 evaluate 가 판정을 건너뜀.
    return {k: v for k, v in (d.get('items') or {}).items() if (v.get('checked') or '') >= lo}


def _d(s):
    return (s or '')[:10] or None


def _text_tenant(t):
    """명세서 '매수인에게 인수되는 권리' 칸에 대항력 임차인/임차권등기가 적혀 있으면 (보증금 만원 또는 None, 임차권등기 여부).
    없으면 None. (2026-11-12: 2025타경103241 — 표에는 보증금 칸이 비어 0으로 읽혔고 이 칸에만 1억8500만 인수가 적혀 있었음)"""
    a = re.sub(r'\s+', ' ', t.get('assumed_rights_text') or '')
    if '임차' not in a or not ('인수' in a or '대항' in a): return None
    m = re.search(r'보증금[^0-9]{0,15}([\d,]{7,})\s*원', a)
    dep = int(m.group(1).replace(',', '')) // 10000 if m else None
    return dep, '임차권' in a


def evaluate(t, prices_manwon, low_manwon):
    """t: tenants/latest.json 의 한 물건. → dict(assumed_manwon, opposing, lines, ok)."""
    base = _d(t.get('base_right_date'))
    if not base: return None
    deadline = _d(t.get('dividend_deadline'))
    bid = (prices_manwon or {}).get('40%') or low_manwon or 0
    pool = bid * POOL_RATE - COST_MANWON
    opp = [dict(x) for x in t.get('tenants') or [] if _d(x.get('move_in')) and _d(x.get('move_in')) < base]
    tt = _text_tenant(t)
    if tt:
        dep_t, reg = tt
        if not opp:   # 표에서 못 잡았어도 명세서 문구에 대항력 임차인이 있으면 그 보증금 전액 인수로 본다
            opp = [dict(deposit_manwon=dep_t, claimed_dividend=False, fixed_date=None, occupant='임차권' if reg else '')]
        for x in opp:
            if not x.get('deposit_manwon'): x['deposit_manwon'] = dep_t if len(opp) == 1 else None
            if reg and '임차권' not in (x.get('occupant') or ''): x['occupant'] = (x.get('occupant') or '') + '(임차권등기)'
    if not opp:
        return dict(assumed_manwon=0, opposing=0, lines=['법원 명세서상 대항력 임차인 없음'], ok=True, checks=None, flags=[])
    opp, flags = _merge_loan_dup(opp, deadline)
    occ = (t.get('occupancy') or {}).get('occupant_type') or ''
    stay = True if '임차' in occ else (None if not occ or '미상' in occ or '불명' in occ else False)
    checks = dict(배당요구=True, 확정일자=True, 순위=True, 재원=True, 전입유지=stay)
    assumed, lines, unknown = 0, [], 0
    opp.sort(key=lambda x: _d(x.get('fixed_date')) or '9999')
    for x in opp:
        if not x.get('deposit_manwon'):   # 0 은 명세서 보증금 칸이 빈 경우 → 미상으로 본다
            unknown += 1
            lines.append('대항력 임차인 보증금 미상 → 인수액 알 수 없음')
            continue
        dep = int(x.get('deposit_manwon') or 0)
        claimed = bool(x.get('claimed_dividend')) or '임차권' in (x.get('occupant') or '')   # 임차권등기권자는 배당요구 없이도 배당
        if claimed and deadline and _d(x.get('claim_date')) and _d(x.get('claim_date')) > deadline: claimed = False
        fx = _d(x.get('fixed_date'))
        # 우선변제 기준일 = max(전입 다음날 0시, 확정일자). 대항력 임차인은 전입 < 말소기준이라 전입 다음날 ≤ 말소기준(0시가 먼저)
        # → 확정일자가 말소기준보다 앞서면 1순위. 같은 날이면 동순위(안분)라 보수적으로 실패.
        first = claimed and fx and fx < base
        pay = int(min(dep, max(0, pool))) if first else 0
        checks['배당요구'] &= claimed; checks['확정일자'] &= bool(fx); checks['순위'] &= bool(first)
        checks['재원'] &= (not first) or pay >= dep
        pool -= pay
        assumed += dep - pay
        why = '배당요구·확정일자 선순위 → 배당' if first else ('배당요구 없음' if not claimed else '확정일자 없음/늦음')
        lines.append(f"대항력 임차인 보증금 {dep:,}만 · {why}" + (f" {pay:,}만" if first else ''))
    lines += [f'⚠ {f}' for f in flags]
    return dict(assumed_manwon=int(assumed), opposing=len(opp), lines=lines, unknown=unknown, ok=assumed <= 0 and not unknown,
                checks=checks, flags=flags)


def _merge_loan_dup(opp, deadline):
    """전입일·확정일자·보증금이 같은 행 = 같은 임차(전세대출 보증기관이 보증금 채권을 양수해 따로 신고) → 1건으로 합침."""
    groups, out, flags = {}, [], []
    for x in opp:
        k = (_d(x.get('move_in')), _d(x.get('fixed_date')), x.get('deposit_manwon'))
        if not x.get('deposit_manwon'): k = (id(x),)
        groups.setdefault(k, []).append(x)
    for g in groups.values():
        if len(g) == 1: out.append(g[0]); continue
        ok = [x for x in g if x.get('claimed_dividend') and not (deadline and _d(x.get('claim_date')) and _d(x.get('claim_date')) > deadline)]
        m = dict(ok[0] if ok else g[0])
        if ok and len(ok) < len(g):
            flags.append(f"같은 임차(보증금 {m['deposit_manwon']:,}만)가 {len(g)}줄 — 전세대출 양도로 보여 1건으로 계산. "
                         '한쪽(보증기관 추정)만 배당요구 → 양도 금액이 보증금 일부면 나머지는 낙찰자 인수, 문건송달내역·비고란 확인 필요')
        out.append(m)
    return out, flags


SIGNALS = [('취하', '취하'), ('변경', '변경'), ('연기', '연기'), ('정지', '정지'), ('기각', '기각'), ('불허가', '불허가'),
           ('유치권', '유치권 신고'), ('송달불능', '송달불능'), ('교부청구', '세금 교부청구'), ('임차권', '임차권등기')]


def court_info(t):
    """법원 문건·송달·현황조사 요약 → 브리핑 한두 줄용."""
    occ = t.get('occupancy') or {}
    ev = t.get('events') or []
    flags = []
    for e in ev:
        txt = e.get('text') or ''
        for kw, label in SIGNALS:
            if kw in txt and not any(f['label'] == label for f in flags):
                flags.append(dict(label=label, date=e.get('date'), text=txt[:60]))
    warn = [f for f in flags if f['label'] in ('취하', '변경', '연기', '정지', '기각', '불허가', '유치권 신고', '송달불능')]
    return dict(occupant=occ.get('occupant_type'), closed_absent=bool(occ.get('closed_absent')),
                lessee_count=occ.get('lessee_count'), spec_published=bool(t.get('base_right_date')),
                withdraw_signal=warn[:3], notes=[f for f in flags if f not in warn][:3])


def apply(items, today):
    """latest.json items 의 risk 를 임차인 자료로 다시 판정. 바꾼 건수 반환."""
    T = load(today); n = 0
    for key, it in items.items():
        t = T.get(key)
        rk = it.get('risk')
        if not t or not rk: continue
        it['court_info'] = court_info(t)
        ev = evaluate(t, it.get('bid_by_prob_manwon'), it.get('low_manwon'))
        if not ev: continue
        reason = rk.get('reason') or ''
        other = [p for p in reason.split(' / ') if p and not p.startswith('대항력 임차인')]
        hard = reason.startswith('특수물건')
        note = dict(source='법원 매각물건명세서', checked=t.get('checked'), assumed_manwon=ev['assumed_manwon'],
                    opposing_tenants=ev['opposing'], unknown_deposit=ev.get('unknown', 0), lines=ev['lines'],
                    checks=ev.get('checks'), flags=ev.get('flags') or [],
                    caution='압류(세금)가 말소기준이면 당해세가 임차인보다 먼저 배당될 수 있음' if '압류' in ((rk.get('summary') or {}).get('base_right') or '') else None)
        it['tenant'] = note
        if hard: continue
        if ev.get('unknown'):
            rk.update(decision='hide', reason='대항력 임차인 보증금 미상 (법원 명세서 기준)'); n += 1
        elif not ev['ok']:
            rk.update(decision='hide', reason=f"보증금 인수 예상 약 {ev['assumed_manwon']:,}만 (법원 명세서 기준)"); n += 1
        elif not other:
            rk.update(decision='show', reason=('대항력 임차인 배당으로 전액 변제 예상 (5가지 조건 통과)' if ev['opposing'] else '')
                      + (' · 대출 양도 금액 확인 필요' if ev.get('flags') else ''), tenant_cleared=True); n += 1
        else:
            rk.update(reason=' / '.join(other))
    return n
