"""금리 백테스트 (2026-11-26 사용자 요청: 기준금리와 은행금리를 나눠서, 상가·건물도).
변형 4가지: 없음 / 기준금리(rate, rate_chg6) / 은행금리(bank, bank_chg6) / 둘 다.
은행금리 = 한국은행 예금은행 대출금리(신규취급액): 아파트·오피스텔 = 주택담보대출, 상가·건물 = 중소기업대출.
  매월 값은 다음 달 말에 발표 → 매각일 기준 2개월 전 값을 씀 (그날 실제로 알 수 있던 값).
python dev/rate_bt.py [apt ot fail other]   → dev/rate_bt_result.json"""
import json, os, sys, time, warnings
import numpy as np, pandas as pd

warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import auction_predictor as ap

BR = json.load(open(os.path.join(ROOT, 'bank_rate.json'), encoding='utf-8'))
LAG = 2
VARS = {'없음': [], '기준금리': ['rate', 'rate_chg6'], '은행금리': ['bank', 'bank_chg6'], '둘다': ['rate', 'rate_chg6', 'bank', 'bank_chg6'],
        # 2026-11-26 추가: 은행채 (산금채 1년), 은행채 5년 대용 국고채 5년. 시장금리라 전월 평균(1개월 전) 사용
        '은행채1년': ['bond1', 'bond1_chg6'], '국고채5년': ['bond5', 'bond5_chg6'], '기준+채권': ['rate', 'rate_chg6', 'bond1', 'bond5']}
if os.environ.get('VARIANTS'):
    VARS = {k: VARS[k] for k in os.environ['VARIANTS'].split(',')}
RATE_COLS = ['rate', 'rate_chg6', 'bank', 'bank_chg6', 'bond1', 'bond1_chg6', 'bond5', 'bond5_chg6']
OUT = os.path.join(HERE, 'rate_bt_result.json')


def bank_at(t, kind='mortgage', lag=LAG):
    s = BR[kind]; t = pd.Timestamp(t) - pd.DateOffset(months=lag)
    k = t.strftime('%Y-%m')
    if k in s: return s[k]
    ks = sorted(s); return s[ks[0]] if k < ks[0] else s[ks[-1]]


def add_rates(d, col='date', kind='mortgage'):
    t = pd.to_datetime(d[col])
    d['rate'] = [ap.rate_at(x) for x in t]
    d['rate_chg6'] = [ap.rate_at(x) - ap.rate_at(x - pd.DateOffset(months=6)) for x in t]
    d['bank'] = [bank_at(x, kind) for x in t]
    d['bank_chg6'] = [bank_at(x, kind) - bank_at(x - pd.DateOffset(months=6), kind) for x in t]
    for c, k in (('bond1', 'kdb1y'), ('bond5', 'ktb5y')):
        d[c] = [bank_at(x, k, 1) for x in t]
        d[c + '_chg6'] = [bank_at(x, k, 1) - bank_at(x - pd.DateOffset(months=6), k, 1) for x in t]
    return d


def swap(cols, v):
    return [c for c in cols if c not in RATE_COLS] + VARS[v]


def mape(res):
    r = np.asarray(res); return round(float(np.mean(np.abs(np.exp(r) - 1))) * 100, 3)


def stats(res):
    r = np.asarray(res)
    return dict(n=int(len(r)), mape=mape(r), within5=round(float((np.abs(np.exp(r) - 1) <= .05).mean()) * 100, 1),
                bias=round(float(np.median(np.exp(r) - 1)) * 100, 2))


# ---------------- 아파트 (운영 앙상블 부스팅+군집별회귀, 월별 롤링 2024-01~) ----------------
_prep0 = ap.prep


def prep_bank(d):
    X = _prep0(d)
    for c in RATE_COLS[2:]:
        X[c] = d[c].values if c in d else np.nan
    return X


def bt_apt(start='2024-01-01'):
    ap.prep = prep_bank
    df = add_rates(ap.load_train())
    print('apt 학습 기간', df.date.min().date(), '~', df.date.max().date(), len(df), flush=True)
    M0 = dict(ap.MEMBERS); out = {}
    for v in VARS:
        ap.MEMBERS.update({k: (M0[k][0], swap(M0[k][1], v), M0[k][2]) for k in ap.ENSEMBLE}); ap._FIT.clear()
        res = []
        for T in pd.date_range(start, df.date.max(), freq='MS'):
            tr, te = df[df.date < T], df[(df.date >= T) & (df.date < T + pd.DateOffset(months=1))]
            if len(te): res += list(te.y.values - np.mean([ap.fit_predict(m, tr, te, T) for m in ap.ENSEMBLE], axis=0))
        out[v] = stats(res); print('apt', v, out[v], flush=True)
    ap.MEMBERS.update(M0); ap.prep = _prep0
    return out


# ---------------- 오피스텔 (RF+부스팅, 2024-07~) ----------------
def bt_ot(start='2024-07-01'):
    import officetel_model as om
    ap.prep = prep_bank
    df = add_rates(om.load_train()); R0 = list(om.OT_RATE); out = {}
    for v in VARS:
        om.OT_RATE = VARS[v]   # 2026-11-26: 운영 fit_models 가 ap.with_rate(S3/S4, OT_RATE) 를 씀
        res = []
        for T in pd.date_range(start, df.date.max(), freq='MS'):
            tr, te = df[df.date < T], df[(df.date >= T) & (df.date < T + pd.DateOffset(months=1))]
            if len(te) and len(tr) >= 60: res += list(te.y.values - om.fit_predict(tr, te, T))
        out[v] = stats(res); print('ot', v, out[v], flush=True)
    om.OT_RATE = R0; ap.prep = _prep0
    return out


# ---------------- 유찰 확률 (아파트·오피스텔, 2024-07~) ----------------
def bt_fail(start='2024-07-01'):
    import fail_model as fm
    from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss
    out = {}
    for kind in ('apt', 'ot'):
        R = fm.load_rounds(kind); R = R[R.ridx <= 4].copy()
        R = add_rates(R, 'rdate'); R['m'] = R.rdate.dt.to_period('M').dt.to_timestamp()
        F0 = list(fm.FEATS[kind])
        for v in VARS:
            fm.FEATS[kind] = swap(F0, v)
            o = []
            for T in pd.date_range(start, R.rdate.max(), freq='MS'):
                tr, te = R[R.rdate < T], R[R.m == T]
                if len(te) and len(tr) >= 300:
                    o.append(te[['fail']].assign(p=fm._raw(fm._fit(tr, kind, T), te, kind)))
            o = pd.concat(o)
            out[f'{kind} {v}'] = dict(n=len(o), auc=round(roc_auc_score(o.fail, o.p), 4), brier=round(brier_score_loss(o.fail, o.p), 4),
                                      logloss=round(log_loss(o.fail, np.clip(o.p, 1e-4, 1 - 1e-4)), 4))
            print('fail', kind, v, out[f'{kind} {v}'], flush=True)
        fm.FEATS[kind] = F0
    return out


# ---------------- 상가·건물 (other_model, 2026-03~ 운영 백테스트와 같은 구간) ----------------
def bt_other():
    import other_model as om
    S, F = om.build()
    S = add_rates(S, kind='sme'); F = add_rates(F, kind='sme')
    print('other 낙찰', len(S), S.date.min(), '~', S.date.max(), '/ 회차', len(F), flush=True)
    F0 = [c for c in om.FEATS if c not in RATE_COLS]; FS = list(om.FEATS); out = {}
    for v in VARS:
        om.FEATS[:] = F0 + VARS[v]
        B, FB, rep = om.backtest(S, F, verbose=False)
        out[v] = {k: rep[k] for k in ('전체', '상가', '건물', '유찰') if k in rep}
        print('other', v, json.dumps(out[v], ensure_ascii=False), flush=True)
    om.FEATS[:] = FS
    return out


# 2026-11-26: 운영 금리 vs 기존(기준금리) 비교를 재학습 때마다 기록 → 경매 페이지 아래 한 줄 (cards_page.rate_note)
LOG = os.path.join(ROOT, 'predictions', 'rate_compare.json')
USED = {'apt': '은행채1년', 'ot': '은행금리', 'other': '은행채1년'}
OLD = {'apt': '기준금리', 'ot': '기준금리', 'other': '없음'}


def log_compare(w, r):
    if w not in USED or USED[w] not in r or OLD[w] not in r: return
    g = lambda x: x.get('mape') if 'mape' in x else (x.get('전체') or {}).get('mape')
    try:
        L = json.load(open(LOG, encoding='utf-8'))
    except Exception:
        L = {}
    L[w] = dict(date=time.strftime('%Y-%m-%d'), used=USED[w], used_mape=g(r[USED[w]]), old=OLD[w], old_mape=g(r[OLD[w]]),
                n=(r[USED[w]].get('n') or (r[USED[w]].get('전체') or {}).get('n')))
    json.dump(L, open(LOG, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    which = sys.argv[1:] or ['apt', 'ot', 'fail', 'other']
    res = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
    for w in which:
        t0 = time.time()
        res[w] = {**(res.get(w) or {}), **globals()['bt_' + w]()}   # 변형 일부만 돌려도 기존 결과에 합침
        res[w + '_sec'] = round(time.time() - t0)
        json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        log_compare(w, res[w])
