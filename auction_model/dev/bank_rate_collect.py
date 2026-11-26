"""은행 대출금리 월별 수집 (2026-11-26 사용자 요청: 기준금리와 은행금리를 나눠서 백테스트).
한국은행 ECOS 121Y006 예금은행 대출금리(신규취급액 기준), 월별. 공개 sample 키는 한 번에 10행만 → 10개월씩 나눠 받음.
  주담대 = BECBLA0302 (주택담보대출), 중기 = BECBLA0202 (중소기업대출: 상가·건물 담보대출 근사)
→ auction_model/bank_rate.json {"mortgage": {"YYYY-MM": %, ...}, "sme": {...}, "updated": ...}
python dev/bank_rate_collect.py [시작 YYYYMM]"""
import json, os, sys, time, urllib.request
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), 'bank_rate.json')
ITEMS = {'mortgage': 'BECBLA0302', 'sme': 'BECBLA0202'}
# 2026-11-26 사용자: 은행채 금리도. ECOS 에 은행채(AAA) 5년이 없어 은행채인 산금채 1년 + 은행채 5년과 거의 같이 움직이는 국고채 5년 (721Y001 월평균)
BONDS = {'kdb1y': '6050000', 'ktb5y': '5040000'}


def months(a, b):
    y, m = int(a[:4]), int(a[4:])
    while f'{y}{m:02d}' <= b:
        yield f'{y}{m:02d}'
        m += 1
        if m > 12: y, m = y + 1, 1


def get(item, a, b, stat='121Y006'):
    u = f'https://ecos.bok.or.kr/api/StatisticSearch/sample/json/kr/1/10/{stat}/M/{a}/{b}/{item}'
    d = json.load(urllib.request.urlopen(u, timeout=30))
    return {r['TIME'][:4] + '-' + r['TIME'][4:]: float(r['DATA_VALUE']) for r in (d.get('StatisticSearch') or {}).get('row') or []}


def main(start='201801'):
    end = date.today().strftime('%Y%m')
    ms = list(months(start, end))
    out = {'updated': date.today().isoformat()}
    for k, (stat, item) in [(k, ('121Y006', i)) for k, i in ITEMS.items()] + [(k, ('721Y001', i)) for k, i in BONDS.items()]:
        s = {}
        for i in range(0, len(ms), 10):
            s.update(get(item, ms[i], ms[min(i + 9, len(ms) - 1)], stat)); time.sleep(0.3)
        out[k] = s
        print(k, len(s), min(s), max(s), list(s.items())[-3:])
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main(*sys.argv[1:2])
