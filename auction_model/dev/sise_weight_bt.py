"""최근 시세에 더 방점 (2026-11-05 사용자 제안): 감정가·최저가 의존을 줄이는 변형 백테스트. M 시세 학습 데이터, 현재 앙상블, 시간 순 월별.
A 현재 / B 감정가를 감정 후 시세 추세만큼 보정해 입력 / C 감정가 입력 제거 / D B + '감정 후 상승' 물건은 시세 기준 예측(최근 낙찰가율×시세)과 반반."""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import auction_predictor as ap
df = ap.load_train()
gap = (df.r_appr_mkt < 0.85) & (df.mom12 > 0.08)
_prep = ap.prep
def prep_b(d):
    X = _prep(d)
    adj = d.appr * (1 + d.mom12.fillna(0) * (d.lag_m.fillna(12).clip(upper=24) / 12))
    X['l_appr'] = np.log(adj / d.mkt); return X
def prep_c(d):
    X = _prep(d); X['l_appr'] = 0.0; return X
def run(prep):
    ap.prep = prep; ap._FIT.clear(); P, I = [], []
    for T in pd.date_range('2024-07-01', df.date.max(), freq='MS'):
        tr, te = df[df.date < T], df[(df.date >= T) & (df.date < T + pd.DateOffset(months=1))]
        if len(te) == 0 or len(tr) < 100: continue
        P.append(np.mean([ap.fit_predict(k, tr, te, T) for k in ap.ENSEMBLE], axis=0)); I.append(te.index)
    ap.prep = _prep
    I = np.concatenate([np.asarray(x) for x in I]); return pd.Series(np.concatenate(P), index=I)
pa, pb, pc = run(_prep), run(prep_b), run(prep_c)
pd_ = pb.copy(); g = gap.reindex(pd_.index)
pd_[g] = 0.5 * pb[g] + 0.5 * np.log(df.heat.reindex(pd_.index)[g])   # 시세 × 최근 낙찰가율
y = df.y.reindex(pa.index)
for nm, p in (('A 현재', pa), ('B 감정가 추세 보정', pb), ('C 감정가 입력 제거', pc), ('D B + 상승형은 시세 기준 반반', pd_)):
    e = np.exp(y - p) - 1; gg = gap.reindex(e.index)
    print(f'{nm}: 전체 {e.abs().mean()*100:.2f}% | 상승형 {gg.sum()}건 {e[gg].abs().mean()*100:.2f}% (치우침 {e[gg].mean()*100:+.1f}%) | 나머지 {e[~gg].abs().mean()*100:.2f}%')
i = df.index[(df.sgg.astype(str).str.contains('남양주')) & (df.date == '2026-11-04')]

# 상승형 물건에서 시세 기준 비중을 바꿔 보기 (B 기반)
print('--- 상승형 시세 기준 비중')
for w in (0.25, 0.5, 0.75, 1.0):
    q = pb.copy(); q[g] = (1 - w) * pb[g] + w * np.log(df.heat.reindex(q.index)[g])
    e = np.exp(y - q) - 1; gg = gap.reindex(e.index)
    print(f'w={w}: 전체 {e.abs().mean()*100:.2f}% | 상승형 {e[gg].abs().mean()*100:.2f}% (치우침 {e[gg].mean()*100:+.1f}%)')
# 힐스테이트다산(2024타경3470) 은 학습 데이터 밖(11/4 매각) — 같은 규칙 적용 시 예상: 시세 11.64억 × 최근 낙찰가율
print('최근 heat (경기)', round(float(df[df.seoul == 0].heat.iloc[-1]), 3))
