"""응모 이벤트·지역 행사 웹페이지 (2026-11-18 사용자 요청) → <저장소>/events/index.html
https://wpaud16.github.io/ML/events/  (pages.yml 이 배포)

- 응모 이벤트: 오늘 검색 결과 + 예전에 찾은 것 중 아직 마감 안 된 것, 경품 종류(커피·먹거리·상품권·전자기기…)별 칩으로 거르기
- 지역 행사: 가장 최근 검색(월요일) 중 아직 안 끝난 것, 시·도 → 시·군·구별로 묶기, '이번 주말' 거르기
데이터: brief/events_cache/<날짜>_prize.json · <날짜>_fest.json, brief/events_seen.json (events.py 가 만든다)
"""
import datetime as dt, glob, html, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(REPO, 'events', 'index.html')
URL = 'https://wpaud16.github.io/ML/events/'
sys.path.insert(0, HERE)
import events as ev

E = html.escape
WD = '월화수목금토일'

# 경품 종류: (키, 표시, 정규식) — 하나의 이벤트가 여러 종류에 들어갈 수 있다. 위에서부터 대표 종류.
CATS = [
    ('tech', '📱 전자기기', r'갤럭시|아이폰|아이패드|패드|노트북|태블릿|\bTV\b|티비|모니터|이어폰|헤드폰|버즈|에어팟|워치|스탠바이미|스타일러|가전|청소기|냉장고|세탁기|건조기|에어컨|카메라|폴드|플립|이북|전자책|게임기|닌텐도|플레이스테이션|로봇|스피커|공기청정기|드라이기|안마'),
    ('travel', '✈️ 여행·티켓', r'여행|숙박|호텔|리조트|항공|비행기|입장권|관람권|티켓|공연|콘서트|체험|캠핑|시승|크루즈|패키지|영화'),
    ('coffee', '☕ 커피·음료', r'커피|아메리카노|라떼|스타벅스|투썸|메가\s*(MGC)?\s*커피|메가커피|컴포즈|이디야|빽다방|폴바셋|할리스|음료|버블티|공차|카페'),
    ('food', '🍗 먹거리·편의점', r'치킨|피자|버거|배달의민족|배민|요기요|쿠팡이츠|케이크|아이스크림|배스킨|베라|젤라또|편의점|\bCU\b|GS25|세븐일레븐|이마트24|뚜레쥬르|파리바게뜨|bhc|BHC|BBQ|교촌|굽네|도넛|떡볶이|식사|외식|뿌링클|한우|과일|라면|햄버거|던킨|식품|밀키트'),
    ('voucher', '🎫 상품권·포인트', r'상품권|포인트|네이버\s*페이|N\s*pay|페이\b|해피콘|기프트\s*카드|기프티카드|현금|캐시|머니|적립금|마일리지|교환권|쿠폰|멤버십|문화상품권|컬처랜드|모바일\s*금액권|금액권'),
    ('beauty', '💄 뷰티·패션', r'화장품|올리브영|뷰티|향수|의류|옷|신발|운동화|패션|가방|지갑|시계|쥬얼리|주얼리|선글라스|립|스킨케어|무신사'),
    ('goods', '🧴 생활·물품', r'굿즈|텀블러|머그|머그컵|담요|키트|용품|우산|쿠션|인형|수건|타월|키링|다이어리|캘린더|달력|도서|책\s*\d|문구|생활용품|물품|식기|침구|선물\s*세트|에코백'),
]
CAT_LABEL = dict((k, l) for k, l, _ in CATS)
CAT_LABEL['etc'] = '🎁 기타'


def cats_of(it):
    """경품 글로 분류, 경품 글이 없거나 안 맞으면 이벤트 제목으로 (제목의 회사 이름 '삼성전자' 등에 끌려가지 않게)."""
    for t in (it.get('prize') or '', it.get('title') or ''):
        got = [k for k, _, rx in CATS if t and re.search(rx, t, re.I)]
        if got:
            return got
    return ['etc']


def latest_cache(kind, today):
    fs = sorted(f for f in glob.glob(os.path.join(ev.CACHE, f'????-??-??_{kind}.json'))
                if os.path.basename(f)[:10] <= today.isoformat())
    if not fs:
        return None, None
    f = fs[-1]
    return json.load(open(f, encoding='utf-8')), dt.date.fromisoformat(os.path.basename(f)[:10])


# ---------------- 응모 이벤트 ----------------
def prize_items(today):
    """지금 응모 가능한 이벤트 전부: 오늘(또는 최근) 검색 결과 + 보낸 기록(seen) 중 마감 안 지난 것."""
    seen = json.load(open(ev.SEEN, encoding='utf-8')) if os.path.exists(ev.SEEN) else {}
    data, day = latest_cache('prize', today)
    out = {}
    for it in (data or {}).get('items') or []:
        if isinstance(it, dict) and it.get('title') and re.match(r'https?://', it.get('url') or ''):
            k = ev.key_of(it)
            first = (seen.get(k) or {}).get('first') or (day.isoformat() if day else today.isoformat())
            out.setdefault(k, dict(it, _first=first))
    for k, s in seen.items():
        if k not in out and s.get('item'):
            out[k] = dict(s['item'], _first=s.get('first'))
    res = []
    for k, it in out.items():
        dl = ev._d(it.get('deadline'))
        st = ev._d(it.get('start'))
        first = ev._d(it.get('_first')) or today
        if dl and dl < today:
            continue
        if not dl and (today - first).days > 21:   # 마감일 모르는 건 3주까지만
            continue
        if st and st > today + dt.timedelta(days=7):
            continue
        res.append(dict(it, _dl=dl, _new=(today - first).days <= 0, _cats=cats_of(it)))
    far = dt.date(9999, 1, 1)
    res.sort(key=lambda x: (x['_dl'] or far, x.get('title') or ''))
    return res, day


def prize_card(it, today):
    dl = it['_dl']
    if dl:
        n = (dl - today).days
        dd = '오늘 마감' if n == 0 else f'D-{n}'
        due = f'{ev.md(dl)} 마감 · <b class="{"hot" if n <= 3 else ""}">{dd}</b>'
    else:
        n, due = 999, '<span class="g">마감일 확인 필요</span>'
    et = ev.entry_type(it)
    badges = f'<span class="ent ent-{et}">{E(ev.ENTRY[et])}</span>' + ''.join(f'<span class="cat">{E(CAT_LABEL[c])}</span>' for c in it['_cats'][:2])
    if it['_new']:
        badges = '<span class="new">NEW</span>' + badges
    w = f' · 총 {it["winners"]:,}명' if isinstance(it.get('winners'), int) and it['winners'] > 0 else ''
    rows = [f'<div class="top">{badges}</div>',
            f'<div class="t">{E(it["title"])}</div>',
            f'<div class="g s">{E(it.get("org") or "")}</div>']
    if it.get('prize'):
        rows.append(f'<div>🎁 {E(it["prize"])}{E(w)}</div>')
    if it.get('how'):
        rows.append(f'<div>✍️ {E(it["how"])}</div>')
    if it.get('condition'):
        rows.append(f'<div class="g s">필요: {E(it["condition"])}</div>')
    ann = f' · 발표 {ev.md(ev._d(it["announce"]))}' if ev._d(it.get('announce')) else ''
    rows.append(f'<div>⏰ {due}{E(ann)}' + ('' if it.get('checked') else ' <span class="g s">· ⚠ 공식 페이지 미확인</span>') + '</div>')
    rows.append(f'<a class="btn" href="{E(it["url"])}" target="_blank" rel="noopener">응모하러 가기 →</a>')
    return (f'<div class="card" data-entry="{et}" data-cats="{" ".join(it["_cats"])}" data-soon="{1 if n <= 3 else 0}" data-new="{1 if it["_new"] else 0}">'
            + ''.join(rows) + '</div>')


# ---------------- 지역 행사 ----------------
SIDO_ORDER = ['서울', '경기', '인천', '부산', '대구', '광주', '대전', '울산', '세종', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']
SIDO_FIX = {'서울특별시': '서울', '경기도': '경기', '인천광역시': '인천', '부산광역시': '부산', '대구광역시': '대구', '광주광역시': '광주',
            '대전광역시': '대전', '울산광역시': '울산', '세종특별자치시': '세종', '강원특별자치도': '강원', '강원도': '강원', '충청북도': '충북',
            '충청남도': '충남', '전북특별자치도': '전북', '전라북도': '전북', '전라남도': '전남', '경상북도': '경북', '경상남도': '경남', '제주특별자치도': '제주'}
# 장소로 구를 알 수 있는 곳 (검색 결과에 구가 빠진 경우)
PLACE_GU = [(r'코엑스|COEX|세텍|SETEC', '강남구'), (r'aT\s*센터|양재', '서초구'),(r'광화문|시청|서울광장|청계', '종로구·중구'),
            (r'잠실|롯데월드|올림픽공원', '송파구'), (r'DDP|동대문디자인플라자', '중구'), (r'여의도|더현대', '영등포구'),
            (r'성수', '성동구'), (r'상암|월드컵공원|하늘공원|노을공원', '마포구'), (r'남산', '중구·용산구'), (r'킨텍스|KINTEX|일산', '고양시'),
            (r'수원메쎄|수원', '수원시')]


def norm_sido(s):
    s = (s or '').strip()
    return SIDO_FIX.get(s, s[:2] if s[:2] in SIDO_ORDER else (s or '기타'))


def norm_gu(it):
    c = (it.get('city') or '').strip()
    c = re.sub(r'^(서울|경기|인천|부산|대구|광주|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주)\S*\s*', '', c)
    c = c.split()[0] if c else ''
    if c and c not in ('일대', '일원', '전역', '곳곳'):
        return c
    place = it.get('place') or ''
    for rx, gu in PLACE_GU:
        if re.search(rx, place, re.I):
            return gu
    return '기타'


# ---------------- 행사 장소 좌표 (지도용, 2026-11-18) ----------------
GEO = os.path.join(HERE, 'events_geo.json')   # 장소 → 좌표 캐시 (카카오 로컬 검색, 키 없으면 캐시만)
SIDO_FULL = {'서울': '서울특별시', '경기': '경기도', '인천': '인천광역시', '부산': '부산광역시', '대구': '대구광역시', '광주': '광주광역시',
             '대전': '대전광역시', '울산': '울산광역시', '세종': '세종특별자치시', '강원': '강원특별자치도', '충북': '충청북도', '충남': '충청남도',
             '전북': '전북특별자치도', '전남': '전라남도', '경북': '경상북도', '경남': '경상남도', '제주': '제주특별자치도'}


def _kakao_key():
    k = os.environ.get('KAKAO_REST_KEY', '').strip()
    if not k:   # 직접 실행할 때: 저장소 밖 .env 에서 (값은 출력하지 않음)
        p = os.path.join(os.path.dirname(REPO), '.env')
        if os.path.exists(p):
            for raw in open(p, encoding='utf-8-sig'):
                if raw.strip().startswith('KAKAO_REST_KEY='):
                    k = raw.split('=', 1)[1].strip().strip('"\'')
    return k


def _kakao(query):
    import urllib.request, urllib.parse
    key = _kakao_key()
    if not key:
        return None
    url = 'https://dapi.kakao.com/v2/local/search/keyword.json?' + urllib.parse.urlencode(dict(query=query, size=1))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'Authorization': 'KakaoAK ' + key}), timeout=15) as r:
            docs = json.load(r).get('documents') or []
    except Exception as e:
        print('kakao 오류', type(e).__name__); return None
    if not docs:
        return None
    d = docs[0]
    return dict(lat=float(d['y']), lng=float(d['x']), addr=d.get('road_address_name') or d.get('address_name'), hit=d.get('place_name'))


def geocode(items):
    """행사마다 _lat/_lng 붙임. 장소 이름으로 찾고, 못 찾으면 시·군·구 중심으로 (exact=False)."""
    cache = json.load(open(GEO, encoding='utf-8')) if os.path.exists(GEO) else {}
    changed, have_key = False, bool(_kakao_key())
    for it in items:
        sido = SIDO_FULL.get(it['_sido'], it['_sido'])
        place = re.sub(r'\(.*?\)|일대|일원|곳곳|추정|출발', ' ', it.get('place') or '')
        place = re.split(r'[·,/]|\s등\s|\s외\s', place)[0]
        # 전시장 안 위치(홀·층·로비·호) 는 지우기: '킨텍스 7~10홀' → '킨텍스'
        place = re.sub(r'제?\d+\s*전시장|\d+[A-Z]?(\s*[~\-]\s*\d+[A-Z]?)?\s*홀|[A-Z]\s*홀|\d+층.*|로비|동문|서문|컨퍼런스룸.*|\d+호', ' ', place)
        place = re.sub(r'\s+', ' ', place).strip()
        gu = it['_gu'] if it['_gu'] != '기타' else ''
        gu = re.split(r'[·]', gu)[0]
        words = place.split()
        shorter = [' '.join(words[:n]) for n in range(len(words) - 1, 0, -1)]   # 긴 장소명이 안 잡히면 앞 단어만
        tries = ([(f'{gu} {place}', True), (f'{sido} {place}', True), (place, True)]
                 + [(f'{gu or sido} {s}', True) for s in shorter] + [(f'{sido} {gu}', False), (sido, False)])
        short = it['_sido']
        names = {short, SIDO_FULL.get(short, short), gu[:2]} - {''}
        for q, exact in tries:
            q = re.sub(r'\s+', ' ', q).strip()
            if not q or (exact and not place):
                continue
            if q not in cache and have_key:   # 키 없으면(클라우드) 캐시에 '없음'을 남기지 않음
                cache[q] = _kakao(q); changed = True
            g = cache.get(q)
            # 엉뚱한 지역 결과 거르기 (예: '포항 불빛축제'가 인천 강화로 잡힘): 주소에 시·도 이름이나 구 이름이 있어야
            if g and short in SIDO_FULL and not any(n in (g.get('addr') or '') for n in names):
                continue
            if g and 33 < g['lat'] < 39 and 124 < g['lng'] < 132:
                it.update(_lat=g['lat'], _lng=g['lng'], _exact=exact, _addr=g.get('addr'))
                break
    if changed:
        json.dump(cache, open(GEO, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, sort_keys=True)
    return items


def fest_items(today):
    data, day = latest_cache('fest', today)
    if not data:
        return [], None
    end = today + dt.timedelta(days=ev.FEST_DAYS)
    out, keys = [], set()
    for it in data.get('items') or []:
        if not isinstance(it, dict) or not it.get('name'):
            continue
        s, e = ev._d(it.get('start')), ev._d(it.get('end')) or ev._d(it.get('start'))
        if not s or not e or e < today or s > end + dt.timedelta(days=7):
            continue
        k = re.sub(r'\s+', '', it['name'])
        if k in keys:
            continue
        keys.add(k)
        out.append(dict(it, _s=s, _e=e, _sido=norm_sido(it.get('sido')), _gu=norm_gu(it)))
    out.sort(key=lambda x: (max(x['_s'], today), x['_e']))
    return out, day


def fest_card(it, today, idx=0):
    p, tag = ev.period(it['_s'], it['_e'], today)
    sat, sun = ev.weekend_of(today)
    wk = it['_s'] <= sun and it['_e'] >= sat
    fee = it.get('fee') or '입장료 확인 필요'
    free = bool(re.search(r'무료', fee)) and not re.search(r'\d+\s*원', fee)
    badges = (f'<span class="cat">{E(it.get("kind") or "행사")}</span>'
              + ('<span class="new">이번 주말</span>' if wk else '') + ('<span class="free">무료</span>' if free else ''))
    rows = [f'<div class="top">{badges}</div>', f'<div class="t">{E(it["name"])}</div>',
            f'<div>📅 {E(p)} <span class="g s">({E(tag)})</span></div>']
    if it.get('hours'):
        rows.append(f'<div class="g s">🕒 {E(it["hours"])}</div>')
    where = ' · '.join(x for x in [it.get('city') or '', it.get('place') or ''] if x)
    if where:
        rows.append(f'<div>📍 {E(where)}</div>')
    rows.append(f'<div>🎟 {E(fee)}</div>')
    if it.get('desc'):
        rows.append(f'<div class="g s">{E(it["desc"])}' + ('' if it.get('checked') else ' · ⚠ 공식 페이지 미확인') + '</div>')
    links = []
    if ev.link_kind(it.get('url')) == 'official':
        links.append(f'<a class="btn" href="{E(it["url"])}" target="_blank" rel="noopener">공식 페이지 →</a>')
    else:   # 기사·모음 사이트 링크는 쓰지 않음 (2026-11-18 사용자 요청)
        links.append(f'<span class="g s">공식 페이지 못 찾음</span> <a class="btn" href="{E(ev.official_search(it["name"]))}" target="_blank" rel="noopener">검색 →</a>')
    if it.get('_lat'):
        links.append(f'<a class="btn" href="#map" onclick="return focusOn({idx})">🗺 지도에서 보기</a>')
    if links:
        rows.append('<div class="links">' + ' '.join(links) + '</div>')
    return (f'<div class="card" id="f{idx}" data-i="{idx}" data-sido="{E(it["_sido"])}" data-wk="{1 if wk else 0}" data-free="{1 if free else 0}">'
            + ''.join(rows) + '</div>')


# ---------------- 페이지 ----------------
CSS = """
:root{--bg:#ffffff;--fg:#1d1d1f;--mut:#777;--bd:#888;--acc:#1a73e8;--hot:#d93025;--chip:#f1f3f4}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#ececec;--mut:#9a9a9a;--bd:#666;--acc:#6fa8ff;--hot:#ff6b5e;--chip:#222}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif;font-size:14px;line-height:1.55}
.wrap{max-width:600px;margin:0 auto;padding:12px 16px 40px}
h1{font-size:19px;margin:6px 0 2px} .meta{color:var(--mut);font-size:12px;margin-bottom:10px}
.nav{position:sticky;top:0;background:var(--bg);padding:8px 0 6px;z-index:2;border-bottom:1px solid var(--bd)}
.tabs{display:flex;gap:6px}
.tab{flex:1;text-align:center;border:1px solid var(--bd);border-radius:10px;padding:8px 4px;font-size:15px;font-weight:bold;cursor:pointer;color:var(--fg);background:none;font-family:inherit}
.tab.on{background:var(--acc);border-color:var(--acc);color:#fff}
.chips{display:flex;gap:6px;overflow-x:auto;padding-top:8px;scrollbar-width:none}
.chips::-webkit-scrollbar{display:none}
.chip{flex:0 0 auto;border:1px solid var(--bd);border-radius:16px;padding:4px 11px;font-size:13px;white-space:nowrap;cursor:pointer;background:none;color:var(--fg);font-family:inherit}
.chip.on{border-color:var(--acc);color:var(--acc);font-weight:bold}
.chip i{font-style:normal;color:var(--mut);font-size:11px;margin-left:3px}
.js .pane{display:none} .js .pane.on{display:block}
.js .chips{display:none} .js .chips.on{display:flex}
h2{font-size:17px;margin:20px 0 8px;padding-bottom:4px;border-bottom:2px solid var(--bd)}
h3{font-size:14px;margin:14px 0 6px;color:var(--mut);border-left:3px solid var(--acc);padding-left:7px}
.card{border:1px solid var(--bd);border-radius:10px;padding:11px 14px;margin-bottom:10px}
.top{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:3px}
.cat,.new,.free{font-size:11px;border-radius:8px;padding:1px 7px;background:var(--chip)}
.new{background:var(--hot);color:#fff;font-weight:bold} .free{background:#1e8e3e;color:#fff}
.ent{font-size:11px;border-radius:8px;padding:1px 7px;font-weight:bold;border:1px solid var(--bd)}
.ent-form{background:#1e8e3e;color:#fff;border-color:#1e8e3e}
.t{font-weight:bold;font-size:15px}
.g{color:var(--mut)} .s{font-size:12px} .hot{color:var(--hot)}
.btn{display:inline-block;margin-top:6px;color:var(--acc);font-weight:bold;text-decoration:none}
.empty{color:var(--mut);padding:20px 0;text-align:center}
.hide{display:none!important}
.foot{color:var(--mut);font-size:12px;margin-top:20px;line-height:1.6}
#map{height:340px;border-radius:16px;margin:12px 0 6px;z-index:0;scroll-margin-top:120px;box-shadow:0 2px 10px rgba(0,0,0,.15);overflow:hidden;background:#b9dcf6}
.mapnote{color:var(--mut);font-size:11px;margin-bottom:6px}
/* 핀 (카카오맵 즐겨찾기 별 느낌): 노란 동그라미 + 흰 테두리 + 이모지, 작은 꼬리, 숫자 배지 */
.pinw{position:relative;cursor:pointer;width:38px;height:46px;display:flex;flex-direction:column;align-items:center;transition:transform .15s}
.pinw:hover{transform:translateY(-2px) scale(1.08)}
.pin{width:36px;height:36px;border-radius:50%;background:linear-gradient(160deg,#ffd45c,#ffb81c);border:3px solid #fff;
 box-shadow:0 3px 8px rgba(0,0,0,.25);display:flex;align-items:center;justify-content:center;box-sizing:border-box}
.pin span{font-size:17px;line-height:1;filter:drop-shadow(0 1px 0 rgba(255,255,255,.6))}
.pinw .tail{width:0;height:0;border-left:6px solid transparent;border-right:6px solid transparent;border-top:8px solid #fff;margin-top:-2px;filter:drop-shadow(0 2px 1px rgba(0,0,0,.15))}
.pinw .cnt{position:absolute;top:-4px;right:-6px;min-width:18px;height:18px;padding:0 5px;border-radius:9px;background:#ff5a5f;color:#fff;
 font:700 11px/18px 'Apple SD Gothic Neo','Malgun Gothic',sans-serif;font-style:normal;text-align:center;border:2px solid #fff;box-sizing:content-box}
.pinw.approx .pin{opacity:.75}
/* 팝업: 둥근 카드 */
.ppw .maplibregl-popup-content{border-radius:14px;box-shadow:0 6px 24px rgba(0,0,0,.18);padding:0;min-width:220px}
.ppw .maplibregl-popup-close-button{font-size:18px;color:#888;right:4px;top:2px}
.pp{max-height:260px;overflow:auto;padding:6px 0;font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif}
.pp-head{font-size:12px;color:#666;padding:6px 14px 4px;font-weight:bold}
.pp-note{font-size:11px;color:#888;padding:4px 14px}
.pp-item{display:block;padding:8px 14px;text-decoration:none;color:#1d1d1f!important;border-top:1px solid #f0f0f0}
.pp-item:first-of-type{border-top:0} .pp-item:hover{background:#f6f8fc}
.pp-t{font-weight:bold;font-size:13.5px;line-height:1.35;margin-bottom:2px} .pp-s{font-size:12px;color:#555;line-height:1.45}
.pp-wk{color:#f04438;font-size:11px;font-weight:bold}
.maplibregl-ctrl-group{border-radius:10px!important;box-shadow:0 2px 8px rgba(0,0,0,.2)!important;overflow:hidden}
.maplibregl-ctrl-group button{width:34px!important;height:34px!important}
.maplibregl-ctrl-attrib{font-size:9px}
.links{margin-top:6px;display:flex;gap:14px;flex-wrap:wrap} .links .btn{margin-top:0}
.card{scroll-margin-top:130px;transition:outline .2s} .card.flash{outline:3px solid var(--acc)}
"""

JS = """
document.documentElement.classList.add('js');
function $(s,r){return (r||document).querySelectorAll(s)}
function tab(t){$('.tab').forEach(b=>b.classList.toggle('on',b.dataset.t==t));$('.pane').forEach(p=>p.classList.toggle('on',p.id==t));
 $('.chips').forEach(c=>c.classList.toggle('on',c.dataset.t==t));try{localStorage.setItem('ev_tab',t)}catch(e){};history.replaceState(null,'','#'+t);
 if(t=='fest')setTimeout(()=>{initMap();if(MAP){MAP.resize();}},60)}
function pick(t,v,btn){$('.chips[data-t="'+t+'"] .chip').forEach(b=>b.classList.toggle('on',b==btn));
 $('#'+t+' .card').forEach(c=>{let ok=v=='all'||(v=='soon'&&c.dataset.soon=='1')||(v=='new'&&c.dataset.new=='1')||(v=='wk'&&c.dataset.wk=='1')||(v=='free'&&c.dataset.free=='1')
  ||(c.dataset.cats||'').split(' ').includes(v)||c.dataset.sido==v||c.dataset.entry==v;c.classList.toggle('hide',!ok)});
 $('#'+t+' .grp').forEach(g=>{g.classList.toggle('hide',!g.querySelector('.card:not(.hide)'))});
 let n=$('#'+t+' .card:not(.hide)').length;document.getElementById(t+'-empty').classList.toggle('hide',n>0);
 if(t=='fest')drawMarkers(true)}
document.addEventListener('DOMContentLoaded',()=>{let t=location.hash.slice(1);if(t!='prize'&&t!='fest'){try{t=localStorage.getItem('ev_tab')}catch(e){}}
 tab(t=='fest'?'fest':'prize')});
/* ---- 지도 (2026-11-18): MapLibre + OpenFreeMap 'liberty' 벡터 지도 (키 필요 없음, 앱 지도 느낌), 이름은 한글 우선 ---- */
let MAP=null,MK=[],GRP={},READY=false;
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function initMap(){if(MAP||!window.maplibregl||!document.getElementById('map'))return;
 MAP=new maplibregl.Map({container:'map',style:'https://tiles.openfreemap.org/styles/liberty',center:[127.8,36.3],zoom:5.6,
  attributionControl:{compact:true}});
 MAP.addControl(new maplibregl.NavigationControl({showCompass:false}),'bottom-right');
 const ready=()=>{if(READY)return;READY=true;softStyle();MAP.resize();drawMarkers(true)};
 // 'load' 를 놓치는 경우가 있어 (탭 전환 직후 등) style.load·idle·주기 확인으로도 시작
 MAP.on('load',ready);MAP.on('style.load',ready);MAP.on('idle',ready);
 const t=setInterval(()=>{if(READY)return clearInterval(t);if(MAP.isStyleLoaded())ready()},500)}
/* 카카오맵 느낌 (2026-11-18 사용자 요청): 하얀 땅·하늘색 바다·옅은 경계선, 길·건물·가게 이름은 많이 확대했을 때만, 지명은 한글 */
function softStyle(){const S=(id,k,v)=>{try{MAP.setPaintProperty(id,k,v)}catch(e){}},Lo=(id,k,v)=>{try{MAP.setLayoutProperty(id,k,v)}catch(e){}};
 MAP.getStyle().layers.forEach(l=>{const id=l.id,sl=l['source-layer']||'';
  if(l.type=='background'){S(id,'background-color','#ffffff');return}
  if(l.type=='raster'||l.type=='hillshade'||/natural_earth|relief/.test(id)){Lo(id,'visibility','none');return}   // 지형 음영 끔
  if(sl=='water'||/water|ocean|sea/.test(id)){if(l.type=='fill')S(id,'fill-color','#b9dcf6');if(l.type=='line')S(id,'line-color','#b9dcf6');return}
  if(sl=='waterway'){S(id,'line-color','#b9dcf6');return}
  if(/landcover|landuse|park|wood|grass|sand|ice|wetland|aeroway|hillshade|terrain/.test(sl+id)){Lo(id,'visibility','none');return}
  if(sl=='building'){Lo(id,'visibility','none');return}
  if(sl=='transportation'||sl=='transportation_name'||/road|highway|rail|bridge|tunnel|ferry/.test(id)){try{MAP.setLayerZoomRange(id,10,24)}catch(e){}
   if(l.type=='line')S(id,'line-color','#e9e9ec');return}
  if(sl=='boundary'){S(id,'line-color','#c8c8cc');return}
  if(sl=='poi'||sl=='aerodrome_label'||sl=='mountain_peak'||sl=='housenumber'){try{MAP.setLayerZoomRange(id,13,24)}catch(e){}}
  if(l.type=='symbol'&&l.layout&&l.layout['text-field']){
   Lo(id,'text-field',['coalesce',['get','name:ko'],['get','name']]);   // 지명: 한글 → 기본 이름
   Lo(id,'text-letter-spacing',0);Lo(id,'text-transform','none');
   S(id,'text-color',sl=='water_name'?'#5b86b0':'#4a4a4f');S(id,'text-halo-color','#ffffff');S(id,'text-halo-width',1.4)}});}
/* 귀여운 핀: 한 가지 색(노랑) 동그라미 + 행사 종류 이모지, 같은 장소 여러 개면 숫자 배지 */
function emo(kind){kind=kind||'';return /빛|불꽃/.test(kind)?'✨':/박람|페어/.test(kind)?'🛍️':/마켓/.test(kind)?'🧺':/축제/.test(kind)?'🎉':'🎈'}
function pinEl(fs,ex){const d=document.createElement('div');   // 바깥 div 는 MapLibre 가 위치(transform)를 잡으므로 꾸밈은 안쪽에만
 d.innerHTML='<div class="pinw'+(ex?'':' approx')+'"><div class="pin"><span>'+emo(fs[0].kind)+'</span></div>'+(fs.length>1?'<i class="cnt">'+fs.length+'</i>':'')+'<div class="tail"></div></div>';return d}
function drawMarkers(fit){if(!MAP||!READY)return;MK.forEach(m=>m.remove());MK=[];GRP={};const b=new maplibregl.LngLatBounds();let any=false;
 (window.FEST||[]).forEach(f=>{const c=document.getElementById('f'+f.i);if(!c||c.classList.contains('hide'))return;
  const k=f.lat.toFixed(3)+','+f.lng.toFixed(3);(GRP[k]=GRP[k]||[]).push(f)});
 Object.entries(GRP).forEach(([k,fs])=>{const [la,ln]=k.split(',').map(Number);const wk=fs.some(f=>f.wk),ex=fs.some(f=>f.exact);
  const pop=new maplibregl.Popup({offset:[0,-38],maxWidth:'290px',className:'ppw',closeButton:true}).setHTML('<div class="pp">'+(ex?'':'<div class="pp-note">정확한 장소를 못 찾아 시·군·구 중심에 표시</div>')+
   (fs.length>1?'<div class="pp-head">이 장소 행사 '+fs.length+'개</div>':'')+fs.map(f=>
   '<a class="pp-item" href="#f'+f.i+'" onclick="return toCard('+f.i+')"><div class="pp-t">'+esc(f.name)+(f.wk?' <span class="pp-wk">이번 주말</span>':'')+'</div>'+
   '<div class="pp-s">'+esc(f.period)+'</div><div class="pp-s">📍 '+esc(f.place)+'</div><div class="pp-s">🎟 '+esc(f.fee)+'</div></a>').join('')+'</div>');
  const m=new maplibregl.Marker({element:pinEl(fs,ex),anchor:'bottom'}).setLngLat([ln,la]).setPopup(pop).addTo(MAP);
  fs.forEach(f=>f._m=m);MK.push(m);b.extend([ln,la]);any=true});
 if(fit&&any)MAP.fitBounds(b,{padding:{top:50,bottom:30,left:30,right:30},maxZoom:13,duration:fit===true?0:600})}
function toCard(i){const c=document.getElementById('f'+i);if(c){c.scrollIntoView({behavior:'smooth',block:'center'});c.classList.add('flash');setTimeout(()=>c.classList.remove('flash'),1600)}return false}
function focusOn(i){const f=(window.FEST||[]).find(x=>x.i==i);if(!f||!MAP)return true;
 document.getElementById('map').scrollIntoView({behavior:'smooth',block:'center'});MK.forEach(m=>m.getPopup()&&m.getPopup().remove());
 MAP.flyTo({center:[f.lng,f.lat],zoom:14,duration:700});if(f._m)setTimeout(()=>f._m.togglePopup(),750);return false}
"""


def build(today):
    P, pday = prize_items(today)
    F, fday = fest_items(today)
    geocode(F)
    for i, x in enumerate(F):
        x['_i'] = i
    fest_js = []
    for x in F:
        if x.get('_lat'):
            p, tag = ev.period(x['_s'], x['_e'], today)
            sat, sun = ev.weekend_of(today)
            fest_js.append(dict(i=x['_i'], lat=round(x['_lat'], 5), lng=round(x['_lng'], 5), exact=x['_exact'], name=x['name'],
                                period=f'{p} ({tag})', place=' · '.join(v for v in [x.get('city') or '', x.get('place') or ''] if v),
                                fee=x.get('fee') or '입장료 확인 필요', kind=x.get('kind') or '', wk=x['_s'] <= sun and x['_e'] >= sat))
    fest_json = json.dumps(fest_js, ensure_ascii=False).replace('</', '<\\/')
    n_map = len(fest_js)
    # 응모 이벤트: 종류 칩
    cnt = {k: sum(k in x['_cats'] for x in P) for k in list(CAT_LABEL)}
    soon = sum(1 for x in P if x['_dl'] and (x['_dl'] - today).days <= 3)
    new = sum(1 for x in P if x['_new'])
    pchips = [f'<button class="chip on" onclick="pick(\'prize\',\'all\',this)">전체<i>{len(P)}</i></button>']
    if new:
        pchips.append(f'<button class="chip" onclick="pick(\'prize\',\'new\',this)">🆕 오늘 새로<i>{new}</i></button>')
    if soon:
        pchips.append(f'<button class="chip" onclick="pick(\'prize\',\'soon\',this)">⏰ 마감 임박<i>{soon}</i></button>')
    ecnt = {k: sum(ev.entry_type(x) == k for x in P) for k in ev.ENTRY}
    pchips += [f'<button class="chip" onclick="pick(\'prize\',\'{k}\',this)">{E(ev.ENTRY[k])}<i>{ecnt[k]}</i></button>'
               for k in ev.ENTRY if ecnt[k]]
    pchips += [f'<button class="chip" onclick="pick(\'prize\',\'{k}\',this)">{E(CAT_LABEL[k])}<i>{cnt[k]}</i></button>'
               for k in [c for c, _, _ in CATS] + ['etc'] if cnt[k]]
    pcards = ''.join(prize_card(x, today) for x in P) or ''
    # 지역 행사: 시·도 칩, 시·도 > 시·군·구 묶음
    sidos = [s for s in SIDO_ORDER if any(x['_sido'] == s for x in F)] + sorted({x['_sido'] for x in F} - set(SIDO_ORDER))
    wk = sum(1 for x in F if x['_s'] <= ev.weekend_of(today)[1] and x['_e'] >= ev.weekend_of(today)[0])
    fr = sum(1 for x in F if re.search(r'무료', x.get('fee') or '') and not re.search(r'\d+\s*원', x.get('fee') or ''))
    fchips = [f'<button class="chip on" onclick="pick(\'fest\',\'all\',this)">전체<i>{len(F)}</i></button>']
    if wk:
        fchips.append(f'<button class="chip" onclick="pick(\'fest\',\'wk\',this)">🔥 이번 주말<i>{wk}</i></button>')
    if fr:
        fchips.append(f'<button class="chip" onclick="pick(\'fest\',\'free\',this)">무료<i>{fr}</i></button>')
    fchips += [f'<button class="chip" onclick="pick(\'fest\',\'{E(s)}\',this)">{E(s)}<i>{sum(x["_sido"] == s for x in F)}</i></button>' for s in sidos]
    fparts = []
    for s in sidos:
        g = [x for x in F if x['_sido'] == s]
        gus = []
        for x in g:
            if x['_gu'] not in gus:
                gus.append(x['_gu'])
        gus.sort(key=lambda u: (u == '기타', u))
        inner = ''.join(f'<div class="grp"><h3>{E(u)} · {sum(x["_gu"] == u for x in g)}개</h3>'
                        + ''.join(fest_card(x, today, x['_i']) for x in g if x['_gu'] == u) + '</div>' for u in gus)
        fparts.append(f'<div class="grp"><h2>{E(s)} <span class="g s">{len(g)}개</span></h2>{inner}</div>')
    now = dt.datetime.now(ev.KST)
    meta_p = f'{pday.month}/{pday.day} 검색' if pday else '검색 결과 없음'
    meta_f = f'{fday.month}/{fday.day}(월) 검색 · 앞으로 3주' if fday else '검색 결과 없음'
    html_ = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>응모 이벤트·지역 행사</title>
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script>{JS}</script><style>{CSS}</style></head><body><div class="wrap">
<h1>🎁 응모 이벤트 · 🎪 지역 행사</h1>
<div class="meta">{now:%m/%d %H:%M} 갱신 · 이벤트 {E(meta_p)} · 행사 {E(meta_f)}</div>
<div class="nav"><div class="tabs"><button class="tab on" data-t="prize" onclick="tab('prize')">🎁 응모 이벤트 {len(P)}</button>
<button class="tab" data-t="fest" onclick="tab('fest')">🎪 지역 행사 {len(F)}</button></div>
<div class="chips on" data-t="prize">{''.join(pchips)}</div><div class="chips" data-t="fest">{''.join(fchips)}</div></div>
<div class="pane on" id="prize">{pcards}<div class="empty{'' if not P else ' hide'}" id="prize-empty">해당하는 이벤트가 없습니다</div>
<div class="foot">무료 응모만 모음 (구매·결제·카드 발급·계좌 개설 필수 이벤트 제외) · 마감 빠른 순 · NEW = 오늘 처음 찾은 이벤트<br>
응모 전에 공식 페이지의 유의사항·개인정보 제공 범위를 확인하세요 · 5만원 넘는 경품은 제세공과금(22%)을 당첨자가 내는 경우가 많아요<br>
Claude 웹 검색으로 매일 새벽 모음 · 공식 페이지에서 확인 못 한 항목은 ⚠ 표시</div></div>
<div class="pane" id="fest"><div id="map"></div>
<div class="mapnote">🎉 축제 · 🛍️ 박람회·페어 · 🧺 마켓 · ✨ 빛축제·불꽃 · 🎈 기타 · 빨간 숫자 = 같은 장소 행사 수 · 핀을 누르면 행사 목록 · 위 칩으로 거르면 지도도 같이 바뀌어요</div>
<script>window.FEST={fest_json};</script>{''.join(fparts)}<div class="empty{'' if not F else ' hide'}" id="fest-empty">해당하는 행사가 없습니다</div>
<div class="foot">시·도 → 시·군·구별 · 시작일 순 · 이미 끝난 행사는 빠짐<br>날짜·입장료는 바뀔 수 있으니 가기 전에 안내 페이지에서 한 번 더 확인하세요 · 매주 월요일 새벽 Claude 웹 검색</div></div>
</div></body></html>"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, 'w', encoding='utf-8').write(html_)
    print('events page:', OUT, '이벤트', len(P), '행사', len(F))
    return len(P), len(F)


if __name__ == '__main__':
    d = ev._d(sys.argv[1]) if len(sys.argv) > 1 else ev.now_day()
    build(d)
