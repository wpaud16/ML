"""지역 열기 백테스트 (2026-11-05, 64236·3470 사례: 송파·남양주처럼 특히 뜨거운 구를 서울 전체 heat 가 못 잡음).
각 사례 날짜 '이전' 낙찰만으로: heat_gu = 같은 구 최근 180일 낙찰가율(시세 대비) 중앙값을 구 사례 수로 축소(k=5)해 광역 heat 쪽으로,
bid_gu = 같은 구 최근 180일 입찰 인원 중앙값(로그)."""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import auction_predictor as ap

df = ap.load_train()
hg, bg, ng = [], [], []
for i, r in df.iterrows():
    past = df[(df.date < r.date) & (df.date >= r.date - pd.Timedelta(days=180))]
    g = past[(past.sd == r.sd) & (past.sgg == r.sgg)]
    reg = past[past.seoul == r.seoul]
    base = reg.r_sell_mkt.median() if len(reg) else np.nan
    n = len(g); k = 5
    hg.append(np.log((n * g.r_sell_mkt.median() + k * base) / (n + k)) if n and base == base else (np.log(base) if base == base else np.nan))
    b = g.bidders.dropna()
    bg.append(np.log(b.median()) if len(b) >= 3 else np.nan); ng.append(n)
df['heat_gu'] = hg; df['bid_gu'] = bg; df['n_gu'] = ng
print('heat_gu 있음', df.heat_gu.notna().sum(), 'bid_gu 있음', df.bid_gu.notna().sum())

orig = ap.prep
def prep2(d):
    X = orig(d); X['heat_gu'] = d.heat_gu.values; X['bid_gu'] = d.bid_gu.values
    return X
base = dict(ap.MEMBERS); res = {}
for name, extra in {'A_현재': [], 'B_heat_gu': ['heat_gu'], 'C_heat_gu+bid_gu': ['heat_gu', 'bid_gu']}.items():
    ap.prep = prep2 if extra else orig; ap._FIT.clear()
    ap.MEMBERS['부스팅_감쇠'] = ('gb', ap.S4 + extra, 365); ap.MEMBERS['군집별회귀'] = ('cluster', ap.S1 + extra, 365)
    rows = []
    for T in pd.date_range('2024-07-01', df.date.max(), freq='MS'):
        tr, te = df[df.date < T], df[(df.date >= T) & (df.date < T + pd.DateOffset(months=1))]
        if len(te) == 0 or len(tr) < 100: continue
        p = np.mean([ap.fit_predict(m, tr, te, T) for m in ap.ENSEMBLE], axis=0)
        rows.append(te[['date', 'sgg', 'r_appr_mkt', 'mom12', 'bidders']].assign(err=np.exp(te.y.values - p) - 1))
    res[name] = pd.concat(rows); ap.MEMBERS.update(base)
for name, R in res.items():
    seg = R[(R.r_appr_mkt < .85) & (R.mom12 > .08)]; h = R[R.date >= R.date.quantile(.5)]; big = R[R.bidders >= 10]
    print(name, '전체 %.2f%%' % (R.err.abs().mean() * 100), '±5%%안 %.1f%%' % ((R.err.abs() <= .05).mean() * 100),
          '| 감정후상승 %d건 치우침 %+.1f%% 오차 %.1f%%' % (len(seg), seg.err.mean() * 100, seg.err.abs().mean() * 100),
          '| 10명+ %d건 치우침 %+.1f%%' % (len(big), big.err.mean() * 100), '| 뒤절반 %.2f%%' % (h.err.abs().mean() * 100))
pd.concat(res).to_csv(os.path.join(HERE, 'local_heat_bt_result.csv'))
