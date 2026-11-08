"""노트북 통합 실행 (2026-11-08~). Windows 작업 스케줄러가 호출.

  python run_all.py night    # 03:00 법원자료 수집 → 경매 예측(국토부 실거래 포함) → 웹페이지 → push
  python run_all.py outfit   # 06:00 날씨·코디 페이지 push → 메일
  python run_all.py brief    # 08:00 할 일·증시·경매 브리핑 메일
옵션: --test (제목 [테스트], 발송 기록 안 남김, push 안 함)  --force (이미 했어도 다시)  --no-mail  --steps a,b

비밀값은 저장소 밖 <저장소 상위 폴더>/.env (예: C:/auction_pc/.env) 에서만 읽는다.
단계가 실패해도 다음 단계는 진행, 로그는 <상위 폴더>/logs/날짜_작업.log.
"""
import argparse, base64, datetime as dt, glob, os, shutil, subprocess, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BASE = os.path.dirname(REPO)
KST = dt.timezone(dt.timedelta(hours=9))
LOG = None


def log(msg):
    line = f"[{dt.datetime.now(KST):%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    if LOG:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def load_env():
    p = os.environ.get('RUNNER_ENV') or os.path.join(BASE, '.env')
    if not os.path.exists(p):
        log(f'.env 없음: {p}'); return
    for raw in open(p, encoding='utf-8-sig'):
        s = raw.strip()
        if not s or s.startswith('#') or '=' not in s:
            continue
        k, v = s.split('=', 1)
        k, v = k.strip(), v.strip().strip('"\'')
        if v and not os.environ.get(k):
            os.environ[k] = v
    have = [k for k in ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REFRESH_TOKEN', 'MOLIT_API_KEY', 'GITHUB_TOKEN') if os.environ.get(k)]
    log(f'.env 읽음 (값 있는 키: {", ".join(have) or "없음"})')


def find_git():
    for p in (os.environ.get('GIT_EXE'),
              os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Programs\PortableGit\cmd\git.exe'), shutil.which('git'),
              os.path.join(BASE, 'tools', 'MinGit', 'cmd', 'git.exe'),   # 관리 프로그램이 설치한 git (다른 PC)
              os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Programs\MinGit\cmd\git.exe'),
              r'C:\Program Files\Git\cmd\git.exe'):
        if p and os.path.exists(p):
            return p
    raise RuntimeError('git 없음')


def find_claude():
    """PATH 에 없으면 Claude 데스크톱 앱이 받아 둔 최신 CLI 를 PATH 에 추가 (claude_summary.py 가 which('claude') 로 찾음)."""
    if shutil.which('claude'):
        return shutil.which('claude')
    c = os.environ.get('CLAUDE_EXE') or ''
    if not os.path.exists(c):
        cands = glob.glob(os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Claude-Data', '*', 'claude-code', '*', '*', 'claude.exe'))
        cands += glob.glob(os.path.join(os.path.expanduser('~'), '.local', 'bin', 'claude.exe'))
        c = max(cands, key=os.path.getmtime) if cands else ''
    if c:
        os.environ['PATH'] = os.path.dirname(c) + os.pathsep + os.environ['PATH']
    return c or None


def child_env(extra=None):
    e = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8', GCM_INTERACTIVE='never', GIT_TERMINAL_PROMPT='0')
    tok = os.environ.get('GITHUB_TOKEN')
    if tok:  # 로그온 안 된 상태(S4U)에선 자격 증명 관리자를 못 쓰므로 토큰을 git 설정으로 주입 (수집기의 git 에도 적용)
        e.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',
                 GIT_CONFIG_VALUE_0='Authorization: Basic ' + base64.b64encode(f'x-access-token:{tok}'.encode()).decode())
    e.update(extra or {})
    return e


def run(cmd, cwd=REPO, timeout=3600, extra=None, check=True):
    log('$ ' + ' '.join(str(c) for c in cmd))
    p = subprocess.Popen(cmd, cwd=cwd, env=child_env(extra), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    t0 = time.time()
    out = []
    try:
        for line in p.stdout:
            line = line.rstrip()
            out.append(line)
            log('  ' + line)
            if time.time() - t0 > timeout:
                p.kill(); raise TimeoutError(f'{timeout}s 초과')
        p.wait(timeout=max(10, timeout - (time.time() - t0)))
    except subprocess.TimeoutExpired:
        p.kill(); raise TimeoutError(f'{timeout}s 초과')
    if check and p.returncode != 0:
        raise RuntimeError(f'종료 코드 {p.returncode}')
    return p.returncode, '\n'.join(out)


def git(*args, check=True):
    return run([GIT, *args], check=check, timeout=300)


def pull():
    for n in range(3):
        if git('pull', '--rebase', '--autostash', '-X', 'theirs', 'origin', 'main', check=False)[0] == 0:
            return
        git('rebase', '--abort', check=False)
        time.sleep(15)
    log('pull 실패 → 현재 사본으로 진행')


def push(paths, msg):
    if ARGS.test:
        log('테스트 → push 생략'); return
    git('add', '-A', '--', *paths, check=False)
    if git('diff', '--cached', '--quiet', check=False)[0] == 0:
        log('변경 없음 → 커밋 생략'); return
    git('-c', 'user.name=laptop-bot', '-c', 'user.email=laptop@users.noreply.github.com', 'commit', '-q', '-m', msg)
    for n in range(1, 6):
        if git('pull', '--rebase', '-X', 'theirs', 'origin', 'main', check=False)[0] == 0 and git('push', 'origin', 'HEAD:main', check=False)[0] == 0:
            log(f'push 완료 ({n})'); return
        git('rebase', '--abort', check=False)
        time.sleep(10)
    raise RuntimeError('push 실패 (5회)')


def today():
    return dt.datetime.now(KST).date()


def heartbeat(job):
    """노트북 시작 기록을 push (Actions 예비 감시 backup.yml 이 '노트북 꺼짐' 판단에 씀, 2026-11-08).
    Actions 가 같은 작업을 이미 시작했으면(진행 중) 겹치지 않게 False."""
    import json
    sys.path.insert(0, HERE)
    import backup_due as bd
    now = dt.datetime.now(KST); day = bd.target_day(job, now).isoformat()
    hb = os.path.join(HERE, 'heartbeat')
    a = bd.jload(os.path.join(hb, 'actions.json')).get(job) or {}
    if not ARGS.force and a.get('date') == day and now < dt.datetime.fromisoformat(a['at']) + dt.timedelta(minutes=bd.MAX_MIN[job]):
        log(f"GitHub Actions 예비 실행이 {a['at'][11:16]} 에 시작함 → 겹치지 않게 건너뜀"); return False
    os.makedirs(hb, exist_ok=True)
    p = os.path.join(hb, 'laptop.json'); d = bd.jload(p)
    d[job] = dict(date=day, at=now.isoformat(timespec='seconds'))
    json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    try:
        push(['local_runner/heartbeat/laptop.json'], f'heartbeat: 노트북 {job} 시작 {now:%m-%d %H:%M} [skip ci]')
    except Exception as e:
        log(f'시작 기록 push 실패(계속 진행): {e}')
    return True


def ensure_browser():
    """Playwright 브라우저가 없으면 설치 (2026-11-08: 코디 카드 '브라우저 없음' 실패, 다른 PC 첫 실행). 이미 있으면 몇 초."""
    try:
        run([sys.executable, '-m', 'playwright', 'install', 'chromium'], timeout=900, check=False)
    except Exception as e:
        log(f'브라우저 확인 실패(계속 진행): {e}')


# ---------- 단계 ----------
def s_collect():
    job = os.environ.get('TENANT_JOB') or os.path.join(HERE, 'tenants_job.py')   # 2026-11-08 저장소로 옮김
    if not os.path.exists(job):
        raise RuntimeError(f'수집 프로그램 없음: {job}')
    a = [sys.executable, job, '--budget-min', os.environ.get('TENANT_BUDGET_MIN', '35')]
    if ARGS.test:
        a += ['--no-upload', '--limit', '2']
    run(a, cwd=os.path.dirname(job), timeout=75 * 60)
    pull()   # 수집기가 올린 tenants/latest.json 반영


def pred_day():
    # auction_predict.yml 과 같은 규칙: 18시 이후는 다음 날
    return (dt.datetime.now(KST) + dt.timedelta(hours=6)).date().isoformat()


def s_predict():
    import json
    if not os.environ.get('MOLIT_API_KEY'):
        log('⚠ MOLIT_API_KEY 없음 → 국토부 실거래는 캐시만 사용')
    p = os.path.join(REPO, 'auction_model', 'predictions', 'latest.json')
    have = json.load(open(p, encoding='utf-8')).get('date') if os.path.exists(p) else None
    if have == pred_day() and not ARGS.force:
        log(f'오늘({have}) 예측 이미 있음 → 건너뜀'); return
    # 국토부 실거래 수집(molit_cache)은 batch_predict 안에서 시군구별로 함
    run([sys.executable, 'batch_predict.py'], cwd=os.path.join(REPO, 'auction_model'), timeout=4 * 3600)


def s_page():
    am = os.path.join(REPO, 'auction_model')
    run([sys.executable, 'cards_page.py'], cwd=am, timeout=1800)
    try:
        run([sys.executable, 'villa_log.py'], cwd=am, timeout=1800)
    except Exception as e:
        log(f'villa_log 실패(무시): {e}')


def s_push_auction():
    push(['auction_model/predictions', 'auction_model/page', 'auction_model/molit_cache', 'auction_model/danji_map.json',
          'auction_model/villa', 'auction_model/officetel', 'auction_model/search_regions.json', 'local_runner/schedule.json'], f'auction: 예측 결과 {today()} (노트북)')


def mail_env():
    return {'TEST_MODE': '1' if ARGS.test else '0'}


def s_outfit():
    d = today().isoformat()
    if not ARGS.test and not ARGS.force and os.path.exists(os.path.join(REPO, 'outfit', d, 'sent.txt')):
        log('오늘 코디 메일 이미 보냄 → 건너뜀'); return
    od = os.path.join(REPO, 'outfit')
    skip = os.path.join(od, '.skip')
    if os.path.exists(skip):
        os.remove(skip)
    run([sys.executable, 'run_outfit.py'], cwd=od, timeout=1200, extra=mail_env())
    if os.path.exists(skip):
        return
    push([f'outfit/{d}'], f'outfit: {d} 코디 카드 (노트북)')
    if ARGS.no_mail:
        log('--no-mail → 메일 생략'); return
    if not ARGS.test:
        time.sleep(90)   # GitHub Pages 반영 대기
    run([sys.executable, 'run_outfit.py', 'send'], cwd=od, timeout=300, extra=mail_env())
    push([f'outfit/{d}/sent.txt'], f'outfit: {d} 메일 발송 기록 (노트북)')


def s_brief():
    d = today().isoformat()
    if not ARGS.test and not ARGS.force and os.path.exists(os.path.join(REPO, 'brief', 'sent', d + '.txt')):
        log('오늘 브리핑 이미 보냄 → 건너뜀'); return
    if ARGS.no_mail:
        log('--no-mail → 브리핑 생략'); return
    c = find_claude() if os.environ.get('BRIEF_SUMMARY', '').lower() == 'cli' else None
    log(f'증시 해설: {os.environ.get("BRIEF_SUMMARY") or "끔"}' + (f' ({c})' if c else ''))
    run([sys.executable, 'run_brief.py'], cwd=os.path.join(REPO, 'brief'), timeout=1800, extra=mail_env())
    push(['brief/sent'], f'brief: {d} 메일 발송 기록 (노트북)')


JOBS = {
    'night': [('collect', s_collect), ('predict', s_predict), ('page', s_page), ('push', s_push_auction)],
    'outfit': [('outfit', s_outfit)],
    'brief': [('brief', s_brief)],
}


def main():
    global LOG, ARGS, GIT
    ap = argparse.ArgumentParser()
    ap.add_argument('job', choices=JOBS)
    ap.add_argument('--test', action='store_true')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--no-mail', action='store_true')
    ap.add_argument('--steps')
    ARGS = ap.parse_args()
    logs = os.path.join(BASE, 'logs')
    os.makedirs(logs, exist_ok=True)
    LOG = os.path.join(logs, f'{today()}_{ARGS.job}{"_test" if ARGS.test else ""}.log')
    for f in glob.glob(os.path.join(logs, '*.log')):   # 30일 지난 로그 삭제
        if time.time() - os.path.getmtime(f) > 30 * 86400:
            os.remove(f)
    log(f'===== {ARGS.job} 시작 {" ".join(sys.argv[2:])}')
    load_env()
    GIT = find_git(); os.environ['GIT_EXE'] = GIT
    pull()
    if not ARGS.test and not ARGS.steps and not heartbeat(ARGS.job):
        log(f'===== {ARGS.job} 끝: 건너뜀 (Actions 진행 중)'); return 0
    ensure_browser()
    only = set(ARGS.steps.split(',')) if ARGS.steps else None
    fails = []
    for name, fn in JOBS[ARGS.job]:
        if only and name not in only:
            continue
        t0 = time.time()
        log(f'--- {name}')
        try:
            fn()
            log(f'--- {name} 완료 ({time.time() - t0:.0f}s)')
        except Exception as e:
            log(f'--- {name} 실패 ({time.time() - t0:.0f}s): {e}')
            log(traceback.format_exc())
            fails.append(name)
    log(f'===== {ARGS.job} 끝: ' + (f'실패 {fails}' if fails else '모두 성공'))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
