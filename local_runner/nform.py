"""네이버 폼 자동 작성 (2026-11-23 사용자 요청: 아침마다 대신 응모 준비 → '응모해줘' 한마디에 제출).
- 이름·연락처·이메일·성별·연령대·거주지는 C:\\auction_pc\\.env (ENTRY_*) 에서만 읽는다. 저장소·출력에 남기지 않는다.
- 답은 사실대로: 안 가 본 곳은 '없다', 처음 본 채널은 '처음', 평가형은 '보통'. 규칙에 없는 필수 질문·자유서술 필수면 멈춘다 (추측해서 쓰지 않음).
- fill(page, url, submit=False) → (상태, 줄들). 상태: ready(끝까지 채움, 제출 안 함) / done(제출됨) / stuck(멈춤)
단독 실행: python nform.py URL [--submit]"""
import os, re, sys

ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env')
MINE = r'성별|연령|나이|거주|생활권|지역|이름|성함|성명|연락처|전화|휴대폰|핸드폰|이메일|메일'   # 출력에서 가리는 질문


def env():
    out = {}
    for l in open(ENV, encoding='utf-8-sig'):
        if '=' in l and not l.lstrip().startswith('#'):
            k, v = l.split('=', 1); out[k.strip()] = v.strip().strip('"\'')
    return out


def rules(e):
    age = re.sub(r'\D', '', e.get('ENTRY_AGE') or '') or '30'
    g = (e.get('ENTRY_GENDER') or '')[:1]
    reg = e.get('ENTRY_REGION') or ''
    return [
        (r'개인정보|동의', ['동의합니다', '동의함', '^동의']),
        (r'성별', [g] if g else []),
        (r'연령|나이', [rf'^{age}대', rf'{age}대 이상', rf'{age}\s*~\s*{int(age) + 9}', rf'{age[0]}[0-9]세']),
        (r'전자기기|기기', ['모바일', '스마트폰']),
        (r'생활권', ['그 외', '타 지역']),
        (r'거주|지역|사는 곳', [reg, '수도권' if reg in ('서울', '경기', '인천') else '^기타', '타 지역', '^기타']),
        (r'방문.*(경험|있)|이용.*경험|이용해 보|이용하신 적', ['없고', '없다', '없음', '^아니']),
        (r'이용\s*여부', ['한 번도', '없']),
        (r'알게|접하게|경로|어떻게 방문|방문하시게', ['이벤트', '^기타']),
        (r'얼마나 자주|빈도|자주', ['처음', '거의 이용하지', '월 1회 미만', '거의 없', '^거의']),
        (r'주로 이용하는.*채널|이용하시는.*채널|어떤 채널|채널은', ['인스타그램']),
        (r'이유|목적|왜 ', ['이벤트']),
        (r'얻는 정보|어떤 정보', ['행사', '이벤트']),
        (r'가장 만족|만족.*(채널|콘텐츠 유형)|선호', ['인스타그램', '카드뉴스']),
        (r'개선', ['다양성', '없음']),
        (r'보고 싶은|원하는 콘텐츠|희망', ['카드뉴스', '정보']),
        (r'알고 (있|계)|인지|어느 정도 알', ['전혀', '모른다', '모름', '알지 못', '^아니']),
        (r'.', ['^보통', '그저 그렇다', '^중간']),   # 만족도·평가형은 '보통'
    ]


def pick(R, title, opts):
    for q, ws in R:
        if re.search(q, title):
            for w in ws:
                if not w: continue
                for o in opts:
                    if re.search(w, o):
                        return o
    return None


def fill(pg, url, submit=False):
    e = env(); R = rules(e)
    name, phone, mail = e['ENTRY_NAME'], re.sub(r'\D', '', e['ENTRY_PHONE']), e.get('ENTRY_EMAIL', '')
    L = []
    pg.goto(url, wait_until='domcontentloaded', timeout=40000); pg.wait_for_timeout(5000)
    if 'form.naver.com' not in pg.url:
        return 'stuck', [f'네이버 폼 아님: {pg.url[:80]}']
    body = pg.evaluate('document.body.innerText')
    if re.search(r'마감|종료된 설문|응답을 받지 않', body[:600]) and not pg.query_selector('div.nsv_survey_question'):
        return 'stuck', ['설문 마감']
    if re.search(r'이미 (응답|참여)', body[:800]):
        return 'done', ['이미 응답한 설문']
    for page_no in range(1, 30):
        qs = pg.query_selector_all('div.nsv_survey_question')
        for q in qs:
            if not q.is_visible(): continue
            tt = q.query_selector('.nsv_survey_reply_question_title')
            title = re.sub(r'^답변 필수', '', (tt.inner_text() if tt else '').strip()).replace('\n', ' ').strip()
            req = bool(q.query_selector('.nsv_survey_question_required'))
            mine = bool(re.search(MINE, title))
            labels = q.query_selector_all('label')
            opts = [l.inner_text().strip() for l in labels]
            txt = q.query_selector('input[type=text], input[type=tel], input[type=email], textarea')
            if labels and not any(opts):   # 표(행렬)형: 행마다 '보통'
                rows = [r for r in q.query_selector_all('tr, [role=row]') if r.query_selector('input')]
                if not rows:
                    return 'stuck', L + [f'표 형식 모름: {title}']
                heads = [h.inner_text().strip() for h in q.query_selector_all('thead th, [role=columnheader]')]
                mid = next((i for i, h in enumerate(heads) if '보통' in h), None)
                if mid is None:
                    return 'stuck', L + [f'표에 보통 칸 없음: {title}']
                for r in rows:
                    r.query_selector_all('label')[mid].evaluate('e => e.click()'); pg.wait_for_timeout(120)
                L.append(f'{title} → 표 {len(rows)}행 모두 "{heads[mid]}"'); continue
            if labels:
                ch = pick(R, title, opts)
                if not ch and not req:
                    L.append(f'(선택 문항 건너뜀) {title}'); continue
                if not ch:
                    return 'stuck', L + [f'모르는 질문: {title} | {" / ".join(opts)[:200]}']
                next(l for l in labels if l.inner_text().strip() == ch).evaluate('e => e.click()'); pg.wait_for_timeout(350)
                etc = q.query_selector('textarea.nsv_survey_question_etc_input, input.nsv_survey_question_etc_input')
                if etc and etc.is_visible():
                    etc.fill('이벤트 안내 보고 처음 들어왔어요'); ch += ' (이벤트 안내 보고 처음 들어왔어요)'
                L.append(f'{title} → {"(내 정보)" if mine else ch}')
            elif txt:
                if re.search(r'이름|성함|성명', title): val = name
                elif re.search(r'연락처|전화|휴대폰|핸드폰', title): val = phone
                elif re.search(r'이메일|메일', title): val = mail
                elif not req: L.append(f'(선택 문항 건너뜀) {title}'); continue
                else: return 'stuck', L + [f'직접 써야 하는 질문: {title}']
                if not val: return 'stuck', L + [f'내 정보 없음: {title}']
                txt.fill(val); pg.wait_for_timeout(150)
                L.append(f'{title} → (내 정보)')
            elif req:
                return 'stuck', L + [f'형식 모름: {title}']
        nxt = pg.query_selector('button:has-text("다음")')
        sub = pg.query_selector('button:has-text("제출")')
        if nxt and nxt.is_visible():
            before = [x.inner_text()[:40] for x in qs if x.is_visible()]
            nxt.click(); pg.wait_for_timeout(2500)
            if before == [x.inner_text()[:40] for x in pg.query_selector_all('div.nsv_survey_question') if x.is_visible()]:
                return 'stuck', L + ['다음 페이지로 안 넘어감']
            continue
        if not sub:
            return 'stuck', L + ['제출 버튼 없음']
        if not submit:
            return 'ready', L
        sub.click(); pg.wait_for_timeout(3000)
        for b in pg.query_selector_all('button:has-text("제출")'):
            if b.is_visible():
                b.click(); pg.wait_for_timeout(3000); break
        body = re.sub(r'\s+', ' ', pg.evaluate('document.body.innerText'))
        if re.search(r'답변이 제출|제출되었|참여해 주셔서|응답이 (제출|완료)', body):
            return 'done', L
        return 'stuck', L + ['제출 후 확인 문구 없음: ' + body[:120]]
    return 'stuck', L + ['페이지가 너무 많음']


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import entry_login as el
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = el.open_profile(p, headless=True)
        st, L = fill(ctx.new_page(), sys.argv[1], '--submit' in sys.argv)
        ctx.close()
    print(st); print('\n'.join(L))
