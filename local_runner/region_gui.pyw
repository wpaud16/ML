"""경매 검색 지역 설정 GUI (2026-11-08). 서울·경기 시군구를 체크해 저장 → 다음 예측부터 적용.
통합 관리 프로그램(briefing_app.py '경매 지역' 탭)이 build() 를 불러 쓰고, 단독 실행도 된다(pythonw region_gui.pyw).
'저장 후 지금 검색' 은 run_all.py night 의 예측·웹페이지·push 단계만 바로 실행 (법원자료 수집 제외)."""
import json, os, subprocess, sys
import tkinter as tk
from tkinter import ttk, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CFG = os.path.join(REPO, 'auction_model', 'search_regions.json')
SEOUL = ['강남구', '강동구', '강북구', '강서구', '관악구', '광진구', '구로구', '금천구', '노원구', '도봉구', '동대문구', '동작구',
         '마포구', '서대문구', '서초구', '성동구', '성북구', '송파구', '양천구', '영등포구', '용산구', '은평구', '종로구', '중구', '중랑구']
GYEONGGI = ['수원시 장안구', '수원시 권선구', '수원시 팔달구', '수원시 영통구', '성남시 수정구', '성남시 중원구', '성남시 분당구',
            '의정부시', '안양시 만안구', '안양시 동안구', '부천시 원미구', '부천시 소사구', '부천시 오정구', '광명시', '평택시', '동두천시',
            '안산시 상록구', '안산시 단원구', '고양시 덕양구', '고양시 일산동구', '고양시 일산서구', '구리시', '남양주시', '오산시', '시흥시',
            '군포시', '의왕시', '하남시', '용인시 처인구', '용인시 기흥구', '용인시 수지구', '파주시', '이천시', '안성시', '김포시', '광주시',
            '양주시', '포천시', '여주시', '양평군']


def load():
    try:
        return json.load(open(CFG, encoding='utf-8'))
    except Exception:
        return {'apt': [], 'ot': list(SEOUL)}


def build(parent, run_cb=None):
    """parent 안에 지역 체크 화면을 만든다. run_cb: '저장 후 지금 검색' 때 부를 함수 (없으면 run_all.py 직접 실행)."""
    cfg = load()
    apt = {tuple(x) for x in cfg.get('apt') or []}
    ot = set(cfg.get('ot') or [])
    bar = ttk.Frame(parent); bar.pack(side='bottom', fill='x', padx=8, pady=(0, 8))   # 버튼이 화면 밖으로 밀리지 않게 먼저 아래에
    nb = ttk.Notebook(parent); nb.pack(fill='both', expand=True, padx=6, pady=6)
    V = {}

    def grid(p, title, names, checked, key, cols):
        f = ttk.LabelFrame(p, text=title); f.pack(fill='x', padx=6, pady=6)
        vs = []
        for i, n in enumerate(names):
            v = tk.BooleanVar(value=checked(n)); vs.append(v)
            ttk.Checkbutton(f, text=n, variable=v).grid(row=i // cols, column=i % cols, sticky='w', padx=4, pady=1)
            V[(key, n)] = v
        b = ttk.Frame(f); b.grid(row=len(names) // cols + 1, column=0, columnspan=cols, sticky='w', pady=3)
        ttk.Button(b, text='전체 선택', command=lambda: [v.set(True) for v in vs]).pack(side='left', padx=2)
        ttk.Button(b, text='전체 해제', command=lambda: [v.set(False) for v in vs]).pack(side='left', padx=2)

    # 2026-11-18: 종류별 최저가 범위 (억, 비우면 제한 없음)
    price = cfg.get('price') or {}
    P = {}

    def price_box(p, key, default=(None, None)):
        f = ttk.LabelFrame(p, text='최저가 범위 (억 원 · 비워 두면 제한 없음)'); f.pack(fill='x', padx=6, pady=6)
        lo, hi = (list(price.get(key, default) or [None, None]) + [None, None])[:2]
        a = tk.StringVar(value='' if lo is None else f'{lo:g}'); b = tk.StringVar(value='' if hi is None else f'{hi:g}')
        ttk.Entry(f, textvariable=a, width=8, justify='right').pack(side='left', padx=(8, 2), pady=6)
        ttk.Label(f, text='억 이상  ~').pack(side='left')
        ttk.Entry(f, textvariable=b, width=8, justify='right').pack(side='left', padx=(8, 2))
        ttk.Label(f, text='억 이하').pack(side='left')
        P[key] = (a, b)

    t1 = ttk.Frame(nb); nb.add(t1, text='🏢 아파트')
    price_box(t1, 'apt')
    grid(t1, '서울', SEOUL, lambda n: ('서울', n) in apt, 'apt서울', 7)
    grid(t1, '경기 (남양주·구리 = 8호선역, 하남 = 5호선역 도보 15분 이내만 표시)', GYEONGGI, lambda n: ('경기', n) in apt, 'apt경기', 5)
    t2 = ttk.Frame(nb); nb.add(t2, text='🏬 오피스텔')
    price_box(t2, 'ot')
    grid(t2, '서울 (역 도보 10분)', SEOUL, lambda n: n in ot, 'ot', 7)
    for key, title, default in (('shop', '🏪 상가', (None, None)), ('bldg', '🏙 건물', (None, 20))):
        sel = cfg.get(key)
        sel = set(SEOUL if sel is None else sel)
        t = ttk.Frame(nb); nb.add(t, text=title)
        price_box(t, key, default)
        grid(t, '서울 (역 도보 15분)', SEOUL, lambda n, s=sel: n in s, key, 7)

    def num(s):
        s = s.strip().replace(',', '').replace('억', '')
        if not s:
            return None
        return float(s)

    def save():
        new = dict(cfg)
        new['apt'] = [['서울', n] for n in SEOUL if V[('apt서울', n)].get()] + [['경기', n] for n in GYEONGGI if V[('apt경기', n)].get()]
        for k in ('ot', 'shop', 'bldg'):
            new[k] = [n for n in SEOUL if V[(k, n)].get()]
        if not any(new[k] for k in ('apt', 'ot', 'shop', 'bldg')):
            messagebox.showwarning('경매 검색 지역', '하나 이상 선택하세요'); return None
        pr = {}
        names = {'apt': '아파트', 'ot': '오피스텔', 'shop': '상가', 'bldg': '건물'}
        for k, (a, b) in P.items():
            try:
                lo, hi = num(a.get()), num(b.get())
            except ValueError:
                messagebox.showwarning('경매 검색 지역', f'{names[k]} 최저가 범위는 숫자(억)로 적어 주세요'); return None
            if lo is not None and hi is not None and lo > hi:
                messagebox.showwarning('경매 검색 지역', f'{names[k]} 최저가: 하한이 상한보다 커요'); return None
            pr[k] = [lo, hi]
        new['price'] = pr
        new['_note'] = ('경매 검색 조건 (local_runner/region_gui.pyw 로 수정). apt = 아파트 시군구, ot/shop/bldg = 오피스텔·상가·건물 서울 구, '
                        'price = 종류별 최저가 범위 [하한억, 상한억] (null = 제한 없음).')
        with open(CFG, 'w', encoding='utf-8') as fp:
            json.dump(new, fp, ensure_ascii=False, indent=1)
        return new

    def on_save():
        n = save()
        if n: messagebox.showinfo('경매 검색 지역', f"저장했어요 (아파트 {len(n['apt'])}곳, 오피스텔 {len(n['ot'])}구, "
                                               f"상가 {len(n['shop'])}구, 건물 {len(n['bldg'])}구).\n다음 03시 예측부터 적용됩니다.")

    def on_run():
        n = save()
        if not n: return
        if run_cb:
            run_cb(); return
        py = sys.executable.replace('pythonw.exe', 'python.exe')
        subprocess.Popen([py, os.path.join(HERE, 'run_all.py'), 'night', '--steps', 'predict,page,push', '--force'],
                         cwd=HERE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        messagebox.showinfo('경매 검색 지역', '저장하고 검색(예측)을 시작했어요. 약 30분~1시간 뒤 웹페이지에 반영됩니다.')

    ttk.Button(bar, text='저장', command=on_save).pack(side='right', padx=4)
    ttk.Button(bar, text='저장 후 지금 검색', command=on_run).pack(side='right', padx=4)
    ttk.Label(bar, text='체크한 지역·최저가 범위 안의 물건만 검색합니다.').pack(side='left')


def main():
    root = tk.Tk(); root.title('경매 검색 지역'); root.geometry('820x820')
    build(root)
    root.mainloop()


if __name__ == '__main__':
    main()
