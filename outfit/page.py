# usage: python3 page.py d.json OUT_DIR   -> writes OUT_DIR/index.html (cards card1..4.png must sit in OUT_DIR)
import json, sys, html, urllib.parse
d=json.load(open(sys.argv[1],encoding='utf-8')); out=sys.argv[2]; e=html.escape
def pin(lk):
    q=lk.get("pin") or " ".join(it["name"].split(" · ")[1]+" "+it["name"].split(" · ")[0] for it in lk["items"][:2])+" 남자 코디"
    return "https://www.pinterest.co.kr/search/pins/?q="+urllib.parse.quote(q)
looks="".join(f'''<section><img src="card{i+2}.png" alt="코디 {"ABC"[i]}">
<a class="btn" href="{pin(lk)}" target="_blank" rel="noopener">📌 코디 {"ABC"[i]} 실제 착용 사진 보기 (핀터레스트)</a></section>''' for i,lk in enumerate(d["looks"]))
page=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>오늘의 코디 · {e(d["date"])}</title><style>
body{{margin:0;background:#E9E6E0;font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;color:#1F1D1A}}
main{{max-width:540px;margin:0 auto;padding:12px 12px 32px}}
h1{{font-size:18px;margin:6px 4px 12px}}
section{{margin-bottom:18px}}img{{width:100%;display:block;border-radius:14px;box-shadow:0 2px 10px #0001}}
.btn{{display:block;margin-top:8px;padding:13px;border-radius:12px;background:#fff;color:#E60023;font-weight:700;text-align:center;text-decoration:none;font-size:15px}}
footer{{font-size:12px;color:#7A746B;text-align:center}}
</style></head><body><main><h1>☀️ {e(d["date"])} 오늘의 날씨·코디</h1>
<section><img src="card1.png" alt="오늘의 날씨"></section>{looks}
<footer>{e(d.get("footer",""))}</footer></main></body></html>'''
open(out.rstrip('/')+'/index.html','w',encoding='utf-8').write(page); print("ok")
