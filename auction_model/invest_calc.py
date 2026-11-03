"""안전 등급 + 투자금 회수기간 (2026-11-03 추가).

투자금 회수기간 = 실투자금 ÷ 연간 순수익(월세 − 이자 − 기타비용)
- 오피스텔: 낙찰 50% 가격 기준, 대출 70%(금리 5.2% 가정), 취득세 등 4.6%, 부대비용 800만, 보증금 1,000만 받고 월세
  (월세 = (전세 − 보증금) × 전월세전환율 6.06% ÷ 12)
- 아파트: 생애최초 주담대는 실거주 의무라 임대 시 대출 없이 계산(현금 매수 가정), 보증금 = 가격의 10%,
  월세 전환율 4.7% (서울 아파트, 국토부 2026-05), 취득세는 1주택 기준 근사
- 기타비용(관리·공실·보유세·수선) = 연 월세의 10%
"""
APT_CONV, OT_CONV = 0.047, 0.0606
OT_LOAN_RATE, OT_LTV = 0.052, 0.70
OTHER = 0.10


def _apt_tax(P, area):
    r = 0.01 if P <= 60000 else (P / 10000 * 2 / 3 - 3) / 100 if P <= 90000 else 0.03
    return P * r * 1.1 + (P * 0.002 if (area or 0) > 85 else 0)


def payback(it):
    """it: latest.json 의 한 물건. → dict 또는 None."""
    P = (it.get('bid_by_prob_manwon') or {}).get('50%')
    if not P: return None
    cat = it.get('category')
    if cat == '오피스텔':
        inc = it.get('income') or {}
        rent = inc.get('est_monthly_rent_manwon')
        if not rent: return None
        dep = inc.get('deposit_assumed_manwon') or 1000
        loan = P * OT_LTV
        cash = P - loan + P * 0.046 + 800 - dep
        interest = loan * OT_LOAN_RATE
        basis = f'대출 70%·금리 {OT_LOAN_RATE*100:.1f}% · 보증금 {dep:,}만'
    else:
        jr = it.get('jeonse_ratio'); mkt = (it.get('richgo_sise_eok') or 0) * 1e4
        if not jr or not mkt: return None
        dep = round(P * 0.1 / 1000) * 1000
        rent = max(0, (mkt * jr - dep) * APT_CONV / 12)
        loan, interest = 0, 0
        cash = P + _apt_tax(P, it.get('area')) + 800 - dep
        basis = f'대출 없이(생애최초 대출은 실거주 의무) · 보증금 {dep:,}만'
    net = rent * 12 * (1 - OTHER) - interest
    out = dict(cash_manwon=int(round(cash)), monthly_rent_manwon=int(round(rent)), annual_net_manwon=int(round(net)),
               basis=basis, years=None, coc_pct=None)
    if net > 0 and cash > 0:
        out.update(years=round(cash / net, 1), coc_pct=round(net / cash * 100, 2))
    return out


def safety(it):
    """안전 / 보통 / 주의 / 위험."""
    rk = it.get('risk') or {}; ci = it.get('court_info') or {}; t = it.get('tenant')
    d = rk.get('decision'); why = []
    if d == 'hide': return dict(grade='위험', reasons=[rk.get('reason') or '권리 위험'])
    if d == 'check': why.append(rk.get('reason') or '권리 확인 필요')
    # 유치권 신고·매각불허가는 권리 위험 → 주의. 재매각·변경·연기 신호는 보여주되 카드에 따로 표시 (2026-11-03)
    for x in ci.get('withdraw_signal') or []:
        if x.get('label') in ('유치권 신고', '불허가'): why.append(f"{x.get('label')} 신호")
    if why: return dict(grade='주의', reasons=why)
    if t and not t.get('assumed_manwon') and not t.get('unknown_deposit'):
        return dict(grade='안전', reasons=['법원 명세서 기준 인수 금액 0원'] + (['세금 교부청구 있음'] if any(n.get('label') == '세금 교부청구' for n in ci.get('notes') or []) else []))
    return dict(grade='보통', reasons=['리치고 기준 권리 문제 없음 · 법원 명세서 미확인'])


def apply(items):
    for it in items.values():
        try:
            it['safety'] = safety(it)
            it['payback'] = payback(it)
        except Exception as e:
            it['payback'] = dict(error=f'{type(e).__name__}: {e}'[:150])
