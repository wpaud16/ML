#!/usr/bin/env python3
"""대신 응모한 이벤트 당첨 확인 (2026-11-19 사용자 요청).

events_entries.json (개인정보 없음): [{key, title, org, url, entered, announce, where, status, checked, result_url, note, reported}]
  status: pending(발표 대기) → won(당첨) | lost(미당첨) | manual(직접 확인 필요: 명단이 이미지·이름만 등) | unknown(발표 못 찾음)
발표일이 지났거나(모르면 응모 1주 뒤부터 3일마다) → 노트북 Claude CLI 웹 검색으로 '당첨자 발표' 글의 명단 원문을 받아
이 PC 에서만 이름·전화 뒷자리와 맞춰 봄. 이름·번호는 C:/auction_pc/.env 의 ENTRY_NAME·ENTRY_PHONE (저장소에 안 올림),
CLI 에는 이름·번호를 보내지 않는다.
결과는 생활 메일 '🎁 당첨 확인' 섹션(render)과 이벤트 웹 카드에 표시.

  python prize_check.py            # 확인할 것 확인
  python prize_check.py --list     # 기록 보기
"""
import datetime as dt, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PATH = os.path.join(HERE, 'events_entries.json')
KST = dt.timezone(dt.timedelta(hours=9))
GIVE_UP_DAYS = 75
LABEL = {'won': '🎉 당첨!', 'lost': '미당첨', 'manual': '👀 발표 확인 필요', 'unknown': '발표 못 찾음', 'pending': '발표 대기'}


def load():
    try:
        return json.load(open(PATH, encoding='utf-8'))
    except Exception:
        return []


def save(es):
    json.dump(es, open(PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def _d(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def add(key, title, url, org='', announce=None, where=None, entered=None):
    """대신 응모를 마쳤을 때 기록 (Claude 가 응모 직후 부름)."""
    es = load()
    if any(e['key'] == key for e in es):
        return
    es.append(dict(key=key, title=title, org=org, url=url, entered=entered or dt.date.today().isoformat(),
                   announce=announce, where=where, status='pending', checked=None, result_url=None, note=None, reported=False))
    save(es)


def due(e, today):
    if e.get('status') != 'pending':
        return False
    ent, ann, chk = _d(e.get('entered')), _d(e.get('announce')), _d(e.get('checked'))
    if chk == today:
        return False
    if ann:
        return today >= ann and (not chk or (today - chk).days >= 2 or (today - ann).days <= 1)
    return ent and (today - ent).days >= 7 and (not chk or (today - chk).days >= 3)


PROMPT = """당첨자 발표 글을 찾아 명단을 옮겨 주세요.
이벤트: {title}
주최: {org}
이벤트 페이지: {url}
발표 예정일: {announce}
발표 장소(알면): {where}

방법: 주최측 공식 홈페이지 공지사항·이벤트 게시판·공식 SNS 에서 이 이벤트의 '당첨자 발표' 글을 찾아 WebFetch 로 열고,
당첨자 명단 부분을 원문 그대로(마스킹된 이름·전화번호 그대로) 옮겨 주세요. 다른 이벤트(예: 지난달 회차)의 발표와 헷갈리지 마세요.
명단이 이미지라 글자를 못 읽으면 image_only=true.
JSON 하나만 출력:
{{"posted": true|false, "post_url": "발표 글 주소 또는 null", "winners_text": "명단 원문(최대 8000자) 또는 null", "image_only": true|false, "note": "한 줄 메모"}}"""


def judge(text, name, phone):
    """명단 원문 → ('won'|'lost'|'manual', 메모). 이름 마스킹(이*명 등)과 전화 뒷자리로 판단."""
    if not text:
        return 'manual', '명단 원문 없음'
    t = re.sub(r'\s+', ' ', text)
    mask = r'[*＊○●◯Oo0xX□■◇◆ㅇ_\-]'
    n = re.sub(r'\s', '', name)
    pats = [re.escape(n)]
    if len(n) == 3:
        pats += [re.escape(n[0]) + mask + re.escape(n[2]), re.escape(n[:2]) + mask, mask + re.escape(n[1:]),
                 re.escape(n[0]) + mask + mask]
    elif len(n) == 2:
        pats += [re.escape(n[0]) + mask]
    rx = re.compile('|'.join(pats))
    digits = re.sub(r'\D', '', phone)
    last4, mid4 = digits[-4:], digits[3:7]
    hits = [m.start() for m in rx.finditer(t)]
    has_phone_list = bool(re.search(r'\d{4}', t))
    for h in hits:
        w = t[max(0, h - 40):h + 70]
        if last4 and last4 in w:
            return 'won', '이름·전화 뒷자리 일치'
    if hits and not has_phone_list:
        return 'manual', '이름만 공개된 명단에 비슷한 이름이 있어요 (동명이인일 수 있음)'
    if hits:
        return 'manual', '비슷한 이름은 있지만 전화번호가 달라 보여요'
    if last4 and re.search(r'(?<!\d)' + last4 + r'(?!\d)', t) and (not mid4 or mid4 in t or '*' in t):
        return 'manual', '전화 뒷자리만 일치'
    return 'lost', '명단에 없음'


def check(today=None):
    from claude_summary import cli_json
    today = today or dt.datetime.now(KST).date()
    name, phone = os.environ.get('ENTRY_NAME', '').strip(), os.environ.get('ENTRY_PHONE', '').strip()
    es = load()
    todo = [e for e in es if due(e, today)]
    print('확인할 응모', len(todo), '/', len(es))
    for e in es:   # 너무 오래된 것은 포기
        ent = _d(e.get('entered'))
        if e.get('status') == 'pending' and ent and (today - ent).days > GIVE_UP_DAYS:
            e.update(status='unknown', note='발표를 찾지 못했어요', reported=False)
    for e in todo:
        r = cli_json(PROMPT.format(**{k: e.get(k) or '모름' for k in ('title', 'org', 'url', 'announce', 'where')}),
                     timeout=600, tag='당첨 확인 ' + e['title'][:20])
        e['checked'] = today.isoformat()
        if not r:
            continue
        if not r.get('posted'):
            ann = _d(e.get('announce'))
            if ann and (today - ann).days >= 14:
                e.update(status='manual', note='발표일이 2주 지났는데 발표 글을 못 찾았어요', reported=False)
            continue
        e['result_url'] = r.get('post_url')
        if r.get('image_only'):
            e.update(status='manual', note='명단이 이미지라 직접 확인이 필요해요', reported=False)
        elif not name:
            e.update(status='manual', note='이름 설정(ENTRY_NAME)이 없어 직접 확인이 필요해요', reported=False)
        else:
            st, note = judge(r.get('winners_text') or '', name, phone)
            e.update(status=st, note=note, reported=False)
        print(e['title'][:30], '→', e['status'], e.get('note'))
    save(es)


def render():
    """생활 메일 섹션 (새 결과만) → (html, text, 보낸 뒤 부를 함수) / 없으면 (None, None, None)."""
    es = load()
    new = [e for e in es if e.get('status') not in ('pending', None) and not e.get('reported')]
    if not new:
        return None, None, None
    rows, txt = [], []
    for e in sorted(new, key=lambda e: e['status'] != 'won'):
        link = e.get('result_url') or e.get('url')
        rows.append(f'<li><b>{LABEL[e["status"]]}</b> {e["title"]}'
                    + (f' <span style="color:#777">· {e["note"]}</span>' if e.get('note') else '')
                    + (f' · <a href="{link}">발표 보기</a>' if link else '') + '</li>')
        txt.append(f'- {LABEL[e["status"]]} {e["title"]} ({e.get("note") or ""}) {link or ""}')
    pend = sum(e.get('status') == 'pending' for e in es)
    h = ('<div><div style="font-weight:bold;font-size:16px;margin-bottom:4px">🎁 당첨 확인</div><ul style="margin:4px 0;padding-left:18px">'
         + ''.join(rows) + f'</ul><div style="color:#777;font-size:12px">발표 대기 {pend}건 · 당첨 경품은 대부분 문자로 와요</div></div>')

    def mark():
        es2 = load()
        keys = {e['key'] for e in new}
        for e in es2:
            if e['key'] in keys:
                e['reported'] = True
        save(es2)
    return h, '🎁 당첨 확인\n' + '\n'.join(txt), mark


def status_of(key):
    for e in load():
        if e['key'] == key:
            return e
    return None


if __name__ == '__main__':
    if '--list' in sys.argv:
        for e in load():
            print(e['status'], '|', e['entered'], '| 발표', e.get('announce'), '|', e['title'], '|', e.get('note') or '')
    else:
        check()
