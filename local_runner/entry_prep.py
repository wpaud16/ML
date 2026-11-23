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
FORM = re.compile(r'https?://(?:naver\.me/[A-Za-z0-9]+|form\.naver\.com/response/[A-Za-z0-9_-]+)')
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
    ready = [(v['title'], v.get('deadline')) for k, v in its.items() if v.get('status') == 'ready' and k not in done]
    stuck = sum(1 for k, v in its.items() if v.get('status') == 'stuck' and k not in done)
    return ready, stuck


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
            try:
                u = x['url']
                if FORM.match(u):
                    form, text = u, ''
                else:
                    pg.goto(u, wait_until='domcontentloaded', timeout=35000); pg.wait_for_timeout(3500)
                    og = pg.evaluate("(document.querySelector('meta[property=\"og:description\"]')||{}).content||''")
                    text = og if len(og) > 80 else pg.evaluate('document.body.innerText')[:6000]
                    links = pg.evaluate("[...document.querySelectorAll('a')].map(a=>a.href)")
                    m = FORM.search(text) or next((FORM.match(h) for h in links if FORM.match(h)), None)
                    form = m.group(0) if m else ''
                if not form:
                    rec.update(status='noform', reason='네이버 폼 링크 없음 (다른 방식 응모)')
                elif NEEDS_ME.search(text + ' ' + (x.get('how') or '') + ' ' + (x.get('condition') or '')):
                    rec.update(status='needs_me', form=form, reason='내 계정 몫: ' + ', '.join(sorted(set(NEEDS_ME.findall(text + (x.get('how') or ''))))))
                else:
                    st, L = nform.fill(pg, form, submit=False)
                    rec.update(status=st if st != 'done' else 'already', form=form, answers=L,
                               reason=(L[-1] if st == 'stuck' and L else ''))
            except Exception as e:
                rec.update(status='error', reason=str(e)[:150])
            its[k] = rec
            print(f"[{rec['status']}] {title[:40]} {rec.get('reason', '')[:80]}", flush=True)
            save(d)
            time.sleep(2)
            if time.time() - t0 > 15 * 60:
                print('시간 한도(15분) → 나머지는 내일'); break
        ctx.close()
    save(d)
    r, s = summary()
    print(f'응모 준비 {len(r)}건 · 확인 필요 {s}건')


if __name__ == '__main__':
    main()
