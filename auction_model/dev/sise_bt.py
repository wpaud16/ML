"""시세 기준 백테스트 (2026-11-05, 사용자 요청: 모델 시세를 리치고 하나 말고 여러 방면으로).
국토부 실거래(dev/molit/apt.csv.gz)로 매각 당시 시세를 다시 만들고, 모델 시세(mkt)를 바꿔 같은 시간 순 월별 검증(2024-07~).
- 매칭: 리치고 단지 지번(dev/probe/danji_info.json) = 국토부 동+지번 → 없으면 같은 시군구·동, 전용 ±1㎡, 준공연도 ±1 (거래 가장 많은 단지)
- 정보 누출 방지: 매각일 30일 전까지 계약된 거래만 (실거래 신고 기한 30일)
- 추세 보정: 같은 시군구 월별 ㎡당 중앙값 지수 (3개월 이동 중앙)
- 직거래·해제 거래 제외
지표 = 실제 낙찰가 대비 오차 (|낙찰가/예측가 − 1| 평균)."""
import os, sys, warnings, json
import numpy as np, pandas as pd
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import auction_predictor as ap

df = ap.load_train()
m = pd.read_csv(os.path.join(HERE, 'molit', 'apt.csv.gz'), dtype=str)
m = m[(m.get('cdealType', '').fillna('') == '') & (m.get('dealingGbn', '').fillna('') != '직거래')].copy()
m['price'] = m.dealAmount.str.replace(',', '').astype(float) * 1e4
m['area'] = m.excluUseAr.astype(float); m['by'] = pd.to_numeric(m.buildYear, errors='coerce')
m['d'] = pd.to_datetime(m.dealYear + '-' + m.dealMonth.str.zfill(2) + '-' + m.dealDay.str.zfill(2), errors='coerce')
m['floor'] = pd.to_numeric(m.floor, errors='coerce')
m = m.dropna(subset=['d', 'price', 'area'])
m['ppa'] = m.price / m.area; m['ym'] = m.d.dt.to_period('M')
# 시군구 월별 ㎡당 지수
ix = m.groupby(['sgg', 'ym']).ppa.median().unstack(0).sort_index()
ix = ix.reindex(pd.period_range(ix.index.min(), ix.index.max(), freq='M')).interpolate(limit_direction='both').rolling(3, min_periods=1).median()


def idx(sgg, p):
    s = ix.get(sgg)
    if s is None: return np.nan
    p = min(max(p, s.index[0]), s.index[-1]); return float(s.loc[p])


m['jb'] = m.jibun.astype(str).str.strip()
G = {k: g for k, g in m.groupby(['sgg', 'umdNm'])}
INFO = json.load(open(os.path.join(HERE, 'probe', 'danji_info.json')))


def jibun_of(danji):
    a = (((INFO.get(danji) or {}).get('basic') or {}).get('address') or {}).get('jibun') or ''
    return a.split()[-1] if a else None


rows = []; how = {}
for i, r in df.iterrows():
    g = G.get((r.sgg, r.emd))
    out = dict(i=i)
    if g is not None:
        by = r.date.year - r.age
        jb = jibun_of(r.danji)
        c = g[(g.jb == jb) & (g.area.sub(r.area).abs() <= 1.0)] if jb else g.iloc[:0]
        out['how'] = '지번' if len(c) else '면적·준공'
        if not len(c):
            c = g[(g.area.sub(r.area).abs() <= 1.0) & (g.by.sub(by).abs() <= 1)]
        if len(c):
            seqs = c.aptSeq.value_counts()
            seq = seqs.index[0]; out['n_seq'] = len(seqs)
            t = c[(c.aptSeq == seq) & (c.d <= r.date - pd.Timedelta(days=30))].sort_values('d')
            Tp = (r.date - pd.Timedelta(days=30)).to_period('M'); I = idx(r.sgg, Tp)
            t = t.assign(adj=t.price * [I / idx(r.sgg, p) for p in t.ym])
            for mo in (3, 6, 12):
                tt = t[t.d >= r.date - pd.DateOffset(months=mo)]
                out[f'n{mo}'] = len(tt)
                if len(tt): out[f'tr{mo}'] = float(tt.adj.median())
            if len(t) and t.d.iloc[-1] >= r.date - pd.DateOffset(months=12):
                out['last'] = float(t.adj.iloc[-1]); out['last_age_m'] = (r.date - t.d.iloc[-1]).days / 30.4
            tt = t[t.d >= r.date - pd.DateOffset(months=12)]
            if len(tt) >= 3:   # 층 많이 섞인 경우 상위 75% 값 (저층 할인 영향 줄이기)
                out['tr12_q60'] = float(tt.adj.quantile(.6))
    rows.append(out)
S = pd.DataFrame(rows).set_index('i')
print('매칭 방법', S.how.value_counts().to_dict())
print('매칭', S.n_seq.notna().sum(), '/', len(df), ' 12개월 거래 있음', S.tr12.notna().sum(), ' 6개월', S.tr6.notna().sum(), ' 3개월', S.tr3.notna().sum(), flush=True)
print('실거래12m ÷ 리치고 중앙', (S.tr12 / df.mkt).median().round(3), ' 낙찰가 ÷ 실거래12m 중앙', (df.sell / S.tr12).median().round(3))

V = {'A 리치고(현재)': df.mkt,
     'B 실거래 6개월(없으면 리치고)': S.tr6.fillna(df.mkt),
     'C 실거래 12개월(없으면 리치고)': S.tr12.fillna(df.mkt),
     'D 최근 1건(없으면 리치고)': S['last'].fillna(df.mkt),
     'E 리치고·실거래12m 중앙(=평균)': ((df.mkt + S.tr12.fillna(df.mkt)) / 2),
     'F 리치고70·실거래12m 30': (0.7 * df.mkt + 0.3 * S.tr12.fillna(df.mkt)),
     'G 실거래12m 60%분위(없으면 리치고)': S.tr12_q60.fillna(df.mkt)}


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


E_ = {k: run(v) for k, v in V.items()}
has = S.tr12.notna()
res = []
for k, e in E_.items():
    h = has.reindex(e.index).fillna(False)
    res.append(dict(시세=k, 건수=len(e), 평균오차=round(e.abs().mean() * 100, 2), within5=round((e.abs() <= .05).mean() * 100, 1),
                    치우침=round(e.mean() * 100, 2), 실거래있는건_오차=round(e[h].abs().mean() * 100, 2), 실거래없는건_오차=round(e[~h].abs().mean() * 100, 2)))
R = pd.DataFrame(res); print(R.to_string(index=False))
R.to_csv(os.path.join(HERE, 'sise_bt_result.csv'), index=False)
pd.DataFrame(E_).join(S).to_csv(os.path.join(HERE, 'sise_bt_rows.csv'))
