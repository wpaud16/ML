"""리치고 탐색 (2026-11-05): 하남 2건 예측 실패 원인.
- 2026타경50031 효성해링턴 a2jAdUo: 'no matching pyeong price' → pyeongInfos 덤프
- 2026타경234 한솔리치빌1단지(덕풍동): '단지 못 찾음' → 검색 결과·각 단지 경매 목록"""
import json, os, sys, re, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import nearby
OUT = os.path.join(HERE, 'probe'); os.makedirs(OUT, exist_ok=True)


def auctions(dd):
    ids = []
    def flat(x):
        if not x: return
        ids.append(dict(id=x.get('auctionId'), case=x.get('caseNumber') or x.get('caseNo'), area=x.get('buildingTotalArea'), date=x.get('biddingDate')))
        for s in x.get('subList') or []: flat(s)
    flat(dd.get('auctionInfo'))
    return ids


def search(t):
    raw = nearby._get('https://m.richgo.ai/realty/search?q=' + urllib.parse.quote(t))
    if not raw: return 'NO RESPONSE'
    i = raw.find('__NEXT_DATA__'); j = raw.find('>', i); k = raw.find('</script>', j)
    p = json.loads(raw[j + 1:k])['props']['pageProps']
    out = []
    for g in (p.get('agentSearch') or {}).get('groups') or []:
        for it in g.get('items') or []:
            out.append(dict(kind=g.get('kind'), name=it.get('name'), addr=it.get('address'), href=it.get('href')))
    return out[:20]


res = {}
dd = nearby.page_props('danji', 'a2jAdUo').get('data') or {}
res['a2jAdUo'] = dict(name=dd.get('name') or dd.get('danjiName'), keys=sorted(dd.keys()),
    pyeong={p: dict(lo=v.get('minPrivateArea'), hi=v.get('maxPrivateArea'), hh=v.get('households'),
                    dp=v.get('danjiPriceInfo')) for p, v in (dd.get('pyeongInfos') or {}).items()},
    auctions=auctions(dd))
for t in ['한솔리치빌', '한솔리치빌1단지', '덕풍동 한솔리치빌', '하남 덕풍동', '하남시 덕풍동', '한솔리치빌아파트1단지']:
    res['search:' + t] = search(t)
ids = set()
for k, v in res.items():
    if k.startswith('search:') and isinstance(v, list):
        for x in v:
            m = re.search(r'/realty/danji/([0-9A-Za-z]+)', x.get('href') or '')
            if m and '한솔' in (x.get('name') or ''): ids.add(m.group(1))
res['hansol_auctions'] = {i: auctions(nearby.page_props('danji', i).get('data') or {}) for i in ids}
print(json.dumps(res, ensure_ascii=False)[:4000])
json.dump(res, open(os.path.join(OUT, 'hanam.json'), 'w'), ensure_ascii=False, indent=1)
