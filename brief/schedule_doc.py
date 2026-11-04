"""STEP 1 오늘 날짜 섹션 / 1b 식사 가능 시간 (구글 문서 "JM's Schedule")."""
import datetime as dt, html, re
import google_api as g

DOC = '16r3j5QD_VJZKxL9hOxbv-Aj58jNbp92nCM4szeKrq6Y'
WD = '월화수목금토일'
DAYS = {1: '등 + 이두', 2: '하체 + 측면어깨', 3: '가슴 + 삼두', 4: '유산소'}
FIXED = ('큐티', '독서 30분')
WORK_RE = re.compile(r'^운동:\s*(.+?)\s*\(Day\s*(\d)\)')


def label_of(d):
    return f'{d.month}월 {d.day}일 ({WD[d.weekday()]})'


def norm(t):
    return re.sub(r'\s+', ' ', t.replace('\\', '').replace('~', '')).strip()


def paragraphs(doc):
    out = []
    for e in doc['body']['content']:
        p = e.get('paragraph')
        if not p:
            continue
        t = ''.join(x.get('textRun', {}).get('content', '') for x in p['elements']).rstrip('\n')
        out.append(dict(start=e['startIndex'], end=e['endIndex'], text=t,
                        style=p['paragraphStyle'].get('namedStyleType'), bullet='bullet' in p))
    return out


def sections(paras):
    """Daily 아래 H3 날짜 섹션들 (최신순)."""
    i = next(k for k, p in enumerate(paras) if p['style'] == 'HEADING_1' and p['text'].strip() == 'Daily')
    daily, secs, cur = paras[i], [], None
    for p in paras[i + 1:]:
        if p['style'] == 'HEADING_1':
            break
        if p['style'] == 'HEADING_3':
            cur = dict(label=p['text'].strip(), head=p, items=[], memos=[]); secs.append(cur)
        elif cur and p['style'] == 'NORMAL_TEXT' and p['text'].strip():
            (cur['items'] if p['bullet'] else cur['memos']).append(p)
    month = next((p for p in paras[i + 1:] if p['style'] == 'HEADING_2'), None)
    return daily, month, secs


def done_map(md, label):
    """Drive 마크다운에서 해당 날짜 섹션 항목 → 완료 여부."""
    m = re.search(r'^###\s*' + re.escape(label) + r'\s*$', md, re.M)
    if not m:
        return {}
    body = md[m.end():]
    nx = re.search(r'^#{1,3}\s', body, re.M)
    body = body[:nx.start()] if nx else body
    out = {}
    for ln in body.splitlines():
        mm = re.match(r'\s*[-*]\s*(\[[ xX]\])?\s*(.*)', ln)
        if mm and mm.group(2).strip():
            out[norm(mm.group(2))] = ('~~' in ln) or (mm.group(1) or '').lower() == '[x]'
    return out


def meal(sec):
    if sec:
        ms = [p['text'] for p in sec['memos'] if p['text'].strip().startswith('🍽 마지막 식사')]
        if ms:
            m = re.search(r'(\d{1,2}):(\d{2})', ms[-1])
            if m:
                last = f'{int(m.group(1)):02d}:{m.group(2)}'
                h = (int(m.group(1)) + 14) % 24
                return dict(ok=f'{h:02d}:{m.group(2)}', note=f'어제 마지막 식사 {last} + 14시간 공복')
    return dict(ok='10:00', note='기록 없음 → 20:00 가정')


def plan(today, write=False):
    """오늘 섹션 계획(+ write=True 이면 문서에 생성). 결과 dict."""
    doc = g.doc_get(DOC)
    paras = paragraphs(doc)
    daily, month, secs = sections(paras)
    label = label_of(today)
    res = dict(label=label, warnings=[])
    md = g.drive_export(DOC)

    if secs and secs[0]['label'] == label:          # 이미 오늘 섹션 있음
        cur, prev = secs[0], (secs[1] if len(secs) > 1 else None)
        items = [p['text'].strip() for p in cur['items']]
        res['created'] = False
    else:
        cur, prev = None, (secs[0] if secs else None)
        items = None
        res['created'] = write

    # 어제(직전 섹션) 완료 여부
    dm = done_map(md, prev['label']) if prev else {}
    prev_items = [p['text'].strip() for p in prev['items']] if prev else []
    day, y = 1, {}
    for t in prev_items:
        w = WORK_RE.match(t)
        if w:
            d = int(w.group(2)); y['운동'] = dm.get(norm(t), False)
            day = (d % 4) + 1 if y['운동'] else d
        elif t in FIXED:
            y['큐티' if t == '큐티' else '독서'] = dm.get(norm(t), False)
    others_prev = [t for t in prev_items if not WORK_RE.match(t) and t not in FIXED]
    carry = [t for t in others_prev if not dm.get(norm(t), False)]
    res['yesterday'] = y
    res['done_n'], res['carry_n'] = len(others_prev) - len(carry), len(carry)

    if items is None:                               # 새로 만들 섹션
        work = f'운동: {DAYS[day]} (Day {day})'
        items = [work, *FIXED, *carry]
        if write:
            _insert(doc, daily, month, today, label, items)
            _verify(today, items, res)
    else:
        w = next((t for t in items if WORK_RE.match(t)), None)
        day = int(WORK_RE.match(w).group(2)) if w else day
        missing = [f for f in FIXED if f not in items]
        if missing:
            res['warnings'].append('오늘 섹션에 ' + '·'.join(missing) + ' 없음' + ('' if write else ' (테스트: 추가 안 함)'))
            if write and w:
                p = next(p for p in cur['items'] if p['text'].strip() == w)
                _insert_items_after(p['end'], missing)
                items = [w, *missing, *[t for t in items if t != w]]
    res['day'] = day
    res['items'] = items
    res['todos'] = [t for t in items if not WORK_RE.match(t) and t not in FIXED]
    res['meal'] = meal(prev)
    return res


def _style_reqs(start, texts, heads):
    """start부터 들어간 문단들 스타일 지정. heads = {문단번호: 'HEADING_2'|'HEADING_3'}."""
    reqs, pos, body = [], start, []
    end_all = start + sum(len(t) + 1 for t in texts)
    reqs.append({'updateTextStyle': {'range': {'startIndex': start, 'endIndex': end_all - 1},
                                     'textStyle': {}, 'fields': 'bold,italic,strikethrough,underline,foregroundColor,fontSize'}})
    reqs.append({'deleteParagraphBullets': {'range': {'startIndex': start, 'endIndex': end_all - 1}}})
    for k, t in enumerate(texts):
        r = {'startIndex': pos, 'endIndex': pos + len(t) + 1}
        st = heads.get(k, 'NORMAL_TEXT')
        ps = {'namedStyleType': st}
        fields = 'namedStyleType'
        if st == 'HEADING_3':
            ps['keepWithNext'] = True; fields += ',keepWithNext'
        if st == 'NORMAL_TEXT':
            ps['indentStart'] = {'magnitude': 0, 'unit': 'PT'}; ps['indentFirstLine'] = {'magnitude': 0, 'unit': 'PT'}
            fields += ',indentStart,indentFirstLine'
            body.append(r)
        reqs.append({'updateParagraphStyle': {'range': r, 'paragraphStyle': ps, 'fields': fields}})
        pos += len(t) + 1
    if body:
        reqs.append({'createParagraphBullets': {'range': {'startIndex': body[0]['startIndex'], 'endIndex': body[-1]['endIndex'] - 1},
                                                'bulletPreset': 'BULLET_CHECKBOX'}})
    return reqs


def _insert(doc, daily, month, today, label, items):
    mlabel = f'{today.year}년 {today.month}월'
    if month and month['text'].strip() == mlabel:
        at, texts, heads = month['end'], [label, *items], {0: 'HEADING_3'}
    else:
        at, texts, heads = daily['end'], [mlabel, label, *items], {0: 'HEADING_2', 1: 'HEADING_3'}
    reqs = [{'insertText': {'location': {'index': at}, 'text': '\n'.join(texts) + '\n'}}] + _style_reqs(at, texts, heads)
    g.doc_update(DOC, reqs, doc['revisionId'])


def _insert_items_after(at, texts):
    reqs = [{'insertText': {'location': {'index': at}, 'text': '\n'.join(texts) + '\n'}}] + _style_reqs(at, texts, {})
    g.doc_update(DOC, reqs)


def _verify(today, items, res):
    _, _, secs = sections(paragraphs(g.doc_get(DOC)))
    s = secs[0] if secs else None
    got = [p['text'].strip() for p in s['items']] if s else []
    if not s or s['label'] != label_of(today) or s['head']['style'] != 'HEADING_3' or got != items:
        res['warnings'].append('오늘 섹션 생성 확인 실패 — 문서를 확인해 주세요')


def render(r):
    g_ = 'color:#777;font-size:12px'
    nd = r['day'] % 4 + 1
    yy = r.get('yesterday') or {}
    ok = lambda k: '✅' if yy.get(k) else '❌'
    h = ('<div style="font-weight:bold;font-size:17px;margin-bottom:8px">✅ 오늘의 할 일 · ' + html.escape(r['label']) + '</div>'
         '<div style="border:1px solid #888888;border-radius:10px;padding:12px 14px;line-height:1.8">'
         '<div style="font-size:12px;color:#777">오늘의 루틴</div>'
         f'<div><b>🍽 식사 가능: {r["meal"]["ok"]}부터</b> <span style="{g_}">({r["meal"]["note"]})</span></div>'
         f'<div>💪 오늘 운동: {DAYS[r["day"]]} (Day {r["day"]}) <span style="{g_}">· 다음: {DAYS[nd]}</span></div>'
         '<div>🙏 큐티 15분 (밤 10시)</div><div>📚 독서 30분 — 지금 읽는 책: 경매 책</div></div>')
    if yy:
        h += f'<div style="{g_};margin-top:6px">어제 루틴: 운동 {ok("운동")} · 큐티 {ok("큐티")} · 독서 {ok("독서")}</div>'
    h += '<ol style="padding-left:22px;line-height:1.6">' + ''.join(f'<li style="margin-bottom:4px">{html.escape(t)}</li>' for t in r['todos']) + '</ol>'
    h += f'<div style="{g_}">어제 완료: {r["done_n"]}개 / 이월: {r["carry_n"]}개</div>'
    t = (f'✅ 오늘의 할 일 · {r["label"]}\n🍽 식사 가능: {r["meal"]["ok"]}부터 ({r["meal"]["note"]})\n'
         f'💪 오늘 운동: {DAYS[r["day"]]} (Day {r["day"]}) · 다음: {DAYS[nd]}\n🙏 큐티 15분 (밤 10시)\n📚 독서 30분 — 지금 읽는 책: 경매 책\n')
    if yy:
        t += f'어제 루틴: 운동 {ok("운동")} · 큐티 {ok("큐티")} · 독서 {ok("독서")}\n'
    t += '\n' + '\n'.join(f'{i}. {x}' for i, x in enumerate(r['todos'], 1)) + f'\n\n어제 완료: {r["done_n"]}개 / 이월: {r["carry_n"]}개'
    return h, t
