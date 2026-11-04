"""리치고 페이지 구조 탐색 (2026-11-05): 주변 단지 시세 설계용 샘플 저장. 수동 실행 전용.
단지 페이지·동 검색 결과의 __NEXT_DATA__ 를 키 구조 + 일부 값만 잘라 dev/probe/ 에 저장한다."""
import json, os, re, sys, subprocess, urllib.parse

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'probe')
os.makedirs(OUT, exist_ok=True)


def get(url):
    return subprocess.run(['curl', '-sL', '-m', '40', '-A', 'Mozilla/5.0', url], capture_output=True).stdout.decode('utf-8', 'replace')


def nd(raw):
    i = raw.find('__NEXT_DATA__'); j = raw.find('>', i); k = raw.find('</script>', j)
    return json.loads(raw[j + 1:k]) if i >= 0 else {}


def shrink(x, depth=0):
    """구조는 남기고 긴 리스트·문자열은 자른다."""
    if isinstance(x, dict):
        return {k: shrink(v, depth + 1) for k, v in x.items()}
    if isinstance(x, list):
        return [shrink(v, depth + 1) for v in x[:3]] + ([f'...(+{len(x) - 3})'] if len(x) > 3 else [])
    if isinstance(x, str) and len(x) > 200:
        return x[:200] + '…'
    return x


def save(name, url):
    raw = get(url)
    d = nd(raw)
    json.dump(dict(url=url, html_len=len(raw), next_data=shrink(d)), open(os.path.join(OUT, name + '.json'), 'w'), ensure_ascii=False, indent=1)
    # HTML 안의 JSON 조각 중 indexName 종류 (주변 시설 목록 등)
    kinds = sorted(set(re.findall(r'"indexName":"([^"]+)"', raw)))
    print(name, len(raw), 'indexName:', kinds[:40])


q = urllib.parse.quote
save('danji_apt', 'https://m.richgo.ai/realty/danji/a6eBfVs')          # 래미안대치팰리스
save('officetel', 'https://m.richgo.ai/realty/officetel/' + (sys.argv[1] if len(sys.argv) > 1 else ''))
save('search_dong', 'https://m.richgo.ai/realty/search?q=' + q('강남구 대치동'))
save('search_dong_ot', 'https://m.richgo.ai/realty/search?q=' + q('강서구 등촌동 오피스텔'))
