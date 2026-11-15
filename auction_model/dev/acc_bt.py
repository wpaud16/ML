"""정확도 개선 실험 틀 (2026-11-15, 사용자 요청: 오차 3% 목표, 가능한 것 모두 시도).
- 월별 롤링(학습 = 그 달 이전 매각만), 2023-09~ 예측, 평가는 2024-07~ (band_bt 와 같은 987건)
- 피처: 운영 S4 + 추가(같은 단지 과거 낙찰, 동·구 최근 낙찰가율, 실거래 세부, 리치고/M 차이, 최저가/감정가 등) — 모두 그 물건 매각일 이전 정보만
- 예측값 = log(낙찰가/M시세). 물건별 예측은 dev/acc_bt/P_<이름>.csv 에 저장(다시 돌릴 때 재사용)
  python dev/acc_bt.py [실험이름 ...]   # 없으면 전부"""
import os, sys, warnings, time, json
import numpy as np, pandas as pd
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import auction_predictor as ap
OUT = os.path.join(HERE, 'acc_bt'); os.makedirs(OUT, exist_ok=True)
PRED_FROM, EVAL_FROM = '2023-09-01', '2024-07-01'


# ---------------- 피처 ----------------
def build():
    cache = os.path.join(OUT, 'F.pkl')
    if os.path.exists(cache) and os.path.getmtime(cache) > os.path.getmtime(__file__) - 1e9 and os.environ.get('REF') != '1':
        try: return pd.read_pickle(cache)
        except Exception: pass
    df = ap.load_train()
    S = pd.read_csv(os.path.join(HERE, 'sise_bt_S.csv'), index_col=0).reindex(df.index)
    X = ap.prep(df)
    F = pd.concat([df, X.add_prefix('x_')], axis=1)
    F['low_appr'] = df.low / df.appr
    F['l_richgo'] = np.log(df.mkt_richgo / df.mkt)
    F['l_tr12'] = np.log(S.tr12 / df.mkt); F['l_tr12f'] = np.log(S.tr12f / df.mkt)
    F['l_last'] = np.log(S['last'] / df.mkt); F['last_age'] = S.last_age_m
    F['l_tr3'] = np.log(S.tr3 / df.mkt); F['l_q60'] = np.log(S.tr12_q60 / df.mkt)
    F['n12'] = S.n12; F['neff'] = S.neff; F['disp'] = S.disp; F['m_w'] = df.m_w
    F['l_appr_tr'] = np.log(df.appr / S.tr12)
    F['doy'] = df.date.dt.dayofyear; F['dow'] = df.date.dt.dayofweek
    F['l_mktm2'] = np.log(df.mkt / df.area)   # 면적당 시세
    # 이전 정보만 쓰는 누적 피처
    n = len(df); dj_n = np.zeros(n); dj_y = np.full(n, np.nan); dj_age = np.full(n, np.nan)
    emd_y = np.full(n, np.nan); emd_n = np.zeros(n); sgg_y = np.full(n, np.nan); sgg_n = np.zeros(n)
    sgg_bid = np.full(n, np.nan); all_bid = np.full(n, np.nan); fail_y = np.full(n, np.nan)
    sgg_lowr = np.full(n, np.nan)
    dates = df.date.values; y = df.y.values; rlow = np.log(df.sell / df.low).values
    for i in range(n):
        prev = dates < dates[i]
        if not prev.any(): continue
        m = prev & (df.danji.values == df.danji.values[i])
        if m.any():
            dj_n[i] = m.sum(); dj_y[i] = y[m][-3:].mean(); dj_age[i] = (dates[i] - dates[m][-1]) / np.timedelta64(30, 'D')
        w365 = prev & (dates >= dates[i] - np.timedelta64(365, 'D'))
        m = w365 & (df.emd.values == df.emd.values[i]) & (df.sgg.values == df.sgg.values[i])
        emd_n[i] = m.sum(); emd_y[i] = np.median(y[m]) if m.any() else np.nan
        w180 = prev & (dates >= dates[i] - np.timedelta64(180, 'D'))
        m = w180 & (df.sgg.values == df.sgg.values[i]) & (df.sd.values == df.sd.values[i])
        sgg_n[i] = m.sum(); sgg_y[i] = np.median(y[m]) if m.any() else np.nan
        sgg_lowr[i] = np.median(rlow[m & (df.fails.values == df.fails.values[i])]) if (m & (df.fails.values == df.fails.values[i])).any() else np.nan
        b = df.bidders.values
        mb = m & ~np.isnan(b); sgg_bid[i] = np.mean(b[mb]) if mb.any() else np.nan
        mb2 = w180 & ~np.isnan(b); all_bid[i] = np.mean(b[mb2]) if mb2.any() else np.nan
        mf = w180 & (df.fails.values == df.fails.values[i]) & (df.seoul.values == df.seoul.values[i])
        fail_y[i] = np.median(y[mf]) if mf.sum() >= 5 else np.nan
    F['dj_n'] = dj_n; F['dj_y'] = dj_y; F['dj_age'] = dj_age
    F['emd_y'] = emd_y; F['emd_n'] = emd_n; F['sgg_y'] = sgg_y; F['sgg_n'] = sgg_n
    F['sgg_bid'] = sgg_bid; F['all_bid'] = all_bid; F['fail_y'] = fail_y; F['sgg_lowr'] = sgg_lowr
    # 축소한 지역 낙찰가율 (표본 적으면 서울/경기 heat 쪽으로)
    hl = np.log(df.heat)
    F['emd_ys'] = (F.emd_y.fillna(hl) * F.emd_n + hl * 5) / (F.emd_n + 5)
    F['sgg_ys'] = (F.sgg_y.fillna(hl) * F.sgg_n + hl * 8) / (F.sgg_n + 8)
    F['dj_ys'] = (F.dj_y.fillna(hl) * F.dj_n + hl * 2) / (F.dj_n + 2)
    F['m0'] = df.date.dt.to_period('M').dt.to_timestamp()
    F.to_pickle(cache)
    return F


F = build()
S4 = ['x_' + c for c in ap.S4]
EXTRA = ['low_appr', 'l_richgo', 'l_tr12f', 'l_last', 'last_age', 'l_tr3', 'n12', 'neff', 'disp', 'l_appr_tr',
         'dj_n', 'dj_ys', 'dj_age', 'emd_ys', 'emd_n', 'sgg_ys', 'sgg_n', 'sgg_bid', 'all_bid', 'fail_y', 'l_mktm2']
LOC = ['dj_ys', 'dj_n', 'emd_ys', 'sgg_ys', 'fail_y']
SISE = ['l_richgo', 'l_tr12f', 'l_last', 'last_age', 'n12', 'neff', 'disp', 'l_appr_tr', 'low_appr']


def target(d, kind):
    if kind == 'mkt': return d.y.values, np.zeros(len(d))
    if kind == 'low': return np.log(d.sell / d.low).values, np.log(d.low / d.mkt).values
    if kind == 'appr': return np.log(d.sell / d.appr).values, np.log(d.appr / d.mkt).values


def model(spec):
    k = spec['m']; p = spec.get('p', {})
    if k == 'hgb':
        from sklearn.ensemble import HistGradientBoostingRegressor
        return HistGradientBoostingRegressor(**{**dict(max_iter=300, learning_rate=0.04, max_depth=3, min_samples_leaf=25, l2_regularization=2.0, random_state=0), **p})
    if k == 'lgb':
        import lightgbm as lgb
        return lgb.LGBMRegressor(**{**dict(n_estimators=500, learning_rate=0.03, num_leaves=15, min_child_samples=20, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=2.0, verbose=-1, random_state=0), **p})
    if k == 'cat':
        from catboost import CatBoostRegressor
        return CatBoostRegressor(**{**dict(iterations=700, learning_rate=0.04, depth=4, l2_leaf_reg=3, verbose=0, random_seed=0, thread_count=8), **p})
    if k == 'xgb':
        import xgboost as xgb
        return xgb.XGBRegressor(**{**dict(n_estimators=500, learning_rate=0.03, max_depth=3, subsample=0.8, colsample_bytree=0.8, reg_lambda=2.0, min_child_weight=5, random_state=0, n_jobs=8), **p})
    if k == 'et':
        from sklearn.ensemble import ExtraTreesRegressor
        return ExtraTreesRegressor(**{**dict(n_estimators=500, min_samples_leaf=5, max_features=0.5, n_jobs=8, random_state=0), **p})
    if k == 'rf':
        from sklearn.ensemble import RandomForestRegressor
        return RandomForestRegressor(**{**dict(n_estimators=500, min_samples_leaf=5, max_features=0.5, n_jobs=8, random_state=0), **p})
    if k == 'ridge':
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        from sklearn.linear_model import Ridge, HuberRegressor
        return make_pipeline(StandardScaler(), HuberRegressor(alpha=p.get('alpha', 1.0), epsilon=1.35, max_iter=500) if p.get('huber') else Ridge(alpha=p.get('alpha', 3.0)))
    raise ValueError(k)


def run_one(name, spec):
    path = os.path.join(OUT, f'P_{name}.csv')
    if os.path.exists(path) and os.environ.get('FORCE') != '1':
        return pd.read_csv(path, index_col=0).p
    cols = spec['cols']; decay = spec.get('decay', 365); tk = spec.get('t', 'mkt')
    out = pd.Series(np.nan, index=F.index)
    for T in pd.date_range(PRED_FROM, F.date.max(), freq='MS'):
        tr, te = F[F.date < T], F[(F.date >= T) & (F.date < T + pd.DateOffset(months=1))]
        if spec.get('train_months'): tr = tr[tr.date >= T - pd.DateOffset(months=spec['train_months'])]
        if len(te) == 0 or len(tr) < 100: continue
        Xtr, Xte = tr[cols].astype(float), te[cols].astype(float)
        med = Xtr.median(); Xtr, Xte = Xtr.fillna(med), Xte.fillna(med)
        ytr, _ = target(tr, tk); _, off = target(te, tk)
        wt = np.exp(-((T - tr.date).dt.days.values) / decay) if decay else None
        m = model(spec)
        if spec['m'] == 'ridge': m.fit(Xtr, ytr, **({f'{m.steps[-1][0]}__sample_weight': wt} if wt is not None else {}))
        else: m.fit(Xtr, ytr, sample_weight=wt)
        out[te.index] = m.predict(Xte) + off
    pd.DataFrame({'p': out}).to_csv(path)
    return out


EV = F.date >= EVAL_FROM


def score(p, mask=None):
    m = EV & p.notna() if mask is None else EV & p.notna() & mask
    e = np.exp(F.y[m] - p[m]) - 1
    half = F.date[m] >= F.date[EV].sort_values().iloc[EV.sum() // 2]
    return dict(n=int(m.sum()), mae=round(e.abs().mean() * 100, 3), bias=round(e.mean() * 100, 2),
                w3=round((e.abs() <= .03).mean() * 100, 1), w5=round((e.abs() <= .05).mean() * 100, 1),
                h1=round(e[~half].abs().mean() * 100, 2), h2=round(e[half].abs().mean() * 100, 2))


# ---------------- 실험 목록 ----------------
L1 = dict(loss='absolute_error')
EXPS = {
    'hgb_S4': dict(m='hgb', cols=S4),
    'hgb_S4_l1': dict(m='hgb', cols=S4, p=L1),
    'hgb_S4X': dict(m='hgb', cols=S4 + EXTRA),
    'hgb_S4X_l1': dict(m='hgb', cols=S4 + EXTRA, p=L1),
    'hgb_S4loc': dict(m='hgb', cols=S4 + LOC),
    'hgb_S4sise': dict(m='hgb', cols=S4 + SISE),
    'hgb_S4X_low': dict(m='hgb', cols=S4 + EXTRA, t='low'),
    'hgb_S4X_appr': dict(m='hgb', cols=S4 + EXTRA, t='appr'),
    'hgb_S4X_d180': dict(m='hgb', cols=S4 + EXTRA, decay=180),
    'hgb_S4X_d730': dict(m='hgb', cols=S4 + EXTRA, decay=730),
    'hgb_S4X_d0': dict(m='hgb', cols=S4 + EXTRA, decay=0),
    'lgb_S4X': dict(m='lgb', cols=S4 + EXTRA),
    'lgb_S4X_l1': dict(m='lgb', cols=S4 + EXTRA, p=dict(objective='l1')),
    'lgb_S4X_hub': dict(m='lgb', cols=S4 + EXTRA, p=dict(objective='huber', alpha=0.05)),
    'cat_S4': dict(m='cat', cols=S4),
    'cat_S4X': dict(m='cat', cols=S4 + EXTRA),
    'cat_S4X_mae': dict(m='cat', cols=S4 + EXTRA, p=dict(loss_function='MAE')),
    'cat_S4X_low': dict(m='cat', cols=S4 + EXTRA, t='low'),
    'xgb_S4X': dict(m='xgb', cols=S4 + EXTRA),
    'xgb_S4X_l1': dict(m='xgb', cols=S4 + EXTRA, p=dict(objective='reg:absoluteerror')),
    'et_S4X': dict(m='et', cols=S4 + EXTRA),
    'rf_S4X': dict(m='rf', cols=S4 + EXTRA),
    'ridge_S4X': dict(m='ridge', cols=S4 + EXTRA),
    'huber_S4X': dict(m='ridge', cols=S4 + EXTRA, p=dict(huber=True)),
}
# 2라운드: 튜닝·씨앗 평균·단조 제약
R2 = {
    'hgb_X_deep': dict(m='hgb', cols=S4 + EXTRA, p=dict(max_depth=5, min_samples_leaf=15, max_iter=500, learning_rate=0.03)),
    'hgb_X_slow': dict(m='hgb', cols=S4 + EXTRA, p=dict(max_iter=800, learning_rate=0.015)),
    'hgb_X_leaf40': dict(m='hgb', cols=S4 + EXTRA, p=dict(min_samples_leaf=40, l2_regularization=5.0)),
    'cat_X_d6': dict(m='cat', cols=S4 + EXTRA, p=dict(depth=6, iterations=1000, learning_rate=0.03)),
    'cat_X_d3': dict(m='cat', cols=S4 + EXTRA, p=dict(depth=3, iterations=1200, learning_rate=0.03)),
    'cat_X_s1': dict(m='cat', cols=S4 + EXTRA, p=dict(random_seed=1)),
    'cat_X_s2': dict(m='cat', cols=S4 + EXTRA, p=dict(random_seed=2)),
    'lgb_X_dart': dict(m='lgb', cols=S4 + EXTRA, p=dict(boosting_type='dart', n_estimators=400, learning_rate=0.05)),
    'lgb_X_small': dict(m='lgb', cols=S4 + EXTRA, p=dict(num_leaves=7, min_child_samples=30, n_estimators=800, learning_rate=0.02)),
    'cat_X_d730': dict(m='cat', cols=S4 + EXTRA, decay=730),
    'cat_X_d180': dict(m='cat', cols=S4 + EXTRA, decay=180),
}
R2.update({
    'rf_S4sise': dict(m='rf', cols=S4 + SISE),
    'rf_X_leaf3': dict(m='rf', cols=S4 + EXTRA, p=dict(min_samples_leaf=3, max_features=0.33)),
    'rf_X_leaf8': dict(m='rf', cols=S4 + EXTRA, p=dict(min_samples_leaf=8, max_features=0.5)),
    'rf_X_mae': dict(m='rf', cols=S4 + EXTRA, p=dict(criterion='absolute_error', n_estimators=300)),
    'rf_X_d730': dict(m='rf', cols=S4 + EXTRA, decay=730),
    'et_X_leaf3': dict(m='et', cols=S4 + EXTRA, p=dict(min_samples_leaf=3, max_features=0.7)),
    'lgb_X_l1_small': dict(m='lgb', cols=S4 + EXTRA, p=dict(objective='l1', num_leaves=7, min_child_samples=30, n_estimators=800, learning_rate=0.02)),
    'lgb_S4sise_l1': dict(m='lgb', cols=S4 + SISE, p=dict(objective='l1')),
})
EXPS.update(R2)


def add_bid_hat():
    """응찰자 수 롤링 예측(그 달 이전 학습)을 피처로: bid_hat=log 인원 예측, p1_hat=단독 입찰 확률. 최근 30·60일 낙찰가율도."""
    path = os.path.join(OUT, 'bidhat.csv')
    if os.path.exists(path):
        B = pd.read_csv(path, index_col=0).reindex(F.index)
    else:
        from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier
        cols = S4 + EXTRA
        B = pd.DataFrame(index=F.index, columns=['bid_hat', 'p1_hat'], dtype=float)
        for T in pd.date_range('2023-10-01', F.date.max(), freq='MS'):
            tr = F[(F.date < T) & F.bidders.notna()]; te = F[(F.date >= T) & (F.date < T + pd.DateOffset(months=1))]
            if len(te) == 0 or len(tr) < 80: continue
            med = tr[cols].median(); Xtr, Xte = tr[cols].fillna(med), te[cols].fillna(med)
            r = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.04, max_depth=3, min_samples_leaf=20, random_state=0).fit(Xtr, np.log(tr.bidders))
            c = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.04, max_depth=3, min_samples_leaf=20, random_state=0).fit(Xtr, (tr.bidders <= 1).astype(int))
            B.loc[te.index, 'bid_hat'] = r.predict(Xte); B.loc[te.index, 'p1_hat'] = c.predict_proba(Xte)[:, 1]
        B.to_csv(path)
    F['bid_hat'] = B.bid_hat; F['p1_hat'] = B.p1_hat
    dates, y = F.date.values, F.y.values
    for w in (30, 60):
        v = np.full(len(F), np.nan)
        for i in range(len(F)):
            m = (dates < dates[i]) & (dates >= dates[i] - np.timedelta64(w, 'D')) & (F.seoul.values == F.seoul.values[i])
            if m.sum() >= 5: v[i] = np.median(y[m])
        F[f'heat{w}'] = v


add_bid_hat()
EXTRA2 = EXTRA + ['bid_hat', 'p1_hat', 'heat30', 'heat60']
R3 = {
    'rf_X2': dict(m='rf', cols=S4 + EXTRA2),
    'lgb_X2_l1': dict(m='lgb', cols=S4 + EXTRA2, p=dict(objective='l1')),
    'cat_X2_mae': dict(m='cat', cols=S4 + EXTRA2, p=dict(loss_function='MAE')),
    'et_X2': dict(m='et', cols=S4 + EXTRA2),
    'xgb_X2_l1': dict(m='xgb', cols=S4 + EXTRA2, p=dict(objective='reg:absoluteerror')),
    'hgb_X2': dict(m='hgb', cols=S4 + EXTRA2),
}
EXPS.update(R3)


def current():
    """운영 방식 예측 (band_bt 가 만든 것: 앙상블+구별+상승형+소규모)."""
    P = pd.read_csv(os.path.join(HERE, 'band_bt_rows.csv'), index_col=0).reindex(F.index)
    return P.c, P.raw


if __name__ == '__main__':
    names = sys.argv[1:] or list(EXPS)
    res = []
    c, raw = current()
    res.append(dict(name='운영(최종)', **score(c))); res.append(dict(name='운영 앙상블(보정 전)', **score(raw)))
    for nm in names:
        t0 = time.time(); p = run_one(nm, EXPS[nm])
        r = dict(name=nm, **score(p), sec=round(time.time() - t0)); res.append(r); print(r, flush=True)
    R = pd.DataFrame(res).sort_values('mae')
    print(R.to_string(index=False))
    R.to_csv(os.path.join(OUT, 'results_round1.csv'), index=False)
