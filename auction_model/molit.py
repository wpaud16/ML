"""국토부 아파트 실거래 + M 시세 (2026-11-05 확정, 사용자 결정 — 백테스트 dev/sise_bt.py·dev/combo_bt.py: 평균 오차 5.08→4.78%).

M 시세 = w × (층 보정 실거래 12개월 최근성 가중 평균) + (1 − w) × (층 보정 리치고 시세)
  - 실거래: 같은 단지(리치고 지번 = 국토부 동+지번), 전용 ±1㎡, 직거래·해제 제외, 최근 12개월, 반감기 3개월 가중,
            시군구 월별 ㎡당 중앙값 지수(3개월 이동 중앙)로 오늘 값으로 보정
  - 층 보정: 단지 안 상대 층 구간(1층·2~3층·저층·중층·고층·꼭대기) 가격 비율 FP (2024-07 이전 국토부 거래로 추정)
  - w = neff/(neff+2) (최대 0.7) × (1 − 0.5 × min(분산/0.2, 1)), neff = 가중치 합, 분산 = 거래가 표준편차/평균
  - 실거래 0건이면 층 보정 리치고 (no_trade=True → 메일에서 숨김, 웹페이지 '실거래 없음(참고)')
데이터: 공공데이터포털 API (환경변수 MOLIT_API_KEY), 시군구별 월 단위 캐시 molit_cache/apt_<코드>.csv.gz
  (지난달 이전 달은 한 번 받으면 재사용, 최근 2개월은 신고 지연 때문에 매번 다시 받음)."""
import os, re, json, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import date
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, 'molit_cache'); os.makedirs(CACHE, exist_ok=True)
URL = 'https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev'
FP = {'1층': 0.95, '2~3층': 0.975, '저층': 0.99, '중층': 1.0, '고층': 1.004, '꼭대기': 0.998, 'mid': 0.994}
COLS = ['aptSeq', 'aptNm', 'umdNm', 'jibun', 'excluUseAr', 'floor', 'buildYear', 'dealYear', 'dealMonth', 'dealDay', 'dealAmount', 'cdealType', 'dealingGbn']
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
_MEM = {}
import threading
_LOCK = threading.Lock()   # 배치가 여러 스레드로 물건을 처리해도 같은 시군구를 한 번만 받는다


def _key():
    return (os.environ.get('MOLIT_API_KEY') or '').strip()


def _call(lawd, ym, page=1):
    q = urllib.parse.urlencode(dict(serviceKey=_key(), LAWD_CD=lawd, DEAL_YMD=ym, pageNo=page, numOfRows=1000))
    for k in range(4):
        try:
            root = ET.fromstring(urllib.request.urlopen(URL + '?' + q, timeout=40).read().decode('utf-8', 'replace'))
            code = (root.findtext('.//resultCode') or '').strip()
            if code not in ('00', '000'):
                raise RuntimeError(f'API {code} {(root.findtext(".//resultMsg") or "").strip()}')
            return [{c.tag: (c.text or '').strip() for c in it} for it in root.iter('item')], int(root.findtext('.//totalCount') or 0)
        except Exception as e:
            err = str(e).replace(_key(), '***') if _key() else str(e)
            time.sleep(3 + 5 * k)
    raise RuntimeError(f'국토부 API 실패 {lawd} {ym}: {err[:150]}')


def _months(n=13, today=None):
    t = pd.Timestamp(today or date.today())
    return [p.strftime('%Y%m') for p in pd.period_range(t - pd.DateOffset(months=n), t, freq='M')]


def load_sgg(sd, sgg, months=13, refresh_recent=2, today=None):
    """시군구 최근 N개월 거래 (캐시 사용). API 키 없으면 캐시만."""
    lawd = CODE.get((sd, sgg))
    if not lawd: return None
    if lawd in _MEM: return _MEM[lawd]
    with _LOCK:
        if lawd in _MEM: return _MEM[lawd]
        return _load(sd, sgg, lawd, months, refresh_recent, today)


def _load(sd, sgg, lawd, months, refresh_recent, today):
    path = os.path.join(CACHE, f'apt_{lawd}.csv.gz')
    old = pd.read_csv(path, dtype=str) if os.path.exists(path) else pd.DataFrame(columns=COLS + ['ym'])
    want = _months(months, today); recent = set(want[-refresh_recent:])
    have = set(old.ym.unique()) if len(old) else set()
    if _key():
        parts = [old[~old.ym.isin(recent)]] if len(old) else []
        for ym in want:
            if ym in have and ym not in recent: continue
            rows, page = [], 1
            while True:
                items, total = _call(lawd, ym, page)
                rows += [{c: x.get(c, '') for c in COLS} | {'ym': ym} for x in items]
                if page * 1000 >= total: break
                page += 1
            parts.append(pd.DataFrame(rows, columns=COLS + ['ym']))
        new = pd.concat(parts, ignore_index=True) if parts else old
        new = new[new.ym >= want[0]]
        new.to_csv(path, index=False, compression='gzip')
        old = new
    _MEM[lawd] = _prep(old)
    return _MEM[lawd]


def _prep(m):
    if not len(m): return m
    m = m[(m.cdealType.fillna('') == '') & (m.dealingGbn.fillna('') != '직거래')].copy()
    m['price'] = pd.to_numeric(m.dealAmount.str.replace(',', ''), errors='coerce') * 1e4
    m['area'] = pd.to_numeric(m.excluUseAr, errors='coerce'); m['floor'] = pd.to_numeric(m.floor, errors='coerce')
    m['d'] = pd.to_datetime(m.dealYear + '-' + m.dealMonth.str.zfill(2) + '-' + m.dealDay.str.zfill(2), errors='coerce')
    m = m.dropna(subset=['price', 'area', 'd'])
    m['ppa'] = m.price / m.area; m['p'] = m.d.dt.to_period('M')
    m['top'] = m.groupby('aptSeq').floor.transform('max'); m['jb'] = m.jibun.astype(str).str.strip()
    return m


def fbin(f, top):
    if f is None or pd.isna(f) or pd.isna(top) or top < 3: return 'mid'
    if f <= 1: return '1층'
    if f <= 3: return '2~3층'
    if f >= top: return '꼭대기'
    r = f / top
    return '저층' if r < 1 / 3 else ('중층' if r < 2 / 3 else '고층')


def floor_of(address):
    x = re.search(r'(\d+)층', address or '')
    return int(x.group(1)) if x else (1 if '지하' in (address or '') else None)


def m_sise(sd, sgg, emd, jibun_addr, area, address, richgo_won, today=None, lag_days=0):
    """M 시세 (원). today = 기준일(기본 오늘), lag_days = 기준일 이전 며칠까지 계약된 거래만 (재학습: 매각일 −30일, 백테스트와 같게). 반환 dict(mkt, richgo, richgo_floor, trade_w, trade_avg, n12, neff, disp, w, floor_bin, fprem, no_trade, note)."""
    out = dict(mkt=richgo_won, richgo=richgo_won, no_trade=None, n12=0, w=0.0)   # no_trade None = 확인 못 함(숨기지 않음)
    try:
        m = load_sgg(sd, sgg)
    except Exception as e:
        out['note'] = f'국토부 실패: {str(e)[:80]}'; return out
    if m is None or not len(m):
        out['note'] = '국토부 자료 없음'; return out
    jb = (jibun_addr or '').split()[-1] if jibun_addr else None
    # 읍·면 지역: 국토부 umdNm = '오남읍 양지리', 리치고 emd = '오남읍' 또는 '양지리' → 띄어쓰기 단위로 비교 (2026-11-05 수정)
    same = m.umdNm.map(lambda u: u == emd or emd in str(u).split()) if emd else m.umdNm.map(lambda u: False)
    c = m[same & (m.jb == jb) & ((m.area - area).abs() <= 1.0)] if jb else m.iloc[:0]
    top = m[same & (m.jb == jb)].top.max() if jb else np.nan
    fb = fbin(floor_of(address), top); tp = FP.get(fb, 1.0)
    rf = richgo_won * tp
    out.update(floor_bin=fb, fprem=tp, richgo_floor=rf, mkt=rf, no_trade=True if jb else None)
    t0 = pd.Timestamp(today or date.today()); cut = t0 - pd.Timedelta(days=lag_days)
    t = c[(c.d >= t0 - pd.DateOffset(months=12)) & (c.d <= cut)]
    if not len(t): return out
    ix = m[m.d <= cut].groupby('p').ppa.median().sort_index()
    ix = ix.reindex(pd.period_range(ix.index.min(), ix.index.max(), freq='M')).interpolate(limit_direction='both').rolling(3, min_periods=1).median()
    I = float(ix.iloc[-1])
    # 거래가 × (이 물건 층 비율 / 그 거래 층 비율). 시군구 지수 추세 보정은 뺌 (2026-11-05: 거래 단지 구성에 따라 출렁여
    # 힐스테이트다산 실거래 평균이 12억대→9.6억으로 깎임. 백테스트 보정 없음 4.71% vs 있음 4.77%) — 최근 거래 가중(반감기 3개월)만 사용
    adj = t.price.values * np.array([tp / FP.get(fbin(f, tt), 1.0) for f, tt in zip(t.floor, t.top)])
    age = (t0 - t.d).dt.days.values / 30.4; wt = 0.5 ** (age / 3)
    tw = float(np.sum(wt * adj) / wt.sum()); neff = float(wt.sum())
    disp = float(np.std(adj, ddof=1) / np.mean(adj)) if len(adj) >= 3 else 0.1
    w = min(neff / (neff + 2), 0.7) * (1 - min(max(disp / 0.2, 0), 1) * 0.5)
    out.update(mkt=w * tw + (1 - w) * rf, trade_w=tw, n12=int(len(t)), neff=round(neff, 2), disp=round(disp, 3), w=round(w, 3), no_trade=False,
               last_trade=dict(date=str(t.d.max().date()), price=int(t.sort_values('d').price.iloc[-1])))
    return out
