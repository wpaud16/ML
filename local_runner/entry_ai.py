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

말투 (사용자 본인 말투 — 짧고 편한 해요체, 꾸밈 적고 솔직하게, 느낌표 가끔):
- "정답 사망원인통계! 죽음의 기록이 다른 사람의 생명을 지키는 데이터가 된다는 게 인상 깊었어요."
- "AI로 꿈을 그려내는 이야기가 따뜻해서 좋았어요. 노래도 계속 귀에 맴돌아요!"
- "혼자가 아니라 함께 돌보는 사회가 되면 좋겠어요. 발달장애인 당사자분들과 가족분들 늘 응원합니다!"
- "나에게 사진이란 지나가면 다시 오지 않는 순간을 붙잡아 두는 일기 같아요."

규칙:
- 한국어 1~2문장, 30~90자. 위 말투 그대로. 이모지는 0~1개. 광고 문구·과한 칭찬·AI 같은 딱딱한 문장 금지.
- 이벤트가 요구하는 내용(정답·응원·소감·기대평·질문 답 등)을 정확히 담기. 정답이 필요하면 웹 검색으로 확인.
- 요구가 애매하면 영상 제목·설명에서 구체적인 내용 하나를 집어 소감+응원으로 자연스럽게 쓰기 (건너뛰지 말 것).
- 겪지 않은 경험·가족·직업 등 사실을 지어내지 말 것 ("저도 그래요", "공감돼요"처럼 같은 경험을 암시하는 말도 피하기). 링크·해시태그·광고·정치·종교·남 비방 금지.
- ok=false 는 사진·사연·개인정보처럼 댓글로는 정말 할 수 없는 걸 요구할 때만.
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
    """2026-11-25 사용자: 내 말투로, 애매해도 잘 써서 달기. 응답이 규칙에 안 맞으면 한 번 더 받아 봄."""
    p = COMMENT_PROMPT.format(title=title, text=(text or '')[:1500], vtitle=vtitle, vdesc=(vdesc or '')[:1200])
    for i in range(2):
        out = _cli(p if i == 0 else p + '\n\n(앞 답이 규칙에 안 맞았어. 30~90자, 링크·해시태그·@ 없이 다시.)', 'comment') or {}
        c = re.sub(r'\s+', ' ', str(out.get('comment') or '')).strip()
        if out.get('ok') is False and c == '':
            return None   # 댓글로는 할 수 없는 이벤트
        if 15 <= len(c) <= 150 and not BAD.search(c):
            return c
    return None
