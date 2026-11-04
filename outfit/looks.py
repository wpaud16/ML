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
    ],
    'cool': [
        ('네이비 블레이저 + 화이트 셔츠', 'shirt', [it('옥스퍼드 셔츠 · 화이트', 'offwhite', 'top'), it('언컨 블레이저 · 네이비', 'navy', 'outer'), it('와이드 슬랙스 · 그레이', 'grey', 'bottom'), it('로퍼 · 다크브라운', 'brown', 'shoes')], '블레이저 단추는 열고, 셔츠 단추 하나 풀기.'),
        ('크루넥 니트 + 셔츠 깃', 'shirt', [it('크루넥 니트 · 네이비', 'navy', 'top'), it('옥스퍼드 셔츠 · 라이트블루', 'lightblue', 'top'), it('치노 팬츠 · 베이지', 'beige', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '니트 위로 셔츠 깃만 살짝, 밑단도 2cm.'),
        ('카키 필드재킷', 'tee', [it('헤비 크루넥 티 · 오프화이트', 'offwhite', 'top'), it('필드 재킷 · 카키', 'khaki', 'outer'), it('스트레이트 데님 · 인디고', 'indigo', 'bottom'), it('스니커즈 · 블랙', 'black', 'shoes')], '재킷은 허리 스트링 살짝 조여서.'),
        ('차콜 가디건 레이어드', 'tee', [it('크루넥 티 · 화이트', 'white', 'top'), it('니트 가디건 · 차콜', 'charcoal', 'outer'), it('와이드 슬랙스 · 블랙', 'black', 'bottom'), it('로퍼 · 블랙', 'black', 'shoes')], '가디건 단추 모두 풀고 티가 보이게.'),
        ('스웻 후드 + 코치재킷', 'tee', [it('후드 스웻셔츠 · 그레이', 'grey', 'top'), it('코치 재킷 · 네이비', 'navy', 'outer'), it('스트레이트 데님 · 블랙', 'blackdenim', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '후드는 재킷 밖으로 깔끔하게 꺼내기.'),
    ],
    'cold': [
        ('울 코트 + 터틀넥', 'tee', [it('터틀넥 니트 · 블랙', 'black', 'top'), it('싱글 울 코트 · 카멜', 'camel', 'outer'), it('울 슬랙스 · 차콜', 'charcoal', 'bottom'), it('더비 슈즈 · 블랙', 'black', 'shoes')], '코트는 무릎 위 기장, 단추 열고 걸치기.'),
        ('경량 패딩 + 니트', 'tee', [it('크루넥 니트 · 크림', 'cream', 'top'), it('경량 패딩 재킷 · 네이비', 'navy', 'outer'), it('치노 팬츠 · 베이지', 'beige', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '경량 패딩은 니트 위로 딱 맞게 M.'),
        ('발마칸 코트 + 셔츠', 'shirt', [it('옥스퍼드 셔츠 · 화이트', 'offwhite', 'top'), it('발마칸 코트 · 차콜', 'charcoal', 'outer'), it('스트레이트 데님 · 인디고', 'indigo', 'bottom'), it('로퍼 · 다크브라운', 'brown', 'shoes')], '셔츠 단추 끝까지 잠그고 코트는 열어서.'),
        ('플리스 + 블랙 데님', 'tee', [it('하프집 플리스 · 오프화이트', 'offwhite', 'top'), it('스트레이트 데님 · 블랙', 'blackdenim', 'bottom'), it('스니커즈 · 그레이', 'stone', 'shoes')], '플리스 지퍼는 반쯤 내려서.'),
        ('숏 패딩 + 그레이 니트', 'tee', [it('크루넥 니트 · 그레이', 'grey', 'top'), it('숏 패딩 · 블랙', 'black', 'outer'), it('와이드 슬랙스 · 차콜', 'charcoal', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '숏 패딩은 엉덩이 위 기장, 바지는 넉넉하게.'),
    ],
    'freezing': [
        ('롱 패딩 + 터틀넥', 'tee', [it('터틀넥 니트 · 차콜', 'charcoal', 'top'), it('롱 패딩 · 블랙', 'black', 'outer'), it('기모 슬랙스 · 블랙', 'black', 'bottom'), it('부츠 · 블랙', 'black', 'shoes')], '목도리 하나 더하면 체감 온도가 확 달라져요.'),
        ('덕다운 숏패딩 + 니트', 'tee', [it('크루넥 니트 · 네이비', 'navy', 'top'), it('덕다운 숏패딩 · 카키', 'olive', 'outer'), it('기모 데님 · 인디고', 'indigo', 'bottom'), it('스니커즈 · 블랙', 'black', 'shoes')], '안에 히트텍류 이너 필수.'),
        ('울 코트 + 경량 패딩 레이어드', 'tee', [it('터틀넥 니트 · 크림', 'cream', 'top'), it('경량 패딩 조끼 · 블랙', 'black', 'outer'), it('울 코트 · 차콜', 'charcoal', 'outer'), it('울 슬랙스 · 그레이', 'grey', 'bottom'), it('더비 슈즈 · 블랙', 'black', 'shoes')], '코트 안에 패딩 조끼로 보온, 겉은 깔끔하게.'),
        ('후드 + 숏패딩', 'tee', [it('후드 스웻셔츠 · 그레이', 'grey', 'top'), it('숏 패딩 · 네이비', 'navy', 'outer'), it('기모 이지팬츠 · 블랙', 'black', 'bottom'), it('스니커즈 · 화이트', 'white', 'shoes')], '후드는 패딩 밖으로 꺼내 캐주얼하게.'),
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


def pick(tmin, tmax, rain, recent_titles, seed):
    b = band(tmin, tmax)
    pool = LOOKS[b]
    order = sorted(range(len(pool)), key=lambda i: ((i - seed) % len(pool)))
    fresh = [i for i in order if pool[i][0] not in recent_titles]
    use = (fresh + [i for i in order if i not in fresh])[:3]
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
        pin = ' '.join(x['name'].split(' · ')[1] + ' ' + x['name'].split(' · ')[0].split()[-1] for x in items if x['role'] != 'shoes') + ' 남자 코디'
        out.append(dict(title=title, kind=kind, items=items, tip=tip, pin=pin))
    return out
