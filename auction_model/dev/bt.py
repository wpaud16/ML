import sys, numpy as np, pandas as pd, warnings; warnings.filterwarnings('ignore')
sys.path.insert(0,'/home/claude/ml/auction_model')
import officetel_model as om, auction_predictor as ap
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
b=pd.read_csv('../bid/ot_bid2.csv')[['auction_id','bidders']].drop_duplicates('auction_id')
df=om.load_train().merge(b,on='auction_id',how='left'); df.index=range(len(df))
BID=['l_bid','bid1','bid2']
def X(x,cols):
    Z=om._X(x,cols)
    nb=x['bidders'] if 'bidders' in x else pd.Series(np.nan,index=x.index)
    Z['l_bid']=np.log(nb).values; Z['bid1']=(nb==1).astype(float).where(nb.notna()).values; Z['bid2']=(nb==2).astype(float).where(nb.notna()).values
    return Z
def fit(tr,T,bid):
    out=[]
    for kind,cols in [('rf',ap.S3),('gb',ap.S4)]:
        Xt=X(tr,cols) if bid else om._X(tr,cols)
        if not bid: Xt=Xt
        med=Xt.median(); Xt=Xt.fillna(med).fillna(0)
        w=np.exp(-((pd.Timestamp(T)-tr.date).dt.days.values)/365)
        m=(RandomForestRegressor(300,min_samples_leaf=6,max_features=0.5,random_state=0,n_jobs=-1) if kind=='rf' else
           HistGradientBoostingRegressor(max_iter=300,learning_rate=0.04,max_depth=3,min_samples_leaf=max(10,len(tr)//30),l2_regularization=2.0,random_state=0))
        out.append((cols,med,m.fit(Xt,tr.y.values,sample_weight=w)))
    return out
def pred(models,te,bid):
    return np.mean([m.predict((X(te,c) if bid else om._X(te,c)).fillna(med).fillna(0)) for c,med,m in models],axis=0)
rows=[]
for T in pd.date_range('2024-07-01',df.date.max(),freq='MS'):
    tr,te=df[df.date<T],df[(df.date>=T)&(df.date<T+pd.DateOffset(months=1))]
    if len(te)==0 or len(tr)<60: continue
    a=pred(fit(tr,T,False),te,False)
    mb=fit(tr,T,True); bb=pred(mb,te,True)
    # 인원 모르는 상태(시나리오 아님): 인원 NaN으로 예측
    rows.append(te[['date','y','bidders','fails','r_low_mkt']].assign(rA=te.y.values-a,rB=te.y.values-bb))
R=pd.concat(rows); R.to_pickle('R.pkl')
k=R[R.bidders.notna()]
for c in ['rA','rB']:
    e=np.exp(k[c])-1; print(c,'n',len(k),'MAPE %.2f'%(e.abs().mean()*100),'±5%% %.0f'%((e.abs()<=.05).mean()*100))
g=lambda n:1 if n<=1 else 2 if n==2 else 3 if n<=4 else 5 if n<=7 else 8
k=k.assign(g=k.bidders.map(g))
print(k.groupby('g').agg(n=('rA','size'),biasA=('rA',lambda x:(np.exp(x)-1).mean()*100),maeA=('rA',lambda x:(np.exp(x)-1).abs().mean()*100),biasB=('rB',lambda x:(np.exp(x)-1).mean()*100),maeB=('rB',lambda x:(np.exp(x)-1).abs().mean()*100)).round(1))
