"""성적표 아파트 예상 입찰가를 M 시세 모델로 다시 계산 (2026-11-08 사용자 요청).
11/5 이전 예측(리치고 시세)으로 기록된 성적표 행을, 현재 모델(USE_M=1, M 시세)로 다시 예측해 바꾼다.
- 학습 데이터는 그 매각기일 이전 사례만 사용(정답 누출 방지)
- 리치고 페이지의 최저가가 기록과 다르면(유찰 후 다음 회차로 바뀜 등) 건너뜀
- 원래 값은 orig_bid_by_prob_manwon 에 보관, rescored 에 날짜 기록
사용: python dev/rescore_pred_m.py  (auction_model 폴더 기준 상위에서)"""
import json, os, re, sys
from datetime import date
HERE = os.path.dirname(os.path.abspath(__file__)); AM = os.path.dirname(HERE); sys.path.insert(0, AM)
os.environ['USE_M'] = '1'
import pandas as pd
import auction_predictor as ap, batch_predict as bp

P = os.path.join(AM, 'predictions')
res = json.load(open(os.path.join(P, 'results.json'), encoding='utf-8'))
last = {}
for fn in sorted(f for f in os.listdir(P) if re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json', f)):
    for k, it in json.load(open(os.path.join(P, fn), encoding='utf-8'))['items'].items():
        bd = it.get('bidding_date') or ''
        if bd and fn[:10] <= bd: last[f'{k}|{bd}'] = dict(it, pred_date=fn[:10])
df = ap.load_train(); cfg = json.load(open(os.path.join(AM, 'auction_config.json'), encoding='utf-8'))
lo = str(date.fromordinal(date.today().toordinal() - 30))
done, skip = 0, []
for rid, r in sorted(res.items()):
    it = last.get(rid)
    if (r.get('category') or '아파트') != '아파트' or r['bidding_date'] < lo or not it: continue
    if it.get('m_sise') or r.get('rescored'): continue   # 이미 M 기준
    try:
        p = ap.predict_dict(it['danji_id'], it['auction_id'], df=df[df.date < pd.Timestamp(r['bidding_date'])], cfg=cfg)
    except BaseException as e:
        skip.append((rid, f'예측 실패 {str(e)[:60]}')); continue
    ms = p.get('m_sise') or {}
    if abs(p['low_eok'] * 1e4 - r['low_manwon']) > 6:   # low_eok 는 소수 3자리 반올림
        skip.append((rid, f"최저가 다름 {p['low_eok']}억 vs {r['low_manwon']}만")); continue
    if not ms or ms.get('note', '').startswith('M 시세 실패'):
        skip.append((rid, 'M 시세 실패 ' + str(ms.get('note'))[:60])); continue
    new = p['bid_by_prob_manwon']
    r.update(orig_bid_by_prob_manwon=r['bid_by_prob_manwon'], bid_by_prob_manwon=new, rescored=str(date.today()),
             expected_bidders=(p.get('by_bidders') or {}).get('expected_bidders'), expected_range=(p.get('by_bidders') or {}).get('expected_range'),
             sise_manwon=int(round(p['model_sise_eok'] * 1e4)),
             rescored_pred={k: p.get(k) for k in ('bid_by_prob_manwon', 'bid_by_prob_eok', 'by_bidders', 'model_sise_eok', 'richgo_sise_eok', 'm_sise', 'no_trade_12m', 'p50_ensemble_eok', 'gap_rule', 'small_danji_adj', 'sise', 'fail')})
    if r.get('actual_manwon'):
        a = r['actual_manwon']
        r.update(diff_pct=round((a / new['50%'] - 1) * 100, 1), band=bp.band_of(a, new),
                 closest=bp.closest_cell(dict(it, **r['rescored_pred'], category='아파트'), a))
    done += 1
    print(rid, 'p50', r['orig_bid_by_prob_manwon']['50%'], '->', new['50%'], '실제', r.get('actual_manwon'), r['status'])
json.dump(dict(sorted(res.items())), open(os.path.join(P, 'results.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('다시 계산', done, '건너뜀', len(skip))
for s in skip: print(' -', *s)
