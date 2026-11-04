"""주변 단지 시세 (2026-11-05 사용자 요청: 실거래·KB·리치고에 더해 주변 단지까지 보고 종합 시세 측정).

아파트: 리치고 단지 페이지 pageProps.emdComparison — 같은 법정동 단지들의 대표 평형 평당가(공급평 기준)·연식·세대수.
        비슷한 연식(±10년, 부족하면 ±15년 → 전체) 단지 평당가 중앙값 × 이 물건 공급평.
오피스텔: 리치고 검색 "<구> <동>" 의 오피스텔 단지들 → 각 페이지 pyeongInfos 에서 전용면적이 가까운(±30%) 평형의
        최근 12개월 국토부 실거래(MOLIT) 전용㎡당 가격 중앙값 × 이 물건 전용㎡.
결과 dict: eok, n_danji, basis, detail[:5] — 실패하면 None.
"""
import json, re, statistics, subprocess, time, urllib.parse
from datetime import datetime

_PAGE = {}


def _get(url, tries=2):
    try:   # 배치에서 이미 받은 페이지는 다시 받지 않음
        import auction_predictor as _ap
        r = _ap.fetch(url)
        if '__NEXT_DATA__' in r:
            return r
    except Exception:
        pass
    for k in range(tries):
        try:
            r = subprocess.run(['curl', '-sL', '-m', '40', '-A', 'Mozilla/5.0', url], capture_output=True).stdout.decode('utf-8', 'replace')
        except Exception:
            r = ''
        if '__NEXT_DATA__' in r:
            return r
        time.sleep(2 + 3 * k)
    return ''


def page_props(kind, pid):
    key = (kind, pid)
    if key not in _PAGE:
        raw = _get(f'https://m.richgo.ai/realty/{kind}/{pid}')
        pp = {}
        if raw:
            i = raw.find('__NEXT_DATA__'); j = raw.find('>', i); k = raw.find('</script>', j)
            try:
                pp = json.loads(raw[j + 1:k])['props']['pageProps']
            except Exception:
                pp = {}
        _PAGE[key] = pp
    return _PAGE[key]


def apt_from_props(pp, danji_id, pyeong):
    """emdComparison 으로 주변 시세. pyeong = 이 물건 공급평(숫자)."""
    ec = pp.get('emdComparison') or {}
    rows = [r for r in (ec.get('rows') or []) if isinstance(r, dict) and r.get('perPyeong')]
    if not rows or not pyeong:
        return None
    me = next((r for r in rows if r.get('id') == danji_id), None)
    others = [r for r in rows if r.get('id') != danji_id]
    age = (me or {}).get('age') or (((pp.get('data') or {}).get('basic') or {}).get('construction') or {}).get('year')
    pick, basis = [], ''
    for tol in (10, 15, None):
        pick = [r for r in others if tol is None or age is None or r.get('age') is None or abs(r['age'] - age) <= tol]
        if len(pick) >= 3:
            basis = f'연식 ±{tol}년' if tol else '동 전체'
            break
    if len(pick) < 2:
        return None
    pp_med = statistics.median(r['perPyeong'] for r in pick)
    eok = round(pp_med * float(pyeong) / 1e4, 2)
    return dict(eok=eok, n_danji=len(pick), basis=f"{ec.get('emd', '')} {basis}".strip(), per_pyeong_manwon=round(pp_med),
                self_per_pyeong_manwon=(me or {}).get('perPyeong'), price_date=ec.get('priceDate'),
                detail=[dict(name=r.get('name'), age=r.get('age'), per_pyeong=r['perPyeong']) for r in sorted(pick, key=lambda r: abs((r.get('age') or 0) - (age or 0)))[:5]])


def nearby_apt(danji_id, pyeong):
    try:
        return apt_from_props(page_props('danji', danji_id), danji_id, pyeong)
    except Exception:
        return None


def _ot_unit_prices(pp, area, today):
    """오피스텔 한 단지: 전용면적이 가까운 평형의 12개월 내 실거래 전용㎡당 가격(만원)."""
    out = []
    for p in ((pp.get('data') or {}).get('pyeongInfos') or {}).values():
        try:
            pa = float(p.get('minPrivateArea') or 0)
        except Exception:
            continue
        if not pa or abs(pa / area - 1) > 0.3:
            continue
        mo = ((p.get('danjiPriceInfo') or {}).get('memePriceDict') or {}).get('MOLIT') or {}
        if not mo.get('price') or not mo.get('yyyymmdd'):
            continue
        age_m = (today - datetime.strptime(mo['yyyymmdd'], '%Y.%m.%d')).days / 30.4
        if age_m <= 12:
            out.append(mo['price'] / pa)
    return out


def ot_from_list(pages, self_id, area, today=None):
    today = today or datetime.now()
    per, names = [], []
    for pid, name, pp in pages:
        if pid == self_id:
            continue
        u = _ot_unit_prices(pp, area, today)
        if u:
            per.append(statistics.median(u)); names.append((name, round(statistics.median(u))))
    if len(per) < 2:
        return None
    m = statistics.median(per)
    return dict(eok=round(m * area / 1e4, 2), n_danji=len(per), basis='같은 동 오피스텔 · 전용 ±30% · 12개월 실거래',
                per_m2_manwon=round(m), detail=[dict(name=n, per_m2=v) for n, v in names[:5]])


_SEARCH = {}


def nearby_ot(self_id, sgg, emd, area):
    try:
        if not (sgg and emd and area):
            return None
        q = f'{sgg} {emd}'
        if q not in _SEARCH:
            raw = _get('https://m.richgo.ai/realty/search?q=' + urllib.parse.quote(q))
            res = []
            if raw:
                i = raw.find('__NEXT_DATA__'); j = raw.find('>', i); k = raw.find('</script>', j)
                for g in (json.loads(raw[j + 1:k])['props']['pageProps'].get('agentSearch') or {}).get('groups') or []:
                    if g.get('kind') != 'officetel':
                        continue
                    for it in g.get('items') or []:
                        m = re.search(r'/realty/officetel/([0-9A-Za-z]+)', it.get('href', ''))
                        if m:
                            res.append((m.group(1), it.get('name', '')))
            _SEARCH[q] = res
        pages = [(pid, nm, page_props('officetel', pid)) for pid, nm in _SEARCH[q][:10]]
        return ot_from_list(pages, self_id, float(area))
    except Exception:
        return None


def merge_into_sise(sise, nb, low_manwon, appr_manwon=None):
    """종합 시세(중앙값)에 주변 시세를 네 번째 근거로 넣는다. sise 는 auction_predictor.sise_detail 결과."""
    if not nb or not sise or sise.get('error'):
        return sise
    s = dict(sise)
    s['nearby'] = nb
    used = s.get('used') or []
    vals = []
    if '리치고' in used and s.get('richgo_eok'):
        vals.append(('리치고', s['richgo_eok']))
    if '실거래' in used and (s.get('trade') or {}).get('adj_eok'):
        vals.append(('실거래', s['trade']['adj_eok']))
    if 'KB' in used and (s.get('kb') or {}).get('adj_eok'):
        vals.append(('KB', s['kb']['adj_eok']))
    vals.append(('주변', nb['eok']))
    v = [x[1] for x in vals]
    est = statistics.median(v)
    s.update(est_eok=round(est, 2), range_eok=[round(min(v), 2), round(max(v), 2)], used=[x[0] for x in vals],
             spread_pct=round((max(v) / min(v) - 1) * 100, 1), low_vs_est_pct=round(low_manwon / 1e4 / est * 100))
    flags = [f for f in (s.get('flags') or []) if not f.startswith('출처 간 차이') and not f.startswith('주변 단지')]
    if s['spread_pct'] > 15:
        flags.append('출처 간 차이 큼')
    others = [x[1] for x in vals if x[0] != '주변']
    if others:
        own = statistics.median(others)
        d = (nb['eok'] / own - 1) * 100
        s['nearby_vs_own_pct'] = round(d, 1)
        if abs(d) > 10:
            flags.append(f'주변 단지 시세가 이 단지보다 {d:+.0f}%')
    s['flags'] = flags
    return s
