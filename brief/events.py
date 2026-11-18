"""응모 이벤트·지역 행사 메일 (2026-11-18~ 사용자 요청).

  python events.py prize   # 매일: 지금 응모할 수 있는 무료 경품 이벤트 (새로 찾은 것 + 마감 임박)
  python events.py fest    # 매주 월요일: 앞으로 3주 전국 지역 행사·축제·박람회 (서울·경기 먼저)
  옵션 --day YYYY-MM-DD, TEST_MODE=1 이면 제목 [테스트]·발송 기록 안 남김

수집: 노트북 Claude Code CLI 웹 검색 → JSON (청약 알림과 같은 방식, claude_summary.cli_json).
같은 날 다시 실행하면 events_cache/<날짜>_<종류>.json 을 다시 씀 (검색 생략).
본 이벤트 기록: events_seen.json (링크 → 처음 본 날·마감일). 한 번 보낸 이벤트는 '새 이벤트'에 다시 안 나오고,
마감 3일 안이면 '마감 임박'에 한 번 더 나온다.
"""
import argparse, datetime as dt, html, json, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, 'events_cache')
SEEN = os.path.join(HERE, 'events_seen.json')
SENT = os.path.join(HERE, 'sent')
KST = dt.timezone(dt.timedelta(hours=9))
E = html.escape
WD = '월화수목금토일'
GRAY = 'color:#777;font-size:12px'
CARD = 'border:1px solid #888888;border-radius:10px;padding:10px 14px;margin-bottom:10px;line-height:1.6'
LAB = '<div style="font-weight:bold;font-size:16px;margin:16px 0 8px">'
TO = os.environ.get('BRIEF_TO', 'wpaud16@naver.com')
TEST = os.environ.get('TEST_MODE', '1') == '1'
FEST_DAYS = 21
SOON = 3

PRIZE_PROMPT = """오늘은 {today} (한국시간)입니다. 웹 검색으로 '지금 한국에서 누구나 무료로 응모할 수 있는 경품 이벤트'를 최대한 많이 찾아 사실만 JSON 으로 정리하세요.

[포함] 마감일이 {today} 이후인 것만. 예:
- 대기업·브랜드 공식 이벤트 (예: 삼성·LG·현대차·SK·KT·롯데·신세계·CJ·농심·오뚜기 등 — 우승 기념·신제품·창립 기념 경품)
- 회원가입·앱 설치·출석·퀴즈·설문·댓글·SNS 팔로우만 하면 응모되는 이벤트 (은행·증권·카드·통신사 앱, 편의점·배달앱·쇼핑몰)
- 정부·공공기관·지자체 SNS 퀴즈/설문/정책 홍보 이벤트, 방송사·언론사 시청자 이벤트, 스포츠 구단 이벤트
[제외] 구매·결제·충전·카드 발급·대출·계좌 개설 금액 조건이 '필수'인 것, 유료 참가, 도박·코인, 블로그 체험단(리뷰 작성 의무), 공모전(작품 제출), 마감 지난 것.
  (계좌 개설·카드 발급이 필요하면 제외. 단순 회원가입·앱 설치는 포함)
[찾는 법] 검색어 예: "경품 이벤트 {m}월", "응모 이벤트 진행중", "우승 기념 이벤트 응모", "퀴즈 이벤트 {m}월 공공기관", "회원가입 이벤트 경품", "앱 출석 이벤트 경품 {m}월", "이벤트 모음 {m}월".
  모음 글·커뮤니티에서 찾았더라도 url 은 반드시 주최사의 공식 이벤트 페이지(응모 페이지)를 WebFetch 로 열어 확인한 주소로 쓰세요. 공식 페이지가 SNS 게시물이면 그 게시물 주소.
  공식 페이지에서 마감일을 확인하지 못하면 deadline 을 null 로.
목표 20~40개. 반드시 아래 JSON 하나만 출력 (설명·코드블록 없이). 모르는 값은 null, 날짜는 YYYY-MM-DD.
{{"items": [{{"title": "이벤트 이름", "org": "주최", "prize": "주요 경품 (예: 갤럭시 S26 3명, 커피 쿠폰 1000명)", "how": "응모 방법 한 줄 (예: 앱 로그인 후 퀴즈 정답 입력)",
   "condition": "회원가입·앱 설치 등 필요한 것 또는 null", "entry": "form|login|app|sns", "start": "", "deadline": "", "announce": "당첨 발표일 또는 null",
   "winners": 0, "kind": "기업|금융|유통·쇼핑|공공기관|방송·언론|스포츠|기타", "url": "공식 응모 페이지", "checked": true}}],
 "sources": ["참고한 사이트 이름"]}}
checked 는 공식 페이지를 직접 열어 확인했으면 true.
entry: form = 로그인 없이 웹 양식에 이름·연락처·답만 적어 내면 끝 / login = 사이트 로그인·회원가입 필요 / app = 앱 설치·앱 안에서 / sns = SNS 팔로우·댓글·공유 필요."""

FEST_PROMPT = """오늘은 {today} (한국시간)입니다. 웹 검색으로 {today} ~ {end} 사이에 열리는 한국 지역 행사(축제·박람회·페어·마켓·불꽃놀이·빛축제·전시형 행사·공연형 지역 행사)를 찾아 사실만 JSON 으로 정리하세요.

[지역] 서울(특히 광화문·시청·잠실·성수·여의도·코엑스·DDP·세텍·aT센터 등)과 경기·인천을 가장 많이, 그 외 전국 시·도는 대표 행사 위주.
[포함] 베이커리·커피·디저트·푸드·와인·맥주 페어, 리빙·캠핑·펫·웨딩·육아·여행 박람회, 지역 축제, 크리스마스 마켓·빛축제, 플리마켓, 지자체 문화행사.
[제외] 일반 미술관 상설전, 공연 티켓(콘서트·뮤지컬), 기업 내부·B2B 전용 전시(일반인 입장 불가), 이미 끝난 것.
[찾는 법] 검색어 예: "{m}월 서울 축제", "{m}월 박람회 일정 코엑스", "킨텍스 전시 일정 {m}월", "세텍 전시 일정", "aT센터 박람회 {m}월", "{m}월 경기도 축제", "{m}월 전국 축제", "크리스마스 마켓 {y}", "빛축제 {y}", "베이커리 페어 {y}", "커피 엑스포 {y}".
  가능하면 공식 사이트·주최 페이지·대한민국 구석구석(korean.visitkorea.or.kr)·전시장 일정 페이지를 WebFetch 로 열어 날짜·장소·입장료를 확인하세요.
목표 30~50개. 반드시 아래 JSON 하나만 출력 (설명·코드블록 없이). 모르는 값은 null, 날짜는 YYYY-MM-DD.
{{"items": [{{"name": "행사명", "sido": "서울|경기|인천|부산|대구|광주|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주", "city": "시·구",
   "place": "장소 (예: 코엑스 B홀, 광화문광장)", "start": "", "end": "", "hours": "운영 시간 한 줄 또는 null",
   "fee": "입장료 (예: 무료, 사전등록 무료·현장 1만원, 성인 5,000원)", "kind": "축제|박람회·페어|마켓|빛축제·불꽃|기타",
   "desc": "무엇을 하는지 한 줄 (35자 이내)", "url": "공식 페이지 (주최 홈페이지·지자체 공지·전시장의 그 행사 상세 페이지 — 뉴스 기사·블로그·축제 모음 사이트·전시장 전체 일정 목록 금지, 없으면 null)", "checked": true}}],
 "sources": ["참고한 사이트 이름"]}}
checked 는 날짜·장소를 공식/안내 페이지에서 직접 확인했으면 true."""


# ---------------- 행사 링크: 기사·모음 사이트 말고 공식(주최·지자체·전시장 행사) 페이지로 (2026-11-18 사용자 요청) ----------------
NEWS_RX = re.compile(r'articleView|/news/|/article/|news\.|\.news|newsis|yna\.co\.kr|yonhap|chosun|joongang|donga|hani\.co|khan\.co|'
                     r'mk\.co\.kr|hankyung|fnnews|edaily|mt\.co\.kr|asiae|heraldcorp|sedaily|kmib|segye|munhwa|nocutnews|ohmynews|'
                     r'newspim|etoday|ytn|kbs\.co|mbc\.co|sbs\.co|jtbc|tvchosun|channela|mbn|sisunnews|specialtimes|enewstoday|'
                     r'sukbakmagazine|koreancenter|wikitree|insight\.co|dispatch', re.I)
AGG_RX = re.compile(r'tourpia|chukjemoa|petfairschedule|onpublic|xn--|festivallife|eventmoa|blog\.|tistory|brunch|post\.naver|'
                    r'cafe\.|instagram\.com|facebook\.com|youtube\.com|namu\.wiki|wikipedia|search\.naver|google\.com/search|'
                    r'interpark|ticketlink|yes24|melon|nol\.', re.I)
# 전시장·포털의 '전체 일정' 목록 페이지 (행사 하나의 페이지가 아님)
LIST_RX = re.compile(r'coex\.co\.kr/event/full-schedules|kintex\.com/web/ko/event/list|setec\.or\.kr/.*list|atcenter.*list|'
                     r'/festival/\d{4}-\d{2}|/IC010501$|bsevents/?$', re.I)


def link_kind(url):
    """'official' = 주최·지자체·전시장의 그 행사 페이지 / 'list' = 전시장 전체 일정 목록 / 'bad' = 기사·블로그·모음 사이트·없음."""
    u = (url or '').strip()
    if not re.match(r'https?://', u):
        return 'bad'
    host = re.sub(r'^https?://([^/]+).*$', r'\1', u).lower()
    if host.endswith('.go.kr') or host.endswith('.korea.kr'):   # 정부·지자체 (news.seoul.go.kr 같은 지자체 소식도 공식)
        return 'list' if LIST_RX.search(u) else 'official'
    if NEWS_RX.search(u) or AGG_RX.search(u):
        return 'bad'
    if LIST_RX.search(u):
        return 'list'
    return 'official'


FIX_PROMPT = """아래 한국 행사들의 '공식 안내 페이지' 주소를 웹 검색으로 찾아 주세요. 오늘은 {today}.
공식 = 주최측 홈페이지의 그 행사 페이지, 지자체(시·군·구청, ○○문화재단 등) 공지·축제 페이지, 전시장(코엑스·킨텍스·세텍·aT센터·벡스코 등)의 그 행사 상세 페이지, 대한민국 구석구석(korean.visitkorea.or.kr)의 그 행사 상세 페이지.
금지 = 뉴스 기사, 블로그·카페·SNS, 축제 모음 사이트(tourpia·chukjemoa 등), 전시장 '전체 일정' 목록 페이지, 예매 사이트.
찾은 주소는 반드시 WebFetch 로 열어 행사 이름·날짜가 맞는지 확인하고, 확인 못 하면 null.
반드시 아래 JSON 하나만 출력 (설명·코드블록 없이):
{{"links": [{{"name": "행사명(아래 목록과 똑같이)", "url": "공식 주소 또는 null", "source": "주최|지자체|전시장|구석구석"}}]}}

행사 목록 (이름 | 장소 | 날짜 | 지금 링크):
{rows}"""


def fix_fest_links(data, today):
    """기사·모음·목록 링크인 행사만 모아 Claude CLI 로 공식 페이지를 다시 찾는다. 못 찾으면 url 비움(웹·메일에 '공식 페이지 못 찾음' + 검색 링크)."""
    items = [it for it in data.get('items') or [] if isinstance(it, dict) and it.get('name')]
    need = [it for it in items if link_kind(it.get('url')) != 'official']
    print(f'행사 링크: 공식 {len(items) - len(need)} / 다시 찾기 {len(need)}')
    if not need:
        return data
    sys.path.insert(0, HERE)
    import claude_summary
    found = {}
    for k in range(0, len(need), 25):   # 한 번에 25개씩
        chunk = need[k:k + 25]
        rows = '\n'.join(f"- {it['name']} | {it.get('place') or ''} | {it.get('start')}~{it.get('end')} | {it.get('url') or ''}" for it in chunk)
        out = claude_summary.cli_json(FIX_PROMPT.format(today=today, rows=rows), timeout=int(os.environ.get('EVENTS_TIMEOUT', '1500')), tag='행사 링크 cli')
        for l in (out or {}).get('links') or []:
            if isinstance(l, dict) and l.get('name') and link_kind(l.get('url')) == 'official':
                found[re.sub(r'\s+', '', l['name'])] = l
    n = 0
    for it in need:
        l = found.get(re.sub(r'\s+', '', it['name']))
        if l and alive(l['url']):
            it['url_was'] = it.get('url'); it['url'] = l['url']; it['url_src'] = l.get('source'); n += 1
        else:
            it['url_was'] = it.get('url'); it['url'] = None   # 기사·모음 링크는 쓰지 않음
    print(f'행사 링크: 공식으로 바꿈 {n} / 못 찾음 {len(need) - n}')
    data['links_fixed'] = today.isoformat()
    return data


def official_search(name):
    """공식 페이지를 못 찾은 행사: 네이버 검색 링크 (행사명 + 공식)."""
    import urllib.parse
    return 'https://search.naver.com/search.naver?query=' + urllib.parse.quote(f'{name} 공식')


def now_day():
    return dt.datetime.now(KST).date()


def _d(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def md(d):
    return f'{d.month}/{d.day}({WD[d.weekday()]})'


def fetch(kind, today, search=True):
    """오늘 캐시가 있으면 그대로, 없으면 CLI 웹 검색(search=False 면 None). 실패 None."""
    p = os.path.join(CACHE, f'{today}_{kind}.json')
    if os.path.exists(p):
        return json.load(open(p, encoding='utf-8'))
    if not search:
        print(f'{kind}: 오늘 검색 결과 없음 (05:00 검색 실패?)'); return None
    sys.path.insert(0, HERE)
    import claude_summary
    prompt = (PRIZE_PROMPT if kind == 'prize' else FEST_PROMPT).format(
        today=today, end=today + dt.timedelta(days=FEST_DAYS), m=today.month, y=today.year)
    out = claude_summary.cli_json(prompt, timeout=int(os.environ.get('EVENTS_TIMEOUT', '1500')), tag=f'{kind} cli')
    if out is None or not isinstance(out.get('items'), list):
        return None
    if kind == 'fest':
        try:
            out = fix_fest_links(out, today)
        except Exception as e:
            print('행사 링크 고치기 실패(원래 링크 유지):', type(e).__name__, e)
    os.makedirs(CACHE, exist_ok=True)
    json.dump(out, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return out


def alive(url):
    """링크가 확실히 죽었으면(404·410·주소 없음) False. 막힘(403)·시간 초과는 살아 있다고 본다."""
    if not re.match(r'https?://', url or ''):
        return False
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130 Safari/537.36'})
        urllib.request.urlopen(req, timeout=15).close()
        return True
    except urllib.error.HTTPError as e:
        return e.code not in (404, 410)
    except urllib.error.URLError as e:
        return 'getaddrinfo' not in str(e.reason) and 'Name or service' not in str(e.reason)
    except Exception:
        return True


ENTRY = {'form': '⚡ 바로 응모', 'web': '🌐 웹에서 응모', 'login': '🔑 로그인 필요', 'app': '📱 앱 필요', 'sns': '💬 SNS 필요'}


def entry_type(it):
    """응모 난이도 (2026-11-18): 검색이 준 entry 값 우선, 없으면 링크·조건 글로 추정."""
    e = (it.get('entry') or '').strip().lower()
    if e in ENTRY:
        return e
    url = (it.get('url') or '').lower()
    txt = ' '.join(str(it.get(k) or '') for k in ('condition', 'how'))
    if re.search(r'앱\s*(설치|다운|가입|로그인|에서|회원)|어플', txt):
        return 'app'
    if re.search(r'instagram\.com|facebook\.com|youtube\.com|blog\.naver\.com|x\.com|twitter\.com|tiktok', url) or re.search(r'팔로우|구독|댓글|좋아요|리그램|인스타|유튜브|SNS', txt):
        return 'sns'
    if re.search(r'로그인|회원가입|회원\b|회원 ?전용|가입', txt):
        return 'login'
    if re.search(r'forms\.gle|docs\.google\.com/forms|naver\.me|form\.naver|surveymonkey|tally\.so|typeform', url):
        return 'form'
    return 'web'   # 로그인·앱·SNS 조건이 안 적혀 있음 (들어가 봐야 앎)


def key_of(it):
    u = re.sub(r'[?#].*$', '', (it.get('url') or '').strip().rstrip('/'))
    return u or re.sub(r'\s+', '', (it.get('title') or it.get('name') or ''))


# ---------------- 응모 이벤트 ----------------
def prize_select(data, today, seen):
    new, soon = [], []
    for it in data.get('items') or []:
        if not isinstance(it, dict) or not it.get('title') or not it.get('url'):
            continue
        dl = _d(it.get('deadline'))
        if dl and dl < today:
            continue
        st = _d(it.get('start'))
        if st and st > today + dt.timedelta(days=7):
            continue
        k = key_of(it)
        if any(x['_k'] == k for x in new + soon):   # 같은 검색에 같은 이벤트가 두 번 나온 경우
            continue
        if k in seen:
            if dl and (dl - today).days <= SOON and not seen[k].get('soon_sent'):
                soon.append(dict(it, _k=k, _dl=dl))
            continue
        new.append(dict(it, _k=k, _dl=dl))
    # 이전에 본 이벤트도 마감 임박이면 (이번 검색에 안 나왔어도) 다시 알림
    found = {x['_k'] for x in new + soon}
    for k, s in seen.items():
        dl = _d(s.get('deadline'))
        if k not in found and dl and 0 <= (dl - today).days <= SOON and not s.get('soon_sent') and s.get('item'):
            soon.append(dict(s['item'], _k=k, _dl=dl))
    new = [x for x in new if alive(x['url'])]
    far = dt.date(9999, 1, 1)
    new.sort(key=lambda x: (x['_dl'] or far))
    soon.sort(key=lambda x: x['_dl'])
    return new, soon


def dday(d, today):
    if not d:
        return '마감일 확인 필요'
    n = (d - today).days
    return f'{md(d)} 마감 · ' + ('오늘 마감' if n == 0 else f'D-{n}')


def prize_card(it, today):
    a = f'<a style="color:#1a73e8" href="{E(it["url"])}">응모하러 가기 →</a>'
    lines = [f'<div><b style="font-size:15px">{E(it["title"])}</b><span style="{GRAY}"> · {E(it.get("org") or "")} · {E(ENTRY[entry_type(it)])}</span></div>']
    t = [f'■ {it["title"]} ({it.get("org") or ""}) {ENTRY[entry_type(it)]}']
    if it.get('prize'):
        w = f' (총 {it["winners"]:,}명)' if isinstance(it.get('winners'), int) and it['winners'] > 0 else ''
        lines.append(f'<div>🎁 {E(it["prize"])}{E(w)}</div>'); t.append(f'🎁 {it["prize"]}{w}')
    if it.get('how'):
        lines.append(f'<div>✍️ {E(it["how"])}</div>'); t.append(f'✍️ {it["how"]}')
    if it.get('condition'):
        lines.append(f'<div style="{GRAY}">필요: {E(it["condition"])}</div>'); t.append(f'필요: {it["condition"]}')
    ann = f' · 발표 {md(_d(it["announce"]))}' if _d(it.get('announce')) else ''
    chk = '' if it.get('checked') else ' · ⚠ 공식 페이지 미확인'
    lines.append(f'<div>⏰ {E(dday(it["_dl"], today))}{E(ann)}<span style="{GRAY}">{E(chk)}</span> · {a}</div>')
    t.append(f'⏰ {dday(it["_dl"], today)}{ann}{chk}\n{it["url"]}')
    return f'<div style="{CARD}">' + ''.join(lines) + '</div>', '\n'.join(t)


def build_prize(today, search=True):
    seen = json.load(open(SEEN, encoding='utf-8')) if os.path.exists(SEEN) else {}
    data = fetch('prize', today, search)
    H = [f'<div style="font-weight:bold;font-size:19px;border-bottom:2px solid #888888;padding-bottom:4px;margin-bottom:10px">🎁 응모 이벤트 ({today.month}/{today.day})</div>']
    T = ['🎁 응모 이벤트']
    if data is None:
        msg = '이벤트 정보를 불러오지 못했습니다 (Claude 검색 실패·사용량 한도)'
        return H + [f'<div>{msg}</div>'], T + [msg], None, seen
    new, soon = prize_select(data, today, seen)
    if soon:
        H.append(f'{LAB}⏰ 마감 임박 ({SOON}일 안)</div>'); T.append(f'\n▶ 마감 임박 ({SOON}일 안)')
        for it in soon:
            h, t = prize_card(it, today); H.append(h); T.append(t)
    H.append(f'{LAB}🆕 새로 찾은 이벤트 {len(new)}개</div>'); T.append(f'\n▶ 새로 찾은 이벤트 {len(new)}개')
    if not new:
        H.append('<div>오늘 새로 찾은 이벤트가 없습니다</div>'); T.append('오늘 새로 찾은 이벤트가 없습니다')
    for it in new:
        h, t = prize_card(it, today); H.append(h); T.append(t)
    src = ', '.join(data.get('sources') or [])[:200]
    foot = ('무료 응모만 모음 (구매·결제·카드 발급·계좌 개설 필수 이벤트 제외) · 한 번 보낸 이벤트는 마감 3일 전에 한 번 더 알림 · '
            '응모 전에 공식 페이지의 유의사항·개인정보 제공 범위를 확인하세요 · 경품 제세공과금(5만원 초과 경품 22%)은 당첨자 부담인 경우가 많음')
    H.append(f'<div style="{GRAY};margin-top:8px">{E(foot)}' + (f'<br>출처: {E(src)} (Claude 웹 검색)' if src else '') + '</div>')
    T.append(foot)
    return H, T, (new, soon), seen


def save_seen(seen, picked, today):
    new, soon = picked
    for it in new:
        seen[it['_k']] = dict(first=today.isoformat(), deadline=it.get('deadline'),
                              item={k: v for k, v in it.items() if not k.startswith('_')})
        if it['_dl'] and (it['_dl'] - today).days <= SOON:   # 처음 보낼 때 이미 마감 임박이면 다음 날 또 알리지 않음
            seen[it['_k']]['soon_sent'] = today.isoformat()
    for it in soon:
        seen.setdefault(it['_k'], dict(first=today.isoformat(), deadline=it.get('deadline'),
                                       item={k: v for k, v in it.items() if not k.startswith('_')}))['soon_sent'] = today.isoformat()
    # 마감 30일 지난 기록은 지움
    cut = today - dt.timedelta(days=30)
    seen = {k: v for k, v in seen.items() if not (_d(v.get('deadline')) and _d(v['deadline']) < cut)
            and not (not v.get('deadline') and _d(v.get('first')) and _d(v['first']) < today - dt.timedelta(days=90))}
    json.dump(seen, open(SEEN, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, sort_keys=True)


# ---------------- 지역 행사 ----------------
GROUPS = [('서울', ('서울',)), ('경기·인천', ('경기', '인천')), ('그 외 지역', None)]


def fest_select(data, today):
    end = today + dt.timedelta(days=FEST_DAYS)
    out, keys = [], set()
    for it in data.get('items') or []:
        if not isinstance(it, dict) or not it.get('name'):
            continue
        s, e = _d(it.get('start')), _d(it.get('end')) or _d(it.get('start'))
        if not s or not e or e < today or s > end:
            continue
        k = re.sub(r'\s+', '', it['name'])
        if k in keys:
            continue
        keys.add(k)
        out.append(dict(it, _s=s, _e=e))
    out.sort(key=lambda x: (max(x['_s'], today), x['_e']))
    return out


def period(s, e, today):
    p = md(s) if s == e else f'{md(s)} ~ {md(e)}'
    if s <= today <= e:
        tag = '진행 중' + (f' · {md(e)} 종료' if s != e else '')
    else:
        tag = f'D-{(s - today).days}'
    return p, tag


def weekend_of(today):
    sat = today + dt.timedelta(days=(5 - today.weekday()) % 7)
    return sat, sat + dt.timedelta(days=1)


def fest_card(it, today):
    p, tag = period(it['_s'], it['_e'], today)
    sat, sun = weekend_of(today)
    wk = ' 🔥이번 주말' if it['_s'] <= sun and it['_e'] >= sat else ''
    where = ' · '.join(x for x in [it.get('city') or '', it.get('place') or ''] if x)
    a = (f' · <a style="color:#1a73e8" href="{E(it["url"])}">공식 페이지 →</a>' if link_kind(it.get('url')) == 'official'
         else f' · <span style="{GRAY}">공식 페이지 못 찾음</span> <a style="color:#1a73e8" href="{E(official_search(it["name"]))}">검색 →</a>')
    h = [f'<div><b style="font-size:15px">{E(it["name"])}</b><span style="{GRAY}"> · {E(it.get("kind") or "")}</span>'
         f'<span style="color:#d93025;font-size:12px">{wk}</span></div>',
         f'<div>📅 {E(p)} <span style="{GRAY}">({E(tag)})</span>' + (f' · {E(it["hours"])}' if it.get('hours') else '') + '</div>',
         f'<div>📍 {E(where)}</div>' if where else '',
         f'<div>🎟 {E(it.get("fee") or "입장료 확인 필요")}{a}</div>',
         f'<div style="{GRAY}">{E(it["desc"])}' + ('' if it.get('checked') else ' · ⚠ 공식 페이지 미확인') + '</div>' if it.get('desc') else '']
    t = [f'■ {it["name"]}{wk}', f'📅 {p} ({tag})' + (f' · {it["hours"]}' if it.get('hours') else ''),
         f'📍 {where}', f'🎟 {it.get("fee") or "입장료 확인 필요"}', it.get('desc') or '',
         it['url'] if link_kind(it.get('url')) == 'official' else f'공식 페이지 못 찾음 · 검색: {official_search(it["name"])}']
    return f'<div style="{CARD}">' + ''.join(h) + '</div>', '\n'.join(x for x in t if x)


def build_fest(today, search=True):
    data = fetch('fest', today, search)
    end = today + dt.timedelta(days=FEST_DAYS)
    H = [f'<div style="font-weight:bold;font-size:19px;border-bottom:2px solid #888888;padding-bottom:4px;margin-bottom:10px">'
         f'🎪 지역 행사 ({md(today)} ~ {md(end)})</div>']
    T = [f'🎪 지역 행사 ({md(today)} ~ {md(end)})']
    if data is None:
        msg = '행사 정보를 불러오지 못했습니다 (Claude 검색 실패·사용량 한도)'
        return H + [f'<div>{msg}</div>'], T + [msg], None
    items = fest_select(data, today)
    used = set()
    for lab, sidos in GROUPS:
        g = [x for x in items if id(x) not in used and (sidos is None or (x.get('sido') or '') in sidos)]
        if not g:
            continue
        used |= {id(x) for x in g}
        H.append(f'{LAB}{E(lab)} {len(g)}개</div>'); T.append(f'\n▶ {lab} {len(g)}개')
        for it in g:
            if sidos is None:
                it = dict(it, city=' '.join(x for x in [it.get('sido') or '', it.get('city') or ''] if x))
            h, t = fest_card(it, today); H.append(h); T.append(t)
    if not items:
        H.append('<div>찾은 행사가 없습니다</div>'); T.append('찾은 행사가 없습니다')
    src = ', '.join(data.get('sources') or [])[:200]
    foot = '날짜·입장료는 바뀔 수 있으니 가기 전에 안내 페이지에서 한 번 더 확인하세요 · 🔥 = 이번 주말에 열림'
    H.append(f'<div style="{GRAY};margin-top:8px">{E(foot)}' + (f'<br>출처: {E(src)} (Claude 웹 검색)' if src else '') + '</div>')
    T.append(foot)
    return H, T, items


# ---------------- 생활 메일(코디 메일)에 넣을 섹션 ----------------
FEST_WEEKDAY = 0   # 지역 행사: 월요일 (2026-11-18 사용자 결정)


def sections(today, test=TEST):
    """생활 메일용 (html 목록, text 목록, 발송 뒤 부를 함수). 검색은 05:00 events.py search 가 미리 해 둔 캐시만 쓴다."""
    page = 'https://wpaud16.github.io/ML/events/'   # events_page.py 웹 (종류별·지역구별 보기)
    btn = (f'<p style="text-align:center;margin:4px 0 14px"><a href="{page}" style="display:inline-block;background:#1a73e8;color:#ffffff;'
           'text-decoration:none;font-weight:bold;padding:12px 20px;border-radius:10px">🎁 이벤트·🎪 행사 웹에서 보기 (종류별·지역별)</a></p>')
    after = []
    try:
        h, t, picked, seen = build_prize(today, search=False)
        if picked and not test:   # 웹페이지의 NEW 표시·지난 이벤트 유지에 쓰이므로 계속 기록
            after.append(lambda: save_seen(seen, picked, today))
    except Exception as e:
        print('응모 이벤트 섹션 오류:', type(e).__name__, e)
    # 2026-11-18 사용자 결정: 메일엔 웹 바로가기 버튼만 (이벤트·행사 목록은 웹에서)
    return [btn], [f'이벤트·행사 웹에서 보기: {page}'], lambda: [f() for f in after]


def search(today):
    """05:00: 오늘 쓸 검색 결과를 캐시에 미리 (응모 이벤트 매일, 지역 행사 월요일). 둘이 동시에."""
    import threading
    kinds = ['prize'] + (['fest'] if today.weekday() == FEST_WEEKDAY or os.environ.get('FEST_ALWAYS') == '1' else [])
    res = {}
    th = [threading.Thread(target=lambda k=k: res.update({k: fetch(k, today) is not None})) for k in kinds]
    [x.start() for x in th]; [x.join() for x in th]
    print('검색 결과:', res)
    return all(res.values())


# ---------------- 메일 ----------------
def send(subject, H, T):
    sys.path.insert(0, HERE)
    import google_api as g
    top_h = '<p style="color:#777;font-size:12px">테스트 메일입니다</p>' if TEST else ''
    body = ('<div style="font-family:-apple-system,Segoe UI,Malgun Gothic,sans-serif;max-width:600px;'
            'margin:auto;padding:8px;line-height:1.5;color:#222">' + top_h + ''.join(H) + '</div>')
    subject = ('[테스트] ' if TEST else '') + subject
    g.send_mail(TO, subject, body, '\n'.join(T))
    print('sent:', subject)
    return subject


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('kind', choices=('search', 'prize', 'fest'))
    ap.add_argument('--day')
    ap.add_argument('--preview', action='store_true', help='메일 대신 HTML 파일만 저장')
    a = ap.parse_args()
    today = _d(a.day) if a.day else now_day()
    if a.kind == 'search':
        return 0 if search(today) else 1
    mark = os.path.join(SENT, f'{today}_{a.kind}.txt')
    if not TEST and not a.preview and os.path.exists(mark):
        print('오늘 이미 보냄 → 건너뜀'); return 0
    label = f'{today.month}월 {today.day}일 ({WD[today.weekday()]})'
    if a.kind == 'prize':
        H, T, picked, seen = build_prize(today)
        n = len(picked[0]) if picked else 0
        subject = f'[응모 이벤트] {label} 새 이벤트 {n}개' + (f' · 마감 임박 {len(picked[1])}개' if picked and picked[1] else '')
    else:
        H, T, items = build_fest(today)
        subject = f'[지역 행사] {label} 앞으로 3주 {len(items or [])}개'
        picked = items
    if a.preview:
        p = os.path.join(CACHE, f'preview_{today}_{a.kind}.html')
        os.makedirs(CACHE, exist_ok=True)
        open(p, 'w', encoding='utf-8').write(''.join(H)); print('preview:', p, '|', subject); return 0
    send(subject, H, T)
    if picked is None:
        return 1   # 검색 실패 메일은 보냈지만 기록은 안 남김 → 다음 실행에서 다시 시도
    if a.kind == 'prize' and not TEST:
        save_seen(seen, picked, today)
    if not TEST:
        os.makedirs(SENT, exist_ok=True)
        open(mark, 'w', encoding='utf-8').write(subject + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
