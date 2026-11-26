"""시장·은행 금리 (2026-11-26 사용자 결정: 모델마다 백테스트가 가장 좋았던 금리를 운영에 사용).
  아파트 낙찰가   → 은행채 (산금채 1년, 전월 평균)          bond1, bond1_chg6
  오피스텔 낙찰가 → 은행 주택담보대출 금리 (2개월 전 발표값)  bank, bank_chg6
  상가·건물 낙찰가 → 은행채 (산금채 1년)                    bond1, bond1_chg6
  유찰 확률(아파트·오피스텔) → 기준금리 그대로 (auction_predictor.rate_at)
근거: dev/rate_bt.py, dev/rate_bt_result.json. 값: bank_rate.json (한국은행 ECOS, dev/bank_rate_collect.py 로 갱신 — retrain.py 가 매월).
시장금리는 그 달이 끝나야 월평균이 나오므로 1개월 전, 대출금리는 다음 달 말 발표라 2개월 전 값을 씀. 최신 값이 없으면 가장 최근 값."""
import json, os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, 'bank_rate.json')
_D = None
LAG = {'kdb1y': 1, 'ktb5y': 1, 'mortgage': 2, 'sme': 2}


def _data():
    global _D
    if _D is None:
        _D = json.load(open(PATH, encoding='utf-8'))
    return _D


def at(kind, t):
    s = _data()[kind]
    k = (pd.Timestamp(t) - pd.DateOffset(months=LAG[kind])).strftime('%Y-%m')
    if k in s: return s[k]
    ks = sorted(s)
    if k < ks[0]: return s[ks[0]]
    prev = [x for x in ks if x <= k]
    return s[prev[-1]]


def chg6(kind, t):
    return at(kind, t) - at(kind, pd.Timestamp(t) - pd.DateOffset(months=6))


def add(df, col='date'):
    """df 에 bond1, bond1_chg6, bank, bank_chg6 열 추가 (월 단위로 한 번씩만 계산)."""
    t = pd.to_datetime(df[col])
    m = t.dt.to_period('M').dt.to_timestamp()
    cache = {x: (at('kdb1y', x), chg6('kdb1y', x), at('mortgage', x), chg6('mortgage', x)) for x in m.dropna().unique()}
    for i, c in enumerate(('bond1', 'bond1_chg6', 'bank', 'bank_chg6')):
        df[c] = [cache[x][i] if x in cache else float('nan') for x in m]
    return df
