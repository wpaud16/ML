"""증시 해설 — Claude API + 웹 검색 (환경변수 ANTHROPIC_API_KEY 가 있을 때만).
실패(키 없음·크레딧 소진·한도 초과·응답 이상)하면 None 을 돌려주고, 메일에서는 해설 칸만 비운다.
"""
import json, os, re

MODEL = os.environ.get('BRIEF_CLAUDE_MODEL', 'claude-opus-5-5')

PROMPT = """오늘은 {today} (한국시간 아침)입니다. 아래 숫자는 마지막 거래일 종가입니다.
{numbers}

웹 검색으로 최신 한국·미국 증시 뉴스(연합인포맥스, 한국경제, 매일경제, 이데일리, Reuters, CNBC, Bloomberg 등)를 찾아,
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
    if not os.environ.get('ANTHROPIC_API_KEY', '').strip():
        print('claude: ANTHROPIC_API_KEY 없음 → 해설 생략')
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(max_retries=2, timeout=600)
        messages = [{'role': 'user', 'content': PROMPT.format(today=today, numbers=numbers_text)}]
        tools = [{'type': 'web_search_20260209', 'name': 'web_search', 'max_uses': 8}]
        for _ in range(4):  # 검색이 길어 pause_turn 으로 멈추면 이어서 진행
            r = client.beta.messages.create(
                model=MODEL, max_tokens=16000, messages=messages, tools=tools,
                output_config={'effort': 'medium'},
                betas=['server-side-fallback-2026-07-01'], fallbacks='default')
            if r.stop_reason != 'pause_turn':
                break
            messages = messages[:1] + [{'role': 'assistant', 'content': r.content}]
        if r.stop_reason == 'refusal':
            print('claude: refusal'); return None
        txt = ''.join(b.text for b in r.content if b.type == 'text')
        m = re.search(r'\{.*\}', txt, re.S)
        out = json.loads(m.group())
        print('claude ok:', r.model, r.usage.input_tokens, r.usage.output_tokens)
        return out
    except Exception as e:  # 크레딧 소진·한도 초과 등 — 해설만 비우고 계속
        print('claude: 해설 실패 →', type(e).__name__, str(e)[:200])
        return None
