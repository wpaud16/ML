"""성적표 아파트 '가장 가까운 칸'의 시세 대비 % 를 M 시세로 다시 계산 (2026-11-05 사용자 요청).
11/5 이전 예측은 리치고 시세 기준이라, 그 예측일의 M 시세(리치고 × 층 보정 + 국토부 실거래 가중)를 다시 구해 % 만 바꾼다.
가격(확률표)은 그때 예측 그대로. 입력: dev/probe/danji_jibun.json (단지 지번·동), molit_cache."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); AM = os.path.dirname(HERE); sys.path.insert(0, AM)
import molit, batch_predict as bp
J = json.load(open(os.path.join(HERE, 'probe', 'danji_jibun.json')))
P = os.path.join(AM, 'predictions')
res = json.load(open(os.path.join(P, 'results.json')))
last = {}
for fn in sorted(f for f in os.listdir(P) if re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json', f)):
    for k, it in json.load(open(os.path.join(P, fn)))['items'].items():
        bd = it.get('bidding_date') or ''
        if bd and fn[:10] <= bd: last[f'{k}|{bd}'] = dict(it, pred_date=fn[:10])
n = 0
for rid, r in res.items():
    it = last.get(rid)
    if not it or (r.get('category') or '아파트') != '아파트' or not r.get('actual_manwon'): continue
    if not it.get('model_sise_eok'):
        j = J.get(it.get('danji_id')) or {}
        bj = j.get('bjd') or {}
        sd, sgg = (it.get('region') or ' ').split(' ', 1)
        m = molit.m_sise(bj.get('sd') or sd, bj.get('sgg') or sgg, bj.get('emd'), j.get('jibun'), it.get('area'), it.get('address'),
                         (it.get('richgo_sise_eok') or 0) * 1e8, today=it['pred_date'])
        it = dict(it, model_sise_eok=round(m['mkt'] / 1e8, 3))
    c = bp.closest_cell(it, r['actual_manwon'])
    if c: c['sise_basis'] = 'M'; r['closest'] = c; n += 1
json.dump(dict(sorted(res.items())), open(os.path.join(P, 'results.json'), 'w'), ensure_ascii=False, indent=1)
print('M 기준으로 다시 계산', n)
