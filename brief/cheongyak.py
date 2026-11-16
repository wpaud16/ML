"""STEP 3b 청약 알림 (2026-11-16~) — JM 자격 기준으로 앞으로 10일 안 청약 접수 단지만.
일정 수집: 노트북 Claude Code CLI 웹 검색(분양캘린더·청약홈 청약소식·리치고 분양 페이지) → JSON
필터·D-day·예산 초과·정렬·카드는 이 파일에서 정한다. 실패하면 한 줄 "청약 정보를 불러오지 못했습니다".
끄기: 환경변수 CHEONGYAK=0 (STOP RULE: JM이 집을 사면(낙찰·매매 계약) 이 섹션을 없앤다).
같은 날 다시 실행하면 cheongyak_cache/<날짜>.json 을 다시 씀 (검색 생략).
"""
import datetime as dt, html, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, 'cheongyak_cache')
E = html.escape
WD = '월화수목금토일'
GRAY = 'color:#777;font-size:12px'
CARD = 'border:1px solid #888888;border-radius:10px;padding:12px 14px;margin-bottom:12px;line-height:1.6'
LAB = '<div style="font-weight:bold;font-size:13px;margin:10px 0 6px">'
BUDGET = 12.4          # 억
WINDOW = 10            # 접수일: 오늘 ~ 10일 뒤
SOON = 7               # 견본주택 개관: 7일 안
MARRIED = dt.date(2027, 5, 1)   # 혼인신고(2027-04) 뒤부터 신혼부부 특공 표시
REGION = re.compile(r'서울|하남|성남|분당|수정구|중원구|구리|남양주')
EXCLUDE = re.compile(r'공공분양|공공지원|임대|행복주택|국민주택|영구|신혼희망|지분적립|민간참여|LH|SH|GH|'
                     r'오피스텔|도시형|생활숙박|노부모|다자녀|기관추천')
FAIL = '청약 정보를 불러오지 못했습니다'

PROMPT = """오늘은 {today} (한국시간 아침)입니다. 웹 검색으로 아파트 청약 일정을 찾아 사실만 JSON 으로 정리하세요. 청약 권유는 하지 마세요.

[대상자] 무주택 세대주, 1인 세대, 당첨 이력 없음, 서울 거주, 생애최초 대상, 청약통장 2~10년(예치금 충족), 연소득 1~1.5억, 혼인신고 2027년 4월 예정.
[지역] 서울 전역 / 경기 하남시, 성남시(수정·중원·분당), 구리시, 남양주시
[기간] JM 해당 유형의 청약 접수일이 {today} ~ {end} 인 공고. 그리고 {soon} 까지 견본주택 개관(곧 청약 예정).
[포함 유형] 민영 아파트 1순위 일반공급 / 아파트 무순위·계약취소 재공급·임의공급(줍줍) / 생애최초 특별공급(전용 60㎡ 이하만) {newlywed}
[제외] 공공분양(LH·SH·GH, 신혼희망타운, 지분적립형, 민간참여 공공분양), 모든 임대(공공지원민간임대, 국민·영구·행복주택), 오피스텔·도시형생활주택·생활숙박시설, 노부모·다자녀·기관추천 특공
[찾는 법] 청약홈·LH 사이트는 열지 마세요.
1. 주간 일정: "이번 주 분양캘린더 리얼투데이", "{m}월 {w}째 주 청약 일정", "청약홈 청약소식 {m}월 {w}째 주"(kbthink.com/realestate/basics/housenews/ 페이지는 WebFetch), "서울 무순위 청약 {m}월". 이번 주와 다음 주 모두.
2. 단지별 상세: "리치고 <단지명> 분양" 검색 → https://m.richgo.ai/realty/parcel/<id> 를 WebFetch (타입별 공급세대·분양가, 일정, 주변 시세). 리치고 페이지가 없으면 기사·공고 요약을 쓰고 source 를 "기사".

반드시 아래 JSON 하나만 출력하세요 (설명·코드블록 없이). 모르는 값은 null. 날짜는 YYYY-MM-DD.
{{"items": [{{"name": "단지명", "address": "시/구 동", "total_units": 0, "general_units": 0,
   "rounds": [{{"type": "1순위 일반공급|무순위|계약취소 재공급|임의공급|생애최초 특별공급|신혼부부 특별공급", "date": "해당지역 접수일", "date_other": "기타지역 접수일 또는 null"}}],
   "winner_date": "", "contract_date": "", "move_in": "YYYY.MM",
   "types": [{{"area": 84, "price_eok": 12.77, "units": 0}}],
   "eligibility": "무주택·거주·통장 요건 한 줄 (공고 기준)", "lottery_note": "85㎡ 이하 가점/추첨 비율 등 한 줄 또는 null",
   "price_cap": "적용|미적용|null", "resale": "전매·실거주 의무 한 줄 또는 null",
   "market_py_manwon": null, "sale_py_manwon": null, "richgo_url": null, "source": "리치고|기사"}}],
 "upcoming": [{{"name": "단지명", "address": "시/구 동", "date": "견본주택 개관일", "note": "한 줄"}}],
 "sources": ["참고한 사이트 이름"]}}
types 는 59·70·74·84㎡ 위주 최대 4개(분양가는 최고가 기준, 억 단위). 결과가 없으면 items 와 upcoming 을 빈 목록으로."""


def _d(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def md(d):
    return f'{d.month}/{d.day}({WD[d.weekday()]})'


def fetch(today):
    """오늘 캐시가 있으면 그대로, 없으면 CLI 검색. 실패 None."""
    if os.environ.get('CHEONGYAK', '1') == '0':
        return {'off': True}
    p = os.path.join(CACHE, today.isoformat() + '.json')
    if os.path.exists(p):
        return json.load(open(p, encoding='utf-8'))
    import claude_summary
    wk = (today.day - 1) // 7 + 1
    newlywed = '/ 신혼부부 특별공급' if today >= MARRIED else '(신혼부부 특공은 제외)'
    out = claude_summary.cli_json(PROMPT.format(today=today, end=today + dt.timedelta(days=WINDOW),
                                                soon=today + dt.timedelta(days=SOON), m=today.month, w=wk, newlywed=newlywed),
                                  timeout=int(os.environ.get('CHEONGYAK_TIMEOUT', '900')), tag='청약 cli')
    if out is None or not isinstance(out.get('items', []), list):
        return None
    os.makedirs(CACHE, exist_ok=True)
    json.dump(out, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return out


def _ok_round(r, today):
    t = r.get('type') or ''
    if EXCLUDE.search(t):
        return False
    if '신혼' in t and today < MARRIED:
        return False
    d = _d(r.get('date'))
    return d is not None and today <= d <= today + dt.timedelta(days=WINDOW)


def select(data, today):
    """규칙대로 거르기: 지역·제외 유형·기간·신혼 시기. 생애최초는 60㎡ 이하 타입이 있을 때만."""
    items = []
    for it in data.get('items') or []:
        name, addr = it.get('name') or '', it.get('address') or ''
        if not name or EXCLUDE.search(name) or not REGION.search(addr + ' ' + name):
            continue
        types = [t for t in it.get('types') or [] if isinstance(t, dict)]
        rounds = [r for r in it.get('rounds') or [] if isinstance(r, dict) and _ok_round(r, today)]
        if not any(t.get('area') and float(t['area']) <= 60 for t in types):
            rounds = [r for r in rounds if '생애최초' not in (r.get('type') or '')]
        if not rounds:
            continue
        rounds.sort(key=lambda r: _d(r['date']))
        items.append(dict(it, rounds=rounds, types=types, _first=_d(rounds[0]['date'])))
    items.sort(key=lambda x: x['_first'])
    up = [u for u in data.get('upcoming') or [] if isinstance(u, dict) and _d(u.get('date'))
          and today <= _d(u['date']) <= today + dt.timedelta(days=SOON)
          and REGION.search((u.get('address') or '') + ' ' + (u.get('name') or ''))
          and not EXCLUDE.search((u.get('name') or '') + ' ' + (u.get('note') or ''))]
    up.sort(key=lambda u: _d(u['date']))
    return items, up


def _eok(x):
    try:
        return f'{float(x):.2f}억'
    except Exception:
        return '-'


def card(it, today):
    H, T = [], []
    head = ' · '.join(x for x in [it.get('address') or '',
                                   (f"총 {it['total_units']:,}세대" if isinstance(it.get('total_units'), int) else '')
                                   + (f"(일반 {it['general_units']:,})" if isinstance(it.get('general_units'), int) else '')] if x)
    H.append(f'<div><b style="font-size:15px">{E(it["name"])}</b>' + (f'<span style="{GRAY}"> · {E(head)}</span>' if head else '') + '</div>')
    T.append(f'{it["name"]}' + (f' · {head}' if head else ''))
    for r in it['rounds']:
        d = _d(r['date']); n = (d - today).days
        dd = 'D-day' if n == 0 else f'D-{n}'
        other = _d(r.get('date_other'))
        H.append(f'<div>🗓 {E(r["type"])} 접수 <b>{md(d)}</b> · {dd}'
                 + (f'<span style="{GRAY}"> (기타지역 {md(other)})</span>' if other and other != d else '') + '</div>')
        T.append(f'🗓 {r["type"]} 접수 {md(d)} · {dd}' + (f' (기타지역 {md(other)})' if other and other != d else ''))
    sch = ' · '.join(x for x in [f'당첨 {md(_d(it["winner_date"]))}' if _d(it.get('winner_date')) else '',
                                 f'계약 {md(_d(it["contract_date"]))}' if _d(it.get('contract_date')) else '',
                                 f'입주 {it["move_in"]}' if it.get('move_in') else ''] if x)
    if sch:
        H.append(f'<div>{E(sch)}</div>'); T.append(sch)
    if it['types']:
        H.append('<div>💰 분양가</div>'); T.append('💰 분양가')
        for t in it['types'][:4]:
            try:
                over = float(t.get('price_eok')) > BUDGET
            except Exception:
                over = False
            line = f"{t.get('area')}㎡ {_eok(t.get('price_eok'))}" + (f" ({t['units']}세대)" if t.get('units') else '') + (' ⚠ 예산 초과' if over else '')
            H.append(f'<div style="padding-left:10px">{E(line)}</div>'); T.append('  ' + line)
    el = it.get('eligibility') or ''
    kinds = ' · '.join(dict.fromkeys(r['type'] for r in it['rounds']))
    elig = f'{kinds} 가능' + (f' ({el})' if el else '')
    if it.get('lottery_note'):
        elig += f' — {it["lottery_note"]}'
    if any('생애최초' in r['type'] for r in it['rounds']):
        elig += ' · △ 생애최초는 60㎡ 이하만, 소득기준(1인 가구) 초과 가능성 높음 — 공고문 소득표 확인'
    if any('신혼' in r['type'] for r in it['rounds']):
        elig += ' · 부부 합산 소득 기준 확인'
    H.append(f'<div>✅ 내 자격: {E(elig)}</div>'); T.append(f'✅ 내 자격: {elig}')
    small = ' · '.join(x for x in [f'분양가상한제 {it["price_cap"]}' if it.get('price_cap') in ('적용', '미적용') else '',
                                   it.get('resale') or '',
                                   (f'주변 시세 평당 {it["market_py_manwon"]:,}만 vs 분양 평당 {it["sale_py_manwon"]:,}만'
                                    if isinstance(it.get('market_py_manwon'), (int, float)) and isinstance(it.get('sale_py_manwon'), (int, float)) else '')] if x)
    if small:
        H.append(f'<div style="{GRAY}">{E(small)}</div>')
    links = []
    if it.get('richgo_url'):
        links.append(f'<a style="color:#1a73e8" href="{E(it["richgo_url"])}">상세 보기 →</a>')
    elif it.get('source') != '리치고':
        links.append(f'<span style="{GRAY}">(리치고 없음)</span>')
    links.append('<a style="color:#1a73e8" href="https://www.applyhome.co.kr">청약홈 →</a>')
    H.append(f'<div style="font-size:12px">{" · ".join(links)}</div>')
    return f'<div style="{CARD}">' + ''.join(H) + '</div>', '\n'.join(T)


FOOT = ['기준: 무주택 세대주 · 통장 2~10년 · 1인 가구 · 연소득 1~1.5억 · 서울/하남·성남·구리·남양주 · 공공분양·임대·오피스텔 제외 · 최종 자격은 입주자모집공고문 확인',
        '⚠ 집을 사면(경매 낙찰·매매) 무주택 요건이 깨져 이 알림 대부분이 해당 없게 됩니다.']


def build(today):
    """(html, text). 꺼져 있으면 ('', '')."""
    H = ['<div style="font-weight:bold;font-size:19px;border-bottom:2px solid #888888;padding-bottom:4px;margin-bottom:10px">🏗 청약 알림 (내 자격 기준)</div>']
    T = ['▶ 청약 알림']
    try:
        data = fetch(today)
    except Exception as e:
        print('청약: 오류 →', type(e).__name__, str(e)[:200]); data = None
    if data and data.get('off'):
        return '', ''
    if data is None:
        H.append(f'<div>{FAIL}</div>'); T.append(FAIL)
        return ''.join(H), '\n'.join(T)
    items, up = select(data, today)
    for it in items:
        h, t = card(it, today); H.append(h); T.append(t + '\n')
    if up:
        H.append(f'{LAB}📅 곧 청약 예정</div>'); T.append('▶ 📅 곧 청약 예정')
        for u in up:
            line = f"{md(_d(u['date']))} {u.get('name')}" + (f" · {u['address']}" if u.get('address') else '') + (f" — {u['note']}" if u.get('note') else '')
            H.append(f'<div>· {E(line)}</div>'); T.append('- ' + line)
    if not items and not up:
        H.append(f'<div>앞으로 {WINDOW}일 내 해당 청약 없음</div>'); T.append(f'앞으로 {WINDOW}일 내 해당 청약 없음')
    src = ', '.join(data.get('sources') or [])[:200]
    H.append(f'<div style="{GRAY};margin-top:8px">' + '<br>'.join(E(f) for f in FOOT)
             + (f'<br>출처: {E(src)} (Claude 웹 검색)' if src else '') + '</div>')
    T += FOOT
    return ''.join(H), '\n'.join(T)


if __name__ == '__main__':
    import sys
    day = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    h, t = build(day)
    print(t)
    open(os.path.join(CACHE if os.path.isdir(CACHE) else HERE, f'preview_{day}.html'), 'w', encoding='utf-8').write(h)
