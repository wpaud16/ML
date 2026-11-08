"""브리핑 관리 프로그램 (2026-11-08) — 실행 파일(브리핑관리.exe) 하나 + 같은 폴더의 .env 로 어느 PC 에서든.

탭: ▶ 실행(경매 새벽 작업·코디·브리핑 지금/시험 실행) · ⏰ 예약(작업 스케줄러 시각·등록) · 🗺 경매 지역 · ⚙ 설치·상태
폴더 구조 (exe 가 있는 폴더 = 설치 폴더):
  <설치 폴더>/브리핑관리.exe, .env, ML/(저장소, 자동 clone), logs/, tools/(git·파이썬 설치 파일), app_settings.json
처음 실행하면 '설치·점검' 이 파이썬 3.11(사용자 설치)·git(MinGit)·저장소·패키지·브라우저를 자동으로 준비한다.
명령줄: 브리핑관리.exe --register s4u   (관리자 권한으로 예약 등록, 프로그램이 스스로 호출)
빌드: python local_runner/build_app.py"""
import base64, ctypes, datetime as dt, glob, json, os, queue, re, shutil, subprocess, sys, threading, urllib.request, zipfile
import tkinter as tk
from tkinter import ttk, messagebox

APP = '브리핑 관리'
FROZEN = getattr(sys, 'frozen', False)
HOME = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO = os.path.join(HOME, 'ML')
LR = os.path.join(REPO, 'local_runner')
ENV = os.path.join(HOME, '.env')
LOGS = os.path.join(HOME, 'logs')
TOOLS = os.path.join(HOME, 'tools')
SETTINGS = os.path.join(HOME, 'app_settings.json')
REPO_URL = 'https://github.com/wpaud16/ML.git'
PY_URL = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe'
GIT_URL = 'https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/MinGit-2.47.1-64-bit.zip'
NOWIN = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
ENV_KEYS = [('GOOGLE_CLIENT_ID', '구글 OAuth 클라이언트 ID'), ('GOOGLE_CLIENT_SECRET', '구글 OAuth 보안 비밀번호'),
            ('GOOGLE_REFRESH_TOKEN', '구글 토큰 (⚙ 탭 버튼으로 발급)'), ('MOLIT_API_KEY', '국토부 실거래 키 (Decoding)'),
            ('GITHUB_TOKEN', 'GitHub 토큰 (로그아웃 실행·push)'), ('BRIEF_SUMMARY', 'cli = Claude CLI 증시 해설')]
JOBS = [('night', '🏠 경매 새벽 작업', '법원자료 → 예측 → 웹페이지', '03:00'),
        ('outfit', '👕 날씨·코디 메일', '', '06:00'),
        ('brief', '📋 아침 브리핑 메일', '할 일·증시·경매', '08:00')]
TASK_PATH = '\\ML\\'


# ---------- 공통 ----------
def settings():
    try:
        return json.load(open(SETTINGS, encoding='utf-8'))
    except Exception:
        return {}


def save_settings(s):
    json.dump(s, open(SETTINGS, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def read_env():
    d = {}
    if os.path.exists(ENV):
        for ln in open(ENV, encoding='utf-8-sig'):
            m = re.match(r'\s*([A-Z_]+)\s*=\s*(.*)$', ln)
            if m: d[m.group(1)] = m.group(2).strip().strip('"\'')
    return d


def ensure_env_file():
    if not os.path.exists(ENV):
        with open(ENV, 'w', encoding='utf-8') as f:
            f.write('# 브리핑 비밀값 — 이 파일은 저장소에 올리지 않음. 이름=값 (따옴표·공백 없이)\n')
            for k, _ in ENV_KEYS:
                f.write(f'{k}={"cli" if k == "BRIEF_SUMMARY" else ""}\n')


def py_ok(p):
    try:
        out = subprocess.run([p, '-c', 'import sys;print(sys.version_info[:2]>=(3,10))'], capture_output=True, text=True,
                             timeout=30, creationflags=NOWIN).stdout.strip()
        return out == 'True'
    except Exception:
        return False


def find_python():
    s = settings().get('python')
    cands = [s] if s else []
    cands += sorted(glob.glob(os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Programs\Python\Python3*\python.exe')), reverse=True)
    w = shutil.which('python')
    if w and 'WindowsApps' not in w: cands.append(w)
    cands += sorted(glob.glob(r'C:\Program Files\Python3*\python.exe'), reverse=True)
    for c in cands:
        if c and os.path.exists(c) and py_ok(c):
            return c
    return None


def find_git():
    for p in (os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Programs\PortableGit\cmd\git.exe'), shutil.which('git'),
              os.path.join(TOOLS, 'MinGit', 'cmd', 'git.exe'), os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Programs\MinGit\cmd\git.exe'),
              r'C:\Program Files\Git\cmd\git.exe'):
        if p and os.path.exists(p):
            return p
    return None


def find_claude():
    w = shutil.which('claude')
    if w: return w
    c = glob.glob(os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Claude-Data', '*', 'claude-code', '*', '*', 'claude.exe'))
    c += glob.glob(os.path.join(os.path.expanduser('~'), '.local', 'bin', 'claude.exe'))
    return max(c, key=os.path.getmtime) if c else None


def ps(script, elevated=False):
    """PowerShell 스크립트 실행 (-EncodedCommand 로 따옴표 문제 없이). 반환 (코드, 출력)."""
    enc = base64.b64encode(('$ErrorActionPreference="Stop";$ProgressPreference="SilentlyContinue";[Console]::OutputEncoding=[Text.Encoding]::UTF8\n'
                            + script).encode('utf-16-le')).decode()
    r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', enc],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=NOWIN)
    err = '' if r.returncode == 0 else re.sub(r'#< CLIXML.*', '', r.stderr, flags=re.S).strip()
    return r.returncode, (r.stdout.strip() + ('\n' + err if err else '')).strip()


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ---------- 예약 등록 ----------
def register(logon):
    """logon: 'Interactive'(로그인 중에만, 관리자 불필요) 또는 'S4U'(로그아웃에도, 관리자 필요)."""
    py = find_python()
    if not py: return 1, '파이썬이 없어요 — ⚙ 탭에서 설치·점검을 먼저 하세요'
    if logon == 'S4U' and not read_env().get('GITHUB_TOKEN'):
        return 1, '.env 의 GITHUB_TOKEN 이 비어 있어요 (로그아웃 상태에선 토큰 없이 push 불가)'
    exe = py if logon == 'S4U' else (py[:-len('python.exe')] + 'pythonw.exe' if py.endswith('python.exe') else py)
    st = settings().get('schedule', {})
    lines = [f'$p = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\\$env:USERNAME" -LogonType {logon} -RunLevel Limited']
    for job, label, _, default in JOBS:
        s = st.get(job, {})
        name = 'ML_' + job.capitalize()
        if not s.get('enabled', True):
            lines.append(f'Unregister-ScheduledTask -TaskPath "{TASK_PATH}" -TaskName "{name}" -Confirm:$false -ErrorAction SilentlyContinue')
            lines.append(f'Write-Output "해제: {name}"'); continue
        at = s.get('time', default)
        limit = 6 if job == 'night' else 1
        lines += [
            f'$a = New-ScheduledTaskAction -Execute "{exe}" -Argument \'"{os.path.join(LR, "run_all.py")}" {job}\' -WorkingDirectory "{LR}"',
            f'$t = New-ScheduledTaskTrigger -Daily -At "{at}"',
            f'$s = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries '
            f'-ExecutionTimeLimit (New-TimeSpan -Hours {limit}) -MultipleInstances IgnoreNew -RestartCount 1 -RestartInterval (New-TimeSpan -Minutes 10)',
            f'Register-ScheduledTask -TaskPath "{TASK_PATH}" -TaskName "{name}" -Action $a -Trigger $t -Settings $s -Principal $p -Force | Out-Null',
            f'Write-Output "등록: {name} {at} ({logon})"']
    lines.append('if (Get-ScheduledTask -TaskName "AuctionTenants" -ErrorAction SilentlyContinue) { Disable-ScheduledTask -TaskName "AuctionTenants" | Out-Null }')
    return ps('\n'.join(lines))


def task_status():
    code, out = ps(f'Get-ScheduledTask -TaskPath "{TASK_PATH}" -ErrorAction SilentlyContinue | ForEach-Object {{ $i = $_ | Get-ScheduledTaskInfo; '
                   '"{0}|{1}|{2}|{3}|{4}|{5}" -f $_.TaskName,$_.State,$_.Principal.LogonType,$i.LastRunTime,$i.LastTaskResult,$i.NextRunTime }')
    res = {}
    for ln in out.splitlines():
        p = ln.split('|')
        if len(p) == 6: res[p[0]] = dict(state=p[1], logon=p[2], last=p[3], result=p[4], next=p[5])
    return res


def last_result(job):
    fs = sorted(glob.glob(os.path.join(LOGS, f'*_{job}.log')))
    if not fs: return '기록 없음'
    for ln in reversed(open(fs[-1], encoding='utf-8', errors='replace').read().splitlines()):
        m = re.match(r'\[(\S+ \S+)\] ===== \w+ 끝: (.*)', ln)
        if m: return f'{m.group(1)[5:16]} {m.group(2)}'
    return os.path.basename(fs[-1])[:10] + ' 실행 중이거나 중단됨'


# ---------- 화면 ----------
class App:
    def __init__(self, root):
        self.root = root; self.q = queue.Queue(); self.busy = False
        root.title(APP); root.geometry('900x720'); root.minsize(760, 560)
        nb = ttk.Notebook(root); nb.pack(fill='both', expand=True, padx=8, pady=(8, 4))
        self.t_run, self.t_sch, self.t_reg, self.t_set = (ttk.Frame(nb) for _ in range(4))
        nb.add(self.t_run, text='▶ 실행'); nb.add(self.t_sch, text='⏰ 예약'); nb.add(self.t_reg, text='🗺 경매 지역'); nb.add(self.t_set, text='⚙ 설치·상태')
        lf = ttk.LabelFrame(root, text='진행 기록'); lf.pack(fill='both', expand=False, padx=8, pady=(0, 8))
        self.txt = tk.Text(lf, height=9, wrap='none', font=('Consolas', 9)); self.txt.pack(fill='both', expand=True, side='left')
        sb = ttk.Scrollbar(lf, command=self.txt.yview); sb.pack(side='right', fill='y'); self.txt['yscrollcommand'] = sb.set
        self.build_run(); self.build_sch(); self.build_set(); self.build_reg()
        root.after(200, self.pump)
        if not os.path.isdir(os.path.join(REPO, '.git')) or not find_python():
            self.say('처음 실행이에요 → ⚙ 설치·상태 탭에서 [설치·점검] 을 눌러 주세요.'); nb.select(self.t_set)

    # 출력
    def say(self, s):
        self.q.put(s)

    def pump(self):
        try:
            while True:
                s = self.q.get_nowait()
                if callable(s): s(); continue
                self.txt.insert('end', s + '\n'); self.txt.see('end')
        except queue.Empty:
            pass
        self.root.after(200, self.pump)

    def bg(self, fn, *a):
        if self.busy:
            messagebox.showinfo(APP, '다른 작업이 진행 중이에요. 끝난 뒤 다시 눌러 주세요.'); return
        self.busy = True
        def w():
            try: fn(*a)
            except Exception as e: self.say(f'오류: {e}')
            finally:
                self.busy = False; self.q.put(self.refresh)
        threading.Thread(target=w, daemon=True).start()

    def stream(self, cmd, cwd=None):
        self.say('$ ' + ' '.join(cmd))
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                             env=dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8'), creationflags=NOWIN)
        for ln in p.stdout: self.say('  ' + ln.rstrip())
        p.wait(); return p.returncode

    # ▶ 실행
    def build_run(self):
        f = self.t_run
        ttk.Label(f, text='지금 바로 실행합니다. [시험] 은 제목에 [테스트] · 발송 기록·push 안 남김.', foreground='#555').pack(anchor='w', padx=10, pady=8)
        self.force = tk.BooleanVar(value=False)
        self.lbl_last = {}
        for job, label, sub, _ in JOBS:
            r = ttk.LabelFrame(f, text=label + (f'  ({sub})' if sub else '')); r.pack(fill='x', padx=10, pady=6)
            ttk.Button(r, text='지금 실행', command=lambda j=job: self.run_job(j)).pack(side='left', padx=6, pady=6)
            ttk.Button(r, text='시험 (테스트 메일)', command=lambda j=job: self.run_job(j, test=True)).pack(side='left', padx=6)
            if job == 'night':
                ttk.Button(r, text='예측·웹페이지만', command=lambda: self.run_job('night', steps='predict,page,push', force=True)).pack(side='left', padx=6)
            self.lbl_last[job] = ttk.Label(r, text='', foreground='#555'); self.lbl_last[job].pack(side='left', padx=12)
        ttk.Checkbutton(f, text='오늘 이미 보냈어도 다시 실행 (--force)', variable=self.force).pack(anchor='w', padx=12, pady=6)
        ttk.Button(f, text='📂 로그 폴더 열기', command=lambda: os.startfile(LOGS) if os.path.isdir(LOGS) else None).pack(anchor='w', padx=12)

    def run_job(self, job, test=False, steps=None, force=False):
        py = find_python()
        if not py or not os.path.exists(os.path.join(LR, 'run_all.py')):
            messagebox.showwarning(APP, '먼저 ⚙ 설치·상태 탭에서 [설치·점검] 을 해 주세요.'); return
        cmd = [py, os.path.join(LR, 'run_all.py'), job] + (['--test'] if test else []) + (['--steps', steps] if steps else []) \
              + (['--force'] if (force or self.force.get()) else [])
        self.bg(lambda: self.say(f'끝 (종료 코드 {self.stream(cmd, cwd=LR)})'))

    # ⏰ 예약
    def build_sch(self):
        f = self.t_sch; st = settings().get('schedule', {})
        ttk.Label(f, text='매일 이 시각에 자동 실행 (절전 중이면 깨움 · 꺼져 있었으면 켜지자마자 실행).', foreground='#555').pack(anchor='w', padx=10, pady=8)
        self.sv = {}
        for job, label, _, default in JOBS:
            r = ttk.Frame(f); r.pack(fill='x', padx=12, pady=4)
            en = tk.BooleanVar(value=st.get(job, {}).get('enabled', True)); tm = tk.StringVar(value=st.get(job, {}).get('time', default))
            ttk.Checkbutton(r, text=label, variable=en, width=22).pack(side='left')
            ttk.Entry(r, textvariable=tm, width=7).pack(side='left', padx=6)
            lb = ttk.Label(r, text='', foreground='#555'); lb.pack(side='left', padx=10)
            self.sv[job] = (en, tm, lb)
        b = ttk.Frame(f); b.pack(fill='x', padx=12, pady=10)
        ttk.Button(b, text='등록 (로그인 중에만 실행)', command=lambda: self.do_register('Interactive')).pack(side='left', padx=4)
        ttk.Button(b, text='등록 (로그아웃에도 실행 · 관리자 승인)', command=lambda: self.do_register('S4U')).pack(side='left', padx=4)
        ttk.Button(b, text='새로고침', command=self.refresh).pack(side='left', padx=4)
        ttk.Label(f, text='로그아웃에도 실행하려면 .env 에 GITHUB_TOKEN 이 있어야 하고, 누르면 Windows 관리자 승인 창이 떠요.\n'
                          'GitHub Actions 예비 실행은 그대로 있어요(노트북이 이미 보낸 날은 건너뜀).', foreground='#555', wraplength=820).pack(anchor='w', padx=12)

    def save_schedule(self):
        s = settings(); sch = {}
        for job, (en, tm, _) in self.sv.items():
            t = tm.get().strip()
            if not re.fullmatch(r'([01]?\d|2[0-3]):[0-5]\d', t):
                messagebox.showwarning(APP, f'시각 형식이 이상해요: {t} (예: 03:00)'); return False
            sch[job] = dict(enabled=en.get(), time=t.zfill(5))
        s['schedule'] = sch; save_settings(s); return True

    def do_register(self, logon):
        if not self.save_schedule(): return
        if logon == 'S4U' and not is_admin():
            if not read_env().get('GITHUB_TOKEN'):
                messagebox.showwarning(APP, '.env 의 GITHUB_TOKEN 이 비어 있어요.'); return
            exe, args = (sys.executable, '--register s4u') if FROZEN else (sys.executable.replace('python.exe', 'pythonw.exe'), f'"{os.path.abspath(__file__)}" --register s4u')
            r = ctypes.windll.shell32.ShellExecuteW(None, 'runas', exe, args, HOME, 1)
            self.say('관리자 승인 창을 띄웠어요. 승인하면 등록 결과 창이 떠요.' if r > 32 else f'관리자 실행 실패/취소 ({r})')
            self.root.after(8000, self.refresh); return
        def w():
            code, out = register(logon); self.say(out or f'종료 코드 {code}')
        self.bg(w)

    # 🗺 경매 지역 (저장소의 region_gui.pyw 를 불러서 → 저장소가 업데이트되면 함께 바뀜)
    def build_reg(self):
        for w in self.t_reg.winfo_children(): w.destroy()
        p = os.path.join(LR, 'region_gui.pyw')
        if not os.path.exists(p):
            ttk.Label(self.t_reg, text='설치·점검 후 사용할 수 있어요.').pack(pady=20); return
        try:
            import importlib.machinery, importlib.util
            ld = importlib.machinery.SourceFileLoader('region_gui', p)
            m = importlib.util.module_from_spec(importlib.util.spec_from_loader('region_gui', ld)); ld.exec_module(m)
            m.build(self.t_reg, run_cb=lambda: self.run_job('night', steps='predict,page,push', force=True))
        except Exception as e:
            ttk.Label(self.t_reg, text=f'지역 화면을 열지 못했어요: {e}').pack(pady=20)

    # ⚙ 설치·상태
    def build_set(self):
        f = self.t_set
        ttk.Label(f, text=f'설치 폴더: {HOME}', foreground='#555').pack(anchor='w', padx=10, pady=(8, 2))
        ttk.Button(f, text='🔧 설치·점검 (파이썬·git·저장소·패키지·브라우저)', command=lambda: self.bg(self.setup)).pack(anchor='w', padx=13, pady=(6, 0))
        b = ttk.Frame(f); b.pack(fill='x', padx=10, pady=6)
        ttk.Button(b, text='📝 .env 열기', command=self.open_env).pack(side='left', padx=3)
        ttk.Button(b, text='🔄 새로고침', command=self.refresh).pack(side='left', padx=3)
        ttk.Button(b, text='🔑 구글 토큰 발급', command=self.google_auth).pack(side='left', padx=3)
        ttk.Button(b, text='🤖 Claude 로그인', command=self.claude_login).pack(side='left', padx=3)
        self.envf = ttk.LabelFrame(f, text='.env 값 (값은 표시하지 않음)'); self.envf.pack(fill='x', padx=10, pady=6)
        self.stf = ttk.LabelFrame(f, text='프로그램'); self.stf.pack(fill='x', padx=10, pady=6)
        self.refresh()

    def open_env(self):
        ensure_env_file(); subprocess.Popen(['notepad', ENV])
        self.say('.env 를 메모장으로 열었어요. 저장한 뒤 [새로고침] 하세요.')

    def google_auth(self):
        py = find_python(); g = os.path.join(LR, 'google_auth.py')
        if not py or not os.path.exists(g):
            messagebox.showwarning(APP, '먼저 [설치·점검] 을 해 주세요.'); return
        self.bg(lambda: self.stream([py, g]))

    def claude_login(self):
        c = find_claude()
        if not c:
            messagebox.showinfo(APP, 'Claude CLI 가 없어요. Claude 데스크톱 앱을 설치하거나 https://claude.com/claude-code 안내대로 설치하세요.\n'
                                    '(없으면 증시 해설만 빠지고 나머지는 정상)'); return
        subprocess.Popen(['cmd', '/k', c], creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.say('새 창에서 Claude 로그인(구독 계정 선택 → 브라우저 승인) 후 /exit 로 닫으세요.')

    def refresh(self):
        e = read_env()
        for w in self.envf.winfo_children(): w.destroy()
        for i, (k, d) in enumerate(ENV_KEYS):
            ok = bool(e.get(k))
            ttk.Label(self.envf, text=('✅ ' if ok else '⬜ ') + k, width=26).grid(row=i, column=0, sticky='w', padx=6)
            ttk.Label(self.envf, text=d, foreground='#555').grid(row=i, column=1, sticky='w')
        for w in self.stf.winfo_children(): w.destroy()
        py, git, cl = find_python(), find_git(), find_claude()
        for i, (k, v) in enumerate([('파이썬', py), ('git', git), ('저장소', REPO if os.path.isdir(os.path.join(REPO, '.git')) else None),
                                    ('Claude CLI', cl)]):
            ttk.Label(self.stf, text=('✅ ' if v else '⬜ ') + k, width=14).grid(row=i, column=0, sticky='w', padx=6)
            ttk.Label(self.stf, text=v or '없음', foreground='#555').grid(row=i, column=1, sticky='w')
        try: ts = task_status()
        except Exception: ts = {}
        for job, (en, tm, lb) in getattr(self, 'sv', {}).items():
            t = ts.get('ML_' + job.capitalize())
            lb.config(text=(f"{'등록됨' if t['state'] != 'Disabled' else '꺼짐'} · {'로그아웃에도' if t['logon'] == 'S4U' else '로그인 중에만'} · 다음 {t['next'][5:]}"
                            if t else '미등록'))
        for job, lb in getattr(self, 'lbl_last', {}).items():
            lb.config(text='최근: ' + last_result(job))

    def setup(self):
        os.makedirs(TOOLS, exist_ok=True); ensure_env_file()
        # 1) 파이썬
        py = find_python()
        if not py:
            dst = os.path.join(TOOLS, os.path.basename(PY_URL))
            self.say('파이썬 3.11 내려받는 중… (python.org)'); urllib.request.urlretrieve(PY_URL, dst)
            self.say('파이썬 설치 중 (사용자 계정에만, 관리자 불필요)…')
            subprocess.run([dst, '/quiet', 'InstallAllUsers=0', 'PrependPath=0', 'Include_test=0', 'Include_launcher=0', 'Shortcuts=0'], check=True)
            py = find_python()
            if not py: raise RuntimeError('파이썬 설치 확인 실패')
        s = settings(); s['python'] = py; save_settings(s); self.say(f'✅ 파이썬: {py}')
        # 2) git
        git = find_git()
        if not git:
            z = os.path.join(TOOLS, 'MinGit.zip')
            self.say('git(MinGit) 내려받는 중… (github.com/git-for-windows)'); urllib.request.urlretrieve(GIT_URL, z)
            zipfile.ZipFile(z).extractall(os.path.join(TOOLS, 'MinGit')); os.remove(z)
            git = find_git()
            subprocess.run([git, 'config', '--global', 'http.sslBackend', 'schannel'], creationflags=NOWIN)
        self.say(f'✅ git: {git}')
        # 3) 저장소
        if not os.path.isdir(os.path.join(REPO, '.git')):
            self.say('저장소 내려받는 중 (처음 한 번, 몇 분)…')
            if self.stream([git, 'clone', REPO_URL, REPO]) != 0: raise RuntimeError('저장소 clone 실패')
        else:
            self.stream([git, '-C', REPO, 'pull', '--rebase', '--autostash', '-X', 'theirs', 'origin', 'main'])
        # 4) 패키지·브라우저
        self.say('패키지 설치·확인 중…')
        if self.stream([py, '-m', 'pip', 'install', '-q', '--disable-pip-version-check', '-r', os.path.join(LR, 'requirements.txt')]) != 0:
            raise RuntimeError('패키지 설치 실패 (위 기록 확인)')
        self.say('브라우저(Playwright Chromium) 설치·확인 중…')
        if self.stream([py, '-m', 'playwright', 'install', 'chromium']) != 0:
            raise RuntimeError('브라우저 설치 실패 (위 기록 확인)')
        self.q.put(self.build_reg)
        miss = [k for k, _ in ENV_KEYS[:4] if not read_env().get(k)]
        self.say('✅ 설치·점검 끝.' + (f' .env 에 비어 있는 값: {", ".join(miss)}' if miss else '') +
                 ' → ⏰ 예약 탭에서 등록하세요.')


def main():
    if '--register' in sys.argv:   # 관리자 권한으로 다시 실행된 경우
        logon = 'S4U' if 's4u' in [a.lower() for a in sys.argv] else 'Interactive'
        code, out = register(logon)
        r = tk.Tk(); r.withdraw()
        (messagebox.showinfo if code == 0 else messagebox.showerror)(APP, out or f'종료 코드 {code}')
        return
    root = tk.Tk()
    try: ttk.Style().theme_use('vista')
    except Exception: pass
    App(root); root.mainloop()


if __name__ == '__main__':
    main()
