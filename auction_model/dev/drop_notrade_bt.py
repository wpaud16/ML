"""실거래 1년 0건 매물 제외 (2026-11-05, 사용자 질문): ① 보여주기만 제외 ② 학습에서도 제외 — M 시세 + 현재 앙상블, 같은 시간 순 검증."""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import auction_predictor as ap
df = ap.load_train()
S = pd.read_csv(os.path.join(HERE, 'sise_bt_S.csv'), index_col=0).reindex(df.index)
RF_ = df.mkt * S.fprem_case.fillna(1)
w = (S.neff / (S.neff + 2)).clip(upper=0.7).fillna(0) * (1 - (S.disp.fillna(0.1) / 0.2).clip(0, 1) * 0.5)
M = w * S.tr12fw.fillna(RF_) + (1 - w) * RF_
has = S.tr12f.notna()
d = df.copy(); d['mkt'] = M.values
d['r_sell_mkt'] = d.sell / d.mkt; d['r_appr_mkt'] = d.appr / d.mkt; d['r_low_mkt'] = d.low / d.mkt; d['y'] = np.log(d.r_sell_mkt)
d['heat'] = [ap.recent_heat(d, s, t) for s, t in zip(d.seoul, d.date)]
d['loan_ratio'] = [ap.loan_ratio(t, s, g, x) for t, s, g, x in zip(d.date, d.sd, d.sgg, d.mkt)]
out = {}
for lab, keep in (('전체로 학습', d.index == d.index), ('실거래 있는 것만 학습', has.values)):
    ap._FIT.clear(); P, I = [], []
    for T in pd.date_range('2024-07-01', d.date.max(), freq='MS'):
        tr, te = d[(d.date < T) & keep], d[(d.date >= T) & (d.date < T + pd.DateOffset(months=1)) & has.values]
        if len(te) == 0 or len(tr) < 100: continue
        P.append(np.mean([ap.fit_predict(k, tr, te, T) for k in ap.ENSEMBLE], axis=0)); I.append(te.index)
    I = np.concatenate([np.asarray(x) for x in I]); e = np.exp(d.y[I].values - np.concatenate(P)) - 1
    out[lab] = e
    print(lab, '→ 실거래 있는 물건', len(e), '평균오차', round(np.abs(e).mean() * 100, 2), '±5% 안', round((np.abs(e) <= .05).mean() * 100, 1), '치우침', round(e.mean() * 100, 2), flush=True)
