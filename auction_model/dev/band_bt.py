"""금액대별 백테스트 (2026-11-15, 사용자 요청: 금액대를 잘게 나누고, 기준을 감정가·시세·실거래가 등 여러 가지로, 섞어서도).
1) 운영 방식 그대로(앙상블 + 구별 보정 + 상승형 규칙 + 소규모 -3%) 2024-07~ 월별 롤링 예측 → 물건별 오차
2) 기준 여러 개 × 구간(고정 억 단위 / 10·20분위 / 교차) 별 평균 오차·치우침·5% 이내 비율
3) 구간별 치우침 보정(직전 12개월, 축소 k=15)을 롤링으로 넣으면 전체 오차가 줄어드는지
4) 구간별로 과거에 가장 잘 맞던 시세·모델 조합을 고르는 방식(dev/combo_bt_rows.csv 재사용)이 나은지
지표: 오차 = 실제 낙찰가 / 예측 중심 - 1. 결과: dev/band_bt_result.md, dev/band_bt_rows.csv"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import auction_predictor as ap

START = '2024-07-01'
df = ap.load_train()
S = pd.read_csv(os.path.join(HERE, 'sise_bt_S.csv'), index_col=0).reindex(df.index)
df['m0'] = df.date.dt.to_period('M').dt.to_timestamp()
df['g'] = df.sd + ' ' + df.sgg.fillna('')

# ---------- 1) 운영 방식 롤링 예측 ----------
ROWS = os.path.join(HERE, 'band_bt_rows.csv')
if os.path.exists(ROWS) and os.environ.get('REBUILD') != '1':
    P = pd.read_csv(ROWS, index_col=0)
    raw, c = P.raw.reindex(df.index), P.c.reindex(df.index)
else:
    raw = pd.Series(np.nan, index=df.index)
    for T in pd.date_range('2023-07-01', df.date.max(), freq='MS'):   # 구별 보정용으로 1년 앞부터
        tr, te = df[df.date < T], df[(df.date >= T) & (df.date < T + pd.DateOffset(months=1))]
        if len(te) == 0 or len(tr) < 100: continue
        raw[te.index] = np.mean([ap.fit_predict(m, tr, te, T) for m in ap.ENSEMBLE], axis=0)
        print('fit', T.date(), flush=True)
    res = df.y - raw
    c = raw.copy()
    for T in df.m0[raw.notna()].unique():          # 구별 보정 (calibrate 와 같은 방식)
        h = df[(df.m0 < T) & (df.m0 >= T - pd.DateOffset(months=ap.SGG_W)) & raw.notna()]
        if len(h) < 100: continue
        st = res[h.index].groupby(h.g).agg(['mean', 'size'])
        adj = st['mean'] * st['size'] / (st['size'] + ap.SGG_K)
        t = (df.m0 == T) & raw.notna()
        c[t] = raw[t] + df.g[t].map(adj).fillna(0).values
    gap = (df.r_appr_mkt < 0.85) & (df.mom12.fillna(0) > 0.08) & (df.heat > 0)
    c[gap] = np.log(df.heat[gap])
    c = c + np.where(df.hh.notna() & (df.hh < ap.SMALL_HH), np.log(1 + ap.SMALL_ADJ), 0.0)
    pd.DataFrame({'raw': raw, 'c': c}).to_csv(ROWS)

ev = df.date >= START
D = df[ev].copy(); D['c'] = c[ev]
D['pred'] = D.mkt * np.exp(D.c)
D['e'] = D.sell / D.pred - 1
D['res'] = D.y - D.c
print('운영 방식 전체', len(D), f'{D.e.abs().mean()*100:.2f}%')

# ---------- 2) 기준 ----------
E = 1e8
Sx = S[ev]
crit = {
    '감정가': D.appr / E,
    '최저가': D.low / E,
    'M 시세(운영)': D.mkt / E,
    '리치고 시세': D.mkt_richgo / E,
    '실거래 12개월 평균': Sx.tr12 / E,
    '최근 실거래 1건': Sx['last'] / E,
    '예측가(모델)': D.pred / E,
    '실제 낙찰가(사후·참고)': D.sell / E,
    # 섞기
    '감정가·시세 평균': (D.appr + D.mkt) / 2 / E,
    '감정가·시세·실거래 평균': pd.concat([D.appr, D.mkt, Sx.tr12.fillna(D.mkt)], axis=1).mean(axis=1) / E,
    '감정가·시세 중 큰 값': np.maximum(D.appr, D.mkt) / E,
    '감정가·시세 중 작은 값': np.minimum(D.appr, D.mkt) / E,
    '최저가·실거래 평균': (D.low + Sx.tr12.fillna(D.mkt)) / 2 / E,
}
ratio = {
    '감정가/시세': D.appr / D.mkt,
    '최저가/시세': D.low / D.mkt,
    '실거래/리치고': Sx.tr12 / D.mkt_richgo,
    '3.3㎡당 시세(만원)': D.mkt / (D.area / 3.3058) / 1e4,
}
FIX = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20, 30, 999]
RFIX = {'감정가/시세': [0, .8, .9, .95, 1.0, 1.05, 1.1, 1.2, 1.4, 9], '최저가/시세': [0, .55, .6, .65, .7, .75, .8, .85, .9, 9],
        '실거래/리치고': [0, .85, .92, .97, 1.0, 1.03, 1.08, 1.15, 9], '3.3㎡당 시세(만원)': [0, 1500, 2000, 2500, 3000, 3500, 4000, 5000, 6000, 8000, 99999]}


def stat(e, mask=None):
    e = e if mask is None else e[mask]
    e = e.dropna()
    return dict(n=len(e), 평균오차=round(e.abs().mean() * 100, 2) if len(e) else np.nan,
                치우침=round(e.mean() * 100, 2) if len(e) else np.nan, 이내5=round((e.abs() <= .05).mean() * 100, 1) if len(e) else np.nan)


def lab_fix(b):
    return [f'{a}~{z}억' if z < 999 else f'{a}억+' for a, z in zip(b[:-1], b[1:])]


def bins(x, how):
    if how == 'fix':
        return pd.cut(x, FIX, labels=lab_fix(FIX), right=False)
    q = int(how[1:])
    try:
        b = pd.qcut(x, q, duplicates='drop')
    except ValueError:
        return pd.Series(np.nan, index=x.index)
    return b.cat.rename_categories([f'{iv.left:.2f}~{iv.right:.2f}' for iv in b.cat.categories])


def mdt(t, index=True):   # tabulate 없이 마크다운 표
    t = t.reset_index() if index else t
    t = t.astype(object).where(t.notna(), '')
    h = '| ' + ' | '.join(map(str, t.columns)) + ' |'
    return '\n'.join([h, '|' + '---|' * len(t.columns)] + ['| ' + ' | '.join(map(str, r)) + ' |' for r in t.values])


pd.DataFrame.to_markdown = mdt
tables = []   # (제목, DataFrame)
spread = []   # 기준별 구간 간 오차 편차 요약
for name, x in {**crit, **ratio}.items():
    for how in (['fix', 'q10', 'q20'] if name in crit else ['rfix', 'q10']):
        if how == 'rfix':
            b = pd.cut(x, RFIX[name], right=False)
            b = b.cat.rename_categories([f'{iv.left:g}~{iv.right:g}' for iv in b.cat.categories])
        else:
            b = bins(x, how)
        rows = []
        for k in b.cat.categories:
            m = b == k
            if m.sum() == 0: continue
            rows.append(dict(구간=k, **stat(D.e, m)))
        if x.isna().any(): rows.append(dict(구간='값 없음', **stat(D.e, x.isna())))
        T_ = pd.DataFrame(rows)
        tables.append((f'{name} · {dict(fix="고정 억 단위", q10="10분위", q20="20분위", rfix="고정 비율")[how]}', T_))
        big = T_[(T_.n >= 20) & (T_.구간 != '값 없음')]
        if len(big) >= 2:
            spread.append(dict(기준=name, 나눔=how, 구간수=len(big), 최소오차=big.평균오차.min(), 최대오차=big.평균오차.max(),
                               치우침폭=round(big.치우침.max() - big.치우침.min(), 2)))

# 교차 (섞기 2차원)
cross = []
xb = {'시세 구간': pd.cut(D.mkt / E, [0, 4, 6, 8, 10, 15, 999], labels=['~4억', '4~6억', '6~8억', '8~10억', '10~15억', '15억+'], right=False),
      '감정가/시세': pd.cut(D.appr / D.mkt, [0, .9, 1.0, 1.1, 9], labels=['<0.9', '0.9~1.0', '1.0~1.1', '1.1+'], right=False),
      '유찰': D.fails.clip(upper=2).map({0: '신건', 1: '1회', 2: '2회+'}),
      '지역': D.seoul.map({1: '서울', 0: '경기·인천'})}
for a, b2 in [('시세 구간', '감정가/시세'), ('시세 구간', '유찰'), ('시세 구간', '지역')]:
    g = pd.DataFrame({'a': xb[a], 'b': xb[b2], 'e': D.e})
    piv = g.groupby(['a', 'b']).e.agg(lambda s: f'{s.abs().mean()*100:.1f}% ({s.mean()*100:+.1f}) n{len(s)}').unstack()
    cross.append((f'{a} × {b2}  (평균오차 (치우침) 건수)', piv))


# ---------- 3) 구간별 치우침 보정 롤링 ----------
def band_adj(bands, K=15, W=12, min_n=60):
    """직전 W개월 같은 구간 잔차 평균을 K로 축소해 더함. 미래 정보 없음."""
    out = D.res.copy() * np.nan
    for T in sorted(D.m0.unique()):
        h = (D.m0 < T) & (D.m0 >= T - pd.DateOffset(months=W))
        t = D.m0 == T
        if h.sum() < min_n:
            out[t] = D.res[t]; continue
        st = D.res[h].groupby(bands[h]).agg(['mean', 'size'])
        adj = st['mean'] * st['size'] / (st['size'] + K)
        out[t] = D.res[t] - bands[t].map(adj).astype(float).fillna(0).values
    return np.exp(out) - 1


base = stat(D.e)
adj_rows = [dict(보정='없음(운영)', **base)]
cands = {}
for name in ['감정가', '최저가', 'M 시세(운영)', '리치고 시세', '실거래 12개월 평균', '예측가(모델)', '감정가·시세 평균', '감정가·시세·실거래 평균', '감정가·시세 중 큰 값']:
    x = crit[name]
    cands[f'{name} 고정'] = pd.cut(x, FIX, labels=lab_fix(FIX), right=False).astype(str)
    # 분위 경계는 평가 기간 전체로 잡으면 약간의 미래 정보 — 경계만이라 영향 작음, 고정 구간과 비교용
    cands[f'{name} 5분위'] = pd.qcut(x, 5, duplicates='drop').astype(str)
for name in ['감정가/시세', '최저가/시세', '3.3㎡당 시세(만원)']:
    cands[f'{name} 비율'] = pd.cut(ratio[name], RFIX[name], right=False).astype(str)
cands['시세 × 감정가/시세'] = xb['시세 구간'].astype(str) + '|' + xb['감정가/시세'].astype(str)
cands['시세 × 유찰'] = xb['시세 구간'].astype(str) + '|' + xb['유찰'].astype(str)
cands['시세 × 지역'] = xb['시세 구간'].astype(str) + '|' + xb['지역'].astype(str)
for k, bnd in cands.items():
    for K in (15, 40):
        e2 = band_adj(bnd, K=K)
        half = D.date >= D.date.sort_values().iloc[len(D) // 2]
        adj_rows.append(dict(보정=f'{k} (k={K})', **stat(e2), 앞절반=round(e2[~half].abs().mean() * 100, 2),
                             뒤절반=round(e2[half].abs().mean() * 100, 2)))
half = D.date >= D.date.sort_values().iloc[len(D) // 2]
adj_rows[0].update(앞절반=round(D.e[~half].abs().mean() * 100, 2), 뒤절반=round(D.e[half].abs().mean() * 100, 2))
ADJ = pd.DataFrame(adj_rows).sort_values('평균오차')

# ---------- 4) 구간별 최적 시세·모델 고르기 (combo_bt_rows 재사용) ----------
pick_txt = ''
CB = os.path.join(HERE, 'combo_bt_rows.csv')
if os.path.exists(CB):
    C = pd.read_csv(CB, index_col=0).reindex(D.index)
    C = C.loc[:, C.notna().mean() > 0.95]
    whole = C.abs().mean().sort_values()
    best_all = whole.index[0]
    pr = []
    for name in ['M 시세(운영)', '감정가', '감정가·시세 평균']:
        bnd = pd.cut(crit[name], [0, 4, 6, 8, 10, 15, 999], labels=['~4억', '4~6억', '6~8억', '8~10억', '10~15억', '15억+'], right=False).astype(str)
        chosen = pd.Series(np.nan, index=D.index)
        for T in sorted(D.m0.unique()):   # 직전 12개월 기준으로 구간별 최저 오차 조합 선택
            h = (D.m0 < T) & (D.m0 >= T - pd.DateOffset(months=12)); t = D.m0 == T
            for bb in bnd[t].unique():
                hb = h & (bnd == bb); tb = t & (bnd == bb)
                col = C[hb].abs().mean().idxmin() if hb.sum() >= 30 else best_all
                chosen[tb] = C.loc[tb, col]
        pr.append(dict(방식=f'{name} 구간별 과거 최고 조합 선택', **stat(chosen)))
        tb_ = pd.DataFrame({'b': bnd, **{k: C[k] for k in whole.index[:8]}}).groupby('b').agg(lambda s: round(s.abs().mean() * 100, 2))
        pick_txt += f'\n#### {name} 구간별 상위 조합 오차(%) — 전체 기간 사후 비교\n\n' + tb_.to_markdown() + '\n'
    pr.insert(0, dict(방식=f'단일 조합 (전체 1위: {best_all})', **stat(C[best_all])))
    PICK = pd.DataFrame(pr)
else:
    PICK = pd.DataFrame()

# ---------- 출력 ----------
SP = pd.DataFrame(spread).sort_values('치우침폭', ascending=False)
md = [f'# 금액대별 백테스트 ({pd.Timestamp.today().date()})', '',
      f'아파트 {len(D)}건, {START[:7]}~{D.date.max():%Y-%m} 월별 롤링, 운영 방식(앙상블+구별 보정+상승형 규칙+소규모 -3%).',
      f'전체 평균 오차 **{base["평균오차"]}%**, 치우침 {base["치우침"]:+}%, 5% 이내 {base["이내5"]}%.', '',
      '오차 = 실제 낙찰가/예측 중심 − 1. 치우침 + = 실제가 예측보다 높음(예측이 낮았음).', '',
      '## A. 기준별로 구간 차이가 얼마나 나나 (n≥20 구간만)', '', SP.to_markdown(index=False), '',
      '## B. 구간별 치우침 보정을 넣으면 (롤링, 직전 12개월, 축소 k)', '', ADJ.to_markdown(index=False), '']
if len(PICK):
    md += ['## C. 구간마다 다른 시세·모델 조합을 고르면', '', PICK.to_markdown(index=False), pick_txt, '']
md += ['## D. 교차 구간 (섞기)', '']
for t, p in cross:
    md += [f'### {t}', '', p.to_markdown(), '']
md += ['## E. 기준별 상세 표', '']
for t, T_ in tables:
    md += [f'### {t}', '', T_.to_markdown(index=False), '']
open(os.path.join(HERE, 'band_bt_result.md'), 'w', encoding='utf-8').write('\n'.join(md))
print(SP.to_string(index=False)); print(ADJ.head(15).to_string(index=False)); print(PICK.to_string(index=False))
