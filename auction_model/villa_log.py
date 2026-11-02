#!/usr/bin/env python3
"""서울 빌라(다세대·연립) 경매를 매일 기록 → 몇 달 뒤 빌라 낙찰가 모델 백테스트용 데이터 (2026-11-02 시작).

villa/villa_log.json : { "<경매ID>": {case, address, sgg, emd, type, area, land_area,
                                     appr_manwon, rounds:[{date, low_manwon, fails}], first_seen, last_seen,
                                     status, sell_manwon, bidders, second_manwon, sell_date, checked} }
- 매 실행: 서울 25개 구의 다세대·연립 진행 목록을 읽어 회차(최저가·기일)를 기록
- 매각기일이 지났는데 결과가 없는 물건은 상세 페이지에서 결과(매각/유찰/취하)를 확인 (기일 후 60일까지)
역세권 판정은 백테스트 때 주소로 따로 계산한다.
"""
import json, os, sys, urllib.parse
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from batch_predict import get, next_data, auction_detail  # noqa: E402

KST = timezone(timedelta(hours=9))
GU = ['강남구', '강동구', '강북구', '강서구', '관악구', '광진구', '구로구', '금천구', '노원구', '도봉구', '동대문구', '동작구',
      '마포구', '서대문구', '서초구', '성동구', '성북구', '송파구', '양천구', '영등포구', '용산구', '은평구', '종로구', '중구', '중랑구']
TYPES = ['다세대', '연립']
PATH = os.path.join(HERE, 'villa', 'villa_log.json')
q = urllib.parse.quote


def list_items(args):
    gu, ty = args
    out, page = [], 1
    while page <= 30:
        raw = get(f'https://m.richgo.ai/auction/hub/region/{q("서울")}/{q(gu)}/{q(ty)}' + (f'?page={page}' if page > 1 else ''))
        if not raw:
            return out, f'{gu} {ty} p{page} 실패'
        d = next_data(raw)['data']
        out += [dict(it, _type=ty) for it in d['items']]
        if page * d['size'] >= d['totalCount'] or not d['items']:
            break
        page += 1
    return out, None


def main():
    today = str(datetime.now(KST).date())
    log = json.load(open(PATH)) if os.path.exists(PATH) else {}
    errors, seen = [], 0
    with ThreadPoolExecutor(6) as ex:
        for items, err in ex.map(list_items, [(g, t) for g in GU for t in TYPES]):
            if err: errors.append(err)
            for it in items:
                if not it.get('appraisedPrice') or not it.get('lowestSellingPrice'):
                    continue
                seen += 1
                e = log.setdefault(it['id'], dict(case=f"{it['caseName']}[{it.get('itemNumber') or 1}]", address=it.get('address'),
                                                  sgg=it.get('sgg'), emd=it.get('emd'), type=it['_type'],
                                                  area=it.get('buildingTotalArea'), land_area=it.get('groundTotalArea'),
                                                  appr_manwon=int(it['appraisedPrice'] / 1e4), rounds=[], first_seen=today,
                                                  status='진행중'))
                rnd = dict(date=(it.get('biddingDate') or '')[:10], low_manwon=int(it['lowestSellingPrice'] / 1e4),
                           fails=it.get('numberOfFailures'))
                if not e['rounds'] or e['rounds'][-1]['date'] != rnd['date'] or e['rounds'][-1]['low_manwon'] != rnd['low_manwon']:
                    e['rounds'].append(rnd)
                e['last_seen'] = today
                if e.get('status') not in ('진행중',):
                    e['status'] = '진행중'
    # 기일 지난 물건 결과 확인
    lo = str((datetime.fromisoformat(today) - timedelta(days=60)).date())
    todo = [aid for aid, e in log.items() if e['rounds'] and lo <= e['rounds'][-1]['date'] < today and e.get('status') in ('진행중', '결과대기')]

    def check(aid):
        try:
            return aid, auction_detail(aid)
        except Exception:
            return aid, None
    with ThreadPoolExecutor(6) as ex:
        for aid, p in ex.map(check, todo):
            e = log[aid]; e['checked'] = today
            if not p:
                e['status'] = '결과대기'; continue
            if p.get('sellingPrice'):
                e.update(status='매각', sell_manwon=int(p['sellingPrice'] / 1e4), bidders=p.get('bidders'),
                         second_manwon=int(p['secondHighBiddingPrice'] / 1e4) if p.get('secondHighBiddingPrice') else None,
                         sell_date=p.get('sellingDate'), construct_year=p.get('constructYear'))
            elif (p.get('biddingDate') or '').startswith('9999') or (p.get('itemStatus') or '') == '종료':
                e['status'] = '종료(매각없음)'
            elif (p.get('biddingDate') or '')[:10] > e['rounds'][-1]['date']:
                e['status'] = '진행중'   # 유찰·변경 → 다음 회차는 목록에서 다시 기록됨
            else:
                e['status'] = '결과대기'
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    json.dump(log, open(PATH, 'w'), ensure_ascii=False, indent=0)
    sold = sum(e.get('status') == '매각' for e in log.values())
    print(json.dumps(dict(date=today, listed_today=seen, total=len(log), sold=sold, checked=len(todo), errors=errors), ensure_ascii=False))


if __name__ == '__main__':
    main()
