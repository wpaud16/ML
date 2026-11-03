#!/usr/bin/env python3
"""서울 오피스텔 경매 낙찰가 예측기 (랜덤포레스트 + 부스팅 평균) — 보정된 낙찰확률.

2026-11-02 백테스트(서울·역 도보 10분 이내 357건 월별 롤링): 평균 오차 6.14% (아파트 앙상블 그대로 9.29%, 기존방식 7.57%).
학습: officetel/ot_train.csv (2023-06~2026-10 서울 오피스텔 매각 718건; 권리 판정 show + check(키워드·등기요약 불일치) 포함)
보정: officetel/ot_config.json (월별 롤링 예측오차 분포 + 로지스틱 보정)

  python3 officetel_model.py calibrate                         # (개발용) 보정값 재계산
  python3 officetel_model.py predict --ot <리치고 오피스텔ID> --auction <경매ID> [--check 1]
"""
import json, os, sys, argparse, warnings
import numpy as np, pandas as pd

warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import auction_predictor as ap
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression

TRAIN = os.path.join(HERE, 'officetel', 'ot_train.csv')
CFG = os.path.join(HERE, 'officetel', 'ot_config.json')
EXTRA = ['is_check']
RENT_CONV = 0.0606   # 서울 오피스텔 전월세전환율 (한국부동산원, 2026-06)


def enrich(d):
    d = d.copy()
    d['date'] = pd.to_datetime(d.date)
    d['seoul'] = 1
    d['r_sell_mkt'] = d.sell / d.mkt if 'sell' in d else np.nan
    d['r_appr_mkt'] = d.appr / d.mkt; d['r_low_mkt'] = d.low / d.mkt
    d['rate'] = d.date.map(ap.rate_at)
    d['rate_chg6'] = [ap.rate_at(t) - ap.rate_at(t - pd.DateOffset(months=6)) for t in d.date]
    d['tohu_r'] = 0
    d['regulated'] = [ap.regulated_at(t, '서울', g) for t, g in zip(d.date, d.sgg)]
    d['loan_ratio'] = [ap.loan_ratio(t, '서울', g, m) for t, g, m in zip(d.date, d.sgg, d.mkt)]
    if 'is_check' not in d:
        d['is_check'] = (d.get('risk_decision', pd.Series('show', index=d.index)) == 'check').astype(int)
    return d


def load_train():
    d = enrich(pd.read_csv(TRAIN)).sort_values('date').reset_index(drop=True)
    d['y'] = np.log(d.r_sell_mkt)
    d['heat'] = [d.r_sell_mkt[(d.date < t) & (d.date >= t - pd.Timedelta(days=120))].median() for t in d.date]
    d['heat'] = d.heat.fillna(d.r_sell_mkt.expanding().median().shift()).fillna(1.0)
    return d


def heat_at(df, T):
    m = df[(df.date < T) & (df.date >= T - pd.Timedelta(days=120))]
    return float(m.r_sell_mkt.median()) if len(m) >= 5 else float(df.r_sell_mkt.tail(30).median())


def _X(x, cols):
    X = ap.prep(x)
    for c in EXTRA: X[c] = x[c].values
    return X[list(cols) + EXTRA]


def fit_models(tr, T):
    models = []
    for kind, cols in [('rf', ap.S3), ('gb', ap.S4)]:
        Xtr = _X(tr, cols); med = Xtr.median(); Xtr = Xtr.fillna(med).fillna(0)
        wt = np.exp(-((pd.Timestamp(T) - tr.date).dt.days.values) / 365)
        if kind == 'rf':
            m = RandomForestRegressor(300, min_samples_leaf=6, max_features=0.5, random_state=0, n_jobs=-1)
        else:
            m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.04, max_depth=3, min_samples_leaf=max(10, len(tr) // 30),
                                              l2_regularization=2.0, random_state=0)
        models.append((cols, med, m.fit(Xtr, tr.y.values, sample_weight=wt)))
    return models


def predict_models(models, te):
    return np.mean([m.predict(_X(te, cols).fillna(med).fillna(0)) for cols, med, m in models], axis=0)


def fit_predict(tr, te, T):
    return predict_models(fit_models(tr, T), te)


def calibrate(start='2024-07-01'):
    df = load_train(); df['m0'] = df.date.dt.to_period('M').dt.to_timestamp()
    res = pd.Series(np.nan, index=df.index)
    for T in pd.date_range(start, df.date.max(), freq='MS'):
        tr, te = df[df.date < T], df[(df.date >= T) & (df.date < T + pd.DateOffset(months=1))]
        if len(te) == 0 or len(tr) < 60: continue
        res[te.index] = te.y.values - fit_predict(tr, te, T)
    offs = np.linspace(-.2, .2, 41); X, H = [], []
    for i in df.index[(df.date >= pd.Timestamp(start) + pd.DateOffset(months=6)) & res.notna()]:
        T = df.m0[i]; pool = res[(df.date < T) & (df.date >= T - pd.DateOffset(months=12)) & res.notna()].values
        if len(pool) < 40: continue
        for g in offs:
            X.append(ap._logit(ap.raw_prob(pool, g))); H.append(float(res[i] < g))
    lr = LogisticRegression(C=1e6).fit(np.array(X).reshape(-1, 1), H)
    T0 = df.m0.max() + pd.DateOffset(months=1)
    pool = res[(df.date >= T0 - pd.DateOffset(months=12)) & res.notna()]
    cfg = dict(built=str(pd.Timestamp.today().date()), model='오피스텔 랜덤포레스트+부스팅', n_train=int(len(df)),
               calib_a=round(float(lr.coef_[0][0]), 5), calib_b=round(float(lr.intercept_[0]), 5), n_calib_pairs=len(H),
               mape_recent=round(float(np.mean(np.abs(np.exp(pool) - 1))) * 100, 2), resid_pool=[round(float(x), 5) for x in pool.values])
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    json.dump(cfg, open(CFG, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in cfg.items() if k != 'resid_pool'} | {'n_pool': len(cfg['resid_pool'])}, ensure_ascii=False))


def predict_dict(ot_id, auction_id, is_check=0, df=None, cfg=None, models=None):
    cfg = cfg or json.load(open(CFG))
    df = load_train() if df is None else df
    row, info = ap.target_row(ot_id, auction_id, df, kind='officetel')
    T = row.date.iloc[0]
    row = enrich(row.assign(sgg=row.sgg.fillna(''))); row['is_check'] = int(is_check)
    row['heat'] = heat_at(df, T)
    c = float(predict_models(models, row)[0]) if models else float(fit_predict(df[df.date < T + pd.Timedelta(days=1)], row, T)[0])
    mkt, low = float(row.mkt.iloc[0]), float(row.low.iloc[0])
    pool, a, b = cfg['resid_pool'], cfg['calib_a'], cfg['calib_b']

    def wp(bid):
        return 0.0 if bid < low else ap.win_prob(pool, a, b, np.log(bid / mkt) - c)

    def price_at(q):
        lo, hi = low, mkt * 2.0
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if wp(mid) < q else (lo, mid)
        return max(low, hi)
    prices = {f'{q}%': int(round(price_at(q / 100) / 1e4)) for q in ap.PROB_LEVELS}
    p25, p75 = price_at(0.25), price_at(0.75)
    grid = np.arange(np.ceil(max(low, p25) / 5e6) * 5e6, p75 + 1, 5e6)
    table = [dict(bid_manwon=int(g / 1e4), bid_eok=round(g / 1e8, 2), prob=int(round(wp(g) * 100))) for g in grid]
    # 월세 추정: 전세 시세 × 전월세전환율 (보증금 1,000만원 가정)
    jr = row.jeonse_ratio.iloc[0]; basis = '해당 평형 전세 시세'
    if jr != jr and 'jeonse_ratio_bldg' in row and row.jeonse_ratio_bldg.iloc[0] == row.jeonse_ratio_bldg.iloc[0]:
        jr = float(row.jeonse_ratio_bldg.iloc[0]); basis = '같은 건물 다른 평형의 전세가율로 추정'   # 2026-11-03 사용자 요청
    jeonse = mkt * jr if jr == jr else None
    rent = None
    if jeonse:
        rent = max(0.0, (jeonse - 1e7) * RENT_CONV / 12)
    p50 = prices['50%'] * 1e4
    income = dict(jeonse_manwon=int(round(jeonse / 1e4)) if jeonse else None,
                  jeonse_ratio=round(float(jr), 3) if jr == jr else None,
                  est_monthly_rent_manwon=int(round(rent / 1e4)) if rent else None,
                  deposit_assumed_manwon=1000, rent_conversion_rate=RENT_CONV,
                  rent_basis=basis if rent else None,
                  gross_yield_pct_at_p50=round(rent * 12 / p50 * 100, 2) if rent else None)
    return dict(info, model=cfg['model'], category='오피스텔',
                bid_by_prob_manwon=prices, bid_by_prob_eok={k: round(v / 1e4, 2) for k, v in prices.items()},
                prob_by_bid_5m=table, p50_ensemble_manwon=prices['50%'], p50_ensemble_eok=round(prices['50%'] / 1e4, 2),
                income=income, fail=ap._fail_info('ot', row),
                by_bidders=bidder_scenarios(df, row, T, low, mkt, cfg),
                model_error_note=f"평균 오차 약 {cfg['mape_recent']}% (최근 12개월 롤링), 확률 오차 약 ±5%p", warnings=[])



# ---------------- 입찰 인원별 낙찰확률 입찰가 (2026-11-03 추가) ----------------
# 백테스트(2024-07~, 인원 기록 있는 536건): 평균 오차 6.03% → 인원 알 때 5.87%, 인원 그룹별 확률 40/50/60% → 실제 41/52/62%
import threading
BID_CSV = os.path.join(HERE, 'officetel', 'ot_bidders.csv')   # auction_id, bidders
OT_BID_SCEN = [1, 2, 3, 5, 8]
OT_BID_LABEL = {1: '1명', 2: '2명', 3: '3명', 5: '5명', 8: '8명 이상'}
_BCACHE, _BLOCK = {}, threading.Lock()


def ot_bid_group(n):
    return 1 if n <= 1 else 2 if n == 2 else 3 if n <= 4 else 5 if n <= 7 else 8


def _with_bidders(df):
    df = df.drop(columns=['bidders'], errors='ignore')
    b = pd.read_csv(BID_CSV).drop_duplicates('auction_id') if os.path.exists(BID_CSV) else pd.DataFrame(columns=['auction_id', 'bidders'])
    return df.merge(b, on='auction_id', how='left') if 'auction_id' in df else df.assign(bidders=np.nan)


def _Xb(x, cols):
    Z = _X(x, cols)
    nb = x['bidders'] if 'bidders' in x else pd.Series(np.nan, index=x.index)
    Z['l_bid'] = np.log(nb).values
    Z['bid1'] = (nb == 1).astype(float).where(nb.notna()).values
    Z['bid2'] = (nb == 2).astype(float).where(nb.notna()).values
    return Z


def _fit_bid(tr, T):
    out = []
    for kind, cols in [('rf', ap.S3), ('gb', ap.S4)]:
        Xt = _Xb(tr, cols); med = Xt.median(); Xt = Xt.fillna(med).fillna(0)
        w = np.exp(-((pd.Timestamp(T) - tr.date).dt.days.values) / 365)
        m = (RandomForestRegressor(300, min_samples_leaf=6, max_features=0.5, random_state=0, n_jobs=-1) if kind == 'rf' else
             HistGradientBoostingRegressor(max_iter=300, learning_rate=0.04, max_depth=3, min_samples_leaf=max(10, len(tr) // 30),
                                           l2_regularization=2.0, random_state=0))
        out.append((cols, med, m.fit(Xt, tr.y.values, sample_weight=w)))
    return out


def _pred_bid(models, te):
    return np.mean([m.predict(_Xb(te, c).fillna(med).fillna(0)) for c, med, m in models], axis=0)


EXP_F = ['l_appr', 'l_low', 'fails', 'l_area', 'age', 'jeonse', 'heat', 'rate', 'is_check']


def _Xe(d):
    Z = ap.prep(d); Z['is_check'] = d['is_check'].values
    return Z[EXP_F]


def _fit_exp(tr):
    tr = tr[tr.bidders.notna()]; Xt = _Xe(tr); med = Xt.median()
    ms = {q: HistGradientBoostingRegressor(loss='quantile', quantile=q, max_iter=200, max_depth=3, learning_rate=0.05,
                                           min_samples_leaf=15, random_state=0).fit(Xt.fillna(med), np.log(tr.bidders)) for q in (0.25, 0.5, 0.75)}
    return ms, med


def calibrate_bidders(start='2024-07-01'):
    df = _with_bidders(load_train()); df['m0'] = df.date.dt.to_period('M').dt.to_timestamp()
    res = pd.Series(np.nan, index=df.index)
    for T in pd.date_range(start, df.date.max(), freq='MS'):
        tr, te = df[df.date < T], df[(df.date >= T) & (df.date < T + pd.DateOffset(months=1)) & df.bidders.notna()]
        if len(te) == 0 or len(tr) < 60: continue
        res[te.index] = te.y.values - _pred_bid(_fit_bid(tr, T), te)
    T0 = df.date.max(); m = res.notna() & (df.date >= T0 - pd.DateOffset(months=18))
    g = df.bidders[m].map(ot_bid_group)
    cfg = json.load(open(CFG))
    cfg['bidder_resid'] = dict(built=str(pd.Timestamp.today().date()),
                               pools={str(k): [round(float(x), 5) for x in res[m][g == k].values] for k in OT_BID_SCEN},
                               all=[round(float(x), 5) for x in res[m].values],
                               mape=round(float(np.mean(np.abs(np.exp(res.dropna()) - 1)) * 100), 2), n=int(res.notna().sum()))
    json.dump(cfg, open(CFG, 'w'), ensure_ascii=False, indent=1)
    print({k: len(v) for k, v in cfg['bidder_resid']['pools'].items()}, 'mape', cfg['bidder_resid']['mape'])


def bidder_scenarios(df, row, T, low, mkt, cfg):
    """오피스텔 입찰 인원별 낙찰확률 40~60% 입찰가 + 예상 인원."""
    try:
        br = cfg.get('bidder_resid')
        if not br: return dict(error='bidder_resid 없음')
        key = len(df)   # 예측 대상은 모두 앞으로의 기일이라 전체 학습자료로 한 번만 학습
        with _BLOCK:
            if key not in _BCACHE:
                dfb = _with_bidders(df); T0 = dfb.date.max() + pd.Timedelta(days=1)
                _BCACHE.clear(); _BCACHE[key] = (_fit_bid(dfb, T0), _fit_exp(dfb))
        bm, (em, emed) = _BCACHE[key]
        out, price = {}, {}
        for n in OT_BID_SCEN:
            c = float(_pred_bid(bm, row.assign(bidders=float(n)))[0])
            pool = br['pools'].get(str(n)) or []
            if len(pool) < 30: pool = br['all']
            qs = {f'{q}%': round(max(low, mkt * float(np.exp(c + np.quantile(pool, q / 100)))) / 1e8, 2) for q in ap.PROB_LEVELS}
            out[OT_BID_LABEL[n]] = qs; price[OT_BID_LABEL[n]] = qs['50%']
        xe = _Xe(row).fillna(emed)
        e = {q: float(np.exp(m.predict(xe)[0])) for q, m in em.items()}
        return dict(bid_by_prob_eok=out, price_eok=price, expected_bidders=int(round(e[0.5])),
                    expected_range=[max(1, int(round(e[0.25]))), max(1, int(round(e[0.75])))],
                    model_error_note=f"인원을 알 때 평균 오차 약 {br['mape']}%",
                    note='N명이 입찰한다고 가정할 때 낙찰확률별 입찰가. 인원은 당일에야 알 수 있어 예상 인원은 참고용')
    except Exception as ex:
        return dict(error=f'{type(ex).__name__}: {ex}'[:200])

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('cmd', choices=['predict', 'calibrate', 'calibrate_bidders'])
    p.add_argument('--ot'); p.add_argument('--auction'); p.add_argument('--check', type=int, default=0)
    a = p.parse_args()
    if a.cmd == 'calibrate': calibrate()
    elif a.cmd == 'calibrate_bidders': calibrate_bidders()
    else: print(json.dumps(predict_dict(a.ot, a.auction, a.check), ensure_ascii=False))
