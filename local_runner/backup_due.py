"""GitHub Actions 예비 실행 판단 (2026-11-08). backup.yml 이 10분마다 실행.
노트북 예약 시각(local_runner/schedule.json, 브리핑 관리 앱이 등록 때 push)과 시작 기록(heartbeat/laptop.json)을 보고
- 이미 끝났으면(발송 기록·예측 결과) → 그냥 둠
- 예약 시각 + 15분이 지났는데 노트북 시작 기록이 없으면(꺼짐) → 예비 실행
- 노트북이 시작했는데 최대 시간(MAX_MIN)이 지나도 안 끝났으면(멈춤) → 예비 실행
- Actions 가 이미 시작했으면(heartbeat/actions.json) 진행 중으로 보고 기다림, 하루 2번까지만
출력: 실행할 작업 이름(한 줄에 하나). --mark 를 주면 actions.json 에 시작 기록을 남긴다(커밋은 워크플로가)."""
import datetime as dt, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
KST = dt.timezone(dt.timedelta(hours=9))
DEFAULT = {'night': '03:00', 'outfit': '06:00', 'brief': '08:00'}
GRACE_MIN = 15                                         # 예약 시각 후 이만큼 지나도 노트북 시작 기록이 없으면 꺼진 것으로 봄
MAX_MIN = {'night': 180, 'outfit': 30, 'brief': 40}    # 노트북·Actions 한 번 실행에 걸리는 최대 시간
WORKFLOW = {'night': 'auction_predict.yml', 'outfit': 'outfit.yml', 'brief': 'morning_brief.yml'}
HB = os.path.join(HERE, 'heartbeat')


def jload(p, d=None):
    try:
        return json.load(open(p, encoding='utf-8'))
    except Exception:
        return d if d is not None else {}


def target_day(job, now):
    # 경매 예측은 '18시 이후는 다음 날' 규칙(batch_predict.py day) → 03시 실행분은 그날
    return (now + dt.timedelta(hours=6)).date() if job == 'night' else now.date()


def done(job, day):
    d = day.isoformat()
    if job == 'outfit': return os.path.exists(os.path.join(REPO, 'outfit', d, 'sent.txt'))
    if job == 'brief': return os.path.exists(os.path.join(REPO, 'brief', 'sent', d + '.txt'))
    return jload(os.path.join(REPO, 'auction_model', 'predictions', 'latest.json')).get('date') == d


def decide(job, now, sch, lap, act):
    day = target_day(job, now)
    if done(job, day): return False, '이미 완료'
    s = sch.get(job) or {}
    hh, mm = map(int, (s.get('time') or DEFAULT[job]).split(':'))
    start = dt.datetime.combine(day, dt.time(hh, mm), KST)
    a = act.get(job) or {}
    if a.get('date') == day.isoformat():
        if a.get('n', 0) >= 2: return False, 'Actions 2번 시도함 → 그만'
        if now < dt.datetime.fromisoformat(a['at']) + dt.timedelta(minutes=MAX_MIN[job]): return False, 'Actions 진행 중'
    if s.get('enabled', True) is False:
        return (now >= start), '노트북 예약 꺼짐'
    l = lap.get(job) or {}
    if l.get('date') == day.isoformat():
        t = dt.datetime.fromisoformat(l['at'])
        if now < t + dt.timedelta(minutes=MAX_MIN[job]): return False, f'노트북 실행 중 ({t:%H:%M} 시작)'
        return True, f'노트북 {t:%H:%M} 시작 후 {MAX_MIN[job]}분 넘게 안 끝남'
    if now < start + dt.timedelta(minutes=GRACE_MIN): return False, f'노트북 예약 {start:%m-%d %H:%M} 대기'
    return True, f'노트북 {start:%H:%M} 예약 뒤 시작 기록 없음 (꺼짐?)'


def main():
    now = dt.datetime.now(KST)
    if os.environ.get('NOW'): now = dt.datetime.fromisoformat(os.environ['NOW'])   # 시험용
    sch = jload(os.path.join(HERE, 'schedule.json'))
    lap, act = jload(os.path.join(HB, 'laptop.json')), jload(os.path.join(HB, 'actions.json'))
    run = []
    for job in ('night', 'outfit', 'brief'):
        ok, why = decide(job, now, sch, lap, act)
        print(f'[{now:%m-%d %H:%M}] {job}: {"▶ 예비 실행" if ok else "-"} ({why})', file=sys.stderr)
        if ok: run.append(job)
    if '--mark' in sys.argv and run:
        os.makedirs(HB, exist_ok=True)
        for job in run:
            day = target_day(job, now).isoformat(); a = act.get(job) or {}
            act[job] = dict(date=day, at=now.isoformat(timespec='seconds'), n=(a.get('n', 0) + 1) if a.get('date') == day else 1)
        json.dump(act, open(os.path.join(HB, 'actions.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for job in run: print(WORKFLOW[job])


if __name__ == '__main__':
    main()
