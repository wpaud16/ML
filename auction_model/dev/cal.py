import sys, numpy as np, pandas as pd, warnings; warnings.filterwarnings('ignore')
sys.path.insert(0,'/home/claude/ml/auction_model')
import auction_predictor as ap, officetel_model as om
from sklearn.ensemble import HistGradientBoostingRegressor
R=pd.read_pickle('R.pkl'); R=R[R.bidders.notna()].copy()
g=lambda n:1 if n<=1 else 2 if n==2 else 3 if n<=4 else 5 if n<=7 else 8
R['g']=R.bidders.map(g); R['m']=R.date.dt.to_period('M').dt.to_timestamp()
hits={q:[] for q in [.4,.5,.6]}; byg=[]
for i,r in R.iterrows():
    h=R[(R.m<r.m)&(R.m>=r.m-pd.DateOffset(months=18))]
    pool=h[h.g==r.g].rB.values
    if len(pool)<30: pool=h.rB.values
    if len(pool)<40: continue
    for q in hits: hits[q].append(float(r.rB<np.quantile(pool,q)))
    byg.append(r.g)
print('n',len(byg),{q:round(np.mean(v),3) for q,v in hits.items()})
# 예상 인원 모델
b=pd.read_csv('../bid/ot_bid2.csv')[['auction_id','bidders']].drop_duplicates('auction_id')
df=om.load_train().merge(b,on='auction_id',how='left')
F=['l_appr','l_low','fails','l_area','age','jeonse','heat','rate','is_check']
def Xf(d):
    Z=ap.prep(d); Z['is_check']=d.is_check.values; Z['station']=d.station_m.values if 'station_m' in d else np.nan; return Z[F+['station']]
P=[]
for T in pd.date_range('2024-07-01',df.date.max(),freq='MS'):
    tr=df[(df.date<T)&df.bidders.notna()]; te=df[(df.date>=T)&(df.date<T+pd.DateOffset(months=1))&df.bidders.notna()]
    if len(te)==0 or len(tr)<100: continue
    Xt=Xf(tr); med=Xt.median()
    m=HistGradientBoostingRegressor(loss='quantile',quantile=0.5,max_iter=200,max_depth=3,learning_rate=0.05,min_samples_leaf=15,random_state=0).fit(Xt.fillna(med),np.log(tr.bidders))
    p=np.exp(m.predict(Xf(te).fillna(med)))
    P.append(pd.DataFrame(dict(act=te.bidders.values,pred=np.round(p),base=tr.bidders.median())))
P=pd.concat(P)
print('예상 인원 n',len(P),'MAE 모델 %.2f · 단순중앙값 %.2f'%((P.act-P.pred).abs().mean(),(P.act-P.base).abs().mean()),
      '같은 그룹 적중 %.0f%%'%((P.pred.map(g)==P.act.map(g)).mean()*100),'(중앙값 %.0f%%)'%((P.base.map(g)==P.act.map(g)).mean()*100))
