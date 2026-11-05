"""시세 × 모델 동시 비교 (2026-11-05, 사용자 요청: 시세와 모델을 같이 검증해 최고 조합 찾기).
시세 후보는 dev/sise_bt_rows.csv(= sise_bt.py 가 만든 매각 당시 실거래·층 보정 값)로 다시 만든다.
같은 시간 순 월별 검증(2024-07~), 최근 사례 가중(1년 감쇠). 지표 = 실제 낙찰가 대비 평균 오차."""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import auction_predictor as ap
from sklearn.ensemble import RandomForestRegressor
import lightgbm as lgb, xgboost as xgb
from catboost import CatBoostRegressor

df = ap.load_train()
S = pd.read_csv(os.path.join(HERE, 'sise_bt_rows.csv'), index_col=0).reindex(df.index)
RF_ = df.mkt * S.fprem_case.fillna(1)
w = (S.neff / (S.neff + 2)).clip(upper=0.7).fillna(0) * (1 - (S.disp.fillna(0.1) / 0.2).clip(0, 1) * 0.5)
SISE = {'A 리치고': df.mkt,
        'J 50:50 층보정': 0.5 * S.tr12f.fillna(RF_) + 0.5 * RF_,
        'M 가중(최근성·거래수·분산)': w * S.tr12fw.fillna(RF_) + (1 - w) * RF_,
        'C 실거래12m': S.tr12.fillna(df.mkt)}
TRADE_REL = np.log((S.tr12f / RF_).fillna(1.0))


def mk(name):
    if name == 'LightGBM': return lgb.LGBMRegressor(n_estimators=400, learning_rate=0.03, num_leaves=15, min_child_samples=20, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=2.0, verbose=-1, random_state=0)
    if name == 'XGBoost': return xgb.XGBRegressor(n_estimators=400, learning_rate=0.03, max_depth=3, subsample=0.8, colsample_bytree=0.8, reg_lambda=2.0, min_child_weight=5, random_state=0)
    if name == 'CatBoost': return CatBoostRegressor(iterations=600, learning_rate=0.04, depth=4, l2_leaf_reg=3, verbose=0, random_seed=0, thread_count=4)
    if name == '랜덤포레스트': return RandomForestRegressor(400, min_samples_leaf=5, max_features=0.5, n_jobs=-1, random_state=0)


def frame(mkt):
    d = df.copy(); d['mkt'] = mkt.values
    d['r_sell_mkt'] = d.sell / d.mkt; d['r_appr_mkt'] = d.appr / d.mkt; d['r_low_mkt'] = d.low / d.mkt; d['y'] = np.log(d.r_sell_mkt)
    d['heat'] = [ap.recent_heat(d, s, t) for s, t in zip(d.seoul, d.date)]
    d['loan_ratio'] = [ap.loan_ratio(t, s, g, x) for t, s, g, x in zip(d.date, d.sd, d.sgg, d.mkt)]
    return d


rows, allE = [], {}
for sn, mkt in SISE.items():
    d = frame(mkt); ap._FIT.clear()
    P = {k: [] for k in ['현재 앙상블', 'LightGBM', 'XGBoost', 'CatBoost', '랜덤포레스트', 'CatBoost+비율', 'LightGBM+비율']}
    idx = []
    for T in pd.date_range('2024-07-01', d.date.max(), freq='MS'):
        tr, te = d[d.date < T], d[(d.date >= T) & (d.date < T + pd.DateOffset(months=1))]
        if len(te) == 0 or len(tr) < 100: continue
        idx.append(te.index)
        P['현재 앙상블'].append(np.mean([ap.fit_predict(m, tr, te, T) for m in ap.ENSEMBLE], axis=0))
        Xtr, Xte = ap.prep(tr)[ap.S4], ap.prep(te)[ap.S4]
        med = Xtr.median(); Xtr, Xte = Xtr.fillna(med), Xte.fillna(med)
        wt = np.exp(-((pd.Timestamp(T) - tr.date).dt.days.values) / 365)
        for n in ['LightGBM', 'XGBoost', 'CatBoost', '랜덤포레스트']:
            P[n].append(mk(n).fit(Xtr, tr.y.values, sample_weight=wt).predict(Xte))
        Xtr2, Xte2 = Xtr.assign(trade_rel=TRADE_REL[tr.index].values), Xte.assign(trade_rel=TRADE_REL[te.index].values)
        for n in ['CatBoost', 'LightGBM']:
            P[n + '+비율'].append(mk(n).fit(Xtr2, tr.y.values, sample_weight=wt).predict(Xte2))
    ix = np.concatenate([np.asarray(i) for i in idx]); y = d.y.values[ix]; dt = d.date.values[ix]
    pred = {k: np.concatenate(v) for k, v in P.items()}
    pred['현재+CatBoost'] = (pred['현재 앙상블'] + pred['CatBoost']) / 2
    pred['현재+CatBoost+비율'] = (pred['현재 앙상블'] + pred['CatBoost+비율']) / 2
    pred['부스팅3종 평균'] = (pred['LightGBM'] + pred['XGBoost'] + pred['CatBoost']) / 3
    half = dt >= np.sort(dt)[len(dt) // 2]
    for k, p in pred.items():
        e = np.exp(y - p) - 1; allE[(sn, k)] = pd.Series(e, index=ix)
        rows.append(dict(시세=sn, 모델=k, 평균오차=round(np.abs(e).mean() * 100, 2), within5=round((np.abs(e) <= .05).mean() * 100, 1),
                         치우침=round(e.mean() * 100, 2), 앞절반=round(np.abs(e[~half]).mean() * 100, 2), 뒤절반=round(np.abs(e[half]).mean() * 100, 2)))
    print('done', sn, flush=True)
R = pd.DataFrame(rows).sort_values('평균오차')
print(R.to_string(index=False))
print(R.pivot(index='모델', columns='시세', values='평균오차').round(2).to_string())
R.to_csv(os.path.join(HERE, 'combo_bt_result.csv'), index=False)
pd.DataFrame({f'{a}|{b}': v for (a, b), v in allE.items()}).to_csv(os.path.join(HERE, 'combo_bt_rows.csv'))
