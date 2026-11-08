"""서울 강동구 날씨 (Open-Meteo, 키 필요 없음 · 기상청 모델 우선).
2026-11-08 사용자 요청: 오늘 날씨만 (내일·모레 비 예보 제거), 시간대별 기온 표시."""
import json, urllib.request, datetime as dt

LAT, LON = 37.530, 127.124
WD = '월화수목금토일'
SKY = {0: '☀️ 맑음', 1: '🌤 대체로 맑음', 2: '⛅ 구름 많음', 3: '☁️ 흐림', 45: '🌫 안개', 48: '🌫 안개',
       51: '🌦 이슬비', 53: '🌦 이슬비', 55: '🌦 이슬비', 61: '🌧 비', 63: '🌧 비', 65: '🌧 강한 비', 66: '🌧 어는 비', 67: '🌧 어는 비',
       71: '🌨 눈', 73: '🌨 눈', 75: '🌨 많은 눈', 77: '🌨 싸락눈', 80: '🌦 소나기', 81: '🌦 소나기', 82: '⛈ 강한 소나기',
       85: '🌨 눈', 86: '🌨 많은 눈', 95: '⛈ 뇌우', 96: '⛈ 뇌우', 99: '⛈ 뇌우'}
HOURS = (6, 9, 12, 15, 18, 21)   # 시간대별 기온 칸


def fetch():
    base = (f'https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&timezone=Asia%2FSeoul&forecast_days=1'
            '&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum'
            '&hourly=temperature_2m,precipitation,snowfall,weather_code')
    for extra, name in (('&models=kma_seamless', '기상청 모델'), ('', '기본 모델')):
        try:
            with urllib.request.urlopen(base + extra, timeout=30) as r:
                d = json.load(r)
            if d['daily']['temperature_2m_max'][0] is not None and d['hourly']['temperature_2m'][12] is not None:
                d['_src'] = name
                return d
        except Exception as e:
            print('weather', name, e)
    raise RuntimeError('날씨를 가져오지 못했습니다')


def level(mm):
    if mm <= 0: return '없음'
    if mm < 5: return '약한 비'
    if mm < 20: return '보통 비'
    if mm < 50: return '많은 비'
    return '매우 많은 비'


def when(h):
    return '새벽' if h < 6 else '오전' if h < 12 else '낮' if h < 14 else '오후' if h < 18 else '밤'


def icon(code):
    return SKY.get(code, '·').split(' ')[0]


def build():
    d = fetch()
    today = dt.date.fromisoformat(d['daily']['time'][0])
    tmin, tmax = round(d['daily']['temperature_2m_min'][0]), round(d['daily']['temperature_2m_max'][0])
    H = d['hourly']
    hrs = [(dt.datetime.fromisoformat(t), p or 0, s or 0) for t, p, s in zip(H['time'], H['precipitation'], H['snowfall'])]
    hrs = [x for x in hrs if x[0].date() == today]
    seg = [(t, p, s) for t, p, s in hrs if p >= 0.1]   # 오늘 비·눈 오는 시간
    hourly = []
    for t, tc, wc, p in zip(H['time'], H['temperature_2m'], H['weather_code'], H['precipitation']):
        h = dt.datetime.fromisoformat(t)
        if h.date() == today and h.hour in HOURS and tc is not None:
            hourly.append(dict(h=h.hour, t=round(tc), icon=icon(wc), rain=bool(p and p >= 0.1)))
    snow = any(s > 0 for _, _, s in seg)
    word = '눈' if snow else '비'
    if seg:
        mm = round(sum(p for _, p, _ in seg), 1)
        lv = level(mm)
        start, last = seg[0][0], seg[-1][0]
        end = '자정 넘어서까지' if last.hour == 23 else f'{when(last.hour + 1)} {last.hour + 1}시쯤'
        title = f'☔ 오늘 {word} — {lv}' if not snow else '❄️ 오늘 눈'
        rain = [['시작', f'{when(start.hour)} {start.hour}시'], ['그침', end],
                ['예상 강수량', f'약 {mm}mm (강동구)'], ['예상 수준', lv + (' → 우산 필수' if mm >= 5 else ' → 우산 챙기기')]]
    else:
        mm, lv, title = 0, '없음', '☀️ 오늘 비·눈 소식 없음'
        rain = [['오늘', '비·눈 소식 없음']]
    gap = tmax - tmin
    guide = f'<b>아침 {tmin}°, 낮 {tmax}°.</b> '
    guide += ('일교차 ' + str(gap) + '° — <b>벗기 쉬운 겉옷</b>으로 레이어드하세요.') if gap >= 9 else ('하루 종일 기온 차가 크지 않아요.')
    if seg:
        guide += f' {when(seg[0][0].hour)}부터 {word} — <b>우산</b> 챙기세요.'
    out = dict(date=f'{today.month}월 {today.day}일 ({WD[today.weekday()]})', tmin=str(tmin), tmax=str(tmax),
               sky=SKY.get(d['daily']['weather_code'][0], '날씨'), sub=f'일교차 {gap}°', rain_title=title, rain=rain, level=lv,
               hourly=hourly, guide=guide, footer=f"날씨: Open-Meteo ({d['_src']}) · 서울 강동구 · 오늘 예보")
    return out, today, (seg[0][0].hour if seg else None), bool(seg)
