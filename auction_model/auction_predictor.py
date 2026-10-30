#!/usr/bin/env python3
"""JM 경매 낙찰가 예측기 (엑스트라트리 · 앙상블) — 낙찰확률 50% 가격.

사용법 (같은 폴더에 auction_train.csv, auction_config.json 필요):
  python3 auction_predictor.py predict --danji a7BuFFg --auction C49LSPHG
      -> JSON: 엑스트라트리·앙상블의 50% 가격(만원), 입력값 요약
  python3 auction_predictor.py calibrate   # (개발용) 최근 12개월 롤링 오차로 50% 보정값 재계산

예측 대상 정보는 리치고 단지 페이지(https://m.richgo.ai/realty/danji/<danji>)의
auctionInfo(해당 단지의 경매 목록)에서 auctionId로 찾아 읽는다.
학습: 2023-06~2026-10 서울·경기 아파트 매각 1,412건 (권리위험·지분 제외), 2026-10-29 구축.
"""
import sys, json, re, os, subprocess, argparse, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
try:
    from sklearn.linear_model import Ridge
    from sklearn.ensemble import HistGradientBoostingRegressor, ExtraTreesRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans
except ImportError:
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--break-system-packages', 'scikit-learn'])
    from sklearn.linear_model import Ridge
    from sklearn.ensemble import HistGradientBoostingRegressor, ExtraTreesRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------- policy / rate (sale date & location) ----------------
RATE_PATH = [('2022-11-24', 3.25), ('2023-01-13', 3.50), ('2024-10-11', 3.25), ('2024-11-28', 3.00),
             ('2025-02-25', 2.75), ('2025-05-29', 2.50), ('2026-07-16', 2.75), ('2026-08-27', 3.00)]
GG12 = {'과천시', '광명시', '성남시 분당구', '성남시 수정구', '성남시 중원구', '수원시 영통구', '수원시 장안구',
        '수원시 팔달구', '안양시 동안구', '용인시 수지구', '의왕시', '하남시'}
GG_2026 = {'구리시', '화성시 동탄구', '용인시 기흥구'}
GANGNAM4 = {'강남구', '서초구', '송파구', '용산구'}
JSDC = {'잠실동', '삼성동', '대치동', '청담동'}
STRAT = {'압구정동', '여의도동', '목동', '신정동', '성수동1가', '성수동2가'}


def rate_at(d):
    d = pd.Timestamp(d); r = RATE_PATH[0][1]
    for day, v in RATE_PATH:
        if d >= pd.Timestamp(day):
            r = v
    return r


def tohu_at(d, sd, sgg, emd):
    d = pd.Timestamp(d)
    if sd == '서울':
        if d >= pd.Timestamp('2025-10-20'): return 1
        if sgg in GANGNAM4 and d >= pd.Timestamp('2025-03-24'): return 1
        if emd in JSDC and d < pd.Timestamp('2025-02-13'): return 1
        if emd in STRAT: return 1
        return 0
    if sgg in GG12 and d >= pd.Timestamp('2025-10-20'): return 1
    if sgg in GG_2026 and d >= pd.Timestamp('2026-07-05'): return 1
    return 0


def regulated_at(d, sd, sgg):
    d = pd.Timestamp(d)
    if sd == '서울' and sgg in GANGNAM4: return 1
    if (sd == '서울' or sgg in GG12) and d >= pd.Timestamp('2025-10-16'): return 1
    if sgg in GG_2026 and d >= pd.Timestamp('2026-07-01'): return 1
    return 0


def loan_ratio(d, sd, sgg, price):
    d = pd.Timestamp(d); reg = regulated_at(d, sd, sgg)
    ltv = (0.40 if reg else 0.70) if d >= pd.Timestamp('2025-10-16') else (0.50 if reg else 0.70)
    loan = ltv * price
    if d >= pd.Timestamp('2025-10-16'):
        loan = min(loan, 6e8 if price <= 15e8 else (4e8 if price <= 25e8 else 2e8))
    elif d >= pd.Timestamp('2025-06-28'):
        loan = min(loan, 6e8)
    return loan / price


# ---------------- features ----------------
def prep(d):
    X = pd.DataFrame(index=d.index)
    X['l_appr'] = np.log(d.r_appr_mkt); X['l_low'] = np.log(d.r_low_mkt)
    X['fails'] = d.fails.clip(upper=4); X['seoul'] = d.seoul
    X['l_area'] = np.log(d.area); X['age'] = d.age; X['l_hh'] = np.log(d.hh.clip(lower=10))
    X['py_share'] = d.py_share; X['jeonse'] = d.jeonse_ratio
    X['mom3'] = d.mom3; X['mom6'] = d.mom6; X['mom12'] = d.mom12; X['dd24'] = d.dd24
    X['lag_m'] = d.lag_m.clip(upper=60); X['heat'] = d.heat; X['l_mkt'] = np.log(d.mkt)
    X['tohu'] = d.tohu_r; X['rate'] = d.rate; X['rate_chg6'] = d.rate_chg6
    X['regulated'] = d.regulated; X['loan_ratio'] = d.loan_ratio
    return X


S0 = ['l_appr', 'l_low', 'fails', 'seoul', 'l_area']
POL = ['rate', 'rate_chg6', 'tohu', 'regulated', 'loan_ratio']
S1 = S0 + ['age', 'l_hh', 'heat'] + POL
S3 = S1 + ['jeonse', 'py_share', 'lag_m', 'l_mkt']
S4 = S3 + ['mom3', 'mom6', 'mom12', 'dd24']
MEMBERS = {'엑스트라트리': ('et', S3, None), '부스팅_감쇠': ('gb', S4, 365), '군집별회귀': ('cluster', S1, 365)}
ENSEMBLE = ['부스팅_감쇠', '군집별회귀']


def fit_predict(name, tr, te, T):
    kind, cols, decay = MEMBERS[name]
    Xtr, Xte = prep(tr)[cols], prep(te)[cols]
    med = Xtr.median(); Xtr, Xte = Xtr.fillna(med), Xte.fillna(med)
    sc = StandardScaler().fit(Xtr); Ztr, Zte = sc.transform(Xtr), sc.transform(Xte)
    y = tr.y.values
    wt = None if not decay else np.exp(-((pd.Timestamp(T) - tr.date).dt.days.values) / decay)
    if kind == 'et':
        return ExtraTreesRegressor(n_estimators=300, min_samples_leaf=8, max_features=0.6, random_state=0,
                                   n_jobs=-1).fit(Xtr, y, sample_weight=wt).predict(Xte)
    if kind == 'gb':
        return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.04, max_depth=3, min_samples_leaf=25,
                                             l2_regularization=2.0, random_state=0).fit(Xtr, y, sample_weight=wt).predict(Xte)
    cc = [cols.index(c) for c in ['l_appr', 'l_low', 'seoul', 'l_area', 'age']]
    km = KMeans(n_clusters=6, n_init=10, random_state=0).fit(Ztr[:, cc])
    ctr, cte = km.labels_, km.predict(Zte[:, cc])
    p = Ridge(alpha=3.0).fit(Ztr, y, sample_weight=wt).predict(Zte)
    for c in range(6):
        mtr, mte = ctr == c, cte == c
        if mtr.sum() >= 40 and mte.any():
            pw = None if wt is None else wt[mtr]
            p[mte] = 0.5 * p[mte] + 0.5 * Ridge(alpha=10.0).fit(Ztr[mtr], y[mtr], sample_weight=pw).predict(Zte[mte])
    return p


def load_train():
    df = pd.read_csv(os.path.join(HERE, 'auction_train.csv'))
    df['date'] = pd.to_datetime(df.date)
    df = df.sort_values('date').reset_index(drop=True)
    df['seoul'] = (df.sd == '서울').astype(int)
    df['y'] = np.log(df.r_sell_mkt)
    return df


def recent_heat(df, seoul, T):
    T = pd.Timestamp(T)
    m = df[(df.date < T) & (df.date >= T - pd.Timedelta(days=120)) & (df.seoul == seoul)]
    if len(m) < 8:
        m = df[(df.seoul == seoul)].tail(30)
    return float(m.r_sell_mkt.median())


# ---------------- target row from Richgo complex page ----------------
def fetch(url):
    return subprocess.run(['curl', '-sL', '-m', '40', '-A', 'Mozilla/5.0', url], capture_output=True, text=True).stdout


def mshift(m, k):
    y, mo = int(m[:4]), int(m[5:7]); t = y * 12 + mo - 1 - k
    return f'{t // 12:04d}-{t % 12 + 1:02d}'


def target_row(danji, auction_id, df):
    raw = fetch('https://m.richgo.ai/realty/danji/' + danji)
    i = raw.find('__NEXT_DATA__'); j = raw.find('>', i); k = raw.find('</script>', j)
    d = json.loads(raw[j + 1:k])['props']['pageProps']['data']
    au = []

    def flat(x):
        if not x: return
        y = dict(x); sub = y.pop('subList', None); au.append(y)
        for s in sub or []: flat(s)
    flat(d.get('auctionInfo'))
    a = next((x for x in au if x.get('auctionId') == auction_id), None)
    if a is None:
        raise SystemExit(json.dumps({'error': f'auction {auction_id} not found on danji {danji} page',
                                     'auctions_on_page': [x.get('auctionId') for x in au]}, ensure_ascii=False))
    area = a['buildingTotalArea']
    best = None
    for p, v in (d.get('pyeongInfos') or {}).items():
        try: lo, hi = float(v['minPrivateArea']), float(v['maxPrivateArea'])
        except (TypeError, ValueError): continue
        dp = (v.get('danjiPriceInfo') or {})
        meme = (dp.get('meme') or {}).get('price')
        if not meme: continue
        dist = 0 if lo - 0.5 <= area <= hi + 0.5 else abs(area - (lo + hi) / 2)
        if best is None or dist < best[0]:
            best = (dist, p, v, meme, (dp.get('jeonse') or {}).get('price'))
    if best is None or best[0] > 3:
        raise SystemExit(json.dumps({'error': 'no matching pyeong price on complex page'}, ensure_ascii=False))
    tot_hh = sum((v.get('households') or 0) for v in d['pyeongInfos'].values()) or np.nan
    ch = {x['date'][:7]: x.get('averagePrice') for x in d['analyze']['invest']['invest']['chart']['data'] if x.get('averagePrice')}
    ms = sorted(ch); last = ms[-1]

    def idx(m):
        pr = [x for x in ms if x <= m]
        return ch[pr[-1]] if pr else np.nan
    T = pd.Timestamp((a.get('biddingDate') or '')[:10]) if a.get('biddingDate') and not a['biddingDate'].startswith('9999') else pd.Timestamp.today().normalize()
    mkt = best[3] * 1e4
    bj = d.get('bjdInfo') or {}
    sd, sgg, emd = bj.get('sd'), bj.get('sgg'), bj.get('emd')
    kw = (a.get('keyword') or '') + ' ' + (a.get('historyKeyword') or '')
    reg = a.get('registrationDate')
    row = dict(appr=a['appraisedPrice'], low=a['lowestSellingPrice'], fails=a.get('numberOfFailures') or 0,
               area=area, mkt=mkt, sd=sd, sgg=sgg, emd=emd, seoul=int(sd == '서울'),
               age=a.get('constructYear'), hh=a.get('totalHouseholds') or tot_hh,
               py_share=(best[2].get('households') or np.nan) / tot_hh,
               jeonse_ratio=(best[4] / best[3]) if best[4] else np.nan,
               mom3=ch[last] / idx(mshift(last, 3)) - 1, mom6=ch[last] / idx(mshift(last, 6)) - 1,
               mom12=ch[last] / idx(mshift(last, 12)) - 1,
               dd24=ch[last] / max(ch[m] for m in ms if m >= mshift(last, 24)) - 1,
               lag_m=((T - pd.Timestamp(reg[:10])).days / 30.4) if reg else np.nan,
               date=T)
    row['r_appr_mkt'] = row['appr'] / mkt; row['r_low_mkt'] = row['low'] / mkt
    row['heat'] = recent_heat(df, row['seoul'], T)
    row['rate'] = rate_at(T); row['rate_chg6'] = rate_at(T) - rate_at(T - pd.DateOffset(months=6))
    row['tohu_r'] = int(tohu_at(T, sd, sgg, emd) or ('토지거래허가' in kw))
    row['regulated'] = regulated_at(T, sd, sgg); row['loan_ratio'] = loan_ratio(T, sd, sgg, mkt)
    info = dict(name=d.get('name'), case=a.get('caseName'), address=a.get('address'), keyword=kw.strip(),
                pyeong=best[1], area=area, appr_eok=round(row['appr'] / 1e8, 3), low_eok=round(row['low'] / 1e8, 3),
                fails=row['fails'], bidding_date=str(T.date()), richgo_sise_eok=round(mkt / 1e8, 3),
                appr_vs_sise=round(row['r_appr_mkt'], 3))
    return pd.DataFrame([row]), info


def predict(danji, auction_id):
    cfg = json.load(open(os.path.join(HERE, 'auction_config.json')))
    df = load_train()
    row, info = target_row(danji, auction_id, df)
    T = row.date.iloc[0]
    logs = {m: float(fit_predict(m, df, row, T)[0]) for m in MEMBERS}
    mkt = float(row.mkt.iloc[0])
    et = mkt * np.exp(logs['엑스트라트리'] + cfg['median_resid']['엑스트라트리'])
    en = mkt * np.exp(np.mean([logs[m] for m in ENSEMBLE]) + cfg['median_resid']['앙상블'])
    warn = []
    if any(w in info['keyword'] for w in ['지분', '대항력', '유치권', '법정지상권', '선순위', '재매각', '별도등기', '대지권미등기']):
        warn.append('권리위험 키워드 — 학습 대상(일반 물건)과 달라 예측 신뢰 낮음')
    if info['appr_vs_sise'] < 0.6:
        warn.append('감정가가 시세의 60% 미만 — 지분경매 의심, 예측 부적합')
    out = dict(info, p50_extratrees_manwon=int(round(et / 1e4)), p50_ensemble_manwon=int(round(en / 1e4)),
               p50_extratrees_eok=round(et / 1e8, 2), p50_ensemble_eok=round(en / 1e8, 2),
               model_error_note='평균 오차 약 5.7% (2025-02~2026-10 롤링 검증)', warnings=warn)
    print(json.dumps(out, ensure_ascii=False))


def calibrate():
    df = load_train()
    origins = pd.date_range((df.date.max() - pd.DateOffset(months=12)).normalize().replace(day=1), df.date.max(), freq='MS')
    res = {'엑스트라트리': [], '앙상블': []}
    for T in origins:
        tr, te = df[df.date < T], df[(df.date >= T) & (df.date < T + pd.DateOffset(months=1))]
        if len(te) == 0: continue
        p = {m: fit_predict(m, tr, te, T) for m in MEMBERS}
        res['엑스트라트리'] += list(te.y.values - p['엑스트라트리'])
        res['앙상블'] += list(te.y.values - np.mean([p[m] for m in ENSEMBLE], axis=0))
    cfg = dict(built='2026-10-30', n_train=int(len(df)), n_resid=len(res['앙상블']),
               median_resid={k: round(float(np.median(v)), 5) for k, v in res.items()},
               mape_recent={k: round(float(np.mean(np.abs(np.exp(v) - 1))) * 100, 2) for k, v in res.items()})
    json.dump(cfg, open(os.path.join(HERE, 'auction_config.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(cfg, ensure_ascii=False))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['predict', 'calibrate'])
    ap.add_argument('--danji'); ap.add_argument('--auction')
    a = ap.parse_args()
    calibrate() if a.cmd == 'calibrate' else predict(a.danji, a.auction)
