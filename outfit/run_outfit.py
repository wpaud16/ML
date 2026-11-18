"""아침 날씨·코디 (Claude 예약 작업 대체, 2026-11-05). GitHub Actions 05:47 KST.
날씨(Open-Meteo) → 코디 3벌(규칙 기반) → cards.py/page.py → outfit/YYYY-MM-DD/ 커밋(워크플로가 push) → 링크 메일."""
import json, os, subprocess, sys, traceback, glob
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brief'))
import weather, looks

TO = os.environ.get('BRIEF_TO', 'wpaud16@naver.com')
SEND = os.environ.get('SEND_MAIL', '1') == '1'


def recent_titles(today):
    out = set()
    for f in sorted(glob.glob(os.path.join(HERE, '20??-??-??', 'd.json')))[-3:]:
        if os.path.basename(os.path.dirname(f)) < today.isoformat():
            try:
                out |= {l['title'] for l in json.load(open(f))['looks']}
            except Exception:
                pass
    return out


def sent_mark(today):
    return os.path.join(HERE, today.isoformat(), 'sent.txt')


def main():
    fail = []
    d, today, rain_hour, rainy = weather.build()
    # 하루 1통 (2026-11-05): GitHub 예약 실행이 몇 시간씩 밀려 수동 실행 뒤 늦게 또 돌 수 있음
    if os.environ.get('TEST_MODE') != '1' and os.path.exists(sent_mark(today)):
        print('오늘 메일 이미 보냄 → 건너뜀'); open(os.path.join(HERE, '.skip'), 'w').close(); return
    d['looks'] = looks.pick(int(d['tmin']), int(d['tmax']), rainy, recent_titles(today), today.toordinal())
    out = os.path.join(HERE, today.isoformat()); os.makedirs(out, exist_ok=True)
    json.dump(d, open(os.path.join(out, 'd.json'), 'w'), ensure_ascii=False, indent=1)
    try:
        subprocess.run([sys.executable, '../cards.py', 'd.json'], cwd=out, check=True)
        subprocess.run([sys.executable, '../page.py', 'd.json', '.'], cwd=out, check=True)
    except Exception:
        traceback.print_exc(); fail.append('카드 이미지 생성')
    url = f'https://wpaud16.github.io/ML/outfit/{today.isoformat()}/'
    subj = f"[JM's Schedule] {d['date']} {d['tmin']}°/{d['tmax']}°" + (f', ☔ 비 {rain_hour}시부터' if rain_hour is not None else '')
    if os.environ.get('TEST_MODE') == '1':
        subj = '[테스트] ' + subj
    btn = (f'<p style="font-family:\'Apple SD Gothic Neo\',\'Malgun Gothic\',sans-serif;font-size:16px;margin:16px 0;text-align:center">'
           f'<a href="{url}" style="display:inline-block;background:#1F1D1A;color:#ffffff;text-decoration:none;font-weight:bold;padding:14px 24px;border-radius:10px">👉 오늘의 날씨·코디 보기</a></p>')
    if fail:
        btn = f'<p style="color:#d93025;font-size:13px">⚠️ 실패: {", ".join(fail)}</p>' + (
            f"<p>기온 {d['tmin']}°/{d['tmax']}° · {d['rain_title']}<br>코디: " + ' / '.join(l['title'] for l in d['looks']) + '</p>')
    print(subj, url)
    json.dump(dict(subject=subj, test=os.environ.get('TEST_MODE') == '1', day=today.isoformat(), html=btn, text=f'오늘의 날씨·코디 보기: {url}'), open(os.path.join(HERE, '.mail.json'), 'w'), ensure_ascii=False)


DIV = '<hr style="border:none;border-top:1px solid #888888;margin:24px 0">'
DOC_LINK = 'https://docs.google.com/document/d/16r3j5QD_VJZKxL9hOxbv-Aj58jNbp92nCM4szeKrq6Y/edit'


def life_sections(day, test):
    """2026-11-18 사용자 결정: 아침 '생활' 메일 = 날씨·코디 + 오늘의 문장 + 할 일 + 응모 이벤트 + 지역 행사(월요일).
    증시·경매는 07:30 '투자' 메일(brief/run_brief.py). 각 섹션은 실패해도 나머지는 보낸다."""
    import datetime as dt, traceback as tb
    import quote, schedule_doc, events
    today = dt.date.fromisoformat(day)
    # 2026-11-18 순서: 오늘의 문장 → 날씨(바로가기) → 이벤트·행사(바로가기) → 할 일
    H, T, fails, after = [], [], [], None
    try:
        h, t, after = events.sections(today, test)
        H += h; T += t
    except Exception:
        tb.print_exc(); fails.append('이벤트·행사 바로가기')
    try:
        r = schedule_doc.plan(today, write=not test)
        h, t = schedule_doc.render(r); H.append(h); T.append(t)
        fails += r['warnings']
        H.append(f'<div style="color:#777;font-size:12px">📝 <a href="{DOC_LINK}">JM\'s Schedule 문서 열기</a> · '
                 '끝낸 일은 문서에서 체크해 주세요. 내일 아침 자동 정리됩니다.</div>')
    except Exception:
        tb.print_exc(); fails.append('오늘의 할 일 (문서 읽기/쓰기)')
    top = []   # 2026-11-18: 오늘의 문장은 메일 맨 위 (날씨보다 위)
    try:
        h, t = quote.render(quote.today_quote(today)); top = [(h, t)]
    except Exception:
        tb.print_exc(); fails.append('오늘의 문장')
    return top, H, T, fails, after


def send():
    if os.path.exists(os.path.join(HERE, '.skip')):
        print('skip'); return
    m = json.load(open(os.path.join(HERE, '.mail.json')))
    import google_api as g
    top, H, T, fails, after = life_sections(m['day'], m.get('test'))
    parts = [h for h, _ in top] + [m['html']] + H
    if fails:
        parts[0] = f'<p style="color:#d93025;font-size:13px">⚠️ 실패: {", ".join(fails)}</p>' + parts[0]
    html = ('<div style="font-family:-apple-system,Segoe UI,Malgun Gothic,sans-serif;max-width:600px;margin:auto;padding:8px;line-height:1.5;color:#222">'
            + DIV.join(parts) + '</div>')
    g.send_mail(TO, m['subject'], html, '\n\n'.join([t for _, t in top] + [m['text']] + T))
    print('sent:', m['subject'])
    if after:
        try:
            after()
        except Exception:
            traceback.print_exc()
    if not m.get('test'):
        open(os.path.join(HERE, m['day'], 'sent.txt'), 'w').write(m['subject'] + '\n')


if __name__ == '__main__':
    send() if sys.argv[1:] == ['send'] else main()
