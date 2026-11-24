"""구글폼 자동 작성 (2026-11-25 사용자 요청: 응모 이벤트마다 다 시도해서 할 수 있는 건 다 하기).
nform.py(네이버 폼)와 같은 규칙: 개인정보는 C:\\auction_pc\\.env 에서만, 평가형은 '좋은' 쪽, 모르는 건 추측.
퀴즈 정답·댓글 닉네임 같은 이벤트별 답은 extra=[(질문 정규식, 답 정규식 또는 글)] 로 넘긴다.
fill(pg, url, extra=None, submit=False) → (상태, 줄들). 상태: ready / done / stuck
단독 실행: python gform.py URL [extra.json] [--submit]"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nform

QS = """() => [...document.querySelectorAll('div[role=listitem]')].map((q, i) => [q, i]).filter(([q]) => q.offsetParent).map(([q, i]) => {
  const t = ((q.querySelector('[role=heading]')||{}).innerText || '').trim();
  const o = [...q.querySelectorAll('[role=radio],[role=checkbox]')].map(r => r.getAttribute('aria-label')||r.getAttribute('data-value')||'');
  const typ = q.querySelector('[role=radio]') ? 'radio' : q.querySelector('[role=checkbox]') ? 'check'
            : q.querySelector('textarea') ? 'long' : q.querySelector('input[type=text],input[type=email],input[type=tel],input[type=number]') ? 'text'
            : q.querySelector('[role=listbox]') ? 'list' : (q.querySelector('input[type=date]') ? 'date' : 'none');
  return {i, t, o, typ, req: /\\*\\s*$/.test(t) || !!q.querySelector('[aria-label="필수 질문"]'), d: q.innerText.slice(0, 300)};
})"""


def mine_text(title, e, yt=''):
    if re.search(r'유튜브|닉네임|핸들|@아이디|채널', title) and yt:
        return yt
    if re.search(r'이름|성함|성명', title):
        return e.get('ENTRY_NAME')
    if re.search(r'연락처|전화|휴대폰|핸드폰', title):
        ph = e.get('ENTRY_PHONE') or ''
        return re.sub(r'\D', '', ph) if re.search(r'숫자만|기호 없이|-\s*없이|하이픈', title) else ph
    if re.search(r'이메일|e-?mail|메일', title, re.I):
        return e.get('ENTRY_EMAIL')
    return None


def fill(pg, url, extra=None, submit=False, yt=''):
    e = nform.env(); R = nform.rules(e); extra = extra or []
    L = []
    pg.goto(url, wait_until='domcontentloaded', timeout=40000); pg.wait_for_timeout(3500)
    if re.search(r'이미 응답|already responded|응답을 더 이상 받지|no longer accepting', pg.evaluate('document.body.innerText')):
        return 'done' if '이미' in pg.evaluate('document.body.innerText') else 'stuck', ['이미 응답했거나 마감된 폼']
    for page in range(12):
        items = pg.locator('div[role=listitem]')
        for q in pg.evaluate(QS):
            t = q['t'].replace('\n', ' ').rstrip(' *'); loc = items.nth(q['i'])
            if q['typ'] == 'none':
                continue
            ans = None
            for qr, a in extra:
                if re.search(qr, t):
                    ans = a; break
            hide = bool(re.search(nform.MINE, t))
            if q['typ'] in ('radio', 'check'):
                opts = [o for o in q['o'] if o]
                if ans is not None:
                    want = [o for o in opts if re.search(ans, o)] or ([] if q['typ'] == 'radio' else [])
                    if q['typ'] == 'radio': want = want[:1]
                else:
                    p_ = nform.pick(R, t, opts)
                    want = [p_ or nform.guess(opts)] if (q['req'] or p_) else []
                if not want:
                    if q['req']:
                        return 'stuck', L + [f'모르는 필수 질문: {t[:60]} / {opts}']
                    continue
                for w in want:
                    r = loc.locator(f'[role={"radio" if q["typ"] == "radio" else "checkbox"}][aria-label="{w}"], [data-value="{w}"]').first
                    if r.get_attribute('aria-checked') != 'true':
                        r.click()
                    if re.search(r'^기타', w):
                        oi = loc.locator('input[type=text]').first
                        if oi.count(): oi.fill('이벤트 안내 보고 처음 들어왔어요')
                L.append(f"{t[:50]} → {'(내 정보)' if hide else ', '.join(want)}{'' if ans is not None or nform.pick(R, t, opts) else ' (추측)'}"
                         + ('' if hide else f"   [보기: {' / '.join(o[:25] for o in opts)}]"))
            elif q['typ'] in ('text', 'long'):
                v = ans if ans is not None else mine_text(t, e, yt)
                if v is None:
                    if not q['req']:
                        continue
                    v = nform.FREE
                box = loc.locator('textarea, input[type=text], input[type=email], input[type=tel], input[type=number]').first
                box.fill(str(v))
                L.append(f"{t[:50]} → {'(내 정보)' if (hide or v in e.values()) else v}")
            else:
                if q['req']:
                    return 'stuck', L + [f'처리 못 하는 질문 형식({q["typ"]}): {t[:60]}']
        nx = pg.get_by_role('button', name='다음', exact=True)
        sb = pg.get_by_role('button', name='제출', exact=True)
        if nx.count() and nx.first.is_visible():
            before = pg.evaluate(QS)
            nx.first.click(); pg.wait_for_timeout(2500)
            if pg.evaluate(QS) == before:   # 첫 클릭이 안 먹는 경우가 있어 한 번 더
                pg.wait_for_timeout(1500); nx.first.click(); pg.wait_for_timeout(4000)
            if pg.evaluate(QS) == before:
                bad = pg.evaluate("[...document.querySelectorAll('[role=alert]')].map(a=>a.closest('[role=listitem]')?.innerText.slice(0,80))")
                return 'stuck', L + [f'다음으로 못 넘어감: {bad}']
            continue
        if sb.count():
            if not submit:
                return 'ready', L
            sb.first.click(); pg.wait_for_timeout(3500)
            body = pg.evaluate('document.body.innerText')
            ok = not pg.get_by_role('button', name='제출', exact=True).count() and re.search(r'응답이 기록|제출되었|recorded', body)
            return ('done' if ok else 'stuck'), L + ([] if ok else ['제출 확인 문구 없음'])
        return 'stuck', L + ['다음·제출 버튼 없음']
    return 'stuck', L + ['페이지가 너무 많음']


if __name__ == '__main__':
    import entry_login as el
    from playwright.sync_api import sync_playwright
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    extra = [tuple(x) for x in json.load(open(args[1], encoding='utf-8-sig'))] if len(args) > 1 else []
    yt = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--yt=')), '')
    with sync_playwright() as p:
        c = el.open_profile(p, headless=True); pg = c.new_page()
        try:
            st, L = fill(pg, args[0], extra, submit='--submit' in sys.argv, yt=yt)
            print(st); print('\n'.join(L))
            if st == 'stuck':
                shot = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--shot=')), '')
                if shot: pg.screenshot(path=shot, full_page=True)
                for q in pg.evaluate(QS):
                    print('  ?', q['typ'], q['t'][:80], q['o'][:8])
        finally:
            c.close()
