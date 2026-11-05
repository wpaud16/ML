"""실거래 없는 단지 시세 보완 (2026-11-05, 사용자 질문: 부영그린타운3차 — 유찰됐는데 왜 높게 예측했나).
1년 실거래가 0건이면 M 시세 = 리치고뿐 → 감정가(평가 이후 단지 추세 보정)와 섞어 본다. 현재 앙상블, 같은 시간 순 검증."""
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
notr = S.tr12f.isna()
# 감정 시점 이후 추세: lag_m 개월 동안 mom12 의 비율만큼 (단지 시세 지수 기반)
appr_adj = df.appr * (1 + df.mom12.fillna(0) * (df.lag_m.fillna(12).clip(upper=24) / 12))
V = {'M': M}
for a in (0.3, 0.5):
    V[f'M+감정가{int(a*100)}%(실거래 없을 때)'] = M.where(~notr, (1 - a) * RF_ + a * appr_adj)
V['M+감정가30%(실거래 적을 때 w<0.3까지)'] = M.where(w >= 0.3, (1 - 0.3 * (1 - w / 0.3)) * M + 0.3 * (1 - w / 0.3) * appr_adj)


def run(mkt):
    d = df.copy(); d['mkt'] = mkt.values
    d['r_sell_mkt'] = d.sell / d.mkt; d['r_appr_mkt'] = d.appr / d.mkt; d['r_low_mkt'] = d.low / d.mkt; d['y'] = np.log(d.r_sell_mkt)
    d['heat'] = [ap.recent_heat(d, s, t) for s, t in zip(d.seoul, d.date)]
    d['loan_ratio'] = [ap.loan_ratio(t, s, g, x) for t, s, g, x in zip(d.date, d.sd, d.sgg, d.mkt)]
    ap._FIT.clear(); P, I = [], []
    for T in pd.date_range('2024-07-01', d.date.max(), freq='MS'):
        tr, te = d[d.date < T], d[(d.date >= T) & (d.date < T + pd.DateOffset(months=1))]
        if len(te) == 0 or len(tr) < 100: continue
        P.append(np.mean([ap.fit_predict(k, tr, te, T) for k in ap.ENSEMBLE], axis=0)); I.append(te.index)
    I = np.concatenate([np.asarray(x) for x in I]); p = np.concatenate(P)
    return pd.Series(np.exp(d.y.values[df.index.get_indexer(I)] - p) - 1, index=I)


rows = []
for k, v in V.items():
    e = run(v); nt = notr.reindex(e.index)
    step = (df.low / df.appr) ** (1 / df.fails.clip(lower=1)); prev = (df.low / step).reindex(e.index)
    pred = df.sell.reindex(e.index) / (1 + e)
    capped = np.where((df.fails.reindex(e.index) >= 1) & (pred > prev * 1.05), prev * 1.05, pred)
    ec = df.sell.reindex(e.index) / capped - 1
    rows.append(dict(시세=k, 평균오차=round(e.abs().mean() * 100, 2), 실거래없는건=round(e[nt].abs().mean() * 100, 2), 없는건_치우침=round(e[nt].mean() * 100, 2),
                     직전가105상한=round(np.abs(ec).mean() * 100, 2), n없는건=int(nt.sum())))
    print(rows[-1], flush=True)
pd.DataFrame(rows).to_csv(os.path.join(HERE, 'notrade_bt_result.csv'), index=False)
