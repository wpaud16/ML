#!/usr/bin/env python3
"""유찰 확률 모델 — 이번 회차가 유찰될 확률 (2026-11-03 추가).

학습: 낙찰까지 간 사건의 회차별 이력(리치고 historyList 의 매각기일: 유찰/매각)
  아파트 fail_rounds.csv (1,412건 · 2,830회차) / 오피스텔 officetel/ot_fail_rounds.csv (716건 · 2,135회차)
특성: 최저가/시세, 최저가/감정가, 지금까지 유찰 횟수, 면적·연식·세대수·시세흐름·금리·규제·과열도 등
모델: 부스팅 분류기(최근 사례 가중) + 최근 12개월 롤링 예측으로 확률 보정(Platt)
한계: 끝내 낙찰된 사건만 있어(취하·진행중 사건 제외) 여러 번 유찰된 뒤의 유찰 확률은 조금 낮게 나올 수 있음

  python3 fail_model.py calibrate          # 백테스트 + 보정값 재계산 → fail_config.json
"""
import json, os, sys, warnings
import numpy as np, pandas as pd

warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss

ROUNDS = {'apt': os.path.join(HERE, 'fail_rounds.csv'), 'ot': os.path.join(HERE, 'officetel', 'ot_fail_rounds.csv')}
CFG = os.path.join(HERE, 'fail_config.json')
BASE = ['r_rlow_mkt', 'r_rlow_appr', 'ridx', 'area', 'age', 'hh', 'mom3', 'mom6', 'dd24', 'rate', 'rate_chg6',
        'regulated', 'loan_ratio', 'heat', 'jeonse_ratio', 'seoul_']
FEATS = {'apt': BASE, 'ot': BASE + ['is_check']}
HALF = 540  # 최근 사례 가중 (일)
_CACHE = {}
import threading
_LOCK = threading.Lock()


def _lg(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def _train(kind):
    if kind == 'apt':
        import auction_predictor as ap
        d = ap.load_train()
    else:
        import officetel_model as om
        d = om.load_train()
    d = d.copy(); d['dkey'] = d.date.dt.strftime('%Y-%m-%d'); d['skey'] = d.sell.astype('int64')
    return d


def load_rounds(kind):
    r = pd.read_csv(ROUNDS[kind]); r['dkey'] = r.date.astype(str).str[:10]; r['skey'] = r.sell.astype('int64')
    tr = _train(kind).drop_duplicates(['danji', 'dkey', 'skey']).drop(columns=['case'], errors='ignore')
    R = r.drop(columns=['date', 'sell']).merge(tr, on=['danji', 'dkey', 'skey'], how='inner')
    R['rdate'] = pd.to_datetime(R.rdate)
    return add_feats(R, low=R.rlow).sort_values('rdate').reset_index(drop=True)


def add_feats(d, low=None, ridx=None):
    d = d.copy()
    low = d.low if low is None else low
    d['r_rlow_mkt'] = low / d.mkt; d['r_rlow_appr'] = low / d.appr
    if ridx is not None: d['ridx'] = ridx
    d['seoul_'] = (d.sd == '서울').astype(int) if 'sd' in d else 1
    if 'is_check' not in d: d['is_check'] = 0
    return d


def _fit(tr, kind, T):
    X = tr[FEATS[kind]]; med = X.median()
    w = np.exp(-((pd.Timestamp(T) - tr.rdate).dt.days.values) / HALF)
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.04, max_depth=3, min_samples_leaf=20,
                                       l2_regularization=2.0, random_state=0).fit(X.fillna(med), tr.fail, sample_weight=w)
    return m, med


def _raw(model, x, kind):
    m, med = model
    return m.predict_proba(x[FEATS[kind]].fillna(med))[:, 1]


def calibrate(kind, start='2024-07-01'):
    R = load_rounds(kind); R = R[R.ridx <= 4]
    R['m'] = R.rdate.dt.to_period('M').dt.to_timestamp()
    o = []
    for T in pd.date_range(start, R.rdate.max(), freq='MS'):
        tr, te = R[R.rdate < T], R[R.m == T]
        if len(te) == 0 or len(tr) < 300: continue
        o.append(te[['m', 'ridx', 'fail']].assign(p=_raw(_fit(tr, kind, T), te, kind),
                                                  base=te.ridx.clip(0, 3).map(tr.groupby(tr.ridx.clip(0, 3)).fail.mean()).values))
    o = pd.concat(o)
    # 롤링 보정(직전 12개월 예측으로 Platt) 을 백테스트에도 똑같이 적용해 성능 측정
    o['pc'] = np.nan
    for T in sorted(o.m.unique()):
        h = o[(o.m < T) & (o.m >= T - pd.DateOffset(months=12))]
        if len(h) < 300: continue
        c = LogisticRegression(C=1e3).fit(np.c_[_lg(h.p), h.ridx >= 1], h.fail)
        t = o.m == T; o.loc[t, 'pc'] = c.predict_proba(np.c_[_lg(o.p[t]), o.ridx[t] >= 1])[:, 1]
    s = o[o.pc.notna()]
    h = o[o.m >= o.m.max() - pd.DateOffset(months=11)]
    c = LogisticRegression(C=1e3).fit(np.c_[_lg(h.p), h.ridx >= 1], h.fail)

    def met(x):
        return dict(n=int(len(x)), actual_pct=round(float(x.fail.mean()) * 100, 1), pred_pct=round(float(x.pc.mean()) * 100, 1),
                    auc=round(float(roc_auc_score(x.fail, x.pc)), 3) if x.fail.nunique() > 1 else None,
                    brier=round(float(brier_score_loss(x.fail, x.pc)), 3), brier_base=round(float(brier_score_loss(x.fail, x.base)), 3),
                    acc_pct=round(float(((x.pc > .5) == x.fail).mean()) * 100, 1))
    s = s.assign(bin=pd.cut(s.pc, [0, .1, .3, .5, .7, .9, 1], include_lowest=True))
    calib = [dict(bin=str(b), n=int(len(g)), pred=round(float(g.pc.mean()) * 100, 1), actual=round(float(g.fail.mean()) * 100, 1))
             for b, g in s.groupby('bin') if len(g)]
    cfg = json.load(open(CFG)) if os.path.exists(CFG) else {}
    cfg[kind] = dict(built=str(pd.Timestamp.today().date()), n_rounds=int(len(R)), n_cases=int(R.case.nunique()) if 'case' in R else None,
                     platt=[round(float(c.coef_[0][0]), 5), round(float(c.coef_[0][1]), 5), round(float(c.intercept_[0]), 5)],
                     test_from=str(s.m.min().date()), all=met(s), first=met(s[s.ridx == 0]), later=met(s[s.ridx >= 1]), calib=calib)
    json.dump(cfg, open(CFG, 'w'), ensure_ascii=False, indent=1)
    print(kind, json.dumps({k: v for k, v in cfg[kind].items() if k != 'calib'}, ensure_ascii=False))
    _CACHE.pop(kind, None)
    return cfg[kind]


def prob(kind, row, cfg=None):
    """row: 예측 대상 1행 DataFrame (low=이번 회차 최저가, fails=지금까지 유찰 수). → 이번 회차 유찰 확률(0~1)."""
    cfg = cfg or json.load(open(CFG))
    with _LOCK:   # 예측은 여러 스레드에서 돌아서, 모델은 한 번만 학습
        if kind not in _CACHE:
            R = load_rounds(kind); R = R[R.ridx <= 4]
            _CACHE[kind] = _fit(R, kind, R.rdate.max() + pd.Timedelta(days=1))
    x = add_feats(row, ridx=row.fails.clip(0, 4).values)
    a, b, c0 = cfg[kind]['platt']
    p = _raw(_CACHE[kind], x, kind)[0]
    return float(1 / (1 + np.exp(-(a * _lg(p) + b * float(x.ridx.iloc[0] >= 1) + c0))))


def fail_info(kind, row, cfg=None):
    try:
        cfg = cfg or json.load(open(CFG))
        p = prob(kind, row, cfg)
        m = cfg[kind]['first' if int(row.fails.iloc[0]) == 0 else 'later']
        lvl = '높음' if p >= .7 else ('보통' if p >= .3 else '낮음')
        return dict(prob_pct=int(round(p * 100)), level=lvl,
                    note=f"백테스트: 이 회차 유형 평균 유찰률 {m['actual_pct']}% · 예측 정확도 {m['acc_pct']}%")
    except Exception as e:
        return dict(error=f'{type(e).__name__}: {e}'[:200])


def rounds_from_history(danji, date, sell, auction_id, hist):
    """낙찰된 사건 1건의 이력 → 회차 행들 (마지막 매각 회차까지)."""
    hs = sorted([x for x in hist or [] if x.get('appointedDayType') == '매각기일' and x.get('results') in ('유찰', '매각')
                 and x.get('lowestSellingPrice')], key=lambda x: x['appointedDayAt'])
    k = [j for j, x in enumerate(hs) if x['results'] == '매각' and x['appointedDayAt'] == str(date)[:10]]
    if not k: return []
    out, nf = [], 0
    for x in hs[:k[0] + 1]:
        f = int(x['results'] == '유찰')
        out.append(dict(danji=danji, date=str(date)[:10], sell=int(sell), case=auction_id, rdate=x['appointedDayAt'],
                        rlow=int(x['lowestSellingPrice']), ridx=nf, fail=f))
        nf += f
    return out


def add_rounds(kind, new_rows):
    """재학습 때 새 낙찰 사례(auction_id 포함)의 회차 이력을 받아 회차 파일에 추가. 추가한 회차 수 반환."""
    import batch_predict as bp
    if new_rows is None or len(new_rows) == 0 or 'auction_id' not in new_rows: return 0
    old = pd.read_csv(ROUNDS[kind]); have = set(old.case)
    rows = []
    for r in new_rows.itertuples():
        if r.auction_id in have or not isinstance(r.auction_id, str): continue
        try:
            det = bp.auction_detail(r.auction_id) or {}
            rows += rounds_from_history(r.danji, r.date, r.sell, r.auction_id, det.get('historyList'))
        except Exception:
            continue
    if rows:
        pd.concat([old, pd.DataFrame(rows)], ignore_index=True).to_csv(ROUNDS[kind], index=False)
    return len(rows)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'calibrate':
        for k in (sys.argv[2:] or ['apt', 'ot']): calibrate(k)
