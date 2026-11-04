"""리치고 탐색: 특정 물건의 주변 시세·가중 시세 바로 계산 (2026-11-05, 덕현 2025타경72200 예시)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import nearby
OUT = os.path.join(HERE, 'probe'); os.makedirs(OUT, exist_ok=True)
L = json.load(open(os.path.join(os.path.dirname(HERE), 'predictions', 'latest.json')))['items']
res = {}
for k in ['2025타경72200[1]']:
    v = L[k]
    nb = nearby.nearby_apt(v['danji_id'], v.get('pyeong'))
    ws = nearby.weighted_apt(v['danji_id'], v.get('pyeong'), v.get('address'), v['appr_manwon'], v.get('sise'))
    pp = nearby.page_props('danji', f"{v['danji_id']}?pyeongType={int(float(v['pyeong']))}")
    res[k] = dict(nearby=nb, weighted=ws, merged=nearby.merge_into_sise(v.get('sise'), nb, v['low_manwon']) if nb else None,
                  trades=(pp.get('tradeFacts') or {}).get('recent'), listing=(pp.get('tradeFacts') or {}).get('listing'))
    print(json.dumps(res[k], ensure_ascii=False)[:3000])
json.dump(res, open(os.path.join(OUT, 'example.json'), 'w'), ensure_ascii=False, indent=1)
