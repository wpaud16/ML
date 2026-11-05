"""국토부 실거래 수집 (2026-11-05): 시세 기준 백테스트용. 공공데이터포털 API (GitHub Secret MOLIT_API_KEY).
  python molit_collect.py test   # 시군구별 1개월 → 응답 코드·동 이름이 학습 데이터와 맞는지
  python molit_collect.py full   # 2022-01 ~ 지난달, 학습 데이터의 동만 저장 → dev/molit/{apt,ot}.csv.gz"""
import os, sys, json, time, gzip, csv, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import date
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); AM = os.path.dirname(HERE); OUT = os.path.join(HERE, 'molit'); os.makedirs(OUT, exist_ok=True)
KEY = os.environ['MOLIT_API_KEY'].strip()
URL = dict(apt='https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev',
           ot='https://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade')
CODE = {('서울', '종로구'): '11110', ('서울', '중구'): '11140', ('서울', '용산구'): '11170', ('서울', '성동구'): '11200', ('서울', '광진구'): '11215',
        ('서울', '동대문구'): '11230', ('서울', '중랑구'): '11260', ('서울', '성북구'): '11290', ('서울', '강북구'): '11305', ('서울', '도봉구'): '11320',
        ('서울', '노원구'): '11350', ('서울', '은평구'): '11380', ('서울', '서대문구'): '11410', ('서울', '마포구'): '11440', ('서울', '양천구'): '11470',
        ('서울', '강서구'): '11500', ('서울', '구로구'): '11530', ('서울', '금천구'): '11545', ('서울', '영등포구'): '11560', ('서울', '동작구'): '11590',
        ('서울', '관악구'): '11620', ('서울', '서초구'): '11650', ('서울', '강남구'): '11680', ('서울', '송파구'): '11710', ('서울', '강동구'): '11740',
        ('경기', '수원시 장안구'): '41111', ('경기', '수원시 권선구'): '41113', ('경기', '수원시 팔달구'): '41115', ('경기', '수원시 영통구'): '41117',
        ('경기', '성남시 수정구'): '41131', ('경기', '성남시 중원구'): '41133', ('경기', '성남시 분당구'): '41135', ('경기', '의정부시'): '41150',
        ('경기', '안양시 만안구'): '41171', ('경기', '안양시 동안구'): '41173', ('경기', '부천시 원미구'): '41192', ('경기', '부천시 소사구'): '41194',
        ('경기', '부천시 오정구'): '41196', ('경기', '광명시'): '41210', ('경기', '평택시'): '41220', ('경기', '동두천시'): '41250',
        ('경기', '안산시 상록구'): '41271', ('경기', '안산시 단원구'): '41273', ('경기', '고양시 덕양구'): '41281', ('경기', '고양시 일산동구'): '41285',
        ('경기', '고양시 일산서구'): '41287', ('경기', '구리시'): '41310', ('경기', '남양주시'): '41360', ('경기', '오산시'): '41370',
        ('경기', '시흥시'): '41390', ('경기', '군포시'): '41410', ('경기', '의왕시'): '41430', ('경기', '하남시'): '41450',
        ('경기', '용인시 처인구'): '41461', ('경기', '용인시 기흥구'): '41463', ('경기', '용인시 수지구'): '41465', ('경기', '파주시'): '41480',
        ('경기', '이천시'): '41500', ('경기', '안성시'): '41550', ('경기', '김포시'): '41570', ('경기', '광주시'): '41610', ('경기', '양주시'): '41630',
        ('경기', '포천시'): '41650', ('경기', '여주시'): '41670', ('경기', '양평군'): '41830'}


def call(kind, lawd, ym, page=1):
    q = urllib.parse.urlencode(dict(serviceKey=KEY, LAWD_CD=lawd, DEAL_YMD=ym, pageNo=page, numOfRows=1000))
    for k in range(4):
        try:
            raw = urllib.request.urlopen(URL[kind] + '?' + q, timeout=40).read().decode('utf-8', 'replace')
            root = ET.fromstring(raw)
            code = (root.findtext('.//resultCode') or root.findtext('.//returnReasonCode') or '').strip()
            msg = (root.findtext('.//resultMsg') or root.findtext('.//returnAuthMsg') or '').strip()
            items = [{c.tag: (c.text or '').strip() for c in it} for it in root.iter('item')]
            total = int(root.findtext('.//totalCount') or 0)
            return code, msg, items, total
        except Exception as e:
            err = f'{type(e).__name__}: {str(e)[:120]}'.replace(KEY, '***')
            time.sleep(3 + 5 * k)
    return 'ERR', err, [], 0


def need():
    a = pd.read_csv(os.path.join(AM, 'auction_train.csv')); o = pd.read_csv(os.path.join(AM, 'officetel', 'ot_train.csv'))
    return {'apt': a.groupby(['sd', 'sgg']).emd.apply(set).to_dict(), 'ot': o.groupby(['sd', 'sgg']).emd.apply(set).to_dict()}


def months(a='2022-01'):
    t = date.today(); last = f'{t.year if t.month > 1 else t.year - 1}{(t.month - 1) or 12:02d}'
    return [p.strftime('%Y%m') for p in pd.period_range(a, f'{last[:4]}-{last[4:]}', freq='M')]


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'test'
    N = need()
    if mode == 'test':
        rep = {}
        for kind in ('apt', 'ot'):
            for (sd, sgg), emds in N[kind].items():
                lawd = CODE.get((sd, sgg))
                if not lawd: rep[f'{kind} {sd} {sgg}'] = 'NO CODE'; continue
                code, msg, items, total = call(kind, lawd, '202409')
                umd = {x.get('umdNm') for x in items}
                rep[f'{kind} {sd} {sgg}'] = dict(code=code, msg=msg, total=total, sggCd={x.get('sggCd') for x in items} - {None} and sorted({x.get('sggCd') for x in items})[:3],
                                                 emd_hit=len(emds & umd), emd_n=len(emds), fields=sorted(items[0]) if items else [])
                time.sleep(0.2)
        json.dump(rep, open(os.path.join(OUT, 'test.json'), 'w'), ensure_ascii=False, indent=1, default=list)
        print(json.dumps(rep, ensure_ascii=False, default=list)[:3000])
    elif mode == 'eup':   # 읍·면 동이 있는 시군구만 다시 받아 apt.csv.gz 에 합치기 (2026-11-05)
        kind = 'apt'; rows = []
        targets = {k: v for k, v in N['apt'].items() if any(str(e).endswith(('읍', '면')) for e in v)}
        print('대상', list(targets))
        for (sd, sgg), emds in targets.items():
            lawd = CODE.get((sd, sgg))
            for ym in months():
                page = 1
                while True:
                    code, msg, items, total = call(kind, lawd, ym, page)
                    if code not in ('00', '000'): break
                    rows += [dict(x, sd=sd, sgg=sgg) for x in items if set(str(x.get('umdNm')).split()) & emds and x.get('umdNm') not in emds]
                    if page * 1000 >= total: break
                    page += 1
            print(sgg, len(rows), flush=True)
        old = pd.read_csv(os.path.join(OUT, 'apt.csv.gz'), dtype=str)
        pd.concat([old, pd.DataFrame(rows).astype(str)], ignore_index=True).drop_duplicates().to_csv(os.path.join(OUT, 'apt.csv.gz'), index=False, compression='gzip')
        print('추가', len(rows))
    else:
        for kind in ('apt', 'ot'):
            rows, log = [], {}
            for (sd, sgg), emds in N[kind].items():
                lawd = CODE.get((sd, sgg))
                if not lawd: continue
                for ym in months():
                    page = 1
                    while True:
                        code, msg, items, total = call(kind, lawd, ym, page)
                        if code not in ('00', '000'): log[f'{sgg} {ym}'] = f'{code} {msg}'; break
                        rows += [dict(x, sd=sd, sgg=sgg) for x in items if x.get('umdNm') in emds or set(str(x.get('umdNm')).split()) & emds]   # 읍·면 '진접읍 장현리' ↔ '진접읍' (2026-11-05)
                        if page * 1000 >= total: break
                        page += 1
                print(kind, sgg, len(rows), flush=True)
            df = pd.DataFrame(rows)
            df.to_csv(os.path.join(OUT, f'{kind}.csv.gz'), index=False, compression='gzip')
            json.dump(dict(n=len(df), errors=log), open(os.path.join(OUT, f'{kind}_log.json'), 'w'), ensure_ascii=False, indent=1)
