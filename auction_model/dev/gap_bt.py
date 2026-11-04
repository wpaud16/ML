"""감정 후 시세 상승(감정가 < 시세) 물건 과소예측 보정 백테스트 (2026-11-05, 2024타경3470 사례).
A 현재 / B + gap_up(=max(0,-log 감정/시세) × max(0,1년 상승률)) / C + gap(=max(0,-log 감정/시세)) + gap_up"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import auction_predictor as ap

df = ap.load_train()
orig = ap.prep
def prep2(d):
    X = orig(d)
    gap = np.clip(-np.log(d.r_appr_mkt.values), 0, None)
    X['gap'] = gap; X['gap_up'] = gap * np.clip(d.mom12.values, 0, None) * 10
    return X
base = dict(ap.MEMBERS); res = {}
for name, extra in {'A_현재': [], 'B_gap_up': ['gap_up'], 'C_gap+gap_up': ['gap', 'gap_up']}.items():
    ap.prep = prep2 if extra else orig
    ap.MEMBERS['부스팅_감쇠'] = ('gb', ap.S4 + extra, 365); ap.MEMBERS['군집별회귀'] = ('cluster', ap.S1 + extra, 365)
    rows = []
    for T in pd.date_range('2024-07-01', df.date.max(), freq='MS'):
        tr, te = df[df.date < T], df[(df.date >= T) & (df.date < T + pd.DateOffset(months=1))]
        if len(te) == 0 or len(tr) < 100: continue
        p = np.mean([ap.fit_predict(m, tr, te, T) for m in ap.ENSEMBLE], axis=0)
        rows.append(te[['date', 'r_appr_mkt', 'mom12']].assign(err=np.exp(te.y.values - p) - 1))
    res[name] = pd.concat(rows); ap.MEMBERS.update(base)
for name, R in res.items():
    seg = R[(R.r_appr_mkt < .85) & (R.mom12 > .08)]; h = R[R.date >= R.date.quantile(.5)]
    print(name, '전체 %.2f%%' % (R.err.abs().mean() * 100), '±5%%안 %.1f%%' % ((R.err.abs() <= .05).mean() * 100),
          '| 해당유형 %d건 치우침 %+.1f%% 오차 %.1f%%' % (len(seg), seg.err.mean() * 100, seg.err.abs().mean() * 100),
          '| 뒤절반 %.2f%%' % (h.err.abs().mean() * 100))
pd.concat(res).to_csv(os.path.join(HERE, 'gap_bt_result.csv'))
