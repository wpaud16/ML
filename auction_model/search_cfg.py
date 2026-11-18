"""경매 검색 조건 (search_regions.json) 읽기 — 2026-11-18 사용자 요청: 종류별 지역 + 최저가 범위.

search_regions.json
  apt   : [[시도, 시군구], ...]   아파트 검색 지역
  ot    : [서울 구, ...]          오피스텔
  shop  : [서울 구, ...]          상가 (없으면 서울 전체)
  bldg  : [서울 구, ...]          건물 (없으면 서울 전체)
  price : {apt|ot|shop|bldg: [하한억, 상한억]}  최저가 범위, null = 제한 없음
수정은 local_runner/region_gui.pyw (브리핑관리.exe '경매 지역' 탭).
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, 'search_regions.json')
SEOUL = ['강남구', '강동구', '강북구', '강서구', '관악구', '광진구', '구로구', '금천구', '노원구', '도봉구', '동대문구', '동작구',
         '마포구', '서대문구', '서초구', '성동구', '성북구', '송파구', '양천구', '영등포구', '용산구', '은평구', '종로구', '중구', '중랑구']
CAT_KEY = {'아파트': 'apt', '오피스텔': 'ot', '상가': 'shop', '건물': 'bldg'}
DEFAULT_PRICE = {'bldg': [None, 20]}   # 2026-11-16 결정: 건물 최저가 20억 이하


def load():
    try:
        return json.load(open(PATH, encoding='utf-8'))
    except Exception:
        return {}


def gus(cat, cfg=None):
    """상가·건물·오피스텔 검색 구 목록."""
    cfg = load() if cfg is None else cfg
    k = CAT_KEY.get(cat, cat)
    v = cfg.get(k)
    return list(SEOUL) if v is None else list(v)


def price_range(cat, cfg=None):
    """→ (하한억|None, 상한억|None)."""
    cfg = load() if cfg is None else cfg
    k = CAT_KEY.get(cat, cat)
    p = (cfg.get('price') or {}).get(k, DEFAULT_PRICE.get(k)) or [None, None]
    lo, hi = (list(p) + [None, None])[:2]
    return (float(lo) if lo not in (None, '') else None, float(hi) if hi not in (None, '') else None)


def price_ok(cat, low_won, cfg=None):
    lo, hi = price_range(cat, cfg)
    e = (low_won or 0) / 1e8
    return (lo is None or e >= lo) and (hi is None or e <= hi)


def fmt_eok(x):
    return f'{x:g}억'


def price_text(cat, cfg=None):
    lo, hi = price_range(cat, cfg)
    if lo is None and hi is None:
        return ''
    if lo is None:
        return f'최저가 {fmt_eok(hi)} 이하'
    if hi is None:
        return f'최저가 {fmt_eok(lo)} 이상'
    return f'최저가 {fmt_eok(lo)}~{fmt_eok(hi)}'
