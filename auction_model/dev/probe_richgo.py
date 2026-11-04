"""리치고 탐색 (수동/푸시 실행): 특정 사건이 왜 예측 목록에 없는지 확인 (2026-11-05: 2025타경52331, 2026타경50031)."""
import json, os, re, subprocess, urllib.parse
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'probe'); os.makedirs(OUT, exist_ok=True)
q = urllib.parse.quote


def get(url):
    return subprocess.run(['curl', '-sL', '-m', '40', '-A', 'Mozilla/5.0', url], capture_output=True).stdout.decode('utf-8', 'replace')


def nd(raw):
    i = raw.find('__NEXT_DATA__'); j = raw.find('>', i); k = raw.find('</script>', j)
    return json.loads(raw[j + 1:k])['props']['pageProps'] if i >= 0 else {}


CASES = ['2025타경52331', '2026타경50031']
REG = [('서울', g) for g in ['강남구', '서초구', '강동구', '광진구', '송파구']] + [('경기', g) for g in ['성남시 분당구', '성남시 수정구', '성남시 중원구', '남양주시', '구리시']]
found = {}
for sd, sgg in REG:
    for ty in ['아파트', '오피스텔', '주상복합', '다세대', '']:
        page = 1
        while page <= 15:
            url = f'https://m.richgo.ai/auction/hub/region/{q(sd)}/{q(sgg)}' + (f'/{q(ty)}' if ty else '') + (f'?page={page}' if page > 1 else '')
            try:
                d = nd(get(url)).get('data') or {}
            except Exception:
                break
            for it in d.get('items') or []:
                if it.get('caseName') in CASES:
                    found.setdefault(it['caseName'], []).append(dict(list=f'{sd} {sgg} {ty or "(전체)"}', **{k: it.get(k) for k in
                        ['id', 'itemNumber', 'address', 'itemType', 'typeDetails', 'appraisedPrice', 'lowestSellingPrice', 'biddingDate', 'buildingTotalArea', 'itemStatus', 'numberOfFailures']}))
            if not d.get('items') or page * (d.get('size') or 20) >= (d.get('totalCount') or 0):
                break
            page += 1
for c in CASES:
    s = nd(get('https://m.richgo.ai/realty/search?q=' + q(c)))
    found.setdefault(c + '_search', json.dumps(s, ensure_ascii=False)[:1500])
for c, v in found.items():
    print(c, json.dumps(v, ensure_ascii=False)[:1500])
json.dump(found, open(os.path.join(OUT, 'cases.json'), 'w'), ensure_ascii=False, indent=1)
