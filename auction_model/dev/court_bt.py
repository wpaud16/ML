"""법원 인자 백테스트 — 낙찰가 (2026-11-04, 사용자: 메인 목적 = 입찰가 정확도)

과거 사건 법원 자료(court_backfill/data)는 종국 후 30일이 지나면 '기본사항'만 남는다:
접수일·개시결정일·임의/강제·청구금액·중복사건 (점유·명세서·문건은 끝난 사건 대부분 없음).
그래서 입찰 전에 알 수 있는 다음 인자만 시험한다.
  l_claim  = log(청구금액 ÷ 시세)        빚이 시세에 비해 크면 채무자 협조↓·명도 부담?
  forced   = 강제경매 1 / 임의경매 0
  case_age = 접수일 → 매각일 개월 수     오래 끈 사건
  dup      = 중복·병합 사건 있음
비교: 월별 롤링 2025-02~, 같은 모델(아파트 앙상블 2종 평균 / 오피스텔 RF+부스팅)에 인자를 넣고 뺀 평균 절대오차.
  python3 dev/court_bt.py
"""
import sys, os, json, glob, warnings
import numpy as np, pandas as pd
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import auction_predictor as ap
import officetel_model as om

CB = os.path.join(HERE, 'court_backfill')
FEATS = ['l_claim', 'forced', 'case_age', 'dup']


def court_table():
    t = pd.DataFrame(json.load(open(os.path.join(CB, 'targets_all.json')))['items'])
    rows = []
    for r in t.itertuples():
        f = os.path.join(CB, 'data', f'{r.case}_{int(r.item_no)}.json')
        if not os.path.exists(f): continue
        ci = (json.load(open(f)).get('case_info') or {})
        kind = ci.get('case_kind') or ''
        rows.append(dict(auction_id=r.auction_id, claim=ci.get('claim_amount_manwon'), received=ci.get('received_date'),
                         forced=1.0 if '강제' in kind else 0.0 if '임의' in kind else np.nan,
                         dup=float(bool(ci.get('duplicate_cases')))))
    return pd.DataFrame(rows).drop_duplicates('auction_id')


def add_feats(df, ct):
    d = df.merge(ct, on='auction_id', how='left')
    d['l_claim'] = np.log((d.claim * 1e4 / d.mkt).where(d.claim > 0)).clip(-6, 3)
    d['case_age'] = ((pd.to_datetime(d.date) - pd.to_datetime(d.received, errors='coerce')).dt.days / 30.4).clip(0, 120)
    return d


_prep0 = ap.prep


def prep_with(d):
    X = _prep0(d)
    for c in FEATS: X[c] = d[c].values if c in d else np.nan
    return X


def roll(df, predict, start='2025-02-01'):
    res = pd.Series(np.nan, index=df.index)
    for T in pd.date_range(start, df.date.max(), freq='MS'):
        te = df[(df.date >= T) & (df.date < T + pd.DateOffset(months=1))]; tr = df[df.date < T]
        if len(te) == 0 or len(tr) < 60: continue
        res[te.index] = np.exp(predict(tr, te, T)) / np.exp(te.y.values) - 1
    return res


def apt(ct):
    raw = pd.read_csv(os.path.join(HERE, 'auction_train.csv'))
    mp = pd.read_csv(os.path.join(CB, 'apt_case_map.csv')).set_index('index')
    raw['auction_id'] = mp.auction_id.reindex(raw.index).values
    df = add_feats(raw, ct)
    df['date'] = pd.to_datetime(df.date); df = df.sort_values('date').reset_index(drop=True)
    df['seoul'] = (df.sd == '서울').astype(int); df['y'] = np.log(df.r_sell_mkt)
    base_m = {k: v for k, v in ap.MEMBERS.items()}
    out = pd.DataFrame(index=df.index); out['date'] = df.date; out['fails'] = df.fails; out['bidders'] = df.bidders
    out['has_claim'] = df.l_claim.notna()

    def variant(extra, members):
        for name in members:
            kind, cols, decay = base_m[name]
            ap.MEMBERS[name] = (kind, list(cols) + extra, decay)
        f = lambda tr, te, T: np.mean([ap.fit_predict(n, tr, te, T) for n in members], axis=0)
        r = roll(df, f)
        ap.MEMBERS.update(base_m)
        return r
    ap.prep = prep_with
    for lab, ex in [('기본', []), ('+청구금액', ['l_claim']), ('+임의/강제', ['forced']), ('+사건경과', ['case_age']),
                    ('+중복사건', ['dup']), ('+전부', FEATS)]:
        out['ens_' + lab] = variant(ex, ap.ENSEMBLE)
        print('apt ens', lab, flush=True)
    hb = df.bidders.notna()
    for lab, ex in [('기본', []), ('+전부', FEATS), ('+청구금액', ['l_claim'])]:
        out['bid_' + lab] = variant(ex, ['부스팅_인원', '군집_인원']).where(hb)
        print('apt bid', lab, flush=True)
    ap.prep = _prep0
    return out


def ot(ct):
    df = om.load_train()
    df = add_feats(df, ct)
    out = pd.DataFrame(index=df.index); out['date'] = df.date; out['fails'] = df.fails
    out['has_claim'] = df.l_claim.notna(); out['station_m'] = df.station_m
    ex0 = list(om.EXTRA)
    ap.prep = prep_with
    for lab, ex in [('기본', []), ('+청구금액', ['l_claim']), ('+임의/강제', ['forced']), ('+사건경과', ['case_age']),
                    ('+중복사건', ['dup']), ('+전부', FEATS)]:
        om.EXTRA[:] = ex0 + ex
        out['ens_' + lab] = roll(df, lambda tr, te, T: om.fit_predict(tr, te, T))
        print('ot', lab, flush=True)
    om.EXTRA[:] = ex0; ap.prep = _prep0
    return out


def report(name, out, cols):
    ev = out[out[cols[0]].notna()]
    mid = ev.date.sort_values().iloc[len(ev) // 2]
    sets = [('전체', ev), ('청구금액 있음', ev[ev.has_claim]), ('1회 유찰', ev[ev.fails == 1]),
            ('앞 절반', ev[ev.date < mid]), ('뒤 절반', ev[ev.date >= mid])]
    print(f'\n[{name}] 평균 절대오차 % (±5% 안 %)')
    print('구분'.ljust(14) + ''.join(c.split('_', 1)[1].rjust(13) for c in cols))
    for lab, s in sets:
        print(f'{lab} {len(s)}건'.ljust(14) + ''.join(
            f"{s[c].abs().mean() * 100:7.2f}({(s[c].abs() <= .05).mean() * 100:3.0f})".rjust(13) for c in cols))


if __name__ == '__main__':
    ct = court_table(); print('court rows', len(ct))
    a = apt(ct); o = ot(ct)
    report('아파트 앙상블 (인원 모름)', a, [c for c in a if c.startswith('ens_')])
    report('아파트 인원별 모델 (인원 알 때)', a[a.bidders.notna()], [c for c in a if c.startswith('bid_')])
    report('오피스텔 RF+부스팅', o, [c for c in o if c.startswith('ens_')])
    a.to_csv(os.path.join(CB, 'bt_apt.csv')); o.to_csv(os.path.join(CB, 'bt_ot.csv'))
