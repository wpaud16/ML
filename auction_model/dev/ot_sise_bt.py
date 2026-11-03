"""2단계: 오피스텔 시세 기준 백테스트 (2026-11-03)
국토부 실거래(오피스텔 매매) 원자료로 '경매 당시 실거래 시세'를 다시 만들고,
모델의 기준 시세(mkt, 현재 리치고 시세×지수)를 바꿨을 때 낙찰가 오차가 줄어드는지 확인한다.

  python3 dev/ot_sise_bt.py <국토부 파일 또는 폴더 ...>

- 국토부 파일: rt.molit.go.kr 오피스텔 매매 다운로드 (csv/xlsx, 앞쪽 안내문 줄은 자동으로 건너뜀)
- 단지 매칭: officetel/ot_addr.json (리치고 단지 지번) ↔ 국토부 시군구+번지, 실패 시 같은 동+단지명
- 당시 실거래 시세: 매각일 30일 전까지 공개됐을 거래(계약일 기준 매각일-30일 이전, 12개월 이내), 같은 단지
  전용면적 ±15% → ㎡당 가격 × 해당 물건 면적, 최근 3건 각각 단지 시세 지수로 매각월까지 보정 후 중앙값
- 비교: A 현재(리치고) / B 실거래 시세(없으면 리치고) / C 둘의 평균 — 월별 롤링 2025-02~2026-10, RF+부스팅
"""
import sys, os, re, json, glob, warnings
import numpy as np, pandas as pd
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import officetel_model as om

ADDR = os.path.join(HERE, 'officetel', 'ot_addr.json')
OUT = os.path.join(HERE, 'officetel', 'ot_trade_sise.csv')


def read_molit(paths):
    files = []
    for p in paths:
        files += sorted(glob.glob(os.path.join(p, '*'))) if os.path.isdir(p) else [p]
    frames = []
    for f in files:
        ext = f.lower().rsplit('.', 1)[-1]
        if ext in ('xlsx', 'xls'):
            raw = pd.read_excel(f, header=None, dtype=str)
        elif ext == 'csv':
            raw = None
            for enc in ('cp949', 'utf-8-sig', 'utf-8'):
                try:
                    lines = open(f, encoding=enc).read().splitlines(); break
                except Exception: continue
            else:
                print('읽기 실패', f); continue
            hdr = next(i for i, l in enumerate(lines[:60]) if '거래금액' in l)
            raw = pd.read_csv(f, header=None, dtype=str, encoding=enc, skiprows=hdr)
        else:
            continue
        hdr = next(i for i in range(min(60, len(raw))) if raw.iloc[i].astype(str).str.contains('거래금액').any())
        d = raw.iloc[hdr + 1:].copy(); d.columns = [str(c).strip() for c in raw.iloc[hdr]]
        frames.append(d); print(f'{os.path.basename(f)}: {len(d)}행')
    d = pd.concat(frames, ignore_index=True)
    col = lambda *ks: next(c for c in d.columns if all(k in c for k in ks))
    out = pd.DataFrame({
        'sgg_full': d[col('시군구')].str.strip(), 'bunji': d[col('번지')].astype(str).str.strip(),
        'name': d[col('단지명')].astype(str).str.strip(),
        'area': pd.to_numeric(d[col('전용면적')], errors='coerce'),
        'ym': d[col('계약년월')].astype(str).str.strip(), 'day': d[col('계약일')].astype(str).str.strip(),
        'price': pd.to_numeric(d[col('거래금액')].astype(str).str.replace(',', '').str.strip(), errors='coerce') * 1e4,
    })
    try: out['cancel'] = d[col('해제사유')].astype(str).str.strip()
    except StopIteration: out['cancel'] = ''
    out = out[out.price.notna() & out.area.notna()]
    out = out[~out.cancel.str.match(r'^\d')]          # 해제(취소)된 거래 제외
    out['date'] = pd.to_datetime(out.ym.str[:6] + out.day.str.zfill(2).str[:2], format='%Y%m%d', errors='coerce')
    out = out[out.date.notna()].drop_duplicates()
    print('국토부 거래', len(out), out.date.min().date(), '~', out.date.max().date())
    return out


def norm(s):
    return re.sub(r'\s+', '', str(s or '')).replace('서울특별시', '').replace('서울시', '').replace('서울', '')


def match_danji(tr, addr):
    tr['key'] = (tr.sgg_full + tr.bunji).map(norm)
    tr['ename'] = tr.sgg_full.str.split().str[-1] + '|' + tr.name.map(norm)
    by_key = {k: g for k, g in tr.groupby('key')}
    by_name = {k: g for k, g in tr.groupby('ename')}
    m, how = {}, {}
    for pid, v in addr.items():
        if not v: continue
        g = by_key.get(norm(v.get('jibun')))
        if g is not None: m[pid], how[pid] = g, '지번'; continue
        emd = ((v.get('bjd') or {}).get('emd') or '')
        g = by_name.get(emd + '|' + norm(v.get('name')))
        if g is not None: m[pid], how[pid] = g, '이름'
    print('단지 매칭', len(m), '/', len(addr), pd.Series(how).value_counts().to_dict())
    return m


def trade_sise(row, g, ch, lag_days=30, months=12, k=3, tol=0.15):
    if g is None: return np.nan, 0, np.nan
    T = pd.Timestamp(row.date); cut = T - pd.Timedelta(days=lag_days)
    w = g[(g.date < cut) & (g.date >= T - pd.DateOffset(months=months)) & ((g.area / row.area - 1).abs() <= tol)]
    if not len(w): return np.nan, 0, np.nan
    w = w.sort_values('date').tail(k)
    ms = sorted(ch); m = T.strftime('%Y-%m')

    def idx(mm):
        pr = [x for x in ms if x <= mm]
        return ch[pr[-1]] if pr else None
    vals = []
    for _, t in w.iterrows():
        a, b = idx(m), idx(t.date.strftime('%Y-%m'))
        f = a / b if a and b else 1.0
        vals.append(t.price / t.area * row.area * f)
    return float(np.median(vals)), len(w), float((T - w.date.max()).days / 30.4)


def rolling(df, label, start='2025-02-01'):
    df = df.sort_values('date').reset_index(drop=True)
    df['y'] = np.log(df.sell / df.mkt)
    df['r_sell_mkt'] = df.sell / df.mkt
    df['heat'] = [df.r_sell_mkt[(df.date < t) & (df.date >= t - pd.Timedelta(days=120))].median() for t in df.date]
    df['heat'] = df.heat.fillna(df.r_sell_mkt.expanding().median().shift()).fillna(1.0)
    res = pd.Series(np.nan, index=df.index)
    for T in pd.date_range(start, df.date.max(), freq='MS'):
        te = df[(df.date >= T) & (df.date < T + pd.DateOffset(months=1))]; tr = df[df.date < T]
        if len(te) == 0 or len(tr) < 60: continue
        res[te.index] = df.mkt[te.index] * np.exp(om.fit_predict(tr, te, T)) / df.sell[te.index] - 1
    df['err_' + label] = res
    return df[['auction_id', 'err_' + label]]


def main(paths):
    addr = json.load(open(ADDR))
    trades = read_molit(paths)
    gm = match_danji(trades, addr)
    base = pd.read_csv(om.TRAIN)
    rows = []
    for i, r in base.iterrows():
        s, n, age = trade_sise(r, gm.get(r.danji), (addr.get(r.danji) or {}).get('chart') or {})
        rows.append(dict(auction_id=r.auction_id, trade_sise=s, trade_n=n, trade_age_m=age))
    ts = pd.DataFrame(rows); ts.to_csv(OUT, index=False)
    b = base.merge(ts, on='auction_id')
    has = b.trade_sise.notna()
    print(f'\n당시 실거래 시세 있음 {has.sum()} / {len(b)}건')
    print('실거래 시세 ÷ 현재 mkt 중앙값', round(float((b.trade_sise / b.mkt)[has].median()), 3),
          '· 낙찰가 ÷ 실거래 시세 중앙값', round(float((b.sell / b.trade_sise)[has].median()), 3),
          '· 낙찰가 ÷ mkt 중앙값', round(float((b.sell / b.mkt)[has].median()), 3))

    variants = {
        'A_현재': b.mkt,
        'B_실거래': b.trade_sise.fillna(b.mkt),
        'C_평균': np.where(has, (b.trade_sise + b.mkt) / 2, b.mkt),
    }
    res = b[['auction_id', 'date', 'station_m', 'fails']].copy(); res['has'] = has.values
    for k, v in variants.items():
        d = om.enrich(b.assign(mkt=v))
        res = res.merge(rolling(d, k), on='auction_id')
        print('done', k)
    res['date'] = pd.to_datetime(res.date)
    ev = res[res.err_A_현재.notna()]
    sets = {'전체': ev, '실거래 있는 건': ev[ev.has], '역 10분 이내': ev[ev.station_m <= 615],
            '역 10분 · 실거래 있음': ev[(ev.station_m <= 615) & ev.has], '1회 유찰': ev[ev.fails == 1]}
    print('\n평균 절대오차 (%) / ±5% 안 (%) / 치우침 (%)')
    for name, s in sets.items():
        line = [f'{name} {len(s)}건']
        for k in variants:
            e = s['err_' + k]
            line.append(f'{k} {e.abs().mean()*100:.2f} / {(e.abs()<=0.05).mean()*100:.0f} / {e.mean()*100:+.1f}')
        print(' | '.join(line))
    mid = ev.date.sort_values().iloc[len(ev) // 2]
    for name, s in (('앞 절반', ev[ev.date < mid]), ('뒤 절반', ev[ev.date >= mid])):
        print(name, len(s), ' '.join(f"{k} {s['err_'+k].abs().mean()*100:.2f}" for k in variants))
    res.to_csv(os.path.join(HERE, 'officetel', 'ot_sise_bt_result.csv'), index=False)


if __name__ == '__main__':
    main(sys.argv[1:])
