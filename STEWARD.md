# Steward — JM 아침 브리핑 시스템 매뉴얼

매일 아침 메일 2통(날씨·코디 / 할 일·경매)과 경매 웹페이지를 자동으로 만드는 시스템.
코드 저장소: https://github.com/wpaud16/ML (모든 실행은 GitHub Actions, PC·Claude 사용 없음)
최종 수정: 2026-11-05

---

## 1. 매일 자동 실행 (KST)

| 시각 | 무엇 | 워크플로 | 결과 |
|---|---|---|---|
| 21:17 · 23:17 · 01:17 · 03:17 | 경매 낙찰가 예측 배치 (그날 결과 있으면 건너뜀) | `auction_predict.yml` | `auction_model/predictions/latest.json`, 웹페이지 `auction_model/page/` |
| 04:13 · 05:13 · 06:13 · 07:13 | 날씨·코디 메일 (하루 1통) | `outfit.yml` | 메일 + `outfit/날짜/` 카드 페이지 |
| 04:23 · 05:23 · 06:23 · 07:23 | JM's Schedule 브리핑 메일 (하루 1통) | `morning_brief.yml` | 메일 (오늘의 문장·할 일·증시·경매 요약) |
| 매월 2일 02:00 | 경매 모델 재학습 | `auction_retrain.yml` | 학습 데이터·보정값 갱신 |

- GitHub 예약 실행은 몇 시간씩 밀리거나 빠지는 날이 있어 여러 번 예약 + "이미 했으면 건너뜀" 방식.
- 수신: wpaud16@naver.com

웹페이지
- 경매 전체 카드: https://wpaud16.github.io/ML/auction_model/page/
- 오늘의 코디: https://wpaud16.github.io/ML/outfit/YYYY-MM-DD/

## 2. 수동으로 다시 보내기 (예약이 안 돌았을 때)

| 무엇 | 방법 |
|---|---|
| 날씨·코디 메일 | `outfit/` 관련 파일을 고치고 커밋 메시지에 `[실행]` 을 넣어 main 에 push (없으면 [테스트] 메일) |
| 브리핑 메일 | `brief/trigger.txt` 내용을 아무거나 바꿔 main 에 push |
| 경매 예측 | `auction_model/` 예측 코드 수정 push 시 자동 실행 (진행 중 실행은 취소되고 새로 시작) |

하루 1통 기록: `outfit/날짜/sent.txt`, `brief/sent/날짜.txt` — 이 파일이 있으면 예약 실행이 건너뜀.

## 3. 비밀값 (GitHub → Settings → Secrets and variables → Actions)

| 이름 | 용도 |
|---|---|
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REFRESH_TOKEN` | Gmail 발송·구글 문서/시트/드라이브 (OAuth 앱 jm-brief) |
| `MOLIT_API_KEY` | 국토부 아파트·오피스텔 실거래 (공공데이터포털, 일반 인증키 Decoding) |
| `ANTHROPIC_API_KEY` (선택) | 증시 해설 — 현재 사용 안 함 |

## 4. 구성 파일

### 브리핑 (`brief/`)
| 파일 | 역할 |
|---|---|
| `run_brief.py` | 메일 조립·발송 (TEST_MODE=1 이면 [테스트], 문서는 읽기만) |
| `google_api.py` | 구글 OAuth·시트·문서·드라이브·Gmail |
| `quote.py` | 오늘의 문장 (시트 "JM's 말모음") |
| `schedule_doc.py` | 할 일 문서 "JM's Schedule": 오늘 섹션·이월·운동 Day·식사 가능 시간 |
| `market.py` | 증시 숫자 (국내·미국 지수, 환율, 美10년물, WTI) |
| `auction_mail.py` | 경매 요약 (아파트/오피스텔 기일순 2줄, New 표시, 실거래 없는 아파트 숨김) |

### 날씨·코디 (`outfit/`)
| 파일 | 역할 |
|---|---|
| `weather.py` | Open-Meteo 날씨 (서울 강동구, 최저/최고·하늘·시간별 강수) |
| `looks.py` | 기온대별 노멀코어 코디 3벌 (최근 3일 중복 피함, 비 오면 어두운 하의) |
| `cards.py` · `figure.py` · `page.py` | 코디 카드 이미지·웹페이지 |
| `run_outfit.py` | 전체 실행 + 링크 메일 |

### 경매 (`auction_model/`)
| 파일 | 역할 |
|---|---|
| `batch_predict.py` | 매일 배치: 리치고 목록 → 단지 찾기 → 권리 판정 → 예측 → latest.json, 성적표(results.json) |
| `auction_predictor.py` | 아파트 낙찰가 모델 (앙상블: 부스팅 + 군집별 회귀), 확률·인원별 가격 |
| `molit.py` | 국토부 실거래 수집(캐시 `molit_cache/`) + **M 시세** 계산 |
| `officetel_model.py` | 오피스텔 모델 (랜덤포레스트 + 부스팅) |
| `nearby.py` | 주변 시세·가중 시세 |
| `fail_model.py` | 유찰 확률 |
| `tenant_rules.py` | 법원 매각물건명세서 임차인 반영 |
| `cards_page.py` | 경매 전체 카드 웹페이지 (실거래 없음 칸, 성적표 포함) |
| `retrain.py` | 월 1회 재학습 |
| `auction_train.csv` / `auction_config.json` | 아파트 학습 데이터 / 보정값 |

## 5. 경매 예측 방식 (2026-11-05 기준)

- **아파트 시세 = M 시세** = w × (층 보정 국토부 실거래 12개월, 최근일수록 가중) + (1 − w) × (층 보정 리치고 시세)
  - w: 최근 거래가 많을수록 ↑(최대 70%), 거래가들이 들쭉날쭉하면 ↓
  - 층 비율(중층=1): 1층 0.95 · 2~3층 0.975 · 저층 0.99 · 고층 1.004 · 꼭대기 0.998
  - 백테스트(2024-07~, 987건): 평균 오차 5.08% → 4.78%
- **1년 실거래 0건 아파트**: 메일에서 숨김, 웹페이지 "🔍 실거래 없음(참고)" (이런 물건 오차 약 6.1%)
- **오피스텔 시세**: 리치고 (실거래 기반은 백테스트에서 더 나빴음). 해당 면적 가격이 없으면 같은 건물 다른 면적 ㎡당 → 주변 오피스텔 ㎡당
- **입찰가 표**: 인원별(1·2·3·5·8·13명) × 낙찰확률(40~60%), 각 가격 아래 모델 시세 대비 %
- **성적표**(웹페이지): 최근 14일 예측 vs 실제, 실제 낙찰가와 가장 가까운 칸(예: "13명 60% · 15.41억 (84.5%)")
- 검색 지역: 서울 강남·서초·강동·광진·송파 / 성남 수정·분당·중원 / 남양주·구리(8호선역 도보 15분) / 하남(5호선역 도보 15분), 오피스텔은 서울 전체 역 도보 10분
- 예측은 사실·추정만 제공, 입찰 권유 아님

## 6. 문제 생겼을 때

| 증상 | 확인 |
|---|---|
| 메일이 안 옴 | GitHub → Actions 에서 해당 워크플로 실행 여부·실패 확인 → 2장 방법으로 수동 발송 |
| 경매 결과가 어제 기준 | 메일 상단 "예측 결과가 ○일 기준" — 배치가 밀림. Actions 에서 auction predictions 확인 |
| 구글 인증 오류 | refresh token 만료 → OAuth 재발급 후 Secrets 갱신 (google_api.py 참고) |
| 국토부 오류 | 공공데이터포털 활용신청 승인 상태·일일 한도 확인. 실패해도 리치고 시세로 계속 예측 |
| 코디 링크 404 | GitHub Pages 배포 지연 — 몇 분 뒤 다시 |

## 7. 코드 받기

- 전체 코드 (zip): https://github.com/wpaud16/ML/archive/refs/heads/main.zip
- 브리핑 `brief/` · 날씨 `outfit/` · 경매 `auction_model/` · 자동 실행 `.github/workflows/`
- 드라이브 자동 업로드(`brief/steward_sync.py`, 워크플로 `steward_sync.yml`)는 준비돼 있으나 구글 인증 권한이 드라이브 읽기 전용이라 현재 꺼 둠.
  켜려면 OAuth 를 드라이브 쓰기 권한으로 다시 발급해 GOOGLE_REFRESH_TOKEN 갱신.

## 8. 관련 문서·데이터

- 할 일 문서 "JM's Schedule": https://docs.google.com/document/d/16r3j5QD_VJZKxL9hOxbv-Aj58jNbp92nCM4szeKrq6Y/edit
- 오늘의 문장 시트 "JM's 말모음"
- 진행 상황·결정 기록: 저장소 `HANDOFF.md`
