"""리치고 탐색 (2026-11-05): 'no matching pyeong price' 실패(오피스텔 117·아파트 5) 원인 — 평형별 면적·시세 출처 덤프."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import nearby
OUT = os.path.join(HERE, 'probe'); os.makedirs(OUT, exist_ok=True)
res = []
for c in json.load(open(os.path.join(HERE, 'probe_cases.json'))):
    dd = nearby.page_props(c['kind'], c['pid']).get('data') or {}
    au = []
    def flat(x):
        if not x: return
        au.append(x)
        for s in x.get('subList') or []: flat(s)
    flat(dd.get('auctionInfo'))
    a = next((x for x in au if x.get('auctionId') == c['aid']), {})
    py = {}
    for p, v in (dd.get('pyeongInfos') or {}).items():
        dp = v.get('danjiPriceInfo') or {}
        md = dp.get('memePriceDict') or {}
        py[p] = dict(lo=v.get('minPrivateArea'), hi=v.get('maxPrivateArea'), meme=(dp.get('meme') or {}).get('price'), src=dp.get('memeSource'),
                     molit=((md.get('MOLIT') or {}).get('price'), (md.get('MOLIT') or {}).get('yyyymmdd')),
                     offer=(md.get('OFFER') or {}).get('price'))
    res.append(dict(c, page_ok=bool(dd), found=bool(a), au_area=a.get('buildingTotalArea'), n_py=len(py), py=py))
json.dump(res, open(os.path.join(OUT, 'nomatch_pyeong.json'), 'w'), ensure_ascii=False, indent=1)
print(len(res))
