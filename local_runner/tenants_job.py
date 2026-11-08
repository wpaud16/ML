"""법원경매정보(courtauction.go.kr) 임차인·현황 자료를 모아 wpaud16/ML 저장소에 올린다.

run_all.py night 의 collect 단계가 실행 (2026-11-08 저장소로 옮김, 경로는 이 파일 위치 기준). 결과: ML/auction_model/tenants/latest.json (형식은 tenants/README.md)

  python tenants_job.py                       # 전체 (tenant_targets.json)
  python tenants_job.py --limit 5 --no-upload # 시험
  python tenants_job.py --only "2026타경101140[1]@서울중앙지방법원" --no-upload

사이트 화면을 사람이 보는 순서대로 연다 (사건검색 → 문건/송달 → 매각물건명세서 → 물건상세 → 현황조사서).
매각물건명세서는 사이트가 매각기일 1주 전부터만 열어 주므로, 버튼이 비활성화돼 있으면 '공개 전'으로 남긴다.
명세서를 못 읽은 물건(base_right_date 없음)은 3일 캐시 없이 매일 다시 조회한다.
"""
import argparse, json, os, random, re, subprocess, sys, time, traceback
from datetime import date, datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # <설치 폴더>/ML
BASE = os.path.dirname(REPO)                                          # <설치 폴더> (.env·로그)
GIT = os.environ.get('GIT_EXE') or next((p for p in (
    os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Programs\PortableGit\cmd\git.exe'),
    os.path.join(BASE, 'tools', 'MinGit', 'cmd', 'git.exe'),
    os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Programs\MinGit\cmd\git.exe'),
    r'C:\Program Files\Git\cmd\git.exe') if os.path.exists(p)), 'git')
LOG = os.path.join(BASE, 'log.txt')
TARGETS = os.path.join(REPO, 'auction_model', 'predictions', 'tenant_targets.json')
OUT_REL = 'auction_model/tenants/latest.json'
README_REL = 'auction_model/tenants/README.md'
SEARCH_URL = 'https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ159M00.xml'
KST = timezone(timedelta(hours=9))
CACHE_DAYS = 3
SPEC_PENDING = '매각물건명세서 공개 전'
EVENTS_MAX = 20

# 매각물건명세서 임차인 표의 칸 시작 x (표준 서식, '보 증 금'의 '보' = 272 기준)
COLS = [('name', 36), ('part', 74), ('src', 110), ('right', 164), ('period', 200), ('deposit', 270),
        ('rent', 337), ('move_in', 382), ('fixed', 449), ('claim', 505)]
HDR_DEPOSIT_X = 272


def log(msg):
    line = f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def pause():
    time.sleep(random.uniform(1.0, 2.0))


# ---------- 값 정리 ----------
DATE_RE = re.compile(r'(\d{4})\s*[.\-년]\s*(\d{1,2})\s*[.\-월]\s*(\d{1,2})')


def ymd(s):
    m = DATE_RE.search(s or '')
    return f'{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}' if m else None


def manwon(s):
    m = re.search(r'\d[\d,]*', s or '')
    if not m: return None
    return int(round(int(m.group().replace(',', '')) / 10000))


def mask_names(text, names):
    for n in names:
        text = text.replace(n, n[0] + 'O' * (len(n) - 1))
    return text


def person_names(names):
    return sorted({n for n in names if re.fullmatch(r'[가-힣]{2,4}', n) and not re.search(r'공사|은행|조합|회사|법인|금고', n)},
                  key=len, reverse=True)


# ---------- 법원 이름 ----------
def norm_court(s):
    return re.sub(r'\s|지방법원|법원|지법|본원', '', s or '')


def resolve_court(court, options):
    if not court: return None
    if court in options: return court
    c = court.replace(' ', '')
    if c.endswith('지원'):
        branch = re.split(r'법원|지법', c)[-1]
        hit = [o for o in options if o.replace(' ', '').endswith(branch)]
        if hit: return hit[0]
    n = norm_court(c)
    hit = [o for o in options if norm_court(o) == n] or [o for o in options if n and norm_court(o).startswith(n)]
    return hit[0] if hit else None


# ---------- 화면 표 읽기 ----------
TABLES_JS = """()=>[...document.querySelectorAll('table')].filter(t=>t.offsetParent!==null).map(t=>({
  cap:((t.querySelector('caption')||{}).innerText||t.getAttribute('summary')||'').trim(), id:t.id,
  rows:[...t.querySelectorAll('tr')].map(r=>[...r.children].map(c=>c.innerText.trim()))}))"""


def tables(page):
    return page.evaluate(TABLES_JS)


def table_by_cap(tbls, head):
    for t in tbls:
        if t['cap'].startswith(head): return t
    return None


def body_rows(t):
    """머리줄 다음의 내용 행 (빈 행·'검색결과가 없습니다' 제외)."""
    if not t: return []
    return [r for r in t['rows'][1:] if any(c for c in r) and not any('검색결과가 없습니다' in c for c in r)]


# ---------- 매각물건명세서 (뷰어 텍스트 좌표) ----------
def spec_lines(texts):
    """뷰어가 받은 페이지별 텍스트 → [(page, y, [(x0, x1, word)], text)] 위→아래 순."""
    out = []
    for pi in sorted(texts):
        for ln in texts[pi]:
            t, rc = ln.get('text') or '', ln.get('rect') or []
            toks = []
            for m in re.finditer(r'\S+', t):
                a, b = m.start(), m.end() - 1
                if a < len(rc) and b < len(rc):
                    toks.append((rc[a]['left'], rc[b]['right'], m.group()))
            if toks:
                out.append((pi, rc[0]['top'], toks, t.strip()))
    out.sort(key=lambda l: (l[0], -l[1]))
    return out


def col_of(x, off):
    name = COLS[0][0]
    for n, x0 in COLS:
        if x >= x0 + off - 1: name = n
    return name


def parse_spec(texts, case_rcpt):
    L = spec_lines(texts)
    if not L: raise RuntimeError('매각물건명세서 텍스트 없음')
    idx = lambda pred, start=0: next((i for i in range(start, len(L)) if pred(L[i])), None)
    res = dict(base_right_date=None, base_right=None, dividend_deadline=None, tenants=[], remarks='', assumed_rights_text='')

    # 최선순위 설정 / 배당요구종기
    i0 = idx(lambda l: '최선순위' in l[3])
    i1 = idx(lambda l: '최저매각가격' in l[3], (i0 or 0))
    hdr = idx(lambda l: '요구여부' in l[3])
    off = 0
    if hdr is not None:
        bo = [x0 for x0, _, w in L[hdr][2] if w.startswith('보')]
        if bo: off = bo[0] - HDR_DEPOSIT_X
    if i0 is not None:
        left, right = [], []
        for l in L[i0:(i1 or i0) + 1]:
            for x0, x1, w in l[2]:
                if w in ('최선순위', '설정'): continue
                if 200 + off <= x0 < 375 + off: left.append(w)
                elif x0 >= 375 + off: right.append(w)
        s = ' '.join(left)
        m = DATE_RE.search(s)
        if m:
            res['base_right_date'] = ymd(s)
            res['base_right'] = re.sub(r'^[\s.]+', '', s[m.end():]).strip() or None
        r = ' '.join(right)
        if '배당요구종기' in r:
            res['dividend_deadline'] = ymd(r.split('배당요구종기', 1)[1])

    # 임차인 표: 머리글 끝('신청일자') ~ '<비고>'
    hs = idx(lambda l: '신청일자' in l[3], hdr or 0)
    be = idx(lambda l: l[3].startswith('<비고>'), hs or 0)
    region = L[(hs + 1) if hs is not None else 0:be if be is not None else len(L)]
    names = []
    if hs is not None and not any(re.search(r'조사된\s*임차\s*내역\s*없음', l[3]) for l in region):
        def is_main(l):
            # 한 임차인의 기준 줄 = 보증금 금액 또는 전입일이 적힌 줄 (기간·배당요구일만 있는 줄은 아님)
            for x0, x1, w in l[2]:
                c = col_of((x0 + x1) / 2, off)
                if (c == 'deposit' and (re.fullmatch(r'[\d,]{3,}', w) or '미상' in w)) or \
                   (c == 'move_in' and (DATE_RE.search(w) or '미상' in w)):
                    return True
            return False
        mains = [k for k, l in enumerate(region) if is_main(l)]
        rows = {k: [] for k in mains}
        for k, l in enumerate(region):
            if not mains: break
            near = min(mains, key=lambda m: (region[m][0] != l[0], abs(region[m][1] - l[1])))
            rows[near].append(l)
        raw = []
        for k in mains:
            cells = {c: [] for c, _ in COLS}
            for l in sorted(rows[k], key=lambda l: (l[0], -l[1])):
                for x0, x1, w in sorted(l[2]):
                    cells[col_of((x0 + x1) / 2, off)].append(w)
            j = {c: ''.join(v) if c in ('name', 'part', 'src', 'right') else ' '.join(v) for c, v in cells.items()}
            names.append(j['name'])
            claim_d = ymd(j['claim'])
            dep = None if '미상' in j['deposit'] else manwon(j['deposit'])
            rent = None if '미상' in j['rent'] else (manwon(j['rent']) or 0)
            raw.append(dict(_name=j['name'], occupant=j['right'] or j['src'] or None, move_in=ymd(j['move_in']),
                            fixed_date=ymd(j['fixed']), deposit_manwon=dep, monthly_rent_manwon=rent,
                            claimed_dividend=bool(claim_d), claim_date=claim_d, _explicit=bool(claim_d)))
        res['tenants'] = raw

    # 비고 / 인수되는 권리
    def block(start_pred, stop_pred):
        a = idx(start_pred)
        if a is None: return ''
        b = idx(stop_pred, a + 1)
        return '\n'.join(l[3] for l in L[a + 1:b if b is not None else len(L)])
    rem = block(lambda l: l[3].startswith('<비고>'), lambda l: l[3].startswith('※') or l[3].startswith('등기된 부동산에'))
    tail = block(lambda l: l[3] == '비고란', lambda l: re.match(r'^※?\s*\d\s*:', l[3]) or l[3].startswith('부동산의 표시'))
    res['remarks'] = '\n'.join(s for s in (rem, tail) if s.strip())
    res['assumed_rights_text'] = block(lambda l: l[3].startswith('등기된 부동산에'), lambda l: l[3].startswith('매각에 따라'))

    # 비고에서 배당요구를 적은 경우 (예: 신청채권자가 임차인 보증금반환채권 승계 → 경매신청일이 배당요구일)
    for t in res['tenants']:
        if t['claimed_dividend'] or not t['_name']: continue
        for sent in re.split(r'(?<=[.)])\s+|\n', res['remarks']):
            if t['_name'] not in sent and not (t['_name'][:2] and t['_name'][:2] in sent and '임차인' in sent): continue
            if '배당요구' in sent:
                d = ymd(sent.split('배당요구', 1)[1]) or ymd(sent)
                t.update(claimed_dividend=True, claim_date=d or case_rcpt)
            elif '신청채권자' in sent and case_rcpt:
                t.update(claimed_dividend=True, claim_date=case_rcpt)

    # 같은 임차인이 여러 줄(임차권등기·권리신고·현황조사)로 나온 경우 한 명으로 합침:
    # 전입일이 같고 보증금이 같거나 한쪽이 미상이면 같은 임차
    merged = []
    for t in res['tenants']:
        m = next((m for m in merged if t['move_in'] and m['move_in'] == t['move_in']
                  and (m['deposit_manwon'] is None or t['deposit_manwon'] is None or m['deposit_manwon'] == t['deposit_manwon'])), None)
        if not m:
            merged.append(t); continue
        m['claimed_dividend'] = m['claimed_dividend'] or t['claimed_dividend']
        # 명세서 표에 적힌 배당요구일을 비고에서 추정한 날짜보다 우선
        cands = [x for x in (m, t) if x['claim_date'] and x['_explicit']] or [x for x in (m, t) if x['claim_date']]
        m['claim_date'] = min((x['claim_date'] for x in cands), default=None)
        m['_explicit'] = m['_explicit'] or t['_explicit']
        m['fixed_date'] = min([d for d in (m['fixed_date'], t['fixed_date']) if d], default=None)
        for k in ('deposit_manwon', 'monthly_rent_manwon'):
            if m[k] is None or (k == 'monthly_rent_manwon' and m['deposit_manwon'] is None and t[k]): m[k] = t[k]
        if '임차' not in (m['occupant'] or '') and '임차' in (t['occupant'] or ''): m['occupant'] = t['occupant']
    keep = ('occupant', 'move_in', 'fixed_date', 'deposit_manwon', 'monthly_rent_manwon', 'claimed_dividend', 'claim_date')
    res['tenants'] = [{k: t[k] for k in keep} for t in merged]
    pn = person_names(names)
    res['remarks'] = mask_names(res['remarks'], pn)
    res['assumed_rights_text'] = mask_names(res['assumed_rights_text'], pn)
    return res, pn


# ---------- 문건/송달, 기일, 현황조사 ----------
def event_type(text, kind):
    if kind == '송달':
        return '송달불능' if re.search(r'불능|폐문|부재|불명|미거주|이사', text.split('→')[-1]) else '송달'
    for kw, ty in (('유치권', '유치권신고'), ('배당요구', '배당요구'), ('권리신고', '권리신고'), ('취하', '취하'),
                   ('연기', '연기신청'), ('변경', '변경신청'), ('정지', '정지'), ('경매개시결정', '개시결정')):
        if kw in text: return ty
    return kind


def parse_events(tbls):
    ev = []
    for r in body_rows(table_by_cap(tbls, '접수일,접수내역,결과')):
        if len(r) >= 2 and ymd(r[0]):
            text = r[1] + (f' [{r[2]}]' if len(r) > 2 and r[2] else '')
            ev.append(dict(date=ymd(r[0]), type=event_type(text, '문건'), text=text))
    for r in body_rows(table_by_cap(tbls, '송달일,송달내역,송달결과')):
        if len(r) >= 2 and ymd(r[0]):
            text = r[1] + (f' → {r[2]}' if len(r) > 2 and r[2] else '')
            ev.append(dict(date=ymd(r[0]), type=event_type(text, '송달'), text=text))
    ev.sort(key=lambda e: e['date'], reverse=True)
    return ev[:EVENTS_MAX]


def parse_schedule(tbls):
    out = []
    for r in body_rows(table_by_cap(tbls, '기일,기일종류,기일장소,최저매각가격,기일결과')):
        if len(r) >= 5 and ymd(r[0]):
            out.append(dict(date=ymd(r[0]), kind=r[1] or None, result=r[4] or None,
                            min_price_manwon=manwon(r[3]) if r[3] else None))
    return out


def _addr_key(s):
    return re.sub(r'[\s,]|^\d+\.', '', (s or '').strip())


def _pick(chunks, addrs, single):
    """현황조사서의 소재지별 조각 중 이 물건(목록 주소)에 해당하는 것. 물건이 하나뿐인 사건이면 주소가 달라도 전부."""
    keys = [_addr_key(a) for a in addrs if a]
    hit = [c for c in chunks if any(k and (k in _addr_key(c[0]) or _addr_key(c[0]) in k) for k in keys)]
    return hit or (chunks if single or not keys else [])


CURST_LABELS = {'점유인', '당사자구분', '점유부분', '용도', '점유기간', '보증(전세)금', '차임', '전입일자', '확정일자',
                '소재지', '점유관계', '기타', '조사일시', '사건번호'}


def _field(block, label):
    m = re.search(r'(?:^|\n)' + re.escape(label) + r'[^\S\n]*\n[^\S\n]*([^\n]*)', block)
    v = m.group(1).strip() if m else ''
    return '' if v in CURST_LABELS else v


def parse_occupancy(page, names, addrs, single):
    txt = page.inner_text('body')
    i = txt.rfind('현황조사서\n법원')
    if i < 0: raise RuntimeError('현황조사서 화면 없음')
    t = txt[i:]
    survey = _field(t, '조사일시')
    a = t.find('부동산의 점유관계')
    b = t.find('임대차관계 조사서', a)
    sec1 = t[a:b if b > 0 else len(t)] if a >= 0 else ''
    sec2 = t[b:] if b > 0 else ''
    # 1. 부동산의 점유관계: 소재지마다 (주소, 점유관계, 기타)
    chunks = []
    for part in re.split(r'\n소재지\s*\n', sec1)[1:]:
        lines = [x.strip() for x in part.split('\n')]
        addr = next((x for x in lines if x), '')
        occ = _field(part, '점유관계')
        m = re.search(r'\n기타\s*\n(.*?)(?=\n[^\n]*을\(를\) 나타낸 표|\Z)', part, re.S)
        etc = re.sub(r'\n\s*\n', '\n', m.group(1)).strip() if m else ''
        chunks.append((addr, occ, etc))
    mine = _pick(chunks, addrs, single)
    occ_type = ' / '.join(c[1] for c in mine if c[1]) or None
    etc = '\n'.join(c[2] for c in mine if c[2])
    # 2. 임대차관계 조사서: 점유인별 (당사자구분, 용도, 점유기간, 전입일자) — 이름은 넣지 않음
    lease = []
    for part in sec2.split('[소재지]')[1:]:
        addr = part.split('\n', 1)[0]
        for ent in re.split(r'\n\d+\s*\n', '\n' + part)[1:]:
            role = _field(ent, '당사자구분')
            if not role and not _field(ent, '점유기간'): continue
            lease.append((addr, dict(occupant=role or None, use=_field(ent, '용도') or None,
                                     period=_field(ent, '점유기간') or None, move_in=ymd(_field(ent, '전입일자')))))
    periods = [d for _, d in _pick(lease, addrs, single)] if lease else []
    cnt = None
    for tb in tables(page):
        if tb['cap'].startswith('번호,소재지,임대차관계'):
            rows = [(r[1], r[2]) for r in body_rows(tb) if len(r) >= 3]
            sel = _pick(rows, addrs, single)
            nums = [int(m.group(1)) for _, v in sel for m in [re.search(r'(\d+)\s*명', v)] if m]
            if nums: cnt = sum(nums)
    text = mask_names(etc, names)
    return dict(occupant_type=occ_type, lessee_count=cnt, periods=periods,
                surveyed=sorted({ymd(s) for s in re.findall(r'\d{4}년\d{2}월\d{2}일', survey)}),
                text=text[:600], closed_absent=bool(re.search(r'폐문|부재|만날 수 없|만나지 못', etc)))


# ---------- 한 물건 조회 ----------
class Scraper:
    def __init__(self, pw):
        self.browser = pw.chromium.launch(headless=True)
        self.ctx = self.browser.new_context(viewport={'width': 1400, 'height': 1000}, locale='ko-KR')
        self.ctx.set_default_timeout(30000)
        self.texts = {}
        self.ctx.on('response', self._on_resp)
        self.page = self.ctx.new_page()
        self.page.on('dialog', lambda d: (setattr(self, 'last_dialog', d.message), d.accept()))
        self.courts = None

    def _on_resp(self, r):
        m = re.search(r'/streamdocs/v4/documents/[^/]+/texts/(\d+)$', r.url.split('?')[0])
        if m and r.status == 200:
            try: self.texts[int(m.group(1))] = r.json()
            except Exception: pass

    def close(self):
        self.browser.close()

    def search(self, court, year, no):
        pg = self.page
        self.last_dialog = None
        pg.goto(SEARCH_URL, wait_until='networkidle'); pause()
        sel = '#mf_wfm_mainFrame_sbx_auctnCsSrchCortOfc'
        pg.wait_for_selector(sel, state='attached')
        if self.courts is None:
            self.courts = pg.eval_on_selector_all(sel + ' option', 'os=>os.map(o=>o.text.trim())')
        label = resolve_court(court, self.courts)
        if not label: raise RuntimeError(f'법원 이름을 찾지 못함: {court!r}')
        pg.select_option(sel, label=label)
        years = pg.eval_on_selector_all('#mf_wfm_mainFrame_sbx_auctnCsSrchCsYear option', 'os=>os.map(o=>o.text.trim())')
        if str(year) not in years: raise RuntimeError(f'사건 연도 선택 불가: {year}')
        pg.select_option('#mf_wfm_mainFrame_sbx_auctnCsSrchCsYear', label=str(year))
        pg.fill('#mf_wfm_mainFrame_ibx_auctnCsSrchCsNo', str(no))
        pg.click('#mf_wfm_mainFrame_btn_auctnCsSrchBtn')
        pg.wait_for_load_state('networkidle')
        t0 = time.time()
        while True:
            time.sleep(1.5)
            tbls = tables(pg)
            basic = table_by_cap(tbls, '사건번호,사건명')
            found = basic and any(f'{year}타경{no}' in c for r in basic['rows'] for c in r)
            items = [tb for tb in tbls if re.match(r'mf_wfm_mainFrame_gen_gdsDts_\d+_grp_gdsDtsTbl', tb['id'] or '')]
            if found and items: return label, tbls
            if self.last_dialog or time.time() - t0 > 20:
                raise RuntimeError('사건 조회 결과 없음' + (f' ({self.last_dialog})' if self.last_dialog else ''))

    def item(self, t):
        m = re.fullmatch(r'(\d{4})타경(\d+)', t['case'])
        if not m: raise RuntimeError(f"사건번호 형식 이상: {t['case']}")
        year, no = m.groups()
        court, tbls = self.search(t.get('court'), year, no)
        pg = self.page
        out = dict(court=court)
        info = {r[i]: r[i + 1] for tb in [table_by_cap(tbls, '사건번호,사건명')] for r in tb['rows'] for i in range(0, len(r) - 1, 2)}
        case_rcpt = ymd(info.get('접수일자'))
        ddl = [ymd(r[2]) for r in body_rows(table_by_cap(tbls, '목록번호')) if len(r) > 2 and ymd(r[2])]

        # 물건 행 찾기
        gi = None; n_items = 0
        for tb in tbls:
            mm = re.match(r'mf_wfm_mainFrame_gen_gdsDts_(\d+)_grp_gdsDtsTbl', tb['id'] or '')
            n_items += bool(mm)
            if mm and tb['rows'] and len(tb['rows'][0]) > 1 and tb['rows'][0][0] == '물건번호' and tb['rows'][0][1].strip() == str(t['item_no']):
                gi = int(mm.group(1))
        if gi is None: raise RuntimeError(f"물건번호 {t['item_no']} 없음")
        addrs = [r[1] for tb in tbls if (tb['id'] or '').startswith(f'mf_wfm_mainFrame_gen_gdsDts_{gi}_')
                 for r in tb['rows'] if len(r) > 1 and re.fullmatch(r'목록\d+', r[0])]

        # C. 문건/송달
        try:
            pg.get_by_text('문건/송달내역', exact=True).first.click()
            pg.wait_for_load_state('networkidle'); time.sleep(1.5)
            out['events'] = parse_events(tables(pg))
        except Exception as e:
            out['events'] = []; out.setdefault('_errs', []).append(f'문건/송달 실패: {e}')
        pg.get_by_text('사건내역', exact=True).first.click(); pause()

        # A. 매각물건명세서
        names = []
        btn = pg.locator(f'#mf_wfm_mainFrame_gen_gdsDts_{gi}_btn_gdsSpcfc')
        spec_err = None
        if btn.count() == 0:
            spec_err = '매각물건명세서 버튼 없음'
        elif not btn.is_enabled():
            spec_err = f'{SPEC_PENDING} (사이트가 매각기일 1주 전부터 공개)'
        else:
            self.texts = {}
            with self.ctx.expect_page(timeout=20000) as np:
                btn.click()
            vp = np.value
            try:
                vp.wait_for_load_state('networkidle')
                t0 = time.time(); last = -1; stable = 0
                while time.time() - t0 < 25:
                    fr = [f for f in vp.frames if 'streamdocs' in f.url]
                    if fr:
                        try: fr[0].evaluate("()=>{const s=document.querySelector('.pre-scrollable'); if(s) s.scrollTop+=800}")
                        except Exception: pass
                    time.sleep(1)
                    n = len(self.texts)
                    stable = stable + 1 if n == last and n > 0 else 0
                    last = n
                    if stable >= 3: break
                spec, names = parse_spec(dict(self.texts), case_rcpt)
                out.update(spec)
            except Exception as e:
                spec_err = f'매각물건명세서 읽기 실패: {e}'
            finally:
                vp.close()
        if not out.get('dividend_deadline') and ddl: out['dividend_deadline'] = ddl[0]
        pause()

        # D. 기일내역 (물건상세) — 다음 기일이 안 잡힌 물건(유찰 직후 등)은 버튼이 비활성 → 건너뜀 (2026-11-08)
        dbtn = pg.locator(f'#mf_wfm_mainFrame_gen_gdsDts_{gi}_btn_gdsDtlInq')
        if dbtn.count() and dbtn.is_enabled():
            dbtn.click()
            pg.wait_for_load_state('networkidle'); time.sleep(1.5)
            out['schedule'] = parse_schedule(tables(pg))
            pause()
        else:
            out['schedule'] = []; out.setdefault('_errs', []).append('물건상세조회 비활성 (다음 매각기일 미지정)')

        # B. 현황조사서
        try:
            cb = pg.locator('input[value="현황조사서"]:visible')
            if cb.count() == 0: raise RuntimeError('현황조사서 버튼 없음 (사이트가 매각기일 2주 전부터 공개)')
            cb.first.click()
            pg.wait_for_load_state('networkidle'); time.sleep(2)
            out['occupancy'] = parse_occupancy(pg, names, addrs, n_items == 1)
        except Exception as e:
            out['occupancy'] = None; out.setdefault('_errs', []).append(f'현황조사서 실패: {e}')

        out['error'] = spec_err
        return out


# ---------- 저장소 ----------
def git(*args, check=True):
    env = dict(os.environ, GCM_INTERACTIVE='never', GIT_TERMINAL_PROMPT='0')
    r = subprocess.run([GIT, '-C', REPO, *args], capture_output=True, text=True, encoding='utf-8', errors='replace', env=env,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 실패: {(r.stderr or r.stdout).strip()[-400:]}")
    return r


def sync_repo():
    if not os.path.isdir(os.path.join(REPO, '.git')):
        subprocess.run([GIT, 'clone', 'https://github.com/wpaud16/ML.git', REPO], check=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return
    try:
        git('pull', '--rebase', '--autostash', '-X', 'theirs')
    except Exception as e:
        # 대상 목록이 하루 묵을 뿐이므로 계속 진행 (업로드 때 다시 pull)
        log(f'시작 pull 실패 → 기존 사본으로 진행: {e}')
        if 'rebase in progress' in git('status', check=False).stdout:
            git('rebase', '--abort', check=False)


def upload(today):
    git('add', '--', OUT_REL, README_REL)
    if git('diff', '--cached', '--quiet', check=False).returncode == 0:
        log('변경 없음 → 커밋 생략'); return True
    git('commit', '-m', f'tenants: 임차인 자료 {today}', '--', OUT_REL, README_REL)
    for n in range(1, 6):
        try:
            git('pull', '--rebase', '-X', 'theirs')
            git('push')
            log(f'업로드 완료 (시도 {n})'); return True
        except Exception as e:
            log(f'업로드 실패 {n}/5: {e}')
            if git('status', check=False).stdout.find('rebase in progress') >= 0:
                git('rebase', '--abort', check=False)
            if n < 5: time.sleep(10)
    return False


# ---------- 메인 ----------
def need_query(prev, t, today):
    if not prev or not prev.get('checked'): return True
    # 명세서를 아직 못 읽은 물건(최선순위 설정일자 없음)은 캐시 없이 매일 다시
    if not prev.get('base_right_date'): return True
    if prev.get('bidding_date') != t.get('bidding_date'): return True
    age = (date.fromisoformat(today) - date.fromisoformat(prev['checked'])).days
    # 사건이 사이트에 없는 물건은 매일 다시 찾지 않음 (2026-11-08: 매번 30초씩 낭비)
    if '조회 결과 없음' in (prev.get('error') or ''): return age >= CACHE_DAYS
    return age >= CACHE_DAYS or bool(prev.get('error'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int)
    ap.add_argument('--only', nargs='*', help='"사건번호[물건번호]@법원"')
    ap.add_argument('--no-upload', action='store_true')
    ap.add_argument('--no-sync', action='store_true')
    ap.add_argument('--budget-min', type=float, default=35, help='새 물건 조회를 시작하는 시간 한도(분)')
    ap.add_argument('--out', help='결과를 저장소 대신 이 경로에 저장 (시험용)')
    a = ap.parse_args()
    t_start = time.time()
    now = datetime.now(KST); today = str(now.date())
    log(f'시작 ({" ".join(sys.argv[1:])})')
    if not a.no_sync:
        sync_repo()

    if a.only:
        targets = []
        for s in a.only:
            key, _, court = s.partition('@')
            m = re.fullmatch(r'(.+)\[(\d+)\]', key)
            targets.append(dict(key=key, case=m.group(1), item_no=int(m.group(2)), court=court or None))
    elif os.path.exists(TARGETS):
        targets = json.load(open(TARGETS, encoding='utf-8')).get('items') or []
    else:
        log('tenant_targets.json 없음 → 조회할 물건 없음'); targets = []
    for t in targets:
        t.setdefault('key', f"{t['case']}[{t['item_no']}]")
    # 매각기일이 이미 지난 대상(리치고 기일이 묵은 물건 — 2026-01 남양주 등)은 조회하지 않음.
    # 정렬 맨 앞에 와서 '조회 결과 없음'·시간 초과로 시간 한도를 다 써 버리던 문제 (2026-11-08)
    stale = [t for t in targets if not a.only and t.get('bidding_date') and t['bidding_date'] < today]
    if stale:
        log(f'기일 지난 대상 {len(stale)}건 건너뜀 (예: ' + ', '.join(f"{t['key']} {t['bidding_date']}" for t in stale[:3]) + ')')
        sk = {t['key'] for t in stale}
        targets = [t for t in targets if t['key'] not in sk]
    targets.sort(key=lambda t: (t.get('bidding_date') or '9999', t['key']))
    if a.limit: targets = targets[:a.limit]

    out_path = a.out or os.path.join(REPO, OUT_REL)
    prev_path = a.out if a.out and os.path.exists(a.out) else os.path.join(REPO, OUT_REL)
    prev = {}
    if os.path.exists(prev_path):
        try: prev = json.load(open(prev_path, encoding='utf-8')).get('items') or {}
        except Exception as e: log(f'이전 latest.json 읽기 실패: {e}')

    items, todo = {}, []
    if not a.only and not os.path.exists(TARGETS):
        items = dict(prev)  # 대상 목록이 없으면 지우지 말고 이전 값 유지
    for t in targets:
        if a.only or need_query(prev.get(t['key']), t, today): todo.append(t)
        else: items[t['key']] = prev[t['key']]
    log(f'대상 {len(targets)}건, 조회 {len(todo)}건, 이전 값 유지 {len(targets) - len(todo)}건')

    ok = fail = skipped = 0
    with sync_playwright() as pw:
        sc = Scraper(pw)
        try:
            for i, t in enumerate(todo, 1):
                if time.time() - t_start > a.budget_min * 60:
                    for r in todo[i - 1:]:
                        if r['key'] in prev: items[r['key']] = prev[r['key']]
                    skipped = len(todo) - i + 1
                    log(f'시간 한도 {a.budget_min}분 → 남은 {skipped}건은 이전 값 유지'); break
                rec = dict(checked=today, court=t.get('court'), bidding_date=t.get('bidding_date'), category=t.get('category'),
                           base_right_date=None, base_right=None, dividend_deadline=None, tenants=[], remarks='',
                           assumed_rights_text='', occupancy=None, events=[], schedule=[], error=None)
                try:
                    r = sc.item(t)
                    errs = r.pop('_errs', [])
                    rec.update(r)
                    if not rec['bidding_date']:
                        rec['bidding_date'] = next((s['date'] for s in rec['schedule'] if s['kind'] == '매각기일' and s['date'] >= today), None)
                    if errs: rec['warnings'] = errs
                    ok += rec['error'] is None
                    fail += rec['error'] is not None
                    log(f"[{i}/{len(todo)}] {t['key']} 임차인 {len(rec['tenants'])}명" + (f" · {rec['error']}" if rec['error'] else '') + (f" · {errs}" if errs else ''))
                except Exception as e:
                    rec['error'] = f'{type(e).__name__}: {str(e).splitlines()[0][:200]}'
                    fail += 1
                    log(f"[{i}/{len(todo)}] {t['key']} 실패: {rec['error']}")
                    try:
                        sc.close(); sc = Scraper(pw)
                    except Exception:
                        log(traceback.format_exc())
                items[t['key']] = rec
                pause()
        finally:
            sc.close()

    doc = dict(generated_at=datetime.now(KST).isoformat(timespec='seconds'), items=items)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    log(f'저장 {out_path}: 성공 {ok}, 오류 {fail}, 시간초과 {skipped}, 총 {len(items)}건')

    if not a.no_upload and not a.out:
        if not upload(today): log('업로드 최종 실패'); return 1
    log(f'끝 ({(time.time() - t_start) / 60:.1f}분)')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        log('치명적 오류\n' + traceback.format_exc())
        sys.exit(1)
