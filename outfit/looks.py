"""코디 후보 (노멀코어 · 남성 170/66 · M). 기온대별로 고르고 최근 3일과 겹치지 않게 돌린다. 브랜드명 없음."""
C = dict(navy='#2B3247', charcoal='#45474B', khaki='#7B7553', offwhite='#F1EFE8', indigo='#34425E', brown='#4A3125',
         black='#242424', grey='#A9A9A6', beige='#C8B79A', white='#ECEBE6', olive='#5E6146', camel='#A88456',
         lightblue='#B9C7D8', darkgrey='#5A5B5E', cream='#E8E1D0', denim='#55698A', blackdenim='#2F3134', stone='#9C9B97')


def it(name, color, role):
    return dict(name=name, color=C[color], role=role)


# (최저 기온대 기준) band: hot(최고 28+), warm(23~27), mild(17~22), cool(10~16), cold(4~9), freezing(~3)
LOOKS = {
    'hot': [
        ('화이트 티 + 베이지 치노', 'tee', [it('오버핏 반팔 티 · 화이트', 'white', 'top'), it('와이드 치노 반바지 · 베이지', 'beige', 'bottom'), it('캔버스 스니커즈 · 화이트', 'white', 'shoes')], '반팔은 어깨선 살짝 내려오는 M. 반바지는 무릎 위 3cm.'),
        ('린넨 셔츠 + 네이비 숏츠', 'shirt', [it('린넨 반팔 셔츠 · 오프화이트', 'offwhite', 'top'), it('치노 숏츠 · 네이비', 'navy', 'bottom'), it('스니커즈 · 그레이', 'stone', 'shoes')], '단추 2개 풀고 밑단은 빼서 시원하게.'),
        ('블랙 티 + 그레이 와이드', 'tee', [it('반팔 티 · 블랙', 'black', 'top'), it('와이드 이지팬츠 · 그레이', 'grey', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '이지팬츠는 발목이 살짝 보이게.'),
        ('피케 폴로 + 카키 숏츠', 'polo', [it('피케 폴로 · 네이비', 'navy', 'top'), it('치노 숏츠 · 카키', 'khaki', 'bottom'), it('로퍼 · 다크브라운', 'brown', 'shoes')], '폴로 단추는 하나만 풀기.'),
    ],
    'warm': [
        ('옥스퍼드 셔츠 + 네이비 치노', 'shirt', [it('옥스퍼드 셔츠 · 라이트블루', 'lightblue', 'top'), it('치노 팬츠 · 네이비', 'navy', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '소매 두 번 롤업, 밑단은 반만 넣기.'),
        ('헤비 티 + 인디고 데님', 'tee', [it('헤비 반팔 티 · 오프화이트', 'offwhite', 'top'), it('스트레이트 데님 · 인디고', 'indigo', 'bottom'), it('스니커즈 · 블랙', 'black', 'shoes')], '두께감 있는 티라 혼자 입어도 단정.'),
        ('니트 폴로 + 차콜 슬랙스', 'polo', [it('반팔 니트 폴로 · 네이비', 'navy', 'top'), it('와이드 슬랙스 · 차콜', 'charcoal', 'bottom'), it('로퍼 · 다크브라운', 'brown', 'shoes')], '니트 폴로는 레귤러핏 M.'),
        ('스트라이프 티 + 베이지 치노', 'tee', [it('긴팔 티 · 그레이', 'grey', 'top'), it('치노 팬츠 · 베이지', 'beige', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '소매는 팔꿈치까지 걷어서.'),
    ],
    'mild': [
        ('셔츠 재킷 레이어드', 'tee', [it('크루넥 티셔츠 · 그레이', 'grey', 'top'), it('셔츠 재킷 · 카키', 'khaki', 'outer'), it('스트레이트 데님 · 블랙', 'blackdenim', 'bottom'), it('스니커즈 · 블랙', 'black', 'shoes')], '셔츠 재킷은 단추 열고 걸치듯. 낮에 더우면 손에.'),
        ('차분한 니트 폴로', 'polo', [it('니트 폴로 · 네이비', 'navy', 'top'), it('와이드 슬랙스 · 차콜', 'charcoal', 'bottom'), it('로퍼 · 다크브라운', 'brown', 'shoes')], '단추 하나 풀고 소매는 그대로.'),
        ('깔끔한 옥스퍼드 셔츠', 'shirt', [it('옥스퍼드 셔츠 · 화이트', 'offwhite', 'top'), it('치노 팬츠 · 네이비', 'navy', 'bottom'), it('스니커즈 · 그레이', 'stone', 'shoes')], '밑단은 반만 넣어 깔끔하게.'),
        ('데님 재킷 + 화이트 티', 'tee', [it('트러커 데님 재킷 · 인디고', 'indigo', 'outer'), it('헤비 크루넥 티 · 오프화이트', 'offwhite', 'top'), it('치노 팬츠 · 베이지', 'beige', 'bottom'), it('캔버스 스니커즈 · 화이트', 'white', 'shoes')], '데님 재킷은 단추 열고. 낮엔 어깨에 걸쳐도 OK.'),
        ('맨투맨 + 올리브 치노', 'tee', [it('맨투맨 · 차콜', 'charcoal', 'top'), it('치노 팬츠 · 올리브', 'olive', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '맨투맨은 밑단 고무가 골반에 걸리는 길이.'),
        # 2026-11-19 추가
        ('네이비 가디건 + 셔츠', 'shirt', [it('옥스퍼드 셔츠 · 화이트', 'offwhite', 'top'), it('니트 가디건 · 네이비', 'navy', 'outer'), it('치노 팬츠 · 베이지', 'beige', 'bottom'), it('로퍼 · 다크브라운', 'brown', 'shoes')], '가디건 단추는 아래 하나만 잠그기.'),
        ('코치재킷 + 화이트 티', 'tee', [it('크루넥 티셔츠 · 화이트', 'white', 'top'), it('코치 재킷 · 블랙', 'black', 'outer'), it('와이드 이지팬츠 · 그레이', 'grey', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '코치재킷은 지퍼·단추 열고 가볍게.'),
    ],
    'cool': [
        ('네이비 블레이저 + 화이트 셔츠', 'shirt', [it('옥스퍼드 셔츠 · 화이트', 'offwhite', 'top'), it('언컨 블레이저 · 네이비', 'navy', 'outer'), it('와이드 슬랙스 · 그레이', 'grey', 'bottom'), it('로퍼 · 다크브라운', 'brown', 'shoes')], '블레이저 단추는 열고, 셔츠 단추 하나 풀기.'),
        ('크루넥 니트 + 셔츠 깃', 'shirt', [it('크루넥 니트 · 네이비', 'navy', 'top'), it('옥스퍼드 셔츠 · 라이트블루', 'lightblue', 'top'), it('치노 팬츠 · 베이지', 'beige', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '니트 위로 셔츠 깃만 살짝, 밑단도 2cm.'),
        ('카키 필드재킷', 'tee', [it('헤비 크루넥 티 · 오프화이트', 'offwhite', 'top'), it('필드 재킷 · 카키', 'khaki', 'outer'), it('스트레이트 데님 · 인디고', 'indigo', 'bottom'), it('스니커즈 · 블랙', 'black', 'shoes')], '재킷은 허리 스트링 살짝 조여서.'),
        ('차콜 가디건 레이어드', 'tee', [it('크루넥 티 · 화이트', 'white', 'top'), it('니트 가디건 · 차콜', 'charcoal', 'outer'), it('와이드 슬랙스 · 블랙', 'black', 'bottom'), it('로퍼 · 블랙', 'black', 'shoes')], '가디건 단추 모두 풀고 티가 보이게.'),
        ('스웻 후드 + 코치재킷', 'tee', [it('후드 스웻셔츠 · 그레이', 'grey', 'top'), it('코치 재킷 · 네이비', 'navy', 'outer'), it('스트레이트 데님 · 블랙', 'blackdenim', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '후드는 재킷 밖으로 깔끔하게 꺼내기.'),
        # 2026-11-19 추가 (같은 코디가 2~3일마다 반복되던 문제)
        ('스웨이드 재킷 + 크림 니트', 'tee', [it('크루넥 니트 · 크림', 'cream', 'top'), it('스웨이드 트러커 재킷 · 브라운', 'brown', 'outer'), it('스트레이트 데님 · 인디고', 'indigo', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '스웨이드는 단추 열고, 니트는 밑단을 접지 않고 그대로.'),
        ('울 오버셔츠 + 터틀넥', 'tee', [it('얇은 터틀넥 니트 · 크림', 'cream', 'top'), it('울 오버셔츠 · 차콜', 'charcoal', 'outer'), it('치노 팬츠 · 베이지', 'beige', 'bottom'), it('로퍼 · 다크브라운', 'brown', 'shoes')], '오버셔츠는 단추 다 열고 재킷처럼.'),
        ('해링턴 재킷 + 옥스퍼드', 'shirt', [it('옥스퍼드 셔츠 · 라이트블루', 'lightblue', 'top'), it('해링턴 재킷 · 네이비', 'navy', 'outer'), it('와이드 슬랙스 · 그레이', 'grey', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '재킷 지퍼는 가슴 아래까지만.'),
        ('트렌치코트 + 네이비 니트', 'tee', [it('크루넥 니트 · 네이비', 'navy', 'top'), it('트렌치코트 · 베이지', 'beige', 'outer'), it('스트레이트 데님 · 블랙', 'blackdenim', 'bottom'), it('로퍼 · 블랙', 'black', 'shoes')], '트렌치 벨트는 뒤로 묶어 깔끔하게.'),
    ],
    'cold': [
        ('울 코트 + 터틀넥', 'tee', [it('터틀넥 니트 · 블랙', 'black', 'top'), it('싱글 울 코트 · 카멜', 'camel', 'outer'), it('울 슬랙스 · 차콜', 'charcoal', 'bottom'), it('더비 슈즈 · 블랙', 'black', 'shoes')], '코트는 무릎 위 기장, 단추 열고 걸치기.'),
        ('경량 패딩 + 니트', 'tee', [it('크루넥 니트 · 크림', 'cream', 'top'), it('경량 패딩 재킷 · 네이비', 'navy', 'outer'), it('치노 팬츠 · 베이지', 'beige', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '경량 패딩은 니트 위로 딱 맞게 M.'),
        ('발마칸 코트 + 셔츠', 'shirt', [it('옥스퍼드 셔츠 · 화이트', 'offwhite', 'top'), it('발마칸 코트 · 차콜', 'charcoal', 'outer'), it('스트레이트 데님 · 인디고', 'indigo', 'bottom'), it('로퍼 · 다크브라운', 'brown', 'shoes')], '셔츠 단추 끝까지 잠그고 코트는 열어서.'),
        ('플리스 + 블랙 데님', 'tee', [it('하프집 플리스 · 오프화이트', 'offwhite', 'top'), it('스트레이트 데님 · 블랙', 'blackdenim', 'bottom'), it('스니커즈 · 그레이', 'stone', 'shoes')], '플리스 지퍼는 반쯤 내려서.'),
        ('숏 패딩 + 그레이 니트', 'tee', [it('크루넥 니트 · 그레이', 'grey', 'top'), it('숏 패딩 · 블랙', 'black', 'outer'), it('와이드 슬랙스 · 차콜', 'charcoal', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '숏 패딩은 엉덩이 위 기장, 바지는 넉넉하게.'),
        # 2026-11-19 추가
        ('더플코트 + 후드', 'tee', [it('후드 스웻셔츠 · 그레이', 'grey', 'top'), it('더플코트 · 네이비', 'navy', 'outer'), it('치노 팬츠 · 베이지', 'beige', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '후드는 코트 깃 밖으로 꺼내 캐주얼하게.'),
        ('피코트 + 크림 터틀넥', 'tee', [it('터틀넥 니트 · 크림', 'cream', 'top'), it('피코트 · 네이비', 'navy', 'outer'), it('울 슬랙스 · 그레이', 'grey', 'bottom'), it('더비 슈즈 · 블랙', 'black', 'shoes')], '피코트는 단추 잠그면 더 단정해요.'),
        ('울 블레이저 + 니트', 'tee', [it('크루넥 니트 · 그레이', 'grey', 'top'), it('울 블레이저 · 차콜', 'charcoal', 'outer'), it('와이드 슬랙스 · 블랙', 'black', 'bottom'), it('로퍼 · 블랙', 'black', 'shoes')], '두꺼운 니트 위라 블레이저는 한 치수 여유 있게.'),
        ('보아 플리스 재킷 + 맨투맨', 'tee', [it('맨투맨 · 네이비', 'navy', 'top'), it('보아 플리스 재킷 · 크림', 'cream', 'outer'), it('스트레이트 데님 · 인디고', 'indigo', 'bottom'), it('스니커즈 · 블랙', 'black', 'shoes')], '보아 재킷은 지퍼 반쯤 열기.'),
        ('봄버 재킷 + 크림 니트', 'tee', [it('크루넥 니트 · 크림', 'cream', 'top'), it('봄버 재킷 · 올리브', 'olive', 'outer'), it('와이드 슬랙스 · 차콜', 'charcoal', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '봄버는 허리선 기장, 니트 밑단이 살짝 보이게.'),
    ],
    'freezing': [
        ('롱 패딩 + 터틀넥', 'tee', [it('터틀넥 니트 · 차콜', 'charcoal', 'top'), it('롱 패딩 · 블랙', 'black', 'outer'), it('기모 슬랙스 · 블랙', 'black', 'bottom'), it('부츠 · 블랙', 'black', 'shoes')], '목도리 하나 더하면 체감 온도가 확 달라져요.'),
        ('덕다운 숏패딩 + 니트', 'tee', [it('크루넥 니트 · 네이비', 'navy', 'top'), it('덕다운 숏패딩 · 카키', 'olive', 'outer'), it('기모 데님 · 인디고', 'indigo', 'bottom'), it('스니커즈 · 블랙', 'black', 'shoes')], '안에 히트텍류 이너 필수.'),
        ('울 코트 + 경량 패딩 레이어드', 'tee', [it('터틀넥 니트 · 크림', 'cream', 'top'), it('경량 패딩 조끼 · 블랙', 'black', 'outer'), it('울 코트 · 차콜', 'charcoal', 'outer'), it('울 슬랙스 · 그레이', 'grey', 'bottom'), it('더비 슈즈 · 블랙', 'black', 'shoes')], '코트 안에 패딩 조끼로 보온, 겉은 깔끔하게.'),
        ('후드 + 숏패딩', 'tee', [it('후드 스웻셔츠 · 그레이', 'grey', 'top'), it('숏 패딩 · 네이비', 'navy', 'outer'), it('기모 이지팬츠 · 블랙', 'black', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '후드는 패딩 밖으로 꺼내 캐주얼하게.'),
        # 2026-11-19 추가
        ('블랙 롱코트 + 그레이 터틀넥', 'tee', [it('터틀넥 니트 · 그레이', 'grey', 'top'), it('롱 울 코트 · 블랙', 'black', 'outer'), it('울 슬랙스 · 차콜', 'charcoal', 'bottom'), it('더비 슈즈 · 블랙', 'black', 'shoes')], '코트 안에 얇은 이너 하나 더 — 목도리는 그레이 톤.'),
        ('다운 파카 + 크림 니트', 'tee', [it('크루넥 니트 · 크림', 'cream', 'top'), it('다운 파카 · 네이비', 'navy', 'outer'), it('기모 데님 · 인디고', 'indigo', 'bottom'), it('부츠 · 다크브라운', 'brown', 'shoes')], '파카 후드는 바람 불 때만 쓰기.'),
        ('크림 숏패딩 + 차콜 후드', 'tee', [it('후드 스웻셔츠 · 차콜', 'charcoal', 'top'), it('숏 패딩 · 크림', 'cream', 'outer'), it('기모 이지팬츠 · 그레이', 'grey', 'bottom'), it('스니커즈 · 블랙', 'black', 'shoes')], '밝은 패딩엔 어두운 하의로 균형.'),
        ('무스탕 + 블랙 터틀넥', 'tee', [it('터틀넥 니트 · 블랙', 'black', 'top'), it('무스탕 재킷 · 브라운', 'brown', 'outer'), it('스트레이트 데님 · 블랙', 'blackdenim', 'bottom'), it('부츠 · 블랙', 'black', 'shoes')], '무스탕은 지퍼 열고, 올블랙 이너로 깔끔하게.'),
        ('카멜 더플코트 + 셔츠 니트', 'shirt', [it('옥스퍼드 셔츠 · 화이트', 'offwhite', 'top'), it('크루넥 니트 · 네이비', 'navy', 'top'), it('더플코트 · 카멜', 'camel', 'outer'), it('울 슬랙스 · 차콜', 'charcoal', 'bottom'), it('로퍼 · 다크브라운', 'brown', 'shoes')], '셔츠 깃만 니트 밖으로.'),
    ],
}

RAIN_SHOES = it('레더 스니커즈 · 블랙', 'black', 'shoes')
LIGHT = {'white', 'offwhite', 'beige', 'cream', 'stone', 'grey'}


def band(tmin, tmax):
    if tmax >= 28: return 'hot'
    if tmax >= 23: return 'warm'
    if tmax >= 17: return 'mild'
    if tmax >= 10: return 'cool'
    if tmax >= 4: return 'cold'
    return 'freezing'


# ---- 핀터레스트 검색어 (2026-11-19): 한국어 긴 검색어는 엉뚱한 결과가 많아 영어 핵심 단어로 ----
COLOR_EN = {'오프화이트': 'off white', '화이트': 'white', '베이지': 'beige', '네이비': 'navy', '그레이': 'grey', '블랙': 'black',
            '다크브라운': 'dark brown', '브라운': 'brown', '카키': 'khaki', '라이트블루': 'light blue', '인디고': 'indigo',
            '차콜': 'charcoal', '올리브': 'olive', '카멜': 'camel', '크림': 'cream'}
GARMENT_EN = [  # (정규식, 영어) 위에서부터 먼저 맞는 것
    (r'반팔 니트 폴로|니트 폴로', 'knit polo'), (r'피케 폴로', 'polo shirt'), (r'린넨', 'linen shirt'),
    (r'옥스퍼드', 'oxford shirt'), (r'터틀넥', 'turtleneck'), (r'크루넥 니트', 'crewneck sweater'),
    (r'가디건', 'cardigan'), (r'후드', 'hoodie'), (r'맨투맨', 'sweatshirt'), (r'하프집 플리스', 'half zip fleece'),
    (r'보아 플리스', 'sherpa fleece jacket'), (r'긴팔 티', 'long sleeve tee'), (r'반팔|티셔츠|티$', 't-shirt'),
    (r'숏 ?패딩', 'short puffer jacket'), (r'롱 패딩', 'long puffer coat'), (r'경량 패딩 조끼', 'puffer vest'),
    (r'경량 패딩', 'light down jacket'), (r'다운 파카', 'down parka'), (r'더플', 'duffle coat'), (r'피코트', 'peacoat'),
    (r'트렌치', 'trench coat'), (r'발마칸', 'balmacaan coat'), (r'코트', 'wool overcoat'), (r'블레이저', 'blazer'),
    (r'셔츠 재킷|오버셔츠', 'overshirt'), (r'트러커 데님', 'denim jacket'), (r'스웨이드', 'suede jacket'),
    (r'필드', 'field jacket'), (r'코치', 'coach jacket'), (r'해링턴', 'harrington jacket'), (r'봄버', 'bomber jacket'),
    (r'무스탕', 'shearling jacket'), (r'반바지|숏츠', 'shorts'), (r'데님', 'jeans'), (r'치노', 'chinos'),
    (r'슬랙스', 'trousers'), (r'이지팬츠', 'relaxed pants'),
]
SEASON_EN = {'hot': 'summer', 'warm': 'summer', 'mild': 'spring', 'cool': 'fall', 'cold': 'winter', 'freezing': 'winter'}
STYLE_EN = ['minimal', 'casual', 'street style', 'korean style', 'smart casual', 'clean']


def en_item(name):
    import re
    g, _, c = name.partition(' · ')
    for pat, e in GARMENT_EN:
        if re.search(pat, g):
            return f"{COLOR_EN.get(c.strip(), '')} {e}".strip()
    return None


def pin_query(items, b, n):
    """outer → top → bottom 핵심 3개 + 계절 + (날마다 바뀌는) 스타일 단어."""
    order = {'outer': 0, 'top': 1, 'bottom': 2}
    xs = sorted((x for x in items if x['role'] in order), key=lambda x: order[x['role']])
    words = [w for w in (en_item(x['name']) for x in xs) if w][:3]
    return ' '.join(words + ['men', SEASON_EN[b], 'outfit', STYLE_EN[n % len(STYLE_EN)]])


def pick(tmin, tmax, rain, recent_titles, seed):
    """recent_titles: {제목: 며칠 전} (또는 옛 형식 set). 가장 오래 안 보여준 코디부터 3개."""
    b = band(tmin, tmax)
    pool = LOOKS[b]
    if not isinstance(recent_titles, dict):
        recent_titles = {t: 1 for t in recent_titles}
    order = sorted(range(len(pool)), key=lambda i: ((i - seed) % len(pool)))
    use = sorted(order, key=lambda i: -recent_titles.get(pool[i][0], 999))[:3]   # 안 보여준 것(999) → 오래전 것 순
    out = []
    for i in use:
        title, kind, items, tip = pool[i]
        items = [dict(x) for x in items]
        if rain:
            items = [RAIN_SHOES if x['role'] == 'shoes' and x['color'] in [C[c] for c in LIGHT | {'brown'}] else x for x in items]
            for x in items:
                if x['role'] == 'bottom' and x['color'] in [C[c] for c in LIGHT]:
                    x.update(name=x['name'].split(' · ')[0] + ' · 차콜', color=C['charcoal'])
            tip = tip + ' 비 소식 — 어두운 하의·우산 챙기기.'
        pin = pin_query(items, b, seed + i)
        out.append(dict(title=title, kind=kind, items=items, tip=tip, pin=pin))
    return out
