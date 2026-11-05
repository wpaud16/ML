"""탐색 (2026-11-05): 메일의 '경매 전체 카드' 버튼이 반응 없다는 사용자 보고 → 웹페이지 응답 확인."""
import json, os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, 'probe'); os.makedirs(OUT, exist_ok=True)
res = {}
for u in ['https://wpaud16.github.io/ML/auction_model/page/', 'https://wpaud16.github.io/ML/auction_model/page/index.html',
          'https://wpaud16.github.io/ML/outfit/2026-11-05/', 'https://wpaud16.github.io/ML/']:
    r = subprocess.run(['curl', '-sL', '-m', '30', '-o', '/tmp/p.html', '-w', '%{http_code} %{size_download} %{url_effective}', u], capture_output=True, text=True)
    head = open('/tmp/p.html', encoding='utf-8', errors='replace').read()[:300] if os.path.exists('/tmp/p.html') else ''
    res[u] = dict(status=r.stdout, head=head)
json.dump(res, open(os.path.join(OUT, 'pages.json'), 'w'), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False)[:1500])
