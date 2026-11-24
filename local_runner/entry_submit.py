"""준비된 이벤트 제출 (2026-11-23 → 2026-11-25 사용자: 매일 다 시도해서 할 수 있는 건 다 하고 응모 완료 칸에 추가).
06:00 생활 메일 작업(run_all s_outfit)에서 entry_prep.py 다음에 자동으로 돈다.
entry_prep 이 'ready' 로 둔 네이버·구글 폼만 제출한다 (계정 몫·본인인증·퀴즈 추측이 없는 것).
'quiz'(정답 추측)는 자동 제출하지 않는다 — Claude 가 대화에서 정답을 찾아 gform/nform 으로 낸다.
제출하면 events_done.json·당첨 확인(prize_check) 기록 → 이벤트 페이지 다시 만들고 push.
사용: python entry_submit.py [--dry] [--only 제목일부]"""
import argparse, datetime as dt, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, 'brief'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--only')
    a = ap.parse_args()
    import entry_prep as ep, events_page as p, prize_check as pc, nform, gform, entry_login as el
    from playwright.sync_api import sync_playwright
    d = ep.load(); its = d.get('items') or {}
    done = p.done_map()
    todo = [(k, v) for k, v in its.items() if v.get('status') == 'ready' and k not in done and (not a.only or a.only in v['title'])]
    print(f'제출할 것 {len(todo)}건', flush=True)
    ok = []
    if todo:
        with sync_playwright() as pw:
            ctx = el.open_profile(pw, headless=True)
            pg = ctx.new_page()
            for k, v in todo:
                try:
                    if ep.is_google(v['form']):
                        st, L = gform.fill(pg, v['form'], submit=not a.dry, yt=nform.env().get('ENTRY_YT', ''))
                    else:
                        st, L = nform.fill(pg, v['form'], submit=not a.dry)
                except Exception as e:
                    st, L = 'stuck', [f'오류: {str(e)[:120]}']
                v['status'] = {'done': 'submitted', 'ready': 'ready'}.get(st, 'stuck')
                v['reason'] = '' if st in ('done', 'ready') else (L[-1] if L else '')
                v['answers'] = L
                print(f"[{v['status']}] {v['title']} {v['reason'][:100]}", flush=True)
                if st == 'done' and not a.dry:
                    ok.append(v['title'])
                    done[k] = dt.date.today().isoformat()
                    pc.add(k, v['title'], v['form'], v.get('org') or '', v.get('announce'), '폼에 적은 연락처로 개별 연락')
                ep.save(d)
                time.sleep(3)
            ctx.close()
    if a.dry:
        print('--dry: 제출 안 함'); return
    if ok:
        json.dump(done, open(p.DONE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    # 응모 시도 결과(칸 이동)도 페이지에 반영되게 항상 다시 만듦
    subprocess.run([sys.executable, 'events_page.py'], cwd=os.path.join(REPO, 'brief'), check=False)
    g = ['git', '-C', REPO]
    subprocess.run(g + ['add', 'brief/events_done.json', 'brief/events_entries.json', 'events'], check=False)
    subprocess.run(g + ['commit', '-q', '-m', f'events: 자동 응모 {len(ok)}건 ({dt.date.today()})'], check=False)
    subprocess.run(g + ['pull', '--rebase', '--autostash', '-q', 'origin', 'main'], check=False)
    subprocess.run(g + ['push', '-q', 'origin', 'HEAD:main'], check=False)
    print(f'응모 완료 {len(ok)}건: ' + ' / '.join(ok))


if __name__ == '__main__':
    main()
