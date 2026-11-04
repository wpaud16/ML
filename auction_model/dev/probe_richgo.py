"""리치고 탐색: 단지 페이지를 특정 평형으로 여는 URL 형식 확인 (2026-11-05, 가중 시세용)."""
import json, os, subprocess
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'probe'); os.makedirs(OUT, exist_ok=True)


def nd(url):
    raw = subprocess.run(['curl', '-sL', '-m', '40', '-A', 'Mozilla/5.0', url], capture_output=True).stdout.decode('utf-8', 'replace')
    i = raw.find('__NEXT_DATA__'); j = raw.find('>', i); k = raw.find('</script>', j)
    try:
        return json.loads(raw[j + 1:k])['props']['pageProps']
    except Exception:
        return {}


B = 'https://m.richgo.ai/realty/danji/a6eBfVs'   # 래미안대치팰리스 (기본 37평, 경매 물건 33평)
out = {}
for suf in ['', '?pyeong=33', '?pyeongType=33', '?selectedPyeongType=33', '/33', '?py=33', '?pyeong=33&type=meme', '?areaType=33']:
    pp = nd(B + suf)
    d = pp.get('data') or {}
    tr = ((d.get('price') or {}).get('transaction') or {}).get('items') or []
    out[suf or '(기본)'] = dict(selected=d.get('selectedPyeongType'), tradeFacts_pyeong=(pp.get('tradeFacts') or {}).get('pyeong'),
                               n_tr=len(tr), tr=[(t.get('date'), t.get('supplyAreaRep'), t.get('floor'), t.get('price'), t.get('cancelDate')) for t in tr[:12]],
                               tf_recent=len((pp.get('tradeFacts') or {}).get('recent') or []), listing=(pp.get('tradeFacts') or {}).get('listing'),
                               more=((d.get('price') or {}).get('transaction') or {}).get('more'))
    print(suf, json.dumps(out[suf or '(기본)'], ensure_ascii=False)[:600])
json.dump(out, open(os.path.join(OUT, 'pyeong_url.json'), 'w'), ensure_ascii=False, indent=1)
