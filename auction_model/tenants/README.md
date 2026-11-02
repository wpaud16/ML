# 임차인 자료 (사용자 PC → 저장소)

사용자 PC(LAPTOP-M47J0JTR)가 매일 **05:30 KST**에 법원경매정보(courtauction.go.kr) 매각물건명세서·임차인 현황을 읽어
`auction_model/tenants/latest.json` 으로 올린다. 06:10 예측 작업(`batch_predict.py` → `tenant_rules.py`)이 이 파일로
"낙찰금으로 보증금이 다 변제되는지"를 계산해 숨김/포함을 다시 판정한다. 파일이 없거나 14일 넘게 오래되면 리치고 판정 그대로.

조회 대상: `auction_model/predictions/tenant_targets.json` (전날 예측 물건 목록: key, case, item_no, court, bidding_date, category)

## latest.json 형식
```json
{
  "generated_at": "2026-11-04T05:31:00+09:00",
  "items": {
    "2026타경101140[1]": {
      "checked": "2026-11-04",                 // 조회한 날 (YYYY-MM-DD)
      "court": "서울중앙지방법원",
      "base_right_date": "2024-05-16",         // 말소기준권리 접수일 (명세서 '최선순위 설정일자')
      "base_right": "가압류",
      "dividend_deadline": "2026-03-10",       // 배당요구종기
      "tenants": [
        {
          "occupant": "임차인",                 // 점유자 구분 (임차인/소유자/채무자 등)
          "move_in": "2023-02-01",             // 전입신고일 (사업자등록일)
          "fixed_date": "2023-02-01",          // 확정일자 (없으면 null)
          "deposit_manwon": 15000,             // 보증금 (만원)
          "monthly_rent_manwon": 0,            // 차임 (만원)
          "claimed_dividend": true,            // 배당요구 여부
          "claim_date": "2026-01-05"           // 배당요구일 (모르면 null)
        }
      ],
      "remarks": "매각물건명세서 비고란 원문",
      "assumed_rights_text": "등기된 부동산에 관한 권리 또는 가처분으로 매각으로 효력이 소멸되지 아니하는 것 (원문)",
      "error": null                             // 조회 실패 시 사유 (이 물건은 판정에 쓰지 않음)
    }
  }
}
```
날짜는 모두 YYYY-MM-DD, 금액은 만원 정수. 임차인이 없으면 `"tenants": []`.
