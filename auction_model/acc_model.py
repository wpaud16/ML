"""정확도 개선 앙상블 + '3% 안 확률' (2026-11-15, 사용자 결정 A: 셋 다 반영).
근거: dev/acc_bt/REPORT.md — 아파트 987건 월별 롤링 백테스트
  - 중심 예측 = 운영 예측(앙상블+구별+상승형+소규모) 과 추가 피처 모델 8개(랜덤포레스트 6·LightGBM 2) 평균, 최저가 +1% 바닥
    → 평균 오차 4.58 → 4.31%
  - '3% 안 확률' = 그 물건 예측이 실제 낙찰가 ±3% 안에 들 확률 (랜덤포레스트 분류, 백테스트 오차로 학습)
    직전 6개월 물건 중 상위 20% 경계(acc_config.json within3_th) 이상이면 '정밀' → 그 그룹 평균 오차 2.84%
  - 확률표: 새 중심 예측의 최근 12개월 오차 분포(pool_all), 정밀 물건은 정밀 그룹끼리의 분포(pool_precise)
추가 피처: 실거래 세부(s_*: molit.sise_feat), 리치고/M 차이, 최저가/감정가, 같은 단지 과거 낙찰, 동·구 최근 낙찰가율, 구 평균 응찰자 등
— 모두 그 물건 매각일 이전 정보만.
재계산: python acc_model.py calibrate  (retrain.py 가 학습 데이터 추가 후 자동 실행, 약 10분)"""
import os, sys, json, time
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import auction_predictor as ap

CFG_PATH = os.path.join(HERE, 'acc_config.json')
W3_PATH = os.path.join(HERE, 'acc_within3_train.csv')
S4 = ['x_' + c for c in ap.S4]
EXTRA = ['low_appr', 'l_richgo', 'l_tr12f', 'l_last', 'last_age', 'l_tr3', 'n12', 'neff', 'disp', 'l_appr_tr',
         'dj_n', 'dj_ys', 'dj_age', 'emd_ys', 'emd_n', 'sgg_ys', 'sgg_n', 'sgg_bid', 'all_bid', 'fail_y', 'l_mktm2']
SISE = ['l_richgo', 'l_tr12f', 'l_last', 'last_age', 'n12', 'neff', 'disp', 'l_appr_tr', 'low_appr']
RF = dict(n_estimators=500, min_samples_leaf=5, max_features=0.5)
MEMBERS = {   # 백테스트 상위 8개 (dev/acc_bt.py 같은 이름)
    'rf_X_leaf3': ('rf', S4 + EXTRA, 365, dict(RF, min_samples_leaf=3, max_features=0.33)),
    'rf_X_d730': ('rf', S4 + EXTRA, 730, RF),
    'rf_S4X': ('rf', S4 + EXTRA, 365, RF),
    'rf_X_leaf8': ('rf', S4 + EXTRA, 365, dict(RF, min_samples_leaf=8)),
    'lgb_S4X_l1': ('lgb', S4 + EXTRA, 365, dict(objective='l1')),
    'rf_X_mae': ('rf', S4 + EXTRA, 365, dict(RF, criterion='absolute_error', n_estimators=300)),
    'rf_S4sise': ('rf', S4 + SISE, 365, RF),
    'lgb_X_dart': ('lgb', S4 + EXTRA, 365, dict(boosting_type='dart', n_estimators=400, learning_rate=0.05)),
}
FLOOR = 1.01   # 낙찰가는 최저가 아래로 못 감 → 최저가 +1% 아래 예측은 올림
W3_COLS = ['spread', 'rng', 'dj_n', 'n12', 'neff', 'disp', 'fails', 'l_appr', 'l_low', 'l_mkt', 'hh', 'seoul', 'lr', 'lt', 'age', 'mom12', 'lag', 'gap']


# ---------------- 피처 ----------------
def _base(df):
    F = df.copy().reset_index(drop=True)
    for c in ap.ACC_S_COLS + ['mkt_richgo', 'bidders']:
        if c not in F: F[c] = np.nan
    F['seoul'] = (F.sd == '서울').astype(int)
    if 'y' not in F: F['y'] = np.log(F.sell / F.mkt) if 'sell' in F else np.nan
    X = ap.prep(F)
    F = pd.concat([F, X.add_prefix('x_')], axis=1)
    F['low_appr'] = F.low / F.appr
    F['l_richgo'] = np.log(F.mkt_richgo / F.mkt)
    F['l_tr12f'] = np.log(F.s_tr12f / F.mkt); F['l_last'] = np.log(F.s_last / F.mkt); F['last_age'] = F.s_last_age_m
    F['l_tr3'] = np.log(F.s_tr3 / F.mkt); F['n12'] = F.s_n12; F['neff'] = F.s_neff; F['disp'] = F.s_disp
    F['l_appr_tr'] = np.log(F.appr / F.s_tr12); F['l_mktm2'] = np.log(F.mkt / F.area)
    return F


def _cum(F, H, rows):
    """rows 각각에 대해 H(과거 낙찰, y 있음) 중 그 날짜 이전 사례로 누적 피처 계산."""
    hd, hy, hdj = H.date.values, H.y.values, H.danji.values
    hemd, hsgg, hsd, hf, hs, hb = H.emd.values, H.sgg.values, H.sd.values, H.fails.values, H.seoul.values, H.bidders.values.astype(float)
    hrl = np.log(H.sell / H.low).values
    out = {k: np.full(len(rows), np.nan) for k in ['dj_n', 'dj_y', 'dj_age', 'emd_y', 'emd_n', 'sgg_y', 'sgg_n', 'sgg_bid', 'all_bid', 'fail_y']}
    for j, i in enumerate(rows):
        r = F.loc[i]; d = np.datetime64(r.date)
        prev = hd < d
        out['dj_n'][j] = 0; out['emd_n'][j] = 0; out['sgg_n'][j] = 0
        if not prev.any(): continue
        m = prev & (hdj == r.danji)
        if m.any():
            out['dj_n'][j] = m.sum(); out['dj_y'][j] = hy[m][-3:].mean(); out['dj_age'][j] = (d - hd[m][-1]) / np.timedelta64(30, 'D')
        w365 = prev & (hd >= d - np.timedelta64(365, 'D'))
        m = w365 & (hemd == r.emd) & (hsgg == r.sgg)
        out['emd_n'][j] = m.sum(); out['emd_y'][j] = np.median(hy[m]) if m.any() else np.nan
        w180 = prev & (hd >= d - np.timedelta64(180, 'D'))
        m = w180 & (hsgg == r.sgg) & (hsd == r.sd)
        out['sgg_n'][j] = m.sum(); out['sgg_y'][j] = np.median(hy[m]) if m.any() else np.nan
        mb = m & ~np.isnan(hb); out['sgg_bid'][j] = hb[mb].mean() if mb.any() else np.nan
        mb2 = w180 & ~np.isnan(hb); out['all_bid'][j] = hb[mb2].mean() if mb2.any() else np.nan
        mf = w180 & (hf == r.fails) & (hs == r.seoul)
        out['fail_y'][j] = np.median(hy[mf]) if mf.sum() >= 5 else np.nan
    for k, v in out.items(): F.loc[rows, k] = v
    hl = np.log(F.loc[rows, 'heat'].astype(float))
    F.loc[rows, 'emd_ys'] = (F.loc[rows, 'emd_y'].fillna(hl) * F.loc[rows, 'emd_n'] + hl * 5) / (F.loc[rows, 'emd_n'] + 5)
    F.loc[rows, 'sgg_ys'] = (F.loc[rows, 'sgg_y'].fillna(hl) * F.loc[rows, 'sgg_n'] + hl * 8) / (F.loc[rows, 'sgg_n'] + 8)
    F.loc[rows, 'dj_ys'] = (F.loc[rows, 'dj_y'].fillna(hl) * F.loc[rows, 'dj_n'] + hl * 2) / (F.loc[rows, 'dj_n'] + 2)
    return F


_TRF = {}


def train_frame(df):
    key = (len(df), str(df.date.max()), float(df.sell.sum()))
    if key not in _TRF:
        F = _base(df); F = _cum(F, F, list(F.index)); _TRF.clear(); _TRF[key] = F
    return _TRF[key]


# ---------------- 모델 ----------------
def _model(kind, p):
    if kind == 'rf':
        from sklearn.ensemble import RandomForestRegressor
        return RandomForestRegressor(n_jobs=-1, random_state=0, **p)
    import lightgbm as lgb
    return lgb.LGBMRegressor(**{**dict(n_estimators=500, learning_rate=0.03, num_leaves=15, min_child_samples=20, subsample=0.8, subsample_freq=1,
                                     colsample_bytree=0.8, reg_lambda=2.0, verbose=-1, random_state=0), **p})


def fit_members(tr, T):
    fits = {}
    for nm, (kind, cols, decay, p) in MEMBERS.items():
        X = tr[cols].astype(float); med = X.median()
        wt = np.exp(-((pd.Timestamp(T) - tr.date).dt.days.values) / decay)
        fits[nm] = (cols, med, _model(kind, p).fit(X.fillna(med), tr.y.values, sample_weight=wt))
    return fits


def predict_members(fits, te):
    return pd.DataFrame({nm: m.predict(te[cols].astype(float).fillna(med)) for nm, (cols, med, m) in fits.items()}, index=te.index)


def w3_frame(te, Pm, c_new):
    gap = c_new - (np.log(te.low / te.mkt) + np.log(FLOOR))
    return pd.DataFrame({'spread': Pm.std(axis=1, ddof=1), 'rng': Pm.max(axis=1) - Pm.min(axis=1), 'dj_n': te.dj_n, 'n12': te.n12, 'neff': te.neff,
                         'disp': te.disp, 'fails': te.fails, 'l_appr': te.x_l_appr, 'l_low': te.x_l_low, 'l_mkt': te.x_l_mkt,
                         'hh': np.log(te.hh.astype(float).clip(lower=10)), 'seoul': te.seoul, 'lr': te.l_richgo.abs(), 'lt': te.l_tr12f.abs(),
                         'age': te.age, 'mom12': te.mom12, 'lag': te.lag_m, 'gap': gap}, index=te.index)[W3_COLS].astype(float).fillna(-1)


def _w3_model(tab):
    from sklearn.ensemble import RandomForestClassifier
    return RandomForestClassifier(400, min_samples_leaf=10, max_features=0.5, n_jobs=-1, random_state=0).fit(tab[W3_COLS], tab.hit.astype(int))


# ---------------- 운영(매일) ----------------
_RUN = {}


def predict(df, row, c_op):
    """df: 학습 데이터(load_train), row: target_row 결과(1행, danji·s_* 포함), c_op: 운영 최종 중심(log 낙찰가/시세).
    반환 dict(c_new, members, within3, precise, pool, note)."""
    cfg = _RUN.get('cfg')
    if cfg is None:
        cfg = _RUN['cfg'] = json.load(open(CFG_PATH, encoding='utf-8'))
    Ftr = train_frame(df)
    key = ('fit', len(Ftr), str(Ftr.date.max()))
    if _RUN.get('fkey') != key:
        T = pd.Timestamp.today().normalize()
        _RUN['fits'] = fit_members(Ftr, T); _RUN['fkey'] = key
        _RUN['w3'] = _w3_model(pd.read_csv(W3_PATH))
    r = row.copy()
    r['sell'] = np.nan
    te = _base(pd.concat([Ftr[[c for c in r.columns if c in Ftr.columns]].iloc[:0], r], ignore_index=True))
    te = _cum(te, Ftr, list(te.index))
    Pm = predict_members(_RUN['fits'], te)
    fl = float(np.log(te.low.iloc[0] / te.mkt.iloc[0]) + np.log(FLOOR))
    c_new = max(float(np.mean(list(Pm.iloc[0].values) + [c_op])), fl)
    Pm2 = Pm.assign(op=c_op)
    p3 = float(_RUN['w3'].predict_proba(w3_frame(te, Pm2, c_new))[0, 1])
    precise = p3 >= cfg['within3_th']
    return dict(c_new=c_new, floor_applied=bool(c_new == fl), members={k: round(float(v), 4) for k, v in Pm2.iloc[0].items()},
                within3=round(p3, 3), precise=bool(precise), pool=cfg['pool_precise'] if precise else cfg['pool_all'],
                within3_th=cfg['within3_th'])


# ---------------- 재계산(월 1회) ----------------
def _op_rolling(df):
    """운영 예측 롤링 (dev/band_bt.py 와 같은 방식)."""
    df = df.copy(); df['m0'] = df.date.dt.to_period('M').dt.to_timestamp(); df['g'] = df.sd + ' ' + df.sgg.fillna('')
    raw = pd.Series(np.nan, index=df.index)
    for T in pd.date_range('2023-07-01', df.date.max(), freq='MS'):
        tr, te = df[df.date < T], df[(df.date >= T) & (df.date < T + pd.DateOffset(months=1))]
        if len(te) == 0 or len(tr) < 100: continue
        raw[te.index] = np.mean([ap.fit_predict(m, tr, te, T) for m in ap.ENSEMBLE], axis=0)
    res = df.y - raw; c = raw.copy()
    for T in df.m0[raw.notna()].unique():
        h = df[(df.m0 < T) & (df.m0 >= T - pd.DateOffset(months=ap.SGG_W)) & raw.notna()]
        if len(h) < 100: continue
        st = res[h.index].groupby(h.g).agg(['mean', 'size'])
        adj = st['mean'] * st['size'] / (st['size'] + ap.SGG_K)
        t = (df.m0 == T) & raw.notna()
        c[t] = raw[t] + df.g[t].map(adj).fillna(0).values
    gap = (df.r_appr_mkt < 0.85) & (df.mom12.fillna(0) > 0.08) & (df.heat > 0)
    c[gap] = np.log(df.heat[gap])
    return c + np.where(df.hh.notna() & (df.hh < ap.SMALL_HH), np.log(1 + ap.SMALL_ADJ), 0.0)


def calibrate(start='2023-10-01', log=print):
    t0 = time.time()
    df = ap.load_train(); F = train_frame(df); F['m0'] = F.date.dt.to_period('M').dt.to_timestamp()
    op = _op_rolling(df).reindex(F.index)
    log(f'운영 롤링 {time.time() - t0:.0f}s')
    P = pd.DataFrame(np.nan, index=F.index, columns=list(MEMBERS))
    for T in pd.date_range(start, F.date.max(), freq='MS'):
        tr, te = F[F.date < T], F[F.m0 == T]
        if len(te) == 0 or len(tr) < 100: continue
        P.loc[te.index] = predict_members(fit_members(tr, T), te).values
    log(f'모델 롤링 {time.time() - t0:.0f}s')
    P['op'] = op
    fl = np.log(F.low / F.mkt) + np.log(FLOOR)
    ok = P.notna().all(axis=1)
    c_new = np.maximum(P[ok].mean(axis=1), fl[ok]).reindex(F.index)
    res = F.y - c_new; ae = (np.exp(res) - 1).abs()
    C = w3_frame(F[ok], P[ok], c_new[ok]).reindex(F.index)
    tab = C.assign(hit=(ae <= 0.03).astype(int), date=F.date, m0=F.m0, res=res)[ok]
    # 롤링 3% 확률 → 정밀 선별(직전 6개월 상위 20%) → 경계값·오차 풀
    months = sorted(tab.m0.unique()); pc = pd.Series(np.nan, index=tab.index)
    for T in months:
        h, t = tab.m0 < T, tab.m0 == T
        if h.sum() < 150: continue
        pc[t] = _w3_model(tab[h]).predict_proba(tab.loc[t, W3_COLS])[:, 1]
    sel = pd.Series(False, index=tab.index)
    for T in months:
        h = pc.notna() & (tab.m0 < T) & (tab.m0 >= T - pd.DateOffset(months=6)); t = tab.m0 == T
        if h.sum() >= 50: sel[t & (pc >= pc[h].quantile(0.8))] = True
    last = tab.m0.max()
    th = float(pc[pc.notna() & (tab.m0 > last - pd.DateOffset(months=6))].quantile(0.8))
    r12 = tab.m0 > last - pd.DateOffset(months=12)
    pool_all = tab.res[r12].round(5).tolist()
    ps = tab.res[r12 & sel]
    if len(ps) < 40: ps = tab.res[(tab.m0 > last - pd.DateOffset(months=24)) & sel]
    ev = pc.notna()
    cfg = dict(built=str(pd.Timestamp.today().date()), n_train=int(len(df)), within3_th=round(th, 4),
               pool_all=pool_all, pool_precise=ps.round(5).tolist(),
               mape_new=round(float(ae[ok & (F.date >= '2024-07-01')].mean() * 100), 2),
               mape_op=round(float((np.exp(F.y - op) - 1).abs()[ok & (F.date >= '2024-07-01')].mean() * 100), 2),
               mape_precise=round(float(ae[sel[sel].index].mean() * 100), 2) if sel.any() else None,
               precise_share=round(float(sel[ev].mean() * 100), 1),
               mape_recent12=round(float((np.exp(tab.res[r12]) - 1).abs().mean() * 100), 2),
               members=list(MEMBERS), note='dev/acc_bt/REPORT.md')
    tab.drop(columns=['m0']).to_csv(W3_PATH, index_label='i')
    json.dump(cfg, open(CFG_PATH, 'w', encoding='utf-8'), ensure_ascii=False)
    log(f"acc calibrate {time.time() - t0:.0f}s: 새 {cfg['mape_new']}% (운영 {cfg['mape_op']}%), 정밀 {cfg['mape_precise']}% ({cfg['precise_share']}%), 경계 {th:.3f}")
    _RUN.clear()
    return cfg


if __name__ == '__main__':
    if sys.argv[1:2] == ['calibrate']:
        calibrate()
