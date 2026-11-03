"""안전 등급 + 투자금 회수기간 (2026-11-03 추가).

투자금 회수기간(오피스텔만) = 낙찰확률 50% 가격 ÷ (월세 × 12)  — 단순 계산 (2026-11-03 사용자 요청으로 변경)
(아래 옛 설명은 참고용)
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
    """오피스텔만: 낙찰확률 50% 가격을 월세로 모으는 데 걸리는 기간 (단순 계산, 2026-11-03 사용자 요청).
    years = 50% 가격 ÷ (월세 × 12). 대출·세금·비용은 넣지 않음."""
    if it.get('category') != '오피스텔': return None
    P = (it.get('bid_by_prob_manwon') or {}).get('50%')
    rent = (it.get('income') or {}).get('est_monthly_rent_manwon')
    if not P or not rent: return None
    months = P / rent
    return dict(price_manwon=int(P), monthly_rent_manwon=int(rent), months=int(round(months)), years=round(months / 12, 1),
                basis='낙찰확률 50% 가격 ÷ (월세 × 12) · 대출·세금·비용 제외 단순 계산')


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
