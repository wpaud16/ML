"""주변 단지 상대가격 → 낙찰가율 예측 개선 백테스트 (2026-11-05).
운영 앙상블(부스팅_감쇠 + 군집별회귀)과 같은 학습 방식으로 2024-07부터 월별 시간 순 검증.
A = 현재 모델, B = + nb_rel(이 단지 평당가 ÷ 같은 동 비슷한 연식 단지 평당가 중앙값, 로그) + nb_rank(동 내 순위 비율)"""
import json, os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import auction_predictor as ap

NB = json.load(open(os.path.join(HERE, 'nearby_apt.json')))


def feats(d):
    v = NB.get(d) or {}
    rows = [r for r in v.get('rows') or [] if r[4]]
    me = next((r for r in rows if r[0] == d), None)
    if not me:
        return np.nan, np.nan
    oth = [r for r in rows if r[0] != d]
    for tol in (10, 15, None):
        pick = [r for r in oth if tol is None or me[1] is None or r[1] is None or abs(r[1] - me[1]) <= tol]
        if len(pick) >= 3: break
    if len(pick) < 2:
        return np.nan, np.nan
    return np.log(me[4] / np.median([r[4] for r in pick])), (v.get('rank') or me[5] or np.nan) / (v.get('total') or np.nan)


df = ap.load_train()
f = df.danji.map(feats)
df['nb_rel'] = [x[0] for x in f]; df['nb_rank'] = [x[1] for x in f]
print('rows', len(df), 'nb_rel 있음', df.nb_rel.notna().sum())
print(df.nb_rel.describe().round(3).to_dict())

orig_prep = ap.prep
def prep2(d):
    X = orig_prep(d); X['nb_rel'] = d['nb_rel'].values; X['nb_rank'] = d['nb_rank'].values
    return X

VARIANTS = {
    'A_현재': None,
    'B_주변상대가격': ['nb_rel', 'nb_rank'],
    'C_nb_rel만': ['nb_rel'],
}
base = dict(ap.MEMBERS)
res = {}
for name, extra in VARIANTS.items():
    ap.prep = prep2 if extra else orig_prep
    ap.MEMBERS['부스팅_감쇠'] = ('gb', ap.S4 + (extra or []), 365)
    ap.MEMBERS['군집별회귀'] = ('cluster', ap.S1 + (extra or []), 365)
    rows = []
    for T in pd.date_range('2024-07-01', df.date.max(), freq='MS'):
        tr, te = df[df.date < T], df[(df.date >= T) & (df.date < T + pd.DateOffset(months=1))]
        if len(te) == 0 or len(tr) < 100: continue
        p = np.mean([ap.fit_predict(m, tr, te, T) for m in ap.ENSEMBLE], axis=0)
        rows.append(te[['date', 'y', 'bidders', 'nb_rel', 'sd']].assign(err=np.exp(te.y.values - p) - 1))
    R = pd.concat(rows); res[name] = R
    ap.MEMBERS.update(base)
ap.prep = orig_prep

out = []
for name, R in res.items():
    e = R.err
    h = R[R.date >= R.date.quantile(0.5)].err
    out.append(dict(모델=name, n=len(R), 평균오차=round(e.abs().mean() * 100, 2), 오차중앙=round(e.abs().median() * 100, 2),
                    within5=round((e.abs() <= .05).mean() * 100, 1), 치우침=round(e.mean() * 100, 2),
                    뒤절반평균오차=round(h.abs().mean() * 100, 2)))
print(pd.DataFrame(out).to_string(index=False))
# 주변 대비 싼/비싼 단지별 치우침 (A 기준)
A = res['A_현재'].dropna(subset=['nb_rel'])
A['grp'] = pd.cut(A.nb_rel, [-9, -0.15, -0.05, 0.05, 0.15, 9], labels=['주변보다 15%+ 쌈', '5~15% 쌈', '비슷', '5~15% 비쌈', '15%+ 비쌈'])
print(A.groupby('grp').err.agg(n='size', 치우침=lambda x: round(x.mean() * 100, 2), 평균오차=lambda x: round(x.abs().mean() * 100, 2)).to_string())
pd.concat({k: v for k, v in res.items()}).to_csv(os.path.join(HERE, 'nearby_bt_result.csv'))
