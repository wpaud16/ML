# 세션 인계 (2026-11-05 오후 기준)

새 세션 시작 시: 이 문서를 먼저 읽고 이어서 진행. 저장소 wpaud16/ML (public).
- 연결: `add_repo owner=wpaud16 repo=ML access=push` → `git clone --depth 1 https://github.com/wpaud16/ml /home/user/ml`
- push: `git fetch origin main && git rebase origin/main && git push origin HEAD:main` (봇 커밋이 잦음)
- **이 작업공간에서 리치고·github.io·야후·네이버 접속 불가** → 리치고가 필요한 확인은 `auction_model/dev/probe_richgo.py` 를 고쳐 push 하면
  Actions(`probe_richgo.yml`)가 실행·결과를 `dev/probe/` 에 커밋함. 실행 상태는 공개 API로 확인:
  `curl -s https://api.github.com/repos/wpaud16/ML/actions/workflows/<파일>.yml/runs?per_page=1`
- GitHub 버튼(Run workflow)은 직접 못 누름(gh 토큰 없음) → push 로 실행되는 워크플로 사용.
- 구글 인증: GitHub Secrets `GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN` (OAuth 앱 jm-brief, 프로덕션 게시).
  로컬 테스트용 refresh token 파일은 이전 세션 scratchpad 에만 있었음(삭제됨) → 로컬 메일 테스트가 필요하면 사용자에게 OAuth 재발급
  (google_api.py 참고: client JSON + 인증 URL → code 교환) 또는 Actions 로 테스트.

## 0. 진행 로드맵 (2026-11-05 사용자 지정, 순서대로)
1. **명확한 시세 확정** ✅ 11/5 확정: 아파트 = M 가중 시세(층 보정 실거래 12개월[최근성 반감기 3개월] 과 층 보정 리치고를 거래 수·분산에 따라 섞음, 실거래 비중 최대 70%) + 현재 앙상블 (백테스트 5.08→4.78%, dev/combo_bt.py), 오피스텔 = 리치고 유지. 과정: 국토부 실거래(공공데이터포털, Secret MOLIT_API_KEY) 수집 `dev/molit_collect.py`·`dev_molit.yml` → `dev/sise_bt.py` 로 시세 기준 7가지(리치고·실거래 6/12개월·최근 1건·혼합·분위) 백테스트. 아파트 먼저, 오피스텔도 같은 방식.
2. 시세를 기반으로 예측 모델 재설정 및 확인 ← 코드 적용 완료(커밋 4332df3), 11/5 13:34 시작 배치 결과 확인 대기. 적용 내용:
   - 아파트 모델 시세 = M (`molit.py`; 학습 데이터 mkt → M, 원래 값 mkt_richgo; 보정 재계산 최근 오차 5.67→5.39%), 매일 국토부 실거래 수집(시군구별 13개월 캐시 `molit_cache/`), 재학습 새 사례도 M
   - 결과 필드: model_sise_eok, m_sise, no_trade_12m(True=숨김, None=확인 못 함→숨기지 않음). 카드에 🎯 모델 시세 줄
   - 성적표 '가장 가까운 칸' 열 (closest: 'N명 P%' · 가격 · 시세 대비 %), 기존 48건 채움
   - (사용자가 뺌) 유찰 물건 예측가 상한 = 직전 최저가 × 1.05
   - 11/5 오후 추가: M 의 시군구 지수 추세 보정 제거(거래 단지 구성에 따라 출렁여 힐스테이트다산 실거래 평균 12억대→9.6억 왜곡) → 백테스트 4.77→4.71%
     감정 후 시세 상승형(감정가<시세85% & 1년+8%↑)은 예측 중심을 '시세 × 최근 120일 낙찰가율(heat)'로 (상승형 8.54→7.48%, 전체 4.67%). predict_dict gap_rule
   - 오피스텔 M 방식 백테스트: 역 10분 물건 6.27→6.35% 나빠짐 → 리치고 유지 확정
   - 성적표: 가장 가까운 칸 = 예상 인원 줄 기준, 아파트 % 는 M 기준(dev/rescore_m.py 로 과거분 재계산), 차이 열 구간 표시 제거
   - 11/5 점검 수정: 학습용 국토부 읍·면 매칭(재수집 molit_mode=eup) → 학습 M 재계산(실거래 1288건), 백테스트 전체 4.61%(상승형 규칙 포함), 최근 오차 보정값 갱신.
     retrain heat 자기값 버그 수정, 예측 배치 paths 에 molit.py·nearby.py 추가, 성적표 sise_basis(오피스텔=리치고), load_train mergesort.
   - 주의: auction_train.csv 는 load_train() 정렬 순서로 저장(같은 날짜 행 순서 고정) — dev/sise_bt_S*.csv 인덱스와 맞춰야 함
   - 1년 실거래 0건 아파트: 메일에서 숨김, 웹페이지는 '🔍 실거래 없음(참고)' 칸에 따로 (보이는 물건 오차 4.78→4.60%), 학습은 전체 유지
   - 미채택: 실거래 없을 때 감정가 섞기, 고정 −1.8% 보정(시기별 치우침 불안정)
3. 메일 공유 양식 부분 수정
   - 입찰가마다 시세 대비 % 함께 표기 (예: 14억 (89.5%)) — 기준 시세 = 모델 시세. 코드 완료, 원격 브랜치 `pending/sise-pct`(e449b63) 에 보관 → M 배치 끝나면 main 에 cherry-pick·push (지금 push 하면 배치 취소됨)
4. 드라이브 업로드: 기존 '경제' 폴더(17vN8AZK…) 안 'Steward'(11GxjJi_52o__L9ebgY9VFethEgZy0nuo) 에 STEWARD.md(매뉴얼) + 핵심 파일(HANDOFF, brief·outfit·workflows) — Claude 드라이브 커넥터로 직접. 경매 코드는 매뉴얼의 zip 링크.
   자동 업로드(`brief/steward_sync.py`·`steward_sync.yml`)는 구글 토큰이 drive.readonly 라 403 → push 트리거 꺼 둠(쓰기 권한 재발급 시 사용).
- auction_predict.yml concurrency cancel-in-progress: true (11/5) — 경매 코드 push 하면 진행 중 배치 취소 후 새로 시작.
- 11/5 변경: 예약 실행 지연 대비 여러 번 예약+하루 1회(경매 21·23·01·03시, 날씨 04~07시 :13, 브리핑 04~07시 :23), 수동 발송 = outfit 커밋 메시지 [실행] / brief/trigger.txt push.
  11/5 Claude 브리핑은 주간 한도 초과로 실패 → Python 브리핑(테스트 모드)으로 대체 발송. 정식 전환은 사용자가 안정됐다고 할 때.
- 실험①(최저가÷시세→인원→낙찰가): 모델이 최저가 비율은 이미 반영(구간별 치우침 ±1%), 남은 오차는 실제 인원(2명↓ −5%, 13명↑ +4%). 허수로 낙찰가가 덜 오르는 현상은 안 보임. 64236 은 시세 과소 추정 사례.

## 1. 매일 자동 실행 (KST)
| 시각 | 무엇 | 어디서 | 상태 |
|---|---|---|---|
| 03:00 | 법원자료 수집(임차인·문건) | 노트북 LAPTOP-M47J0JTR 작업 스케줄러 `AuctionTenants` | 노트북 꺼지면 수집 안 됨. GitHub 서버(미국)는 법원 사이트 웹방화벽에 차단(11/5 시험) → 노트북 유지, 필요 시 국내 서버 |
| 21:17·23:17·01:17·03:17 | 경매 예측 배치 → `predictions/latest.json` + 웹페이지 | Actions `auction_predict.yml` (결과 있으면 건너뜀, 코드 push 로도 실행) | 약 95분 |
| 04:13~07:13 매시 | 날씨·코디 메일 (하루 1통) | Actions `outfit.yml` | Python 전환 완료, Claude 예약 작업 trig_014ofhU8tyCW8NDDpN3Nd2mT 끔 |
| 04:23~07:23 매시 | JM's Schedule 브리핑 (Python, 하루 1통) | Actions `morning_brief.yml` (TEST_MODE=0, 11/5 정식 전환) | 문서 섹션 생성·이월 |
| (꺼짐) | JM's Schedule 브리핑 (Claude) | Claude 예약 작업 trig_0179rvk2D2q2hDcCBZKnbPoX | 11/5 Python 정식 전환으로 끔 |

## 2. 아침 브리핑 Python 버전 (`brief/`)
- `google_api.py`(OAuth·시트·문서·드라이브·Gmail), `quote.py`(오늘의 문장), `schedule_doc.py`(할 일 섹션·이월·운동 Day·식사 시간, 쓰기는 TEST_MODE=0 일 때만 — 임시 문서로 쓰기 검증 완료),
  `market.py`(증시 숫자: 야후·네이버 보조, 상승 빨강/하락 파랑), `claude_summary.py`(증시 해설: ANTHROPIC_API_KEY 있을 때만, 없으면 빈칸 — **사용자가 해설은 스킵하기로 함**, Gemini 는 429 로 제거),
  `auction_mail.py`(경매: 아파트/오피스텔 각각 **기일순 2줄 요약 + New 표시**(어제 예측 파일에 없던 물건), 낙찰된 물건·10시 이후 당일 물건 제외, 🔍 예측 불가(단지 못 찾음) 목록, 상세·성적표는 웹페이지 버튼).
- 사용자 결정: 추적 중 카테고리 없앰, 전체 카드·성적표는 메일에서 빼고 웹페이지에만, 성적표 14일, 증시 해설 스킵.
- 네이버 앱 다크모드 때문에 색이 안 보일 수 있음(코드 문제 아님).
- **남은 일**: 며칠 비교 → 사용자 OK 시 `morning_brief.yml` 의 TEST_MODE '0' (문서 쓰기 켜짐·[테스트] 제거) → Claude 브리핑 예약 작업 끄기(update_trigger enabled=false).
- 트래커 Google Doc(1Ot5SNpm…)은 Python 버전에서 더 이상 쓰지 않음(New 판정은 예측 파일 비교).

## 3. 날씨·코디 (`outfit/`)
- `weather.py`: Open-Meteo(기상청 모델 → 실패 시 기본), 서울 강동구, 최저/최고·하늘·시간별 강수(오늘, 없으면 이틀 내 다음 비).
- `looks.py`: 기온대별 노멀코어 코디 후보(브랜드 없음), 최근 3일과 겹치지 않게, 비 오면 어두운 하의·레더 스니커즈.
- `run_outfit.py`: d.json → 기존 `cards.py`/`page.py` 렌더 → 워크플로가 `outfit/YYYY-MM-DD/` 커밋 → 90초 뒤 링크 메일(`run_outfit.py send`). push 실행은 제목 [테스트].
- 11/5 테스트 실행 성공(카드 이미지 확인). 11/5 링크 404는 GitHub Pages 배포 대기열 지연 때문이었음 — 다시 404면 Pages 실행 상태 확인.

## 4. 경매 모델·배치 변경 (11/4~11/5)
- 낙찰된 물건이 리치고 목록에 기일만 바뀌어 남는 버그 → 상세 페이지 낙찰가 있으면 `skipped: 매각완료` (재매각 제외).
- 성적표: 확률표가 최저가 하나로 모이면 구간 '최저가 단일'. 웹페이지 맨 아래 📊 성적표(최근 14일, results.json, 같은 물건 중복 정리).
- **주변 시세** `nearby.py`: 아파트 = 리치고 단지 페이지 `emdComparison`(같은 동, 연식 ±10년) 평당가 중앙값 ÷ 이 단지 평당가 비율 × 이 단지 시세
  (평당가×평수는 대형 평형 부풀림 → 11/5 수정), 오피스텔 = 같은 동 검색 → 전용 ±30% 12개월 실거래. 종합 시세(중앙값)의 4번째 근거.
- **가중 시세** `nearby.weighted_apt`: 단지 페이지 `?pyeongType=<평>` 의 tradeFacts — 3개월 실거래 60 · 층 보정(1~3층↔중고층 ±4%) 20 · 매물 최저 호가 15(상한) · 감정가×1년 변동 5. 아파트만(오피스텔 미적용). 카드에 ⚖ 줄.
- 검색 지역 + **하남시(5호선역 도보 15분 = 직선 920m 이내만, station5)**. 남양주·구리는 8호선 920m.
- 단지 못 찾은 아파트: failed 에 category·risk·court 기록 → 메일·웹페이지 🔍 예측 불가 표시, 법원자료 수집 대상 포함(남양주·구리·하남은 역 판정 불가라 제외).
- 감정 후 시세 상승 경고(감정가 < 시세 85% & 1년 +8%↑): 카드·메일에 ⚠.
- 속도 개선: `auction_predictor._fit` 학습 캐시(결과 동일 확인, 물건당 2.9초→0.02초), 같은 단지 페이지 중복 다운로드 제거. 효과(실행 시간) 아직 미확인.

## 5. 백테스트 결론 (아파트 987건, 2024-07~ 월별 시간 순, 현재 평균 오차 5.09%) — 모두 미채택
| 시도 | 결과 | 파일 |
|---|---|---|
| 주변 대비 상대가격(nb_rel) | 5.05% | dev/nearby_bt.py |
| 감정가 차이×상승률 | 5.09~5.10% | dev/gap_bt.py |
| 구 최근 낙찰가율·인원 | 5.07% | dev/local_heat_bt.py |
| 다른 모델(LightGBM·XGBoost·CatBoost·RF·ET·조합) | 최고 5.03%(현재+CatBoost) | dev/models_bt.py |
- 남은 오차는 경쟁 강도: 입찰 10명+ 물건 평균 +3.1% 과소, 감정후상승 유형 76건 +2.2%·3건 중 1건 +5% 초과.
- 사례: 2024타경3470 힐스테이트다산 예측 9.29억 → 실제 10.718억(2등 10.7108억), 2024타경64236 거여2단지 14.18 → 15.60억(10명).
- 다음 가능성: 가중 시세를 모델 기준으로(매일 기록 쌓은 뒤 1~2개월 후 검증), 조회수·관심 등 경쟁 신호 수집. 사용자는 입찰 인원 개선은 어렵다고 봄.

## 6. 미해결·확인할 것
1. 예측 배치 최신 실행이 끝나면 웹페이지에 주변·가중 시세, 하남, 예측 불가, 성적표 반영 확인 + 실행 시간(속도 개선) 확인.
2. 2026타경50031: 검색 지역 어디에도 없음(리치고 검색도 없음) → 사용자에게 주소·유형 받아 확인(하남이면 이제 나올 수 있음).
3. 노트북 법원자료 업로드 누락 원인(이전 인계 문서 auction_model/... 참고), 취하 위험 모델 적용 여부(사용자 결정 대기).
4. 권한: 사용자가 매번 승인 묻는 것을 싫어함 → 모드 Auto 사용 또는 사용자가 직접 `.claude/settings.json` 에 allow 규칙 커밋(Claude 가 직접 추가하는 건 정책상 거부됨).

## 6-1. 이번 주 일요일(11/8) 예정
- 계속 켜두는 윈도우 노트북(Python·Git 설치됨)에 통합 실행(03시 법원자료+예측, 06시 날씨, 08시 브리핑) 설치 — 원격 제어 연결 또는 그 노트북의 Claude 앱에서. GitHub 예약은 예비로 시각을 뒤로.
- 기존 노트북 `AuctionTenants` 작업의 프로그램 경로 확인 필요(수집 코드가 저장소에 없음). 11/3 이후 법원자료 업로드 없음.
- 할 일: 통합 실행 파일(예: `local_runner/run_all.py` + `install.ps1`) — 단계별(collect/predict/outfit/brief) 실행, 로그 파일, 실패해도 다음 단계 진행,
  작업 스케줄러 3개(03:00/06:00/08:00, 절전 깨우기·놓친 실행 즉시·로그온 무관), 비밀값은 노트북 로컬 .env(저장소에 올리지 않음, GOOGLE_* 3개·MOLIT_API_KEY),
  GitHub 예약은 예비로 시각 뒤로(경매 05:00, 날씨 07:00, 브리핑 09:00 근처) + 기존 '이미 보냄/결과 있음' 건너뛰기 유지.
  증시 해설: 사용자 결정 B — 노트북 Claude Code CLI(`claude -p`, 구독 사용량)로, 여유 있으면 실행·한도면 생략. `brief/claude_summary.py` 에 구현됨 → 노트북 .env 에 BRIEF_SUMMARY=cli, claude 로그인 확인.
  비밀값은 GitHub 에서 다시 볼 수 없음 → 구글 OAuth 재발급(google_api.py 방식, 이때 drive 쓰기 권한도 추가하면 Steward 자동 업로드 가능), 국토부 키는 공공데이터포털 마이페이지에서 확인.

## 7. 사용자 선호
- 항상 한국어, **답변은 압축해서**. 불명확하면 질문, 여러 요청은 하나씩, 중간중간 진행 정리, 목적에서 벗어나지 않기.
- 사용자는 실행·확인을 Claude 가 직접 하길 원함(버튼 누르기 요청 최소화).
- 예측은 사실·추정만, 입찰 권유 금지.
