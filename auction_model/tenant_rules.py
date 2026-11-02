"""임차인 보증금 인수 판정 (2026-11-03 추가).

자료: auction_model/tenants/latest.json — 사용자 PC(LAPTOP-M47J0JTR)가 매일 새벽 법원경매정보 매각물건명세서에서 읽어 올리는 파일.
      형식은 tenants/README.md 참고. 파일이 없거나 오래되면(14일) 아무것도 바꾸지 않는다(리치고 판정 그대로).

규칙 (보수적으로):
- 대항력 = 전입일이 말소기준권리 접수일보다 빠른 임차인 (전입 다음날 0시 효력이라 같은 날이면 대항력 없음)
- 대항력 임차인이 배당요구(종기 안)를 했고 확정일자도 말소기준보다 빠르면 → 1순위로 낙찰금에서 배당받는다고 본다
  · 배당 재원 = 낙찰확률 40% 가격 × 95% − 집행비용 300만 (당해세 등 먼저 빠질 수 있는 몫을 남겨 둠)
- 그 외(배당요구 없음, 확정일자 없음/늦음) → 보증금 전액 인수로 본다
- 인수 예상액 > 0 → 숨김, 0 → 포함(대항력 임차인 문제는 해소)
"""
import json, os
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
    return {k: v for k, v in (d.get('items') or {}).items() if (v.get('checked') or '') >= lo and not v.get('error')}


def _d(s):
    return (s or '')[:10] or None


def evaluate(t, prices_manwon, low_manwon):
    """t: tenants/latest.json 의 한 물건. → dict(assumed_manwon, opposing, lines, ok)."""
    base = _d(t.get('base_right_date'))
    if not base: return None
    deadline = _d(t.get('dividend_deadline'))
    bid = (prices_manwon or {}).get('40%') or low_manwon or 0
    pool = bid * POOL_RATE - COST_MANWON
    opp = [x for x in t.get('tenants') or [] if _d(x.get('move_in')) and _d(x.get('move_in')) < base]
    if not opp:
        return dict(assumed_manwon=0, opposing=0, lines=['법원 명세서상 대항력 임차인 없음'], ok=True)
    assumed, lines = 0, []
    opp.sort(key=lambda x: _d(x.get('fixed_date')) or '9999')
    for x in opp:
        dep = int(x.get('deposit_manwon') or 0)
        claimed = bool(x.get('claimed_dividend'))
        if claimed and deadline and _d(x.get('claim_date')) and _d(x.get('claim_date')) > deadline: claimed = False
        first = claimed and _d(x.get('fixed_date')) and _d(x.get('fixed_date')) < base
        pay = int(min(dep, max(0, pool))) if first else 0
        pool -= pay
        assumed += dep - pay
        why = '배당요구·확정일자 선순위 → 배당' if first else ('배당요구 없음' if not claimed else '확정일자 없음/늦음')
        lines.append(f"대항력 임차인 보증금 {dep:,}만 · {why}" + (f" {pay:,}만" if first else ''))
    return dict(assumed_manwon=int(assumed), opposing=len(opp), lines=lines, ok=assumed <= 0)


def apply(items, today):
    """latest.json items 의 risk 를 임차인 자료로 다시 판정. 바꾼 건수 반환."""
    T = load(today); n = 0
    for key, it in items.items():
        t = T.get(key)
        rk = it.get('risk')
        if not t or not rk: continue
        ev = evaluate(t, it.get('bid_by_prob_manwon'), it.get('low_manwon'))
        if not ev: continue
        reason = rk.get('reason') or ''
        other = [p for p in reason.split(' / ') if p and not p.startswith('대항력 임차인')]
        hard = reason.startswith('특수물건')
        note = dict(source='법원 매각물건명세서', checked=t.get('checked'), assumed_manwon=ev['assumed_manwon'],
                    opposing_tenants=ev['opposing'], lines=ev['lines'],
                    caution='압류(세금)가 말소기준이면 당해세가 임차인보다 먼저 배당될 수 있음' if '압류' in ((rk.get('summary') or {}).get('base_right') or '') else None)
        it['tenant'] = note
        if hard: continue
        if not ev['ok']:
            rk.update(decision='hide', reason=f"보증금 인수 예상 약 {ev['assumed_manwon']:,}만 (법원 명세서 기준)"); n += 1
        elif not other:
            rk.update(decision='show', reason='대항력 임차인 배당으로 전액 변제 예상' if ev['opposing'] else '', tenant_cleared=True); n += 1
        else:
            rk.update(reason=' / '.join(other))
    return n
