"""자동 응모에서 판단이 필요한 부분을 Claude CLI 에 맡김 (2026-11-25 사용자: 퀴즈 정답 추측도, 댓글도 Claude 가. 이상한 댓글은 안 됨).
- quiz_answers: 폼의 퀴즈 질문·보기 → 정답 (웹 검색 허용). 실패하면 None (폼 작성기가 추측한 답 그대로).
- comment_text: 영상·이벤트 내용 → 짧고 자연스러운 댓글 한 줄. 애매하면 ok=false 로 안 단다.
개인정보(이름·연락처)는 프롬프트에 넣지 않는다."""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'brief'))

QUIZ_PROMPT = """이벤트 퀴즈 정답을 찾아줘. 웹 검색으로 이벤트 원문·관련 영상 설명·기사를 확인해서 가장 정확한 보기를 골라.
이벤트: {title}
이벤트 안내: {text}
질문과 보기 (→ 뒤는 지금 추측한 답):
{qs}

JSON 하나만 출력: {{"answers": [{{"q": "질문 앞부분 그대로 15자 이상", "a": "고른 보기 글자 그대로"}}]}}
보기가 없는 주관식이면 "a" 에 짧은 정답만. 확신 없으면 가장 그럴듯한 보기."""

COMMENT_PROMPT = """유튜브 이벤트 참여용 댓글 한 줄을 써줘. 사용자 본인 실명 계정에 공개로 달린다.
이벤트: {title}
이벤트 안내(댓글 조건 포함): {text}
영상 제목: {vtitle}
영상 설명: {vdesc}

규칙:
- 한국어 1~2문장, 30~90자. 존댓말, 담백하고 자연스럽게. 이모지는 0~1개.
- 이벤트가 요구하는 내용(정답·응원·소감·기대평 등)을 정확히 담기. 정답이 필요하면 웹 검색으로 확인.
- 겪지 않은 경험·가족·직업 등 사실을 지어내지 말 것. 링크·해시태그·광고·정치·종교·남 비방 금지.
- 사진·사연·개인정보를 요구하는 등 댓글로만 할 수 없으면 ok=false.
JSON 하나만 출력: {{"ok": true, "comment": "댓글"}}"""

BAD = re.compile(r'https?://|#\S|010-?\d|@\w|광고|정치|대통령|선거|종교')


def _cli(prompt, tag):
    import claude_summary
    import run_all   # PATH 에 claude 추가
    run_all.find_claude()
    return claude_summary.cli_json(prompt, timeout=600, tag=tag)


def quiz_answers(title, text, lines):
    qs = '\n'.join(l for l in lines if '(추측)' in l)
    if not qs:
        return []
    out = _cli(QUIZ_PROMPT.format(title=title, text=(text or '')[:1500], qs=qs), 'quiz') or {}
    res = []
    for a in out.get('answers') or []:
        q, ans = str(a.get('q') or '').strip(), str(a.get('a') or '').strip()
        if len(q) >= 6 and ans:
            res.append((re.escape(q[:20]), re.escape(ans[:30])))
    return res


def comment_text(title, text, vtitle, vdesc):
    out = _cli(COMMENT_PROMPT.format(title=title, text=(text or '')[:1500], vtitle=vtitle, vdesc=(vdesc or '')[:1200]), 'comment') or {}
    c = re.sub(r'\s+', ' ', str(out.get('comment') or '')).strip()
    if not out.get('ok') or not (15 <= len(c) <= 150) or BAD.search(c):
        return None
    return c
