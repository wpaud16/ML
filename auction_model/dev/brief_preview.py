import json, os, datetime as dt
L=json.load(open('/home/claude/ml/auction_model/predictions/latest.json')); IT=L['items']
for _k,_b in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'ot_bb.json'))).items(): IT[_k]['by_bidders']=_b
TODAY=dt.date(2026,11,3); WD='월화수목금토일'
CELL='background:#000;color:#fff;border:1px solid #fff;padding:9px 2px'
HL='background:#333;color:#fff;border:1px solid #fff;padding:9px 2px;font-weight:bold'
def d(s):
    t=dt.date.fromisoformat(s); return f"{t.month}/{t.day}({WD[t.weekday()]}) · D-{(t-TODAY).days}"
def eok(m): return f"{m/1e4:.2f}"
def need_apt(P,area):
    L_=min(60000 if P<=150000 else 40000 if P<=250000 else 20000,0.7*P)
    r=0.01 if P<=60000 else (P/1e4*2/3-3)/100 if P<=90000 else 0.03
    T=P*r*1.1+(P*0.002 if area>85 else 0)-(min(200,P*r) if P<=120000 else 0)
    return P-L_+T+800, L_
def need_ot(P): return P-0.7*P+P*0.046+800
def table(v):
    lv=['40%','45%','50%','55%','60%']
    h=f'<tr><th style="{CELL};white-space:nowrap">인원</th>'+''.join(f'<th style="{HL if q=="50%" else CELL}">{q}</th>' for q in lv)+'</tr>'
    base=v['bid_by_prob_eok']
    rows=[] if (v.get('by_bidders') or {}).get('bid_by_prob_eok') else [('전체',base,False)]
    bb=(v.get('by_bidders') or {}).get('bid_by_prob_eok')
    exp=(v.get('by_bidders') or {}).get('expected_bidders')
    import re
    ot=v['category']=='오피스텔'
    grp=(lambda n:1 if n<=1 else 2 if n==2 else 3 if n<=4 else 5 if n<=7 else 8) if ot else (lambda n:1 if n<=1 else 2 if n==2 else 3 if n<=4 else 5 if n<=7 else 8 if n<=12 else 13)
    if bb:
        for k,r in bb.items(): rows.append((k,r,bool(exp) and grp(exp)==int(re.match(r'\d+',k).group())))
    out=''
    for lab,r,me in rows:
        st=lambda q: HL if (q=='50%' or me) else CELL
        out+=f'<tr><td style="{(HL if me else CELL)};white-space:nowrap">{"▶ " if me else ""}{lab}</td>'+''.join(f'<td style="{st(q)}">{r[q]:.2f}</td>' for q in lv)+'</tr>'
    ex=(f' <span style="font-weight:normal;font-size:13px">· 예상 약 {exp}명 (보통 {v["by_bidders"]["expected_range"][0]}~{v["by_bidders"]["expected_range"][1]}명)</span>' if bb else '')
    note='<div style="color:#777;font-size:12px">단위 억 · ▶ 예상 인원 · 모델 오차 약 ±6% · 확률 ±5%p</div>'
    return f'<div style="font-weight:bold;margin-top:10px">👥 입찰 인원별 낙찰확률 입찰가{ex}</div><table style="border-collapse:collapse;width:100%;max-width:560px;table-layout:fixed;margin:8px 0;font-size:14px;text-align:center;background:#000;color:#fff;border:2px solid #fff"><col style="width:19%"><col><col><col><col><col>{h}{out}</table>{note}'
SI=json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'sise.json')))
def sise_lines(v):
    S=SI.get(v['key']) or {}; g='color:#777;font-size:12px'
    if not S.get('est_eok'): return f'<div>매매 시세 {v["richgo_sise_eok"]:.2f}억</div>'
    est=S['est_eok']; h=f'<div>매매 시세(종합) <b>{est:.2f}억</b> <span style="{g}">(범위 {S["range_eok"][0]:.2f}~{S["range_eok"][1]:.2f} · 감정가는 {round(v["appr_eok"]/est*100)}% · 최저가는 {S["low_vs_est_pct"]}%)</span></div>'
    p=[]
    t=S.get('trade')
    if t: p.append(f'실거래 {t["eok"]:.2f}억({int(t["date"][5:7])}/{int(t["date"][8:10])}' + (f' → 추세 반영 {t["adj_eok"]:.2f}' if abs(t["trend_since_pct"])>=1 else '') + ')')
    if S.get('kb'): p.append(f'KB {S["kb"]["eok"]:.2f}')
    o=S.get('offer')
    if o: p.append(f'호가 {o["min_eok"]:.2f}~{o["max_eok"]:.2f}' + (f'(매물 {o["count"]})' if o.get('count') else ''))
    if S.get('richgo_eok') and '리치고' in S.get('used',[]): p.append(f'리치고 {S["richgo_eok"]:.2f}')
    h+=f'<div style="{g}">' + ' · '.join(p) + '</div>'
    tr=S.get('trend') or {}
    if tr.get('3m_pct') is not None: h+=f'<div style="{g}">단지 시세 추세 3개월 {tr["3m_pct"]:+.1f}% · 1년 {tr["12m_pct"]:+.1f}%</div>'
    for f in S.get('flags') or []: h+=f'<div style="color:#C5221F;font-size:12px">⚠ {f}</div>'
    return h
def card(v, tracked=False):
    ot=v['category']=='오피스텔'; P=v['bid_by_prob_manwon']['50%']; f=v.get('fail') or {}; rk=v.get('risk') or {}; s=rk.get('summary') or {}
    gu=v['region'].split()[-1]
    tag=' <span style="color:#777;font-size:12px">· 📋 추적 중</span>' if tracked else ''
    h=f'<div style="border:1px solid #888;border-radius:10px;padding:12px 14px;margin-bottom:12px">'
    hh=f' <span style="font-weight:normal;color:#777;font-size:12px">{v["households"]:,}세대</span>' if (not ot and v.get('households')) else ''
    h+=f'<div style="font-weight:bold;font-size:15px">{v["danji_name"]}{hh} · 전용 {v["area"]}㎡ · 🛡 {(v.get("safety") or {}).get("grade","")}{tag}</div>'
    h+=f'<div style="color:#777;font-size:12px">{gu} · {v["key"].replace("[1]","")} · {v.get("court","")}</div>'
    h+='<div style="font-weight:bold;margin-top:8px">📋 기본 정보</div>'
    h+=f'<div>매각기일 {d(v["bidding_date"])}</div>'
    h+=f'<div>유찰 {v["fails"]}회' + (f' · 유찰 확률(이번 회차) {f["prob_pct"]}% · {f["level"]}' if 'prob_pct' in f else '') + '</div>'
    h+=f'<div>감정가 {v["appr_eok"]:.2f}억 · 최저가 <b>{v["low_eok"]:.2f}억</b> ({round(v["low_manwon"]/v["appr_manwon"]*100)}%) · 보증금 {v["low_manwon"]//10:,}만</div>'
    if ot and v.get('station'): h+=f'<div>🚇 {v["station"]["name"]}역 도보 약 {v["station"]["walk_min"]}분 ({v["station"]["distance_m"]}m)</div>'
    h+=sise_lines(v)
    if ot:
        inc=v.get('income') or {}
        if inc.get('est_monthly_rent_manwon'): h+=f'<div>월세 시세 약 {inc["est_monthly_rent_manwon"]}만원 <span style="color:#777;font-size:12px">(보증금 1,000만 기준 추정{" · 같은 건물 다른 평형 기준" if "같은" in (inc.get("rent_basis") or "") else ""})</span></div>'
        pb=v.get('payback')
        if pb: h+=f'<div>📈 월세 {pb["monthly_rent_manwon"]}만 × 약 {pb["years"]}년({pb["months"]}개월)이면 50% 가격 {P/1e4:.2f}억 <span style="color:#777;font-size:12px">(대출·세금·비용 제외 단순 계산)</span></div>'
    h+=table(v)
    h+='<div style="font-weight:bold;margin-top:8px">⚖️ 권리분석</div>'
    h+=f'<div>말소기준: {s.get("base_right","-")} ({s.get("base_date","-")}) · 이후 소멸</div><div>인수 권리(등기 기준): {"있음" if s.get("right_risk") else "없음"}</div><div>점유자(대항력): 매각물건명세서 확인 필요</div>'
    if not ot and v['region'].startswith('서울'): h+='<div>토지거래허가: 경매 취득은 허가 대상 아님</div>'
    h+=f'<a href="https://m.richgo.ai/auctionMobile/{v["auction_id"]}" style="font-size:12px">상세 보기 →</a></div>'
    return h
def exp_of(r):
    if r.get('expected_bidders'): return r['expected_bidders']
    try:
        sn=json.load(open(f"/home/claude/ml/auction_model/predictions/{r['pred_date']}.json"))['items'].get(r['key']) or {}
        return (sn.get('by_bidders') or {}).get('expected_bidders')
    except Exception: return None
def score(cat):
    rr=[r for r in L['recent_results']['items'] if r.get('category')==cat][:6]
    sold=[r for r in rr if r['status']=='매각']
    head=''.join(f'<th style="{CELL}">{x}</th>' for x in ['물건','기일','예상<br>(50%)','실제','차이','인원<br><span style="font-size:11px">실제/예상</span>'])
    body=''
    for r in rr:
        p=r['bid_by_prob_manwon']['50%']; t=dt.date.fromisoformat(r['bidding_date']); e=exp_of(r)
        if r['status']=='매각':
            c='#FF6B6B' if r['diff_pct']>0 else '#6FA8FF'
            act=f'<b>{r["actual_manwon"]/1e4:.2f}</b>'; dif=f'<span style="color:{c}">{r["diff_pct"]:+.1f}%</span><br><span style="color:#bbb;font-size:11px">{r["band"]}</span>'
            ppl=f'<b>{r.get("bidders") or "-"}</b> / {e if e else "-"}'
        else: act=f'<span style="color:#bbb">{r["status"]}</span>'; dif='-'; ppl=f'- / {e if e else "-"}'
        body+=f'<tr><td style="{CELL};text-align:left;padding-left:4px">{r["danji_name"]}<br><span style="color:#bbb;font-size:11px">{r["key"].replace("[1]","")}<br>{r.get("area")}㎡</span></td><td style="{CELL}">{t.month}/{t.day}</td><td style="{CELL}">{p/1e4:.2f}</td><td style="{CELL}">{act}</td><td style="{CELL}">{dif}</td><td style="{CELL}">{ppl}</td></tr>'
    es=[abs(r['diff_pct']) for r in sold]
    summ=f'낙찰 {len(sold)}건 · 평균 오차 {sum(es)/len(es):.1f}% · ±5% 안 {sum(x<=5 for x in es)}건' if sold else '최근 7일 낙찰 없음'
    note='<div style="color:#777;font-size:12px">인원: 실제 응찰자 수 / 기일 전 모델이 예상한 인원' + (' (오피스텔 예상 인원은 내일 예측분부터 기록)' if cat=='오피스텔' else '') + '</div>'
    return f'<div style="font-weight:bold;margin:14px 0 6px;border-bottom:1px solid #888">📊 모델 성적표 (최근 7일)</div><div>{summ}</div><table style="border-collapse:collapse;width:100%;max-width:560px;table-layout:fixed;margin:8px 0;font-size:13px;text-align:center;background:#000;color:#fff"><col style="width:30%"><col style="width:11%"><col><col><col><col><tr>{head}</tr>{body}</table>{note}'
def block(cat, new, tracked):
    icon='🏢' if cat=='아파트' else '🏬'; title=f'{icon} {cat}'+(' (서울 · 역 도보 10분)' if cat=='오피스텔' else '')
    h=f'<div style="font-weight:bold;font-size:19px;margin:22px 0 8px;border-bottom:2px solid #888">{title}</div>'
    h+=f'<div style="font-weight:bold;margin:10px 0 6px;border-bottom:1px solid #888">🆕 새 물건 ({len(new)}건)</div>'+''.join(card(IT[k]) for k in new)
    h+=f'<div style="font-weight:bold;margin:14px 0 6px;border-bottom:1px solid #888">📋 추적 중인 물건 ({len(tracked)}건)</div>'+''.join(card(IT[k],True) for k in tracked)
    return h+score(cat)
html=f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>경매 알림 새 형식 예시</title></head>
<body style="background:#fff;margin:0;padding:16px"><div style="font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;max-width:640px;margin:0 auto;color:#222;font-size:14px;line-height:1.6">
<div style="color:#777;font-size:12px">예시 — 실제 11/3 예측 결과로 만든 카드 (실제 메일은 해당 물건 전부 · 예시는 카테고리마다 새 물건 1건·추적 1건)</div>
<div style="font-weight:bold;font-size:17px;margin-top:8px">🏠 경매 알림</div>
{block("아파트",["2026타경50070[1]"],["2025타경72200[1]"])}
{block("오피스텔",["2025타경4115[1]"],["2026타경100240[1]"])}
</div></body></html>'''
open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'auction_preview.html'),'w').write(html); print(len(html))
