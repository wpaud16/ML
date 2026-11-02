#!/usr/bin/env python3
"""월 1회 재학습 (2026-11-02~): 지난 학습 이후 새로 매각된 사례를 학습 데이터에 더하고 모델 보정을 다시 계산한다.

  python3 retrain.py            # 수집 → 학습 데이터 추가 → 보정 재계산 → predictions/retrain_log.json 기록
  python3 retrain.py --dry-run  # 수집만 하고 결과 건수만 출력 (파일 변경 없음)

- 아파트: auction_train.csv 의 단지 + danji_map.json 에 연결된 단지 페이지에서, 학습 마지막 날짜 이후 매각된 서울·경기 사례.
  권리 판정(batch_predict.risk_check)이 show 이고 재매각이 아닌 '일반 물건'만 (기존 학습 데이터와 같은 기준).
- 오피스텔: officetel/ot_train.csv 의 오피스텔 + 연결된 오피스텔 페이지에서 새로 매각된 서울 사례 (show + check, 기존과 같은 기준).
- 시세는 매각 달의 리치고 가격지수로 되돌려 맞춘다 (mkt = 현재 시세 × 지수(매각월) / 지수(최신)).
- 응찰자 수(bidders)는 경매 상세 페이지에서.
- 재계산: auction_predictor.calibrate() · calibrate_bidders(), officetel_model.calibrate()
"""
import json, os, sys, argparse
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import auction_predictor as ap
import batch_predict as bp

APT_TRAIN = os.path.join(HERE, 'auction_train.csv')
OT_TRAIN = os.path.join(HERE, 'officetel', 'ot_train.csv')
LOG = os.path.join(HERE, 'predictions', 'retrain_log.json')
KST = timezone(timedelta(hours=9))


def page(kind, pid):
    raw = bp.get(f'https://m.richgo.ai/realty/{kind}/{pid}')
    if not raw: return None, ''
    try: return bp.next_data(raw).get('data') or None, raw
    except Exception: return None, raw


def flat_auctions(d):
    au = []

    def flat(x):
        if not x: return
        y = dict(x); sub = y.pop('subList', None); au.append(y)
        for s in sub or []: flat(s)
    flat((d or {}).get('auctionInfo'))
    return au


def rows_from_page(kind, pid, since):
    """페이지의 매각 사례 중 since 이후 것 → 학습 행 목록."""
    d, raw = page(kind, pid)
    if not d: return []
    sold = [a for a in flat_auctions(d) if a.get('sellingPrice') and (a.get('sellingDate') or '')[:10] > since]
    if not sold: return []
    pis = d.get('pyeongInfos') or {}
    tot_hh = sum((v.get('households') or 0) for v in pis.values()) or np.nan
    try:
        ch = {x['date'][:7]: x.get('averagePrice') for x in d['analyze']['invest']['invest']['chart']['data'] if x.get('averagePrice')}
    except Exception:
        return []
    if not ch: return []
    ms = sorted(ch); last = ms[-1]

    def idx(m):
        pr = [x for x in ms if x <= m]
        return ch[pr[-1]] if pr else np.nan
    bj = d.get('bjdInfo') or {}
    cy = None
    try: cy = int((((d.get('basic') or {}).get('construction') or {}).get('date') or '')[:4])
    except Exception: pass
    st = None
    if kind == 'officetel':
        import re
        dists = [int(m.group(1)) for m in re.finditer(r'"distance":(\d+),"targetName":"[^"]*","indexName":"지하철"', raw)]
        st = min(dists) if dists else None
    out = []
    for a in sold:
        sd = (a.get('bjdInfo') or {}).get('sd') or bj.get('sd')
        if kind == 'danji' and sd not in ('서울', '경기'): continue
        if kind == 'officetel' and sd != '서울': continue
        area = a.get('buildingTotalArea'); best = None
        for p, v in pis.items():
            try: lo, hi = float(v['minPrivateArea']), float(v['maxPrivateArea'])
            except (TypeError, ValueError): continue
            dp = v.get('danjiPriceInfo') or {}; meme = (dp.get('meme') or {}).get('price')
            if not meme or area is None: continue
            dist = 0 if lo - 0.5 <= area <= hi + 0.5 else abs(area - (lo + hi) / 2)
            if best is None or dist < best[0]: best = (dist, p, v, meme, (dp.get('jeonse') or {}).get('price'))
        if best is None or best[0] > 3: continue
        sdt = a['sellingDate'][:10]; m = sdt[:7]; T = pd.Timestamp(sdt)
        if not idx(m) or np.isnan(idx(m)): continue
        mkt = best[3] * 1e4 * idx(m) / ch[last]
        kw = ', '.join(x for x in [(a.get('keyword') or '').strip(), (a.get('historyKeyword') or '').strip()] if x)
        reg = a.get('registrationDate')
        age = a.get('constructYear') if a.get('constructYear') is not None else ((T.year - cy) if cy else np.nan)
        out.append(dict(danji=pid, sd=sd, sgg=bj.get('sgg'), emd=bj.get('emd'), date=sdt, area=area,
                        fails=a.get('numberOfFailures') or 0, appr=a['appraisedPrice'], low=a['lowestSellingPrice'],
                        sell=a['sellingPrice'], mkt=mkt, hh=a.get('totalHouseholds') or tot_hh, age=age,
                        py_share=(best[2].get('households') or np.nan) / tot_hh,
                        jeonse_ratio=(best[4] / best[3]) if best[4] else np.nan,
                        mom3=idx(m) / idx(ap.mshift(m, 3)) - 1, mom6=idx(m) / idx(ap.mshift(m, 6)) - 1,
                        mom12=idx(m) / idx(ap.mshift(m, 12)) - 1,
                        dd24=idx(m) / max(ch[x] for x in ms if ap.mshift(m, 24) <= x <= m) - 1,
                        lag_m=((T - pd.Timestamp(reg[:10])).days / 30.4) if reg else np.nan,
                        keyword=kw, station_m=st, case=a.get('caseName'), auction_id=a.get('auctionId')))
    return out


def add_detail(r):
    det = bp.auction_detail(r['auction_id']) or {}
    r['bidders'] = det.get('bidders')
    risk = bp.risk_check(r['keyword'], r['appr'] / r['mkt'], det.get('rights'))
    r['risk_decision'] = risk['decision']; r['resale'] = bool(risk.get('resale'))
    return r


def _safe(fn, *a, default=None):
    """한 단지/사건에서 오류가 나도 전체 재학습이 멈추지 않게 건너뛴다."""
    try: return fn(*a)
    except Exception as e:
        print('skip', fn.__name__, a[:2] if fn.__name__ != 'add_detail' else '', type(e).__name__, flush=True); return default


def collect(kind, ids, since, workers=12):
    rows = []
    with ThreadPoolExecutor(workers) as ex:
        for rs in ex.map(lambda i: _safe(rows_from_page, kind, i, since, default=[]), sorted(ids)):
            rows += rs
    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(lambda r: _safe(add_detail, r, default=dict(r, risk_decision='error', resale=True)), rows))
    return pd.DataFrame(rows)


def finish_apt(new, old):
    if new.empty: return new
    n = new[(new.risk_decision == 'show') & (~new.resale)].copy()
    n['seoul'] = (n.sd == '서울').astype(int)
    n['r_sell_mkt'] = n.sell / n.mkt; n['r_appr_mkt'] = n.appr / n.mkt; n['r_low_mkt'] = n.low / n.mkt
    n = n[n.r_sell_mkt.between(0.5, 1.6) & n.r_appr_mkt.between(0.6, 2.0) & (n.area >= 25)]
    T = pd.to_datetime(n.date)
    n['rate'] = T.map(ap.rate_at); n['rate_chg6'] = [ap.rate_at(t) - ap.rate_at(t - pd.DateOffset(months=6)) for t in T]
    n['tohu_r'] = [int(bool(ap.tohu_at(t, s, g, e)) or ('토지거래허가' in (k or ''))) for t, s, g, e, k in zip(T, n.sd, n.sgg, n.emd, n.keyword)]
    n['regulated'] = [ap.regulated_at(t, s, g) for t, s, g in zip(T, n.sd, n.sgg)]
    n['loan_ratio'] = [ap.loan_ratio(t, s, g, m) for t, s, g, m in zip(T, n.sd, n.sgg, n.mkt)]
    comb = pd.concat([old.assign(date=pd.to_datetime(old.date)), n.assign(date=T)], ignore_index=True)
    n['heat'] = [ap.recent_heat(comb, s, t) for s, t in zip(n.seoul, T)]
    return n[[c for c in old.columns if c in n.columns]]


def finish_ot(new, old):
    if new.empty: return new
    n = new[new.risk_decision.isin(['show', 'check'])].copy()
    n = n[(n.sell / n.mkt).between(0.4, 2.0) & (n.appr / n.mkt).between(0.5, 2.0)]
    n['status'] = '매각'
    return n[[c for c in old.columns if c in n.columns]]


def main(dry=False):
    today = datetime.now(KST).date().isoformat()
    apt_old, ot_old = pd.read_csv(APT_TRAIN), pd.read_csv(OT_TRAIN)
    a_since, o_since = str(apt_old.date.max())[:10], str(ot_old.date.max())[:10]
    dmap = json.load(open(bp.MAP_PATH)) if os.path.exists(bp.MAP_PATH) else {}
    mapped = set(dmap.values())
    apt_ids = set(apt_old.danji) | (mapped - set(ot_old.danji))
    ot_ids = set(ot_old.danji) | (mapped - set(apt_old.danji))
    t0 = datetime.now()
    apt_new = collect('danji', apt_ids, a_since)
    ot_new = collect('officetel', ot_ids, o_since)
    apt_add = finish_apt(apt_new, apt_old)
    ot_add = finish_ot(ot_new, ot_old)
    # 이미 있는 사례(같은 단지·날짜·낙찰가) 제외
    key = lambda d: set(zip(d.danji, d.date.astype(str).str[:10], d.sell.astype('int64')))
    if len(apt_add): apt_add = apt_add[[k not in key(apt_old) for k in zip(apt_add.danji, apt_add.date.astype(str).str[:10], apt_add.sell.astype('int64'))]]
    if len(ot_add): ot_add = ot_add[[k not in key(ot_old) for k in zip(ot_add.danji, ot_add.date.astype(str).str[:10], ot_add.sell.astype('int64'))]]
    info = dict(date=today, apt_since=a_since, ot_since=o_since, apt_pages=len(apt_ids), ot_pages=len(ot_ids),
                apt_found=int(len(apt_new)), apt_added=int(len(apt_add)), ot_found=int(len(ot_new)), ot_added=int(len(ot_add)),
                collect_min=round((datetime.now() - t0).total_seconds() / 60, 1))
    print(json.dumps(info, ensure_ascii=False))
    if dry: return info
    cfg_a = json.load(open(os.path.join(HERE, 'auction_config.json')))
    cfg_o = json.load(open(os.path.join(HERE, 'officetel', 'ot_config.json')))
    info.update(apt_mape_before=cfg_a.get('mape_recent'), bid_mape_before=(cfg_a.get('bidder_resid') or {}).get('mape'),
                ot_mape_before=cfg_o.get('mape_recent'))
    if len(apt_add):
        out = pd.concat([apt_old, apt_add.assign(date=apt_add.date.astype(str).str[:10])], ignore_index=True).sort_values('date')
        out.to_csv(APT_TRAIN, index=False)
        ap.calibrate(); ap.calibrate_bidders()
    if len(ot_add):
        import officetel_model as om
        out = pd.concat([ot_old, ot_add], ignore_index=True).sort_values('date')
        out.to_csv(OT_TRAIN, index=False)
        om.calibrate()
    cfg_a = json.load(open(os.path.join(HERE, 'auction_config.json')))
    cfg_o = json.load(open(os.path.join(HERE, 'officetel', 'ot_config.json')))
    info.update(apt_n_train=int(len(pd.read_csv(APT_TRAIN))), ot_n_train=int(len(pd.read_csv(OT_TRAIN))),
                apt_mape_after=cfg_a.get('mape_recent'), bid_mape_after=(cfg_a.get('bidder_resid') or {}).get('mape'),
                ot_mape_after=cfg_o.get('mape_recent'))
    log = json.load(open(LOG)) if os.path.exists(LOG) else []
    log.append(info)
    json.dump(log, open(LOG, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(info, ensure_ascii=False))
    return info


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--dry-run', action='store_true')
    main(p.parse_args().dry_run)
