"""경매 검색 지역 설정 GUI (2026-11-08). 서울·경기 시군구를 체크해 저장 → 다음 예측부터 적용.
'저장 후 지금 검색' 은 run_all.py night 의 예측·웹페이지·push 단계만 바로 실행 (법원자료 수집 제외).
실행: 바탕화면 '경매 검색 지역' 바로가기 또는 pythonw region_gui.pyw"""
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


def main():
    cfg = load()
    apt = {tuple(x) for x in cfg.get('apt') or []}
    ot = set(cfg.get('ot') or [])
    root = tk.Tk(); root.title('경매 검색 지역'); root.geometry('820x820')
    nb = ttk.Notebook(root); nb.pack(fill='both', expand=True, padx=8, pady=8)
    V = {}

    def grid(parent, title, names, checked, key, cols):
        f = ttk.LabelFrame(parent, text=title); f.pack(fill='x', padx=6, pady=6)
        vs = []
        for i, n in enumerate(names):
            v = tk.BooleanVar(value=checked(n)); vs.append(v)
            ttk.Checkbutton(f, text=n, variable=v).grid(row=i // cols, column=i % cols, sticky='w', padx=4, pady=1)
            V[(key, n)] = v
        b = ttk.Frame(f); b.grid(row=len(names) // cols + 1, column=0, columnspan=cols, sticky='w', pady=3)
        ttk.Button(b, text='전체 선택', command=lambda: [v.set(True) for v in vs]).pack(side='left', padx=2)
        ttk.Button(b, text='전체 해제', command=lambda: [v.set(False) for v in vs]).pack(side='left', padx=2)

    t1 = ttk.Frame(nb); nb.add(t1, text='🏢 아파트')
    grid(t1, '서울', SEOUL, lambda n: ('서울', n) in apt, 'apt서울', 6)
    grid(t1, '경기 (남양주·구리 = 8호선역, 하남 = 5호선역 도보 15분 이내만 표시)', GYEONGGI, lambda n: ('경기', n) in apt, 'apt경기', 4)
    t2 = ttk.Frame(nb); nb.add(t2, text='🏬 오피스텔 (서울 · 역 도보 10분)')
    grid(t2, '서울', SEOUL, lambda n: n in ot, 'ot', 6)

    def save():
        new = dict(cfg)
        new['apt'] = [['서울', n] for n in SEOUL if V[('apt서울', n)].get()] + [['경기', n] for n in GYEONGGI if V[('apt경기', n)].get()]
        new['ot'] = [n for n in SEOUL if V[('ot', n)].get()]
        if not new['apt'] and not new['ot']:
            messagebox.showwarning('경매 검색 지역', '하나 이상 선택하세요'); return None
        with open(CFG, 'w', encoding='utf-8') as fp:
            json.dump(new, fp, ensure_ascii=False, indent=1)
        return new

    def on_save():
        n = save()
        if n: messagebox.showinfo('경매 검색 지역', f"저장했어요 (아파트 {len(n['apt'])}곳, 오피스텔 {len(n['ot'])}구).\n내일 03시 예측부터 적용됩니다.")

    def on_run():
        n = save()
        if not n: return
        py = sys.executable.replace('pythonw.exe', 'python.exe')
        subprocess.Popen([py, os.path.join(HERE, 'run_all.py'), 'night', '--steps', 'predict,page,push', '--force'],
                         cwd=HERE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        messagebox.showinfo('경매 검색 지역', '저장하고 검색(예측)을 시작했어요. 약 30분~1시간 뒤 웹페이지에 반영됩니다.\n'
                            '진행 기록: C:\\auction_pc\\logs\\오늘날짜_night.log')

    bar = ttk.Frame(root); bar.pack(fill='x', padx=8, pady=(0, 8))
    ttk.Button(bar, text='저장', command=on_save).pack(side='right', padx=4)
    ttk.Button(bar, text='저장 후 지금 검색', command=on_run).pack(side='right', padx=4)
    ttk.Label(bar, text='체크한 지역만 리치고 경매 목록에서 검색합니다.').pack(side='left')
    root.mainloop()


if __name__ == '__main__':
    main()
