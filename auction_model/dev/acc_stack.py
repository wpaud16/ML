"""acc_bt.py 결과 묶기 (2026-11-15).
1) 앙상블: 단순 평균 / 과거 성적 상위 k 평균 / 과거 데이터로 가중치 학습(NNLS·LAD) — 가중치는 그 달 이전 예측만으로 정함
2) 신뢰도 선별: 그 물건 예측이 얼마나 틀릴지(모델 간 불일치·거래 수·같은 단지 기록 등)를 롤링으로 예측 → 확실한 것만 골랐을 때 오차
3) 낙찰 확률: 오차 분포를 전체 하나(운영) / 신뢰도 구간별 / 분위 회귀 로 잡았을 때 확률이 실제와 맞는지
  python dev/acc_stack.py [모델이름 ...]  (없으면 dev/acc_bt/P_*.csv 전부)"""
import os, sys, glob, warnings
import numpy as np, pandas as pd
from scipy.optimize import nnls, linprog
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import acc_bt as A
F, EV = A.F, A.EV
OUT = A.OUT
y = F.y

names = sys.argv[1:] or sorted(n for n in (os.path.basename(p)[2:-4] for p in glob.glob(os.path.join(OUT, 'P_*.csv'))) if not n.startswith('best'))
P = pd.DataFrame({n: pd.read_csv(os.path.join(OUT, f'P_{n}.csv'), index_col=0).p.reindex(F.index) for n in names})
c, raw = A.current(); P['운영'] = c
P = P.loc[:, P[EV].notna().all()]
P.loc[F.date < A.PRED_FROM] = np.nan
months = sorted(F.m0[P.notna().all(axis=1)].unique())   # 예측이 있는 모든 달 (평가 전 달도: 가중치·오차 풀 이력용)
mae = lambda e: np.abs(np.exp(e) - 1).mean() * 100


def lad_weights(X, t):
    """합 1, 0 이상 가중치로 절대오차 최소 (선형계획)."""
    n, k = X.shape
    cst = np.r_[np.zeros(k), np.ones(n), np.ones(n)]
    Aeq = np.c_[X, np.eye(n), -np.eye(n)]
    Aeq = np.r_[Aeq, np.r_[np.ones(k), np.zeros(2 * n)][None]]
    beq = np.r_[t, 1.0]
    r = linprog(cst, A_eq=Aeq, b_eq=beq, bounds=[(0, None)] * (k + 2 * n), method='highs')
    return r.x[:k] if r.success else np.ones(k) / k


def roll_combine(cols, how, hist=12, k=5):
    out = pd.Series(np.nan, index=F.index)
    for T in months:
        h = (F.m0 < T) & (F.m0 >= T - pd.DateOffset(months=hist)) & P[cols].notna().all(axis=1)
        t = F.m0 == T
        Xh, yh = P.loc[h, cols].values, y[h].values
        if how == 'mean' or h.sum() < 60:
            w = np.ones(len(cols)) / len(cols)
        elif how == 'topk':
            err = np.abs(np.exp(yh[:, None] - Xh) - 1).mean(0); w = np.zeros(len(cols)); w[np.argsort(err)[:k]] = 1 / k
        elif how == 'nnls':
            w, _ = nnls(Xh, yh); w = w / w.sum() if w.sum() > 0 else np.ones(len(cols)) / len(cols)
        elif how == 'lad':
            w = lad_weights(Xh, yh)
        out[t] = P.loc[t, cols].values @ w
    return out


rows = []
base_cols = [c for c in P.columns if c != '운영']
for nm in P.columns:
    rows.append(dict(name=nm, **A.score(P[nm])))
R1 = pd.DataFrame(rows).sort_values('mae')
print(R1.to_string(index=False))
top = [n for n in R1.name if n != '운영'][:8]
combos = {}
for how in ['mean', 'topk', 'nnls', 'lad']:
    for label, cols in [('전체', base_cols), ('상위8', top), ('상위8+운영', top + ['운영'])]:
        if how == 'topk' and len(cols) < 6: continue
        combos[f'{how}·{label}'] = roll_combine(cols, how)
for k_ in (3, 8):
    combos[f'topk{k_}·전체'] = roll_combine(base_cols + ['운영'], 'topk', k=k_)
rows = [dict(name=k, **A.score(v)) for k, v in combos.items()]
R2 = pd.DataFrame(rows).sort_values('mae')
print(R2.to_string(index=False))
best_name = R2.name.iloc[0]; best = combos[best_name]
FLOOR = np.log(F.low / F.mkt) + np.log(1.01)   # 낙찰가는 최저가 아래로 못 감 → 최저가 +1% 아래 예측은 올림
best = np.maximum(best, FLOOR).where(best.notna())
print('최저가 바닥 적용', best_name, A.score(best))
pd.DataFrame({'p': best}).to_csv(os.path.join(OUT, 'P_best_combo.csv'))

# ---------------- 2) 신뢰도 선별 ----------------
from sklearn.ensemble import HistGradientBoostingRegressor
res = y - best
spread = P[base_cols].std(axis=1)
C = pd.DataFrame({'spread': spread, 'dj_n': F.dj_n, 'n12': F.n12, 'neff': F.neff, 'disp': F.disp, 'fails': F.fails,
                  'l_appr': F.x_l_appr, 'l_low': F.x_l_low, 'l_mkt': F.x_l_mkt, 'hh': np.log(F.hh.clip(lower=10)), 'seoul': F.seoul,
                  'l_richgo': F.l_richgo.abs(), 'l_tr12f': F.l_tr12f.abs(), 'age': F.age, 'emd_n': F.emd_n, 'mom12': F.mom12,
                  'lag_m': F.lag_m, 'sgg_bid': F.sgg_bid})
pe = pd.Series(np.nan, index=F.index)   # 예측한 |오차|
for T in months:
    h = (F.m0 < T) & res.notna(); t = F.m0 == T
    if h.sum() < 150: continue
    m = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_depth=3, min_samples_leaf=30, loss='absolute_error', random_state=0)
    m.fit(C[h], res[h].abs()); pe[t] = m.predict(C[t])
ok = EV & pe.notna()
ae = (np.exp(res) - 1).abs()
sel = []
for cov in [100, 80, 60, 50, 40, 30, 20, 10]:
    th = pe[ok].quantile(cov / 100)
    m = ok & (pe <= th)
    sel.append(dict(포함비율=cov, 건수=int(m.sum()), 평균오차=round(ae[m].mean() * 100, 2), 이내3=round((ae[m] <= .03).mean() * 100, 1), 이내5=round((ae[m] <= .05).mean() * 100, 1)))
# 롤링 임계값: 과거 12개월에서 '선택된 것 평균오차 ≤ 3%' 되는 최대 비율의 임계값 → 이번 달에 적용
pick = pd.Series(False, index=F.index)
for T in months:
    h = (F.m0 < T) & (F.m0 >= T - pd.DateOffset(months=12)) & pe.notna() & res.notna(); t = (F.m0 == T) & pe.notna()
    if h.sum() < 100: continue
    o = pe[h].sort_values(); cm = ae[o.index].expanding().mean()
    good = cm[cm <= 0.03]
    if len(good) < 10: continue
    th = o[good.index[-1]]
    pick[t & (pe <= th)] = True
mm = EV & pick
roll_sel = dict(건수=int(mm.sum()), 비율=round(mm.sum() / EV.sum() * 100, 1), 평균오차=round(ae[mm].mean() * 100, 2), 이내3=round((ae[mm] <= .03).mean() * 100, 1))
S1 = pd.DataFrame(sel)
print(S1.to_string(index=False)); print('롤링 3% 선별', roll_sel)

# ---------------- 3) 낙찰 확률 ----------------
# 내 입찰가 b 로 낙찰 = b > 실제 낙찰가(1등가) 라고 보고 P(win|b) = P(res < log(b/mkt) - pred)
offs = np.linspace(-0.12, 0.12, 25)


def eval_prob(cdf):
    """cdf(i, g) -> P(res_i < g). 반환: 보정 오차(예측확률 구간별 실제 비율), CRPS 근사, 50% 입찰가 낙찰률·초과지불."""
    pr, hit = [], []
    crps = []
    win50, over50 = [], []
    for i in F.index[EV & best.notna()]:
        p_ = np.array([cdf(i, g) for g in offs]); h_ = (res[i] < offs).astype(float)
        pr += list(p_); hit += list(h_); crps.append(np.mean((p_ - h_) ** 2) * 0.24)
        # 50% 입찰가 (offs 보간)
        g50 = np.interp(0.5, np.maximum.accumulate(p_), offs)
        win50.append(res[i] < g50); over50.append((np.exp(g50 - res[i]) - 1) if res[i] < g50 else np.nan)
    pr, hit = np.array(pr), np.array(hit)
    bins = np.digitize(pr, [.1, .2, .3, .4, .5, .6, .7, .8, .9])
    cal = np.mean([abs(pr[bins == b].mean() - hit[bins == b].mean()) for b in range(10) if (bins == b).sum() > 50]) * 100
    return dict(보정오차_pp=round(cal, 2), CRPS=round(np.mean(crps) * 1000, 3), 낙찰률50=round(np.mean(win50) * 100, 1),
                초과지불50=round(np.nanmean(over50) * 100, 2))


def pool_cdf(group=None, hist=12, bw=0.012):
    cache = {}

    def f(i, g):
        T = F.m0[i]; key = (T, None if group is None else group[i])
        if key not in cache:
            h = (F.m0 < T) & (F.m0 >= T - pd.DateOffset(months=hist)) & res.notna()
            if group is not None:
                hg = h & (group == group[i])
                h = hg if hg.sum() >= 40 else h
            cache[key] = res[h].values
        pool = cache[key]
        from scipy.stats import norm
        return float(norm.cdf((g - pool) / bw).mean())
    return f


pe_q = pd.Series(np.nan, index=F.index)
for T in months:   # 신뢰도 구간 = 직전 데이터 기준 예측 |오차| 3분위
    h = (F.m0 < T) & pe.notna(); t = F.m0 == T
    if h.sum() < 60: pe_q[t] = 1; continue
    q1, q2 = pe[h].quantile([1 / 3, 2 / 3])
    pe_q[t] = np.where(pe[t] <= q1, 0, np.where(pe[t] <= q2, 1, 2))
pe_q = pe_q.fillna(1)
mband = pd.cut(F.mkt / 1e8, [0, 4, 6, 8, 10, 15, 999], labels=False)
abands = pd.cut(F.appr / F.mkt, [0, .9, 1.0, 1.1, 9], labels=False)
PR = []
for label, fn in [('전체 하나(운영 방식)', pool_cdf()), ('신뢰도 3구간별', pool_cdf(pe_q)), ('시세 금액대별', pool_cdf(mband)),
                  ('감정가/시세 구간별', pool_cdf(abands)), ('유찰 횟수별', pool_cdf(F.fails.clip(upper=2))),
                  ('최근 6개월만', pool_cdf(hist=6)), ('최근 24개월', pool_cdf(hist=24))]:
    r = eval_prob(fn); PR.append(dict(방식=label, **r)); print(label, r, flush=True)


# 신뢰도 비례 스케일: 잔차를 예측|오차|로 나눈 표준화 풀 × 이 물건 예측|오차|
def scaled_cdf():
    cache = {}
    z = res / pe.clip(lower=0.01)

    def f(i, g):
        T = F.m0[i]
        if T not in cache:
            h = (F.m0 < T) & (F.m0 >= T - pd.DateOffset(months=12)) & z.notna()
            cache[T] = z[h].values
        from scipy.stats import norm
        s = max(pe[i], 0.01) if pe[i] == pe[i] else 0.035
        return float(norm.cdf((g / s - cache[T]) / 0.3).mean())
    return f


r = eval_prob(scaled_cdf()); PR.append(dict(방식='신뢰도 비례 폭', **r)); print('신뢰도 비례 폭', r)


# 분위 회귀: 물건마다 낙찰가 분포(10~90%)를 직접 예측 (LightGBM quantile, 월별 롤링)
def qr_cdf():
    import lightgbm as lgb
    taus = [0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
    cols = A.S4 + A.EXTRA
    Q = pd.DataFrame(np.nan, index=F.index, columns=taus)
    for T in months:
        tr, te = F[(F.date < T)], F[F.m0 == T]
        if len(tr) < 150 or len(te) == 0: continue
        med = tr[cols].median(); Xtr, Xte = tr[cols].fillna(med), te[cols].fillna(med)
        wt = np.exp(-((T - tr.date).dt.days.values) / 365)
        for tau in taus:
            m = lgb.LGBMRegressor(objective='quantile', alpha=tau, n_estimators=300, learning_rate=0.03, num_leaves=7,
                                  min_child_samples=25, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=0)
            Q.loc[te.index, tau] = m.fit(Xtr, tr.y, sample_weight=wt).predict(Xte)
    Q = pd.DataFrame(np.sort(Q.values, axis=1), index=Q.index, columns=taus)   # 분위 교차 방지
    Q.to_csv(os.path.join(OUT, 'Q_quantile.csv'))
    R = Q.sub(best, axis=0)   # 잔차(실제-best) 기준 분위

    def f(i, g):
        q = R.loc[i].values
        if np.isnan(q).any(): return 0.5
        if g < q[0]: return 0.05 * max(0.0, 1 - (q[0] - g) / max(q[1] - q[0], 0.01) * 0.05 / 0.05 * 0.5)
        if g > q[-1]: return 1 - 0.05 * max(0.0, 1 - (g - q[-1]) / max(q[-1] - q[-2], 0.01) * 0.5)
        return float(np.interp(g, q, taus))
    return f, Q


try:
    fq, Q = qr_cdf()
    r = eval_prob(fq); PR.append(dict(방식='분위 회귀(물건별 분포)', **r)); print('분위 회귀', r)
    # 분위 회귀 중앙값을 중심 예측으로 쓰면
    print('분위 회귀 50% 중심', A.score(Q[0.5]))
except Exception as e:
    print('분위 회귀 실패', e)
PRT = pd.DataFrame(PR)

pd.to_pickle(dict(R1=R1, R2=R2, S1=S1, roll_sel=roll_sel, PRT=PRT, best=best_name), os.path.join(OUT, 'stack_result.pkl'))
print(PRT.to_string(index=False))
