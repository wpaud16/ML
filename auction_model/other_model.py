#!/usr/bin/env python3
"""상가·건물 낙찰가 모델 (2026-11-24 사용자 요청: "백데이터 학습해서 넣어줘").

학습 데이터: history_crawl.py 가 매일 밤 모으는 리치고 과거 경매 (<저장소 상위>/hist/rows.jsonl, 서울·경기·인천 상가·건물).
  매각된 회차 1건 = 학습 1행. 목표 = log(낙찰가 / 그 회차 최저가). 권리 깨끗한 물건만 (other_items.rights_ok 와 같은 기준).
  유찰 모델: 매각기일 회차마다 유찰/매각 (유찰 확률).
모델: 강한 규제 LightGBM(L1) 과 '카테고리·유찰 횟수별 중앙 낙찰가율' 반반 평균 (백테스트 오차 약 11%; 응찰자 수를 미리 알 수 없어 한계).
유찰 모델: LightGBM + 랜덤포레스트 분류 평균 (백테스트 AUC 0.855, 구간별 실제 비율과 일치). 확률표 = 월별 롤링 백테스트 잔차 분포(카테고리별)의 분위수.
  P(내 입찰가로 낙찰) ≈ P(실제 낙찰가 < 내 입찰가 | 매각됨) — 아파트 모델과 같은 정의.

python other_model.py backtest   # 월별 롤링 검증 (오차 출력)
python other_model.py train      # 전체로 학습 → other_model/model.pkl, config.json (backtest 잔차 포함)
"""
import json, math, os, pickle, re, sys
from datetime import datetime
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = os.environ.get('HIST_DIR') or os.path.join(os.path.dirname(os.path.dirname(HERE)), 'hist')
MDIR = os.path.join(HERE, 'other_model')
HARD = {'지분': r'지분\s*(?:매각|경매|만)|\d+\s*분의\s*\d+\s*지분\s*(?:매각|경매)', '유치권': r'유치권',
        '법정지상권': r'법정지상권', '대지권없음': r'대지권\s*(?:없|미등기)', '건물만': r'건물만\s*(?:매각|경매)',
        '토지만': r'토지만\s*(?:매각|경매)', '별도등기': r'별도\s*등기', '분묘': r'분묘'}
TXT = {'tx_vacant': r'공실|미사용|비어\s*있', 'tx_lease': r'임대\s*중|영업\s*중|임차인이?\s*사용|점포로\s*이용',
       'tx_complex': r'아파트\s*단지|단지\s*내\s*상가', 'tx_market': r'상가\s*밀집|번화|상업지역',
       'tx_hosp': r'병원|의원|학원|근린생활시설\(학원', 'tx_sub': r'지하철|전철|역\s'}
TD = ('근린시설', '근린주택', '다가구주택', '대지', '도로')
FEATS = ['cat_b', 'seoul', 'incheon', 'sgg_c', 'log_appr', 'low_ratio', 'log_low', 'fails', 'log_area', 'log_land', 'land_per_area',
         'floor', 'basement', 'ground', 'resale', 'month_i', 'step', 'court_c', 'log_appr_m2', 'rel_appr_m2'] + list(TXT) + ['td_' + t for t in TD]


def _floor(addr):
    a = addr or ''
    m = re.search(r'(?:지하|B)\s*(\d+)\s*층', a)
    if m: return -int(m.group(1))
    m = re.search(r'(\d+)\s*층', a)
    return int(m.group(1)) if m else np.nan


def hard_flags(address, td, appraisal):
    head = ' '.join([address or '', ' '.join(td or [])])
    text = head + ' ' + (appraisal or '')
    return [n for n, p in HARD.items() if re.search(p, text)] + (['지분'] if '지분' in head else [])


def feat_row(cat, sd, sgg, appr, low, fails, area, land, address, td, appraisal, resale, when, prev_low=None, court=None):
    """한 경매 회차 → 피처 dict (학습·예측 공용). appr·low 단위 만원, when = 'YYYY-MM-DD' (매각기일)."""
    f = _floor(address)
    t = appraisal or ''
    d = dict(cat_b=int(cat == '건물'), seoul=int(sd == '서울'), incheon=int(sd == '인천'), sgg_key=f'{sd} {sgg}',
             log_appr=math.log(max(appr, 1)), low_ratio=low / appr if appr else np.nan, log_low=math.log(max(low, 1)),
             fails=fails, log_area=math.log(area) if area else np.nan, log_land=math.log(land) if land else np.nan,
             land_per_area=(land / area) if land and area else np.nan, floor=f,
             basement=int(f < 0) if f == f else 0, ground=int(f == 1) if f == f else 0, resale=int(bool(resale)),
             month_i=(int(when[:4]) - 2025) * 12 + int(when[5:7]) if when else np.nan,
             step=(prev_low / low) if prev_low and low else 1.0,   # 직전 회차 최저가 / 이번 최저가 (저감률 20%·30%)
             court_key=court or '', log_appr_m2=math.log(appr / area) if area else np.nan)
    for k, p in TXT.items():
        d[k] = int(bool(re.search(p, t)))
    for x in TD:
        d['td_' + x] = int(x in (td or []))
    return d


def load_rows():
    R = {}
    with open(os.path.join(HIST, 'rows.jsonl'), encoding='utf-8') as fh:
        for l in fh:
            try:
                r = json.loads(l)
            except Exception:
                continue
            R[r['id']] = r   # 같은 id 는 마지막(최신) 상태
    return [r for r in R.values() if r.get('cat') in ('상가', '건물') and r.get('appr')]


def clean(r):
    rt = r.get('rights') or {}
    return rt.get('known') and not rt.get('tenant') and not rt.get('right') and not hard_flags(r.get('address'), r.get('td'), r.get('appraisal'))


def rounds(r):
    """매각기일 회차 [(date, low, res, fails_before, resale)] (유찰·매각만)."""
    out, nf, sold_once, prev = [], 0, False, None
    for h in sorted(r.get('hist') or [], key=lambda h: h.get('d') or ''):
        if h.get('t') == '대금지급기한' and h.get('res') == '미납':
            sold_once = True
        if h.get('t') != '매각기일' or h.get('res') not in ('유찰', '매각') or not h.get('low'):
            continue
        out.append((h['d'], h['low'], h['res'], nf, sold_once, prev if prev and prev > h['low'] else None))
        prev = h['low']
        if h['res'] == '유찰':
            nf += 1
    return out


def build():
    """→ (sales DataFrame, rounds DataFrame)."""
    S, F = [], []
    for r in load_rows():
        if not clean(r):
            continue
        rs = rounds(r)
        for i, (d, low, res, nf, resale, pl) in enumerate(rs):
            base = feat_row(r['cat'], r.get('sd'), r.get('sgg'), r['appr'], low, nf, r.get('area'), r.get('land'),
                            r.get('address'), r.get('td'), r.get('appraisal'), resale, d, pl, r.get('court'))
            base.update(id=r['id'], case=r.get('case'), cat=r['cat'], date=d, low=low, appr=r['appr'])
            F.append(dict(base, failed=int(res == '유찰')))
            # 매각 회차: 마지막 매각 회차의 낙찰가 = sell (재매각이면 앞 회차 낙찰가는 모름 → 마지막만)
            if res == '매각' and r.get('sell') and i == max(j for j, x in enumerate(rs) if x[2] == '매각'):
                if 0.5 * low <= r['sell'] <= 20 * low:
                    S.append(dict(base, sell=r['sell'], bidders=r.get('bidders'), y=math.log(r['sell'] / low)))
    return pd.DataFrame(S), pd.DataFrame(F)


def _sgg_codes(df, ref):
    """구·시 → 학습 구간의 평균 잔차 순위 대신 단순 코드(빈도 10건 미만은 -1)."""
    vc = ref['sgg_key'].value_counts()
    keys = sorted(vc[vc >= 10].index)
    m = {k: i for i, k in enumerate(keys)}
    return df['sgg_key'].map(m).fillna(-1).astype(int), keys


def _enc(df, enc):
    """구·법원 코드, ㎡당 감정가의 구 중앙값 대비 비율 (학습 구간에서 만든 enc 사용)."""
    df = df.copy()
    df['sgg_c'] = df['sgg_key'].map(enc['sgg']).fillna(-1).astype(int)
    df['court_c'] = df['court_key'].map(enc['court']).fillna(-1).astype(int)
    med = df.apply(lambda r: enc['m2'].get(f"{r['cat_b']}|{r['sgg_key']}", enc['m2'].get(f"{r['cat_b']}|", np.nan)), axis=1)
    df['rel_appr_m2'] = df['log_appr_m2'] - med
    return df


def _make_enc(tr):
    vc = tr['sgg_key'].value_counts(); keys = sorted(vc[vc >= 10].index)
    cv = tr['court_key'].value_counts(); ck = sorted(cv[cv >= 10].index)
    m2 = {}
    for (cb, s), g in tr.groupby(['cat_b', 'sgg_key']):
        if g.log_appr_m2.notna().sum() >= 5: m2[f'{cb}|{s}'] = float(g.log_appr_m2.median())
    for cb, g in tr.groupby('cat_b'):
        m2[f'{cb}|'] = float(g.log_appr_m2.median())
    return dict(sgg={k: i for i, k in enumerate(keys)}, court={k: i for i, k in enumerate(ck)}, m2=m2)


def _fit(tr, target='y', cls=False):
    import lightgbm as lgb
    from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
    enc = _make_enc(tr)
    tr = _enc(tr, enc)
    X = tr[FEATS].astype(float)
    if cls:
        g = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=30, subsample=0.8,
                               subsample_freq=1, colsample_bytree=0.8, verbose=-1)
        rf = RandomForestClassifier(n_estimators=150, min_samples_leaf=30, max_depth=14, n_jobs=-1, random_state=0)   # 파일 크기 줄임
        g.fit(X, tr[target]); rf.fit(X.fillna(-9), tr[target])
        return dict(lgb=g, rf=rf, enc=enc, cls=True)
    # 2026-11-24 백테스트: 랜덤포레스트·약한 규제 LightGBM 은 기준선(유찰 구간 중앙값)보다 못함(11.3~11.6% vs 11.0%).
    # 강한 규제 L1 LightGBM 과 기준선을 반반 섞은 것이 가장 나음(10.9%) → 이 구성 사용.
    g = lgb.LGBMRegressor(objective='l1', n_estimators=250, learning_rate=0.02, num_leaves=7, min_child_samples=60,
                          subsample=0.7, subsample_freq=1, colsample_bytree=0.6, reg_lambda=5, verbose=-1)
    g.fit(X.fillna(-9), tr[target])
    base = {f'{c}|{f}': float(v) for (c, f), v in tr.assign(fb=tr.fails.clip(upper=4)).groupby(['cat', 'fb'])[target].median().items()}
    return dict(lgb=g, base=base, base_all=float(tr[target].median()), enc=enc, cls=False)


def _pred(m, df):
    df = _enc(df, m['enc'])
    X = df[FEATS].astype(float)
    if m['cls']:
        return (m['lgb'].predict_proba(X)[:, 1] + m['rf'].predict_proba(X.fillna(-9))[:, 1]) / 2
    cat = np.where(df['cat_b'] == 1, '건물', '상가')
    b = np.array([m['base'].get(f'{c}|{min(int(f), 4)}', m['base_all']) for c, f in zip(cat, df['fails'])])
    return 0.5 * m['lgb'].predict(X.fillna(-9)) + 0.5 * b


def backtest(S=None, F=None, start='2026-03', verbose=True):
    if S is None:
        S, F = build()
    S = S.sort_values('date'); F = F.sort_values('date')
    months = sorted({d[:7] for d in S.date if d[:7] >= start})
    res, fres = [], []
    for mo in months:
        tr, te = S[S.date < mo + '-01'], S[S.date.str[:7] == mo]
        if len(tr) < 300 or not len(te): continue
        m = _fit(tr)
        p = _pred(m, te)
        # 기준선: 같은 카테고리·유찰 구간의 중앙 낙찰가/최저가
        fb = tr.assign(fb=tr.fails.clip(upper=4)).groupby(['cat', 'fb']).y.median()
        base = [fb.get((c, min(f, 4)), tr.y.median()) for c, f in zip(te.cat, te.fails)]
        res.append(te.assign(p=p, base=base))
        ftr, fte = F[F.date < mo + '-01'], F[F.date.str[:7] == mo]
        if len(fte):
            fm = _fit(ftr, 'failed', cls=True)
            fres.append(fte.assign(pf=_pred(fm, fte)))
    B = pd.concat(res)
    B['err'] = np.exp(B.p - B.y) - 1           # 예측/실제 - 1
    B['err_b'] = np.exp(B.base - B.y) - 1
    B['resid'] = B.y - B.p                     # log(실제/예측)
    out = {}
    for c, g in [('전체', B)] + list(B.groupby('cat')) + [('서울 ' + c, g) for c, g in B[B.seoul == 1].groupby('cat')]:
        out[c] = dict(n=len(g), mape=round(g.err.abs().mean() * 100, 2), med_ape=round(g.err.abs().median() * 100, 2),
                      base_mape=round(g.err_b.abs().mean() * 100, 2), within5=round((g.err.abs() <= .05).mean() * 100, 1),
                      within10=round((g.err.abs() <= .10).mean() * 100, 1), bias=round(g.err.median() * 100, 2))
    FB = pd.concat(fres) if fres else None
    if FB is not None:
        from sklearn.metrics import roc_auc_score, brier_score_loss
        out['유찰'] = dict(n=len(FB), auc=round(roc_auc_score(FB.failed, FB.pf), 3), brier=round(brier_score_loss(FB.failed, FB.pf), 3),
                         base_rate=round(FB.failed.mean(), 3))
    if verbose:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    return B, FB, out


QS = [0.40, 0.45, 0.50, 0.55, 0.60]


def train():
    S, F = build()
    B, FB, rep = backtest(S, F, verbose=True)
    os.makedirs(MDIR, exist_ok=True)
    m = _fit(S); fm = _fit(F, 'failed', cls=True)
    # 확률 보정: 백테스트 잔차(log 실제/예측) 카테고리별 — 최근 12개월
    resid = {c: sorted(g.resid.round(4).tolist()) for c, g in B.groupby('cat')}
    # 유찰 확률 보정 (구간별 실제 비율)
    cal = None
    if FB is not None:
        bins = np.linspace(0, 1, 11)
        FB['b'] = np.clip(np.digitize(FB.pf, bins) - 1, 0, 9)
        cal = {int(b): [round(g.pf.mean(), 3), round(g.failed.mean(), 3), len(g)] for b, g in FB.groupby('b')}
    pickle.dump(dict(m=m, fm=fm), open(os.path.join(MDIR, 'model.pkl'), 'wb'))
    cfg = dict(trained_at=datetime.now().isoformat(timespec='seconds'), n_sales=len(S), n_rounds=len(F),
               sale_dates=[S.date.min(), S.date.max()], backtest=rep, resid=resid, fail_cal=cal, feats=FEATS)
    json.dump(cfg, open(os.path.join(MDIR, 'config.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('saved', len(S), 'sales', len(F), 'rounds')


_M = None


def _load():
    global _M
    if _M is None:
        _M = (pickle.load(open(os.path.join(MDIR, 'model.pkl'), 'rb')),
              json.load(open(os.path.join(MDIR, 'config.json'), encoding='utf-8')))
    return _M


def predict(cat, sd, sgg, appr, low, fails, area, land, address, td, appraisal, resale, bidding_date, prev_low=None, court=None):
    """→ dict(p50_manwon, bid_by_prob_manwon{40%..60%}, prob_by_bid, fail_pct, mape). 단위 만원."""
    M, cfg = _load()
    row = feat_row(cat, sd, sgg, appr, low, fails or 0, area, land, address, td, appraisal, resale, bidding_date, prev_low, court)
    df = pd.DataFrame([row])
    mu = float(_pred(M['m'], df)[0])
    r = np.array(cfg['resid'].get(cat) or sum(cfg['resid'].values(), []))
    price = lambda q: max(low, int(round(low * math.exp(mu + float(np.quantile(r, q))) / 10) * 10))
    bids = {f'{int(q * 100)}%': price(q) for q in QS}
    p50 = int(round(low * math.exp(mu + float(np.median(r)))))
    grid = []
    lo, hi = price(0.2), price(0.8)
    # 낙찰확률 20~80% 구간을 8칸 안팎으로 — 간격은 100만·200만·500만·1000만… 중 가장 촘촘하면서 10칸 이하
    step = next((s for s in (100, 200, 500, 1000, 2000, 5000, 10000) if (hi - lo) / s <= 10), 20000)
    b = int(math.ceil(lo / step) * step)
    while b <= hi and len(grid) < 12:
        pr = float((r < math.log(b / low) - mu).mean())
        grid.append(dict(bid_manwon=b, prob=int(round(pr * 100)))); b += step
    pf = float(_pred(M['fm'], df)[0])
    # fail_cal(백테스트 구간별 예측 평균 vs 실제 비율)이 거의 일치해서 원 확률을 그대로 씀 (구간 값으로 바꾸면 뭉개짐)
    bt = (cfg.get('backtest') or {}).get(('서울 ' if sd == '서울' else '') + cat) or (cfg.get('backtest') or {}).get(cat) or {}
    return dict(model='상가·건물 모델(LightGBM+랜덤포레스트, 과거 낙찰 %d건)' % cfg['n_sales'], p50_manwon=p50,
                p50_ratio_appr=round(p50 / appr, 3) if appr else None, bid_by_prob_manwon=bids,
                prob_by_bid=grid, fail_pct=int(round(pf * 100)), mape=bt.get('mape'), within10=bt.get('within10'))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'backtest'
    if cmd == 'train':
        train()
    else:
        backtest()
