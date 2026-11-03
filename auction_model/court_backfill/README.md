# 과거 사건 법원 자료 (백테스트용, 2026-11-03~)

목적: 법원경매정보에만 있는 인자(청구금액, 채권자·배당요구, 교부청구, 점유 유형, 송달 문제, 기일 변경 등)로
인원별 낙찰가·입찰 인원·유찰·취하 모델의 정확도가 좋아지는지 백테스트한다.

- `targets_test.json` : 가능 여부 시험용 12건 (아파트·오피스텔 × 낙찰·취하 × 2023~2025)
- `targets_all.json`  : 전체 백필 대상 약 5,200건 (리치고 단지 페이지에 있는 끝난/진행 중 사건)
- 결과는 `data/<사건번호>_<물건번호>.json` 한 건당 한 파일 (이미 있는 파일은 다시 조회하지 않음)

## 한 건 파일 형식 (모르는 값은 null, 날짜 YYYY-MM-DD, 금액 만원 정수)
```json
{
  "key": "2023타경1283[1]", "court": "서울동부지방법원", "checked": "2026-11-03",
  "available": true,                       // 법원 사이트에서 사건이 조회됐는지
  "case_info": {
    "received_date": "...",                // 사건접수일
    "start_decision_date": "...",          // 개시결정일
    "case_kind": "부동산임의경매",           // 임의/강제
    "claim_amount_manwon": 12345,          // 청구금액
    "creditor_type": "은행",                // 채권자 구분 원문 그대로 (은행/저축은행/캐피탈/대부/개인/국가 등, 이름은 가려도 됨)
    "end_result": "매각" , "end_date": "...", // 종국결과(매각/취하/기각/취소 등)와 종국일
    "duplicate_cases": ["..."]             // 중복·병합 사건번호
  },
  "spec": {...} ,                          // 매각물건명세서 (tenants/README.md 형식과 같게, 없으면 null)
  "occupancy": {...},                      // 현황조사서 (tenants/README.md 형식과 같게, 없으면 null)
  "events": [{"date","type","text"}],      // 문건/송달 내역 전체
  "schedule": [{"date","kind","result","min_price_manwon"}],
  "parties": [{"role":"근저당권자","type":"은행"}],   // 이해관계인 목록 (역할·구분만, 이름 불필요)
  "error": null
}
```
