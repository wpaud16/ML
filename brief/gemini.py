"""증시 해설 — Google Gemini + Google 검색 (환경변수 GEMINI_API_KEY 가 있을 때만)."""
import datetime as dt, json, os, re, urllib.request, urllib.error

BASE = 'https://generativelanguage.googleapis.com/v1beta'


VERTEX = 'https://aiplatform.googleapis.com/v1/publishers/google/models'
FALLBACK = ['gemini-3-flash', 'gemini-2.5-flash', 'gemini-2.0-flash']


def _post(url, body, key):
    req = urllib.request.Request(url, json.dumps(body).encode(), {'Content-Type': 'application/json', 'x-goog-api-key': key})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'{e.code}: {e.read().decode()[:300]}')


def models(key):
    """시도할 모델 순서. GEMINI_MODEL 이 있으면 그것만. 무료 한도가 없는 최신 모델이 있어 여러 개를 차례로 시도."""
    if os.environ.get('GEMINI_MODEL'):
        return [os.environ['GEMINI_MODEL']]
    try:
        req = urllib.request.Request(f'{BASE}/models?pageSize=200', headers={'x-goog-api-key': key})
        with urllib.request.urlopen(req, timeout=30) as r:
            ms = [m['name'].split('/')[-1] for m in json.load(r).get('models', [])
                  if 'generateContent' in m.get('supportedGenerationMethods', [])]
    except Exception as e:
        print('model list failed:', str(e)[:120])
        return FALLBACK
    ver = lambda m: float(re.search(r'\d+(\.\d+)?', m).group())
    flash = sorted((m for m in ms if re.fullmatch(r'gemini-\d+(\.\d+)?-flash', m)), key=ver, reverse=True)
    lite = sorted((m for m in ms if re.fullmatch(r'gemini-\d+(\.\d+)?-flash-lite', m)), key=ver, reverse=True)
    out = []
    for i in range(max(len(flash), len(lite))):  # 최신 flash → 최신 lite → 그 이전 flash → ...
        out += flash[i:i + 1] + lite[i:i + 1]
    return out[:8] or FALLBACK


PROMPT = """오늘은 {today} (한국시간 아침)입니다. 아래 숫자는 마지막 거래일 종가입니다.
{numbers}

Google 검색으로 최신 한국·미국 증시 뉴스(연합인포맥스, 한국경제, 매일경제, 이데일리, Reuters, CNBC, Bloomberg 등)를 찾아,
사실만 정리하세요. 매수·매도 권유는 절대 하지 마세요. 각 문장은 한국어 35자 이내, 한 줄에 사실 하나.
반드시 아래 JSON 하나만 출력하세요 (설명·코드블록 없이):
{{"kr": {{"direction": "올랐나|떨어졌나|보합이었나", "reasons": ["2~3개"],
         "up": [{{"theme": "테마", "stocks": "대표 종목 1~2개", "reason": "이유 한 줄"}}],
         "down": [{{"theme": "", "stocks": "", "reason": ""}}]}},
 "us": {{"direction": "...", "reasons": [...], "up": [...], "down": [...]}},
 "week": [{{"day": "요일(날짜) 예: 목(11/6)", "event": "경제지표·FOMC·한은·주요 실적(삼성·SK하이닉스·미국 빅테크) 등"}}],
 "themes": [{{"theme": "", "reason": "왜 볼 만한지 한 줄"}}],
 "sources": ["참고한 언론사 이름"]}}
up/down 은 각각 2~4개, week 는 3~6개, themes 는 2~3개. 휴장이었다면 reasons 첫 줄에 휴장이라고 쓰고 직전 거래일 기준으로 정리."""


def market_summary(today, numbers_text):
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not key:
        return None
    body = {'contents': [{'parts': [{'text': PROMPT.format(today=today, numbers=numbers_text)}]}],
            'tools': [{'google_search': {}}], 'generationConfig': {'temperature': 0.2}}
    r, errs = None, []
    for model in models(key):
        try:
            r = _post(f'{BASE}/models/{model}:generateContent', body, key)
            print('gemini ok:', model)
            break
        except Exception as e:
            errs.append(f'{model}: {str(e)[:120]}')
    if r is None:
        raise RuntimeError('Gemini 호출 실패\n' + '\n'.join(errs))
    txt = ''.join(p.get('text', '') for p in r['candidates'][0]['content']['parts'])
    m = re.search(r'\{.*\}', txt, re.S)
    return json.loads(m.group())
