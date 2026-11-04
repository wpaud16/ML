"""다른 모델 비교 백테스트 (2026-11-05). 운영과 같은 입력(S4)·같은 시간 순 월별 검증(2024-07~), 최근 사례 가중(1년 감쇠).
목표 = log(낙찰가 / 리치고 시세). 지표 = 낙찰가 평균 오차(%) 등."""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import auction_predictor as ap
from sklearn.ensemble import RandomForestRegressor, ExtraTreesRegressor
import lightgbm as lgb, xgboost as xgb
from catboost import CatBoostRegressor

df = ap.load_train()
COLS = ap.S4


def mk(name):
    if name == 'LightGBM': return lgb.LGBMRegressor(n_estimators=400, learning_rate=0.03, num_leaves=15, min_child_samples=20, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=2.0, verbose=-1, random_state=0)
    if name == 'XGBoost': return xgb.XGBRegressor(n_estimators=400, learning_rate=0.03, max_depth=3, subsample=0.8, colsample_bytree=0.8, reg_lambda=2.0, min_child_weight=5, random_state=0)
    if name == 'CatBoost': return CatBoostRegressor(iterations=600, learning_rate=0.04, depth=4, l2_leaf_reg=3, verbose=0, random_seed=0)
    if name == '랜덤포레스트': return RandomForestRegressor(400, min_samples_leaf=5, max_features=0.5, n_jobs=-1, random_state=0)
    if name == '엑스트라트리': return ExtraTreesRegressor(400, min_samples_leaf=5, max_features=0.6, n_jobs=-1, random_state=0)


P = {k: [] for k in ['현재 앙상블', 'LightGBM', 'XGBoost', 'CatBoost', '랜덤포레스트', '엑스트라트리']}
idx = []
for T in pd.date_range('2024-07-01', df.date.max(), freq='MS'):
    tr, te = df[df.date < T], df[(df.date >= T) & (df.date < T + pd.DateOffset(months=1))]
    if len(te) == 0 or len(tr) < 100: continue
    idx.append(te.index)
    P['현재 앙상블'].append(np.mean([ap.fit_predict(m, tr, te, T) for m in ap.ENSEMBLE], axis=0))
    Xtr, Xte = ap.prep(tr)[COLS], ap.prep(te)[COLS]
    med = Xtr.median(); Xtr, Xte = Xtr.fillna(med), Xte.fillna(med)
    w = np.exp(-((pd.Timestamp(T) - tr.date).dt.days.values) / 365)
    for n in list(P)[1:]:
        P[n].append(mk(n).fit(Xtr, tr.y.values, sample_weight=w).predict(Xte))
    print(T.date(), len(te), flush=True)
ix = np.concatenate([np.asarray(i) for i in idx]); y = df.y.values[ix]; d = df.date.values[ix]
pred = {k: np.concatenate(v) for k, v in P.items()}
pred['현재+CatBoost'] = (pred['현재 앙상블'] + pred['CatBoost']) / 2
pred['현재+LightGBM'] = (pred['현재 앙상블'] + pred['LightGBM']) / 2
pred['부스팅3종 평균'] = (pred['LightGBM'] + pred['XGBoost'] + pred['CatBoost']) / 3
pred['전체 평균'] = np.mean([pred[k] for k in ['현재 앙상블', 'LightGBM', 'XGBoost', 'CatBoost', '랜덤포레스트']], axis=0)
half = d >= np.quantile(d.astype('int64'), .5).astype('datetime64[ns]')
rows = []
for k, p in pred.items():
    e = np.exp(y - p) - 1
    rows.append(dict(모델=k, 평균오차=round(np.abs(e).mean() * 100, 2), 오차중앙=round(np.median(np.abs(e)) * 100, 2),
                     within5=round((np.abs(e) <= .05).mean() * 100, 1), 치우침=round(e.mean() * 100, 2), 뒤절반=round(np.abs(e[half]).mean() * 100, 2)))
R = pd.DataFrame(rows).sort_values('평균오차'); print(R.to_string(index=False))
pd.DataFrame({k: np.exp(y - p) - 1 for k, p in pred.items()}, index=ix).assign(date=d).to_csv(os.path.join(HERE, 'models_bt_result.csv'))
