"""리치고 탐색 (2026-11-05): 평형별 실거래 '더보기' 전체 이력 API 찾기 (시세 기준 백테스트용)."""
import json, os, re, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, 'probe'); os.makedirs(OUT, exist_ok=True)
def get(u, extra=()):
    return subprocess.run(['curl', '-sL', '-m', '30', '-A', 'Mozilla/5.0', *extra, u], capture_output=True).stdout.decode('utf-8', 'replace')
res = {}
raw = get('https://m.richgo.ai/realty/danji/a0AkrGl?pyeongType=33')
res['len'] = len(raw)
res['scripts'] = sorted(set(re.findall(r'src="(/_next/static/[^"]+\.js)"', raw)))[:80]
i = raw.find('__NEXT_DATA__'); j = raw.find('>', i); k = raw.find('</script>', j)
nd = json.loads(raw[j + 1:k]); res['buildId'] = nd.get('buildId'); res['runtimeConfig'] = nd.get('runtimeConfig'); res['page'] = nd.get('page')
pp = nd['props']['pageProps']; res['pp_keys'] = sorted(pp)
tf = pp.get('tradeFacts') or {}; res['tf_keys'] = {k: (type(v).__name__, len(v) if hasattr(v, '__len__') else v) for k, v in tf.items()}
res['tf_sample'] = json.dumps(tf, ensure_ascii=False)[:1500]
# JS 안에서 API 경로 찾기
hits = {}
for s in res['scripts']:
    js = get('https://m.richgo.ai' + s)
    for m in re.finditer(r'["`\'](/?(?:api|v\d)[^"`\'\s]{3,120})["`\']', js):
        p = m.group(1)
        if re.search(r'trade|deal|meme|price|danji|transaction|history', p, re.I): hits.setdefault(p, s)
    for m in re.finditer(r'https?://[a-z0-9.\-]*richgo[a-z0-9.\-]*\.[a-z]+[^"`\'\s]{0,80}', js):
        hits.setdefault(m.group(0), s)
res['api_hits'] = hits
json.dump(res, open(os.path.join(OUT, 'trade_api.json'), 'w'), ensure_ascii=False, indent=1)
print(json.dumps({k: res[k] for k in ['len', 'buildId', 'page', 'pp_keys', 'tf_keys']}, ensure_ascii=False)); print(len(hits))
