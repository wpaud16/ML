"""탐색 (2026-11-05): GitHub 서버에서 법원경매정보(courtauction.go.kr) 접속 가능한지 — 가능하면 임차인 수집을 노트북 대신 GitHub 으로."""
import json, os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, 'probe'); os.makedirs(OUT, exist_ok=True)
res = {}
for u in ['https://www.courtauction.go.kr/', 'https://www.courtauction.go.kr/pgj/index.on']:
    r = subprocess.run(['curl', '-sS', '-L', '-m', '30', '-o', '/tmp/c.html', '-w', '%{http_code} %{size_download} %{time_total} %{url_effective}', u],
                       capture_output=True, text=True)
    head = open('/tmp/c.html', encoding='utf-8', errors='replace').read()[:200] if os.path.exists('/tmp/c.html') else ''
    res[u] = dict(out=r.stdout, err=r.stderr[-200:], head=head)
    if os.path.exists('/tmp/c.html'): os.remove('/tmp/c.html')
ip = subprocess.run(['curl', '-s', '-m', '10', 'https://ipinfo.io/json'], capture_output=True, text=True).stdout
res['runner'] = {k: v for k, v in (json.loads(ip) if ip.strip().startswith('{') else {}).items() if k in ('country', 'region', 'org')}
json.dump(res, open(os.path.join(OUT, 'court.json'), 'w'), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False)[:1500])
