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


def main():
    fail = []
    d, today, rain_hour, rainy = weather.build()
    d['looks'] = looks.pick(int(d['tmin']), int(d['tmax']), rainy, recent_titles(today), today.toordinal())
    out = os.path.join(HERE, today.isoformat()); os.makedirs(out, exist_ok=True)
    json.dump(d, open(os.path.join(out, 'd.json'), 'w'), ensure_ascii=False, indent=1)
    try:
        subprocess.run([sys.executable, '../cards.py', 'd.json'], cwd=out, check=True)
        subprocess.run([sys.executable, '../page.py', 'd.json', '.'], cwd=out, check=True)
    except Exception:
        traceback.print_exc(); fail.append('카드 이미지 생성')
    url = f'https://wpaud16.github.io/ML/outfit/{today.isoformat()}/'
    subj = f"[오늘의 코디] {d['date']} {d['tmin']}°/{d['tmax']}°" + (f', ☔ 비 {rain_hour}시부터' if rain_hour is not None else '')
    if os.environ.get('TEST_MODE') == '1':
        subj = '[테스트] ' + subj
    btn = (f'<p style="font-family:\'Apple SD Gothic Neo\',\'Malgun Gothic\',sans-serif;font-size:16px;margin:16px 0;text-align:center">'
           f'<a href="{url}" style="display:inline-block;background:#1F1D1A;color:#ffffff;text-decoration:none;font-weight:bold;padding:14px 24px;border-radius:10px">👉 오늘의 날씨·코디 보기</a></p>')
    if fail:
        btn = f'<p style="color:#d93025;font-size:13px">⚠️ 실패: {", ".join(fail)}</p>' + (
            f"<p>기온 {d['tmin']}°/{d['tmax']}° · {d['rain_title']}<br>코디: " + ' / '.join(l['title'] for l in d['looks']) + '</p>')
    print(subj, url)
    json.dump(dict(subject=subj, html=btn, text=f'오늘의 날씨·코디 보기: {url}'), open(os.path.join(HERE, '.mail.json'), 'w'), ensure_ascii=False)


def send():
    m = json.load(open(os.path.join(HERE, '.mail.json')))
    import google_api as g
    g.send_mail(TO, m['subject'], m['html'], m['text'])
    print('sent:', m['subject'])


if __name__ == '__main__':
    send() if sys.argv[1:] == ['send'] else main()
