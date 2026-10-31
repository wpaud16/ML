#!/usr/bin/env python3
"""JM 경매 낙찰가 예측기 (앙상블: 부스팅 + 군집별 회귀) — 보정된 낙찰확률.

사용법 (같은 폴더에 auction_train.csv, auction_config.json 필요):
  python3 auction_predictor.py predict --danji a7BuFFg --auction C49LSPHG
      -> JSON: 낙찰확률 40/45/50/55/60% 입찰가(만원), 500만원 단위 입찰가별 낙찰확률, 입력값 요약
  python3 auction_predictor.py calibrate   # (개발용) 월별 롤링 예측오차로 확률 곡선 재계산

낙찰확률 = P(실제 낙찰가 < 내 입찰가). 최근 12개월 롤링 예측오차 분포(가우시안 커널, 폭 BW)로
원확률을 구한 뒤, 2025-02 이후 1회 유찰 사건의 실제 결과로 맞춘 로지스틱 보정(a, b)을 적용한다.

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
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans
except ImportError:
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--break-system-packages', 'scikit-learn'])
    from sklearn.linear_model import Ridge
    from sklearn.ensemble import HistGradientBoostingRegressor
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
MEMBERS = {'부스팅_감쇠': ('gb', S4, 365), '군집별회귀': ('cluster', S1, 365)}
ENSEMBLE = ['부스팅_감쇠', '군집별회귀']


def fit_predict(name, tr, te, T):
    kind, cols, decay = MEMBERS[name]
    Xtr, Xte = prep(tr)[cols], prep(te)[cols]
    med = Xtr.median(); Xtr, Xte = Xtr.fillna(med), Xte.fillna(med)
    sc = StandardScaler().fit(Xtr); Ztr, Zte = sc.transform(Xtr), sc.transform(Xte)
    y = tr.y.values
    wt = None if not decay else np.exp(-((pd.Timestamp(T) - tr.date).dt.days.values) / decay)
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


BW = 0.012
PROB_LEVELS = [40, 45, 50, 55, 60]


def _logit(p):
    p = np.clip(p, 1e-3, 1 - 1e-3); return np.log(p / (1 - p))


def raw_prob(pool, g):
    """P(residual < g) with a Gaussian-kernel-smoothed residual distribution; g = log(bid/mkt) - pred."""
    from math import erf
    z = (g - np.asarray(pool)) / BW
    return float(np.mean(0.5 * (1 + np.vectorize(erf)(z / np.sqrt(2)))))


def win_prob(pool, a, b, g):
    return float(1 / (1 + np.exp(-(a * _logit(raw_prob(pool, g)) + b))))


def predict_dict(danji, auction_id, df=None, cfg=None):
    cfg = cfg or json.load(open(os.path.join(HERE, 'auction_config.json')))
    df = load_train() if df is None else df
    row, info = target_row(danji, auction_id, df)
    T = row.date.iloc[0]
    c = float(np.mean([fit_predict(m, df, row, T)[0] for m in ENSEMBLE]))
    mkt, low = float(row.mkt.iloc[0]), float(row.low.iloc[0])
    pool, a, b = cfg['resid_pool'], cfg['calib_a'], cfg['calib_b']

    def wp(bid):
        return 0.0 if bid < low else win_prob(pool, a, b, np.log(bid / mkt) - c)

    def price_at(q):  # bisection on bid (원), 1만원 precision
        lo, hi = low, mkt * 1.5
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if wp(mid) < q else (lo, mid)
        return max(low, hi)
    prices = {f'{q}%': int(round(price_at(q / 100) / 1e4)) for q in PROB_LEVELS}
    p25, p75 = price_at(0.25), price_at(0.75)
    grid = np.arange(np.ceil(max(low, p25) / 5e6) * 5e6, p75 + 1, 5e6)
    table = [dict(bid_manwon=int(g / 1e4), bid_eok=round(g / 1e8, 2), prob=int(round(wp(g) * 100))) for g in grid]
    warn = []
    if any(w in info['keyword'] for w in ['지분', '대항력', '유치권', '법정지상권', '선순위', '재매각', '별도등기', '대지권미등기']):
        warn.append('권리위험 키워드 — 학습 대상(일반 물건)과 달라 예측 신뢰 낮음')
    if info['appr_vs_sise'] < 0.6:
        warn.append('감정가가 시세의 60% 미만 — 지분경매 의심, 예측 부적합')
    out = dict(info, model='앙상블(부스팅+군집별회귀)',
               bid_by_prob_manwon=prices,
               bid_by_prob_eok={k: round(v / 1e4, 2) for k, v in prices.items()},
               prob_by_bid_5m=table,
               p50_ensemble_manwon=prices['50%'], p50_ensemble_eok=round(prices['50%'] / 1e4, 2),
               model_error_note=f"평균 오차 약 {cfg['mape_recent']}% (최근 12개월 롤링), 확률 보정 오차 약 ±5%p",
               warnings=warn)
    return out


def predict(danji, auction_id):
    print(json.dumps(predict_dict(danji, auction_id), ensure_ascii=False))


def calibrate(start='2024-01-01'):
    df = load_train()
    df['m0'] = df.date.dt.to_period('M').dt.to_timestamp()
    res = pd.Series(np.nan, index=df.index)
    for T in pd.date_range(start, df.date.max(), freq='MS'):
        tr, te = df[df.date < T], df[(df.date >= T) & (df.date < T + pd.DateOffset(months=1))]
        if len(te) == 0: continue
        res[te.index] = te.y.values - np.mean([fit_predict(m, tr, te, T) for m in ENSEMBLE], axis=0)
    # calibration pairs: each 1회 유찰 case, prior-12-month pool, offsets -15%..+15%
    offs = np.linspace(-.15, .15, 31); X, H = [], []
    for i in df.index[(df.date >= pd.Timestamp(start) + pd.DateOffset(months=12)) & (df.fails == 1) & res.notna()]:
        T = df.m0[i]; pool = res[(df.date < T) & (df.date >= T - pd.DateOffset(months=12)) & res.notna()].values
        if len(pool) < 50: continue
        for g in offs:
            X.append(_logit(raw_prob(pool, g))); H.append(float(res[i] < g))
    from sklearn.linear_model import LogisticRegression
    lr = LogisticRegression(C=1e6).fit(np.array(X).reshape(-1, 1), H)
    T0 = df.m0.max() + pd.DateOffset(months=1)
    pool = res[(df.date >= T0 - pd.DateOffset(months=12)) & res.notna()]
    cfg = dict(built=str(pd.Timestamp.today().date()), model='앙상블(부스팅+군집별회귀)', n_train=int(len(df)),
               bw=BW, calib_a=round(float(lr.coef_[0][0]), 5), calib_b=round(float(lr.intercept_[0]), 5),
               n_calib_pairs=len(H), mape_recent=round(float(np.mean(np.abs(np.exp(pool) - 1))) * 100, 2),
               resid_pool=[round(float(x), 5) for x in pool.values])
    json.dump(cfg, open(os.path.join(HERE, 'auction_config.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in cfg.items() if k != 'resid_pool'} | {'n_pool': len(cfg['resid_pool'])}, ensure_ascii=False))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['predict', 'calibrate'])
    ap.add_argument('--danji'); ap.add_argument('--auction')
    a = ap.parse_args()
    calibrate() if a.cmd == 'calibrate' else predict(a.danji, a.auction)
