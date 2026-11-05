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
    if os.environ.get('IDX') == 'none': return 1.0   # 추세 보정 없음 (2026-11-05: 시군구 지수가 거래 단지 구성에 따라 출렁임)
    s = ix.get(sgg)
    if s is None: return np.nan
    p = min(max(p, s.index[0]), s.index[-1]); return float(s.loc[p])


m['jb'] = m.jibun.astype(str).str.strip()
# 층 보정 (2026-11-05): 단지 안 상대 층 구간별 가격 차이 — 2024-07 이전 거래로만 추정(검증 기간 정보 누출 방지)
m['top'] = m.groupby('aptSeq').floor.transform('max')


def fbin(f, top):
    if pd.isna(f) or pd.isna(top) or top < 3: return 'mid'
    if f <= 1: return '1층'
    if f <= 3: return '2~3층'
    if f >= top: return '꼭대기'
    r = f / top
    return '저층' if r < 1 / 3 else ('중층' if r < 2 / 3 else '고층')


m['fb'] = [fbin(f, t) for f, t in zip(m.floor, m.top)]
_e = m[m.d < '2024-07-01'].copy(); _e['lp'] = np.log(_e.ppa)
_e['res'] = _e.lp - _e.groupby(['aptSeq', 'ym', _e.area.round(0)]).lp.transform('mean')
_e = _e[_e.groupby(['aptSeq', 'ym', _e.area.round(0)]).lp.transform('size') >= 2]
FP = _e.groupby('fb').res.mean(); FP = np.exp(FP - FP.get('중층', 0))
print('층 구간별 가격 (중층=1)', FP.round(3).to_dict(), ' 표본', _e.groupby('fb').size().to_dict())
m['fprem'] = m.fb.map(FP).fillna(1.0)
CASE = json.load(open(os.path.join(HERE, 'probe', 'case_addr.json')))
AMAP = pd.read_csv(os.path.join(os.path.dirname(HERE), 'court_backfill', 'apt_case_map.csv')).set_index('index').auction_id
import re as _re


def case_floor(i):
    a = (CASE.get(AMAP.get(i, '')) or {}).get('address') or ''
    x = _re.search(r'(\d+)층', a)
    return int(x.group(1)) if x else (1 if '지하' in a else np.nan)


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
            top = c[c.aptSeq == seq].top.max() if len(c) else np.nan
            tp = FP.get(fbin(case_floor(i), top), 1.0); out['fprem_case'] = tp; out['fb_case'] = fbin(case_floor(i), top)
            tf = t.assign(adj=t.adj * tp / t.fprem)
            tt = tf[tf.d >= r.date - pd.DateOffset(months=12)]
            if len(tt):
                out['tr12f'] = float(tt.adj.median())
                # 최근 거래일수록 큰 가중 (반감기 3개월) 가중 평균, 유효 거래 수
                age = (r.date - tt.d).dt.days.values / 30.4; wt = 0.5 ** (age / 3)
                out['tr12fw'] = float(np.sum(wt * tt.adj.values) / wt.sum()); out['neff'] = float(wt.sum())
                out['disp'] = float(tt.adj.std() / tt.adj.mean()) if len(tt) >= 3 else np.nan
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
S.to_csv(os.path.join(HERE, 'sise_bt_S' + ('_noidx' if os.environ.get('IDX') == 'none' else '') + '.csv'))   # 학습 사례 전체의 당시 시세 값 (combo_bt.py 입력)
if os.environ.get('S_ONLY'): sys.exit(0)
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
# 2026-11-05 사용자 요청: 섞는 비율 (실거래 비중 w)
for w in (0.4, 0.6, 0.7):
    V[f'W 실거래{int(w*100)}·리치고{int(100-w*100)}'] = w * S.tr12.fillna(df.mkt) + (1 - w) * df.mkt
V['H 층보정 실거래12m(없으면 리치고)'] = S.tr12f.fillna(df.mkt)
V['I 층보정 실거래40·리치고60'] = 0.4 * S.tr12f.fillna(df.mkt) + 0.6 * df.mkt
V['J 층보정 실거래50·리치고(층보정)50'] = 0.5 * S.tr12f.fillna(df.mkt * S.fprem_case.fillna(1)) + 0.5 * df.mkt * S.fprem_case.fillna(1)
V['K 리치고×층보정'] = df.mkt * S.fprem_case.fillna(1)
RF = df.mkt * S.fprem_case.fillna(1)
for k in (1, 2, 4):   # 거래 많을수록 실거래 비중↑: w = neff/(neff+k), 최대 0.7
    w = (S.neff / (S.neff + k)).clip(upper=0.7).fillna(0)
    V[f'L 최근성가중 실거래 w=n/(n+{k})'] = w * S.tr12fw.fillna(RF) + (1 - w) * RF
w = (S.neff / (S.neff + 2)).clip(upper=0.7).fillna(0) * (1 - (S.disp.fillna(0.1) / 0.2).clip(0, 1) * 0.5)
V['M 최근성+분산(들쭉날쭉하면 실거래↓)'] = w * S.tr12fw.fillna(RF) + (1 - w) * RF
if os.environ.get('ONLY'):
    V = {k: v for k, v in V.items() if k[0] in os.environ['ONLY']}


def run(mkt, feat=None):
    d = df.copy(); d['mkt'] = mkt.values
    if feat is not None:   # 실거래÷시세 비율을 입력으로 (모델이 가중치 학습) — jeonse 자리를 빌리지 않고 py_share 옆에 추가
        d['trade_rel'] = feat.values
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
if 'N' in os.environ.get('ONLY', 'N'):
    _prep = ap.prep
    def prep2(d):
        X = _prep(d); X['trade_rel'] = np.log(d['trade_rel']) if 'trade_rel' in d else np.nan; return X
    ap.prep = prep2
    for nm in list(ap.MEMBERS):
        k_, c_, dc = ap.MEMBERS[nm]; ap.MEMBERS[nm] = (k_, c_ + ['trade_rel'], dc)
    J = V.get('J 층보정 실거래50·리치고(층보정)50', 0.5 * S.tr12f.fillna(RF) + 0.5 * RF)
    E_['N J + 실거래÷리치고 비율을 모델 입력'] = run(J, (S.tr12f / RF).fillna(1.0))
    ap.prep = _prep
has = S.tr12.notna()
res = []
for k, e in E_.items():
    h = has.reindex(e.index).fillna(False)
    res.append(dict(시세=k, 건수=len(e), 평균오차=round(e.abs().mean() * 100, 2), within5=round((e.abs() <= .05).mean() * 100, 1),
                    치우침=round(e.mean() * 100, 2), 실거래있는건_오차=round(e[h].abs().mean() * 100, 2), 실거래없는건_오차=round(e[~h].abs().mean() * 100, 2)))
R = pd.DataFrame(res); print(R.to_string(index=False))
R.to_csv(os.path.join(HERE, 'sise_bt_result.csv'), index=False)
pd.DataFrame(E_).join(S).to_csv(os.path.join(HERE, 'sise_bt_rows.csv'))
