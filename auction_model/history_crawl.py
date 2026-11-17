#!/usr/bin/env python3
"""리치고 과거 경매 수집 (2026-11-16 사용자 결정: 빌라·상가·건물 낙찰가 모델 학습용, 매일 밤 나눠서).

리치고 사이트맵(auctionMobile*.xml, 전국 약 14만 건)의 경매 상세 페이지를 하루 예산(기본 120분)만큼 천천히 읽어
서울·경기·인천의 빌라(다세대·연립)·상가(구분상가)·건물(꼬마빌딩·상가주택·다가구) 행만 저장한다.
다른 유형·지역은 '봤음' 표시만 남겨 다시 읽지 않는다. 진행 중 물건은 기일이 지나면 다시 읽는다.

저장 위치(용량이 커서 저장소 밖, 노트북만): <저장소 상위>/hist/
  sitemap_ids.json  {id: lastmod}            (7일마다 새로 받음)
  seen.json         {id: 'x' | 'pending:<기일>' | 'ok'}
  rows.jsonl        한 줄 = 한 경매 (마지막 상태로 덮어쓰기는 train 단계에서 id 기준 최신만 사용)
python history_crawl.py [--budget-min 120] [--workers 4]
"""
import argparse, json, os, re, subprocess, sys, time
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from batch_predict import next_data  # noqa: E402
from other_items import category  # noqa: E402

KST = timezone(timedelta(hours=9))
DIR = os.environ.get('HIST_DIR') or os.path.join(os.path.dirname(os.path.dirname(HERE)), 'hist')
SITEMAPS = ['auctionMobile', 'auctionMobile_2', 'auctionMobile_3']
REGIONS = ('서울', '경기', '인천')


def curl(url, timeout=60):
    try:
        return subprocess.run(['curl', '-sL', '-m', str(timeout), '-A', 'Mozilla/5.0', url], capture_output=True).stdout.decode('utf-8', 'replace')
    except Exception:
        return ''


def load(name, default):
    p = os.path.join(DIR, name)
    try:
        return json.load(open(p, encoding='utf-8'))
    except Exception:
        return default


def save(name, obj):
    p = os.path.join(DIR, name)
    json.dump(obj, open(p + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    os.replace(p + '.tmp', p)


def sitemap_ids(now):
    meta = load('sitemap_meta.json', {})
    ids = load('sitemap_ids.json', {})
    if ids and meta.get('at', '') >= str((now - timedelta(days=7)).date()):
        return ids
    new = {}
    for n in SITEMAPS:
        t = curl(f'https://m.richgo.ai/{n}.xml', 180)
        for m in re.finditer(r'<loc>https://m\.richgo\.ai/auctionMobile/([0-9A-Za-z]+)</loc>(?:<lastmod>([^<]*)</lastmod>)?', t):
            new[m.group(1)] = (m.group(2) or '')[:10]
        time.sleep(3)
    if len(new) < 10000:   # 받기 실패 → 이전 목록 사용
        print('sitemap 받기 실패', len(new)); return ids
    save('sitemap_ids.json', new); save('sitemap_meta.json', dict(at=str(now.date()), n=len(new)))
    return new


def row_from(aid, pg):
    td = pg.get('typeDetails') or []
    r = pg.get('rights') or {}
    hist = [dict(d=(h.get('appointedDayAt') or '')[:10], t=h.get('appointedDayType'),
                 low=int(h['lowestSellingPrice'] / 1e4) if h.get('lowestSellingPrice') else None, res=h.get('results'))
            for h in pg.get('historyList') or []]
    return dict(id=aid, case=f"{pg.get('caseName')}[{pg.get('itemNumber') or 1}]", court=pg.get('caseSite'), address=pg.get('address'),
                sd=pg.get('sd'), sgg=pg.get('sgg'), emd=pg.get('emd'), td=td, item_type=pg.get('itemType'),
                cat=category('', td, pg.get('address')),
                appr=int((pg.get('appraisedPrice') or 0) / 1e4), low=int((pg.get('lowestSellingPrice') or 0) / 1e4),
                fails=pg.get('numberOfFailures'), bd=(pg.get('biddingDate') or '')[:10], status=pg.get('itemStatus'),
                sell=int(pg['sellingPrice'] / 1e4) if pg.get('sellingPrice') else None, sell_date=(pg.get('sellingDate') or '')[:10] or None,
                bidders=pg.get('bidders'), second=int(pg['secondHighBiddingPrice'] / 1e4) if pg.get('secondHighBiddingPrice') else None,
                area=pg.get('buildingTotalArea'), land=pg.get('groundTotalArea'), year=pg.get('constructYear'), reg=(pg.get('registrationDate') or '')[:10],
                rights=dict(known=bool(r.get('hasRegistryData')), tenant=(r.get('assumedTenantCount') or 0) + (r.get('uncertainTenantCount') or 0),
                            right=(r.get('assumedRightCount') or 0) + int(bool(r.get('hasAssumption'))),
                            base=(r.get('baseRight') or {}).get('type'), base_date=((r.get('baseRight') or {}).get('date') or '')[:10]),
                appraisal=(pg.get('appraisalSummary') or '')[:1500], hist=hist, at=str(datetime.now(KST).date()))


def fetch(aid):
    raw = curl('https://m.richgo.ai/auctionMobile/' + aid, 40)
    if '__NEXT_DATA__' not in raw:
        return aid, None
    try:
        return aid, next_data(raw).get('auctionPageData') or {}
    except Exception:
        return aid, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--budget-min', type=float, default=float(os.environ.get('HIST_BUDGET_MIN', '120')))
    ap.add_argument('--workers', type=int, default=4)
    a = ap.parse_args()
    os.makedirs(DIR, exist_ok=True)
    now = datetime.now(KST); today = str(now.date())
    t_end = time.time() + a.budget_min * 60
    ids = sitemap_ids(now)
    seen = load('seen.json', {})

    def due(aid):
        s = seen.get(aid)
        return s is None or (s.startswith('pending:') and s[8:] < today)
    # 최근 갱신된 것부터 (표본 400건: 2026 갱신분 56% 낙찰, 오래된 것은 대부분 종료·연기)
    todo = sorted((i for i in ids if due(i)), key=lambda i: ids[i] or '0000', reverse=True)
    print(f'사이트맵 {len(ids)}건 · 남은 {len(todo)}건 · 예산 {a.budget_min:.0f}분', flush=True)
    n = dict(read=0, kept=0, skip=0, fail=0)
    out = open(os.path.join(DIR, 'rows.jsonl'), 'a', encoding='utf-8')
    fails_in_row = 0
    try:
        with ThreadPoolExecutor(a.workers) as ex:
            for i in range(0, len(todo), a.workers * 25):
                if time.time() > t_end: break
                for aid, pg in ex.map(fetch, todo[i:i + a.workers * 25]):
                    n['read'] += 1
                    if pg is None:
                        n['fail'] += 1; fails_in_row += 1; continue
                    fails_in_row = 0
                    if not pg:
                        seen[aid] = 'x'; n['skip'] += 1; continue
                    if pg.get('sd') not in REGIONS or category('', pg.get('typeDetails'), pg.get('address')) not in ('상가', '건물'):   # 빌라 끔 (2026-11-17)
                        seen[aid] = 'x'; n['skip'] += 1; continue
                    out.write(json.dumps(row_from(aid, pg), ensure_ascii=False, separators=(',', ':')) + '\n'); n['kept'] += 1
                    bd = (pg.get('biddingDate') or '')[:10]
                    finished = pg.get('sellingPrice') or (pg.get('itemStatus') or '') in ('종료', '매각', '취하', '기각') or bd.startswith('9999') or not bd
                    seen[aid] = 'ok' if finished else f'pending:{bd}'
                if fails_in_row >= 40:   # 연속 실패 = 차단·장애 의심 → 오늘은 멈춤
                    print('연속 실패 40건 → 중단', flush=True); break
                save('seen.json', seen); out.flush()
                time.sleep(1.0)   # 묶음 사이 쉬기
    finally:
        out.close(); save('seen.json', seen)
    left = sum(1 for i in ids if due(i))
    print(json.dumps(dict(n, left=left, kept_total=sum(1 for v in seen.values() if v != 'x')), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
