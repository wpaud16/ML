"""아침 대신 응모 준비 (2026-11-23 사용자 요청: 말 안 해도 아침마다 준비 → '응모해줘' 한마디에 제출).
06:00 생활 메일 작업(run_all s_outfit)에서 이벤트 검색 뒤에 돈다.
1) 아직 응모 안 한 이벤트의 원문(인스타 글·웹페이지)을 읽어 네이버 폼 링크를 찾는다.
2) 팔로우·댓글·공유·캡처처럼 내 계정이 필요한 조건이 있으면 뺀다.
3) 폼을 끝 페이지까지 채워 보되 제출은 하지 않는다 (nform.fill submit=False). 모르는 질문이 있으면 '확인 필요'.
결과: C:\\auction_pc\\entry\\ready.json (저장소 밖: 고른 답이 들어 있어서). 메일·이벤트 페이지는 제목·건수만 쓴다.
제출은 사용자가 대화창에서 '응모해줘' 했을 때 entry_submit.py 로만 한다 (자동 제출 안 함).
사용: python entry_prep.py [--limit 25] [--recheck]"""
import argparse, datetime as dt, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BASE = os.path.dirname(REPO)
OUT = os.path.join(BASE, 'entry', 'ready.json')
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, 'brief'))
FORM = re.compile(r'https?://(?:naver\.me/[A-Za-z0-9]+|form\.naver\.com/response/[A-Za-z0-9_-]+|forms\.gle/[A-Za-z0-9]+|docs\.google\.com/forms/d/(?:e/)?[A-Za-z0-9_-]+/viewform)')
QUIZ = re.compile(r'퀴즈|정답|문제|quiz', re.I)


def is_google(u):
    return bool(re.search(r'forms\.gle|docs\.google\.com/forms', u or ''))


YT = re.compile(r'https?://(?:youtu\.be/[\w-]{6,}|(?:www\.|m\.)?youtube\.com/(?:watch\?v=[\w-]{6,}|shorts/[\w-]{6,}))')
YT_OK = {'구독', '좋아요', '댓글', '캡처', '캡쳐', '업로드', '첨부', '인증샷'}   # 유튜브 몫 + 그 캡처 올리기까지는 Claude 가
SHOTS = os.path.join(BASE, 'entry', 'shots')


def fill_form(pg, form, files=None, extra=None, submit=False):
    import nform
    if is_google(form):
        import gform
        return gform.fill(pg, form, extra=extra, submit=submit, yt=nform.env().get('ENTRY_YT', ''))
    return nform.fill(pg, form, submit=submit, files=files, extra=extra)


def do_youtube(pg, k, video, needs, title, cond):
    """2026-11-25 사용자: 댓글도 Claude 가 (이상한 댓글 말고). 구독·좋아요·댓글 + 캡처. → (캡처 파일들, 오류)"""
    import yt, entry_ai, hashlib
    os.makedirs(SHOTS, exist_ok=True)
    h = hashlib.md5(k.encode()).hexdigest()[:8]
    files = []
    pg.goto(video, wait_until='domcontentloaded', timeout=40000); pg.wait_for_timeout(5000)
    vtitle = pg.title().replace(' - YouTube', '')
    vdesc = pg.evaluate("(document.querySelector('meta[name=description]')||{}).content||''")
    if '구독' in needs:
        f = os.path.join(SHOTS, f'{h}_sub.png'); yt.subscribe(pg, video, f); files.append(f)
    if '좋아요' in needs:
        yt.like(pg, video)
    if '댓글' in needs:
        c = entry_ai.comment_text(title, cond, vtitle, vdesc)
        if not c:
            return files, '댓글 문구를 정하지 못함 (조건이 애매하거나 Claude 응답 없음)'
        f = os.path.join(SHOTS, f'{h}_comment.png')
        if not yt.comment(pg, video, c, f):
            return files, '댓글 등록 확인 안 됨'
        files.append(f)
        print(f'  댓글: {c}', flush=True)
    return files, ''
# 2026-11-25: 밀양 퀴즈(실명인증)·아름다운가게(전회원 대상)를 '바로 응모'에 넣었다가 사용자 지적 → 응모 화면까지 들어가 막힘 확인
VERIFY = [(re.compile(r'실명\s*인증|본인\s*(인증|확인)|휴대폰\s*인증|아이핀|I-?PIN|checkplus|nice\.co\.kr', re.I), '본인인증(휴대폰 PASS·보안문자 직접)'),
          (re.compile(r'전\s*회원|회원\s*(대상|전용|만)|로그인\s*(후|이 필요|하셔야|해\s*주세요)|로그인이 필요'), '사이트 로그인(회원 대상)')]
NEEDS_ME = re.compile(r'팔로우|구독|좋아요|댓글|공유|리그램|태그|캡[처쳐]|인증샷|업로드|첨부|스토리|게시물\s*작성|로그인 후|회원\s*가입')


def load():
    try:
        return json.load(open(OUT, encoding='utf-8'))
    except Exception:
        return {'items': {}}


def save(d):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    d['updated'] = dt.datetime.now().isoformat(timespec='seconds')
    json.dump(d, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def summary(today=None):
    """메일·페이지용: (응모 준비된 [(제목, 마감)], 확인 필요 건수). 이미 응모한 건 뺌."""
    import events_page as p
    done = p.done_map()
    its = load().get('items') or {}
    ready = [(v['title'], v.get('deadline')) for k, v in its.items() if v.get('status') in ('ready', 'quiz') and k not in done]
    stuck = sum(1 for k, v in its.items() if v.get('status') == 'stuck' and k not in done)
    return ready, stuck


def report(today=None):
    """메일용 (2026-11-25): 오늘 응모한 것 / 내가 할 것 / 못 하는 것. 제목만."""
    import events_page as p, events as ev
    today = today or dt.date.today()
    items, _ = p.prize_items(today)
    done = p.done_map(); t = today.isoformat()
    out = {'done': [], 'mine': [], 'no': [], 'quiz': []}
    for x in items:
        k = ev.key_of(x); g = p.group_of(x)
        if done.get(k) == t:
            out['done'].append(x['title'])
        elif g in ('verify', 'google'):
            out['mine'].append(f"{x['title']} — {p.note_of(x).get('mine') or ' · '.join(p.mine_of(x))}")
        elif g == 'proxy':
            out['quiz'].append(x['title'])
        elif g == 'self' and x.get('_new'):
            out['no'].append(x['title'])
    return out


def page_text(pg):
    try:
        return pg.evaluate("document.body.innerText+' '+[...document.images].map(i=>i.alt).join(' ')")[:15000] + ' ' + pg.url
    except Exception:
        return ''


def dig(pg, url, title, hops=3):
    """원문 → 이벤트로 이어지는 링크(제목 낱말·이벤트·퀴즈·응모)를 최대 3번 따라가 (누리집 → 팝업 → 응모 화면) 응모 화면 글까지 모음."""
    words = [w for w in re.findall(r'[가-힣A-Za-z0-9]{2,}', title) if w not in ('이벤트', '2026년', '2026')]
    pg.goto(url, wait_until='domcontentloaded', timeout=35000); pg.wait_for_timeout(3500)
    texts, seen = [page_text(pg)], {pg.url}
    for _ in range(hops):
        links = pg.evaluate("[...document.querySelectorAll('a')].map(a=>[a.href,(a.innerText||'')+' '+(a.title||'')+' '+[...a.querySelectorAll('img')].map(i=>i.alt).join(' ')])")
        best = None
        for h, t in links:
            if not h.startswith('http') or h in seen:
                continue
            sc = sum(w in t for w in words) + (1 if re.search(r'이벤트|퀴즈|응모|참여', t) else 0)
            if sc >= 2 and (not best or sc > best[0]):
                best = (sc, h)
        if not best:
            break
        seen.add(best[1])
        try:
            pg.goto(best[1], wait_until='domcontentloaded', timeout=35000); pg.wait_for_timeout(3000)
        except Exception:
            break
        texts.append(page_text(pg))
    return '\n'.join(texts)


def blocker(text):
    return next((lab for r, lab in VERIFY if r.search(text)), '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=25)
    ap.add_argument('--recheck', action='store_true')
    a = ap.parse_args()
    import events_page as p, events as ev, nform, entry_login as el
    from playwright.sync_api import sync_playwright
    today = dt.date.today()
    items, _ = p.prize_items(today)
    done = p.done_map()
    d = load(); its = d.setdefault('items', {})
    for k in list(its):   # 응모했거나 목록에서 빠진 건 정리
        if k in done or not any(ev.key_of(x) == k for x in items):
            its.pop(k)
    cand = [x for x in items if ev.key_of(x) not in done and p.group_of(x) in ('proxy', 'help', 'insta', 'google')
            and (a.recheck or ev.key_of(x) not in its or its[ev.key_of(x)].get('status') == 'ready')]
    print(f'후보 {len(cand)}건 (이미 본 것 {len(its)}건)', flush=True)
    t0 = time.time()
    with sync_playwright() as pw:
        ctx = el.open_profile(pw, headless=True)
        pg = ctx.new_page()
        for x in cand[:a.limit]:
            k = ev.key_of(x); title = x.get('title') or ''
            rec = dict(title=title, url=x.get('url'), org=x.get('org'), deadline=x.get('deadline'), announce=x.get('announce'),
                       checked=today.isoformat())
            old = its.get(k) or {}
            try:
                u = x['url']
                pg.goto(u, wait_until='domcontentloaded', timeout=35000); pg.wait_for_timeout(3500)
                og = pg.evaluate("(document.querySelector('meta[property=\"og:description\"]')||{}).content||''")
                text = og if len(og) > 80 else pg.evaluate('document.body.innerText')[:6000]
                links = pg.evaluate("[...document.querySelectorAll('a')].map(a=>a.href)")
                if FORM.match(u):
                    form = u
                else:
                    m = FORM.search(text) or next((FORM.match(h) for h in links if FORM.match(h)), None)
                    form = m.group(0) if m else ''
                    if not form and 'instagram.com' not in u and not YT.match(u):
                        text = dig(pg, u, title)
                vm = YT.match(u) or YT.search(text) or next((YT.match(h) for h in links if YT.match(h)), None)
                video = vm.group(0) if vm else ''
                cond = text + ' ' + (x.get('how') or '') + ' ' + (x.get('condition') or '')
                needs = set(NEEDS_ME.findall(cond))
                yt_ok = bool(needs) and needs <= YT_OK and bool(video)   # 유튜브 구독·좋아요·댓글(+캡처)만 필요한 것
                b = blocker(text)
                if b:
                    rec.update(status='verify', form=form, reason=b)
                elif needs and not yt_ok:
                    rec.update(status='needs_me', form=form, reason='내 계정 몫: ' + ', '.join(sorted(needs))
                               + ('' if video or not needs <= YT_OK else ' (영상 링크 못 찾음)'))
                elif not form and not (yt_ok and '댓글' in needs):
                    rec.update(status='noform', reason='응모 폼 링크 없음 (다른 방식 응모)')
                else:
                    files, yerr = [], ''
                    if yt_ok:
                        if old.get('yt_done'):
                            files = old.get('files') or []
                        else:
                            files, yerr = do_youtube(pg, k, video, needs, title, cond)
                        rec.update(video=video, files=files, yt_done=not yerr)
                    if yerr:
                        rec.update(status='stuck', form=form, reason=yerr)
                    elif not form:   # 댓글만 달면 되는 이벤트
                        rec.update(status='ready', form='', reason='댓글로 응모')
                    else:
                        st, L = fill_form(pg, form, files, old.get('extra') or [])
                        extra = old.get('extra') or []
                        # 2026-11-25 사용자: 퀴즈 정답 추측도 Claude 가 → 추측한 문항은 Claude CLI 로 정답 확인 후 다시 채움
                        if st == 'ready' and any('(추측)' in l for l in L) and QUIZ.search(title + ' ' + cond + ' '.join(L)):
                            import entry_ai
                            extra = entry_ai.quiz_answers(title, cond, L) or []
                            if extra:
                                st, L = fill_form(pg, form, files, extra)
                        rec.update(status=st if st != 'done' else 'already', form=form, answers=L, extra=extra,
                                   reason=(L[-1] if st == 'stuck' and L else ''))
            except Exception as e:
                rec.update(status='error', reason=str(e)[:150])
            its[k] = rec
            print(f"[{rec['status']}] {title[:40]} {rec.get('reason', '')[:80]}", flush=True)
            save(d)
            time.sleep(2)
            if time.time() - t0 > 30 * 60:
                print('시간 한도(30분) → 나머지는 내일'); break
        ctx.close()
    save(d)
    r, s = summary()
    print(f'응모 준비 {len(r)}건 · 확인 필요 {s}건')


if __name__ == '__main__':
    main()
