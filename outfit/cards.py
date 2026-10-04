import json, sys, html
from playwright.sync_api import sync_playwright
from PIL import Image
d=json.load(open(sys.argv[1],encoding='utf-8')); e=html.escape
SK="#E6C3A0"
def figure(items, kind):
    c={it.get("role"):it["color"] for it in items}
    top=c.get("top","#DDD"); outer=c.get("outer"); bot=c.get("bottom","#555"); sh=c.get("shoes","#EEE")
    arm=outer or top; s='stroke="#00000026" stroke-width="1.5"'
    o=f'<ellipse cx="100" cy="392" rx="70" ry="8" fill="#00000014"/>'
    o+=f'<path d="M60 95 Q48 100 46 120 L40 210 Q40 218 48 218 L58 218 L66 120Z" fill="{arm}" {s}/><path d="M140 95 Q152 100 154 120 L160 210 Q160 218 152 218 L142 218 L134 120Z" fill="{arm}" {s}/>'
    o+=f'<circle cx="51" cy="226" r="8" fill="{SK}"/><circle cx="149" cy="226" r="8" fill="{SK}"/>'
    o+=f'<path d="M64 200 L136 200 L132 372 L106 372 L100 240 L94 372 L68 372Z" fill="{bot}" {s}/>'
    o+=f'<path d="M100 240 L100 210" stroke="#00000030"/>'
    o+=f'<path d="M62 92 Q100 78 138 92 L140 212 L60 212Z" fill="{top}" {s}/>'
    if kind=="shirt": o+=f'<path d="M86 84 L100 102 L114 84" fill="none" stroke="#00000040" stroke-width="2"/><line x1="100" y1="102" x2="100" y2="210" stroke="#00000030"/>'+"".join(f'<circle cx="104" cy="{y}" r="1.8" fill="#00000050"/>' for y in (118,140,162,184))
    elif kind=="polo": o+=f'<path d="M86 84 L100 96 L114 84 L110 80 L90 80Z" fill="{top}" stroke="#00000040" stroke-width="2"/><line x1="100" y1="96" x2="100" y2="122" stroke="#00000040"/>'
    else: o+=f'<path d="M88 86 Q100 96 112 86" fill="none" stroke="#00000040" stroke-width="2"/>'
    if outer:
        o+=f'<path d="M62 92 Q78 84 90 84 L92 222 L56 222Z" fill="{outer}" {s}/><path d="M138 92 Q122 84 110 84 L108 222 L144 222Z" fill="{outer}" {s}/>'
        o+=f'<path d="M90 84 L80 110 L92 116" fill="none" stroke="#00000040" stroke-width="2"/><path d="M110 84 L120 110 L108 116" fill="none" stroke="#00000040" stroke-width="2"/>'
    o+=f'<rect x="91" y="64" width="18" height="20" rx="4" fill="{SK}"/><circle cx="100" cy="46" r="24" fill="{SK}"/><path d="M76 44 Q76 18 100 18 Q125 18 124 44 Q116 30 100 31 Q86 30 76 44Z" fill="#2A2522"/>'
    o+=f'<path d="M64 370 L96 370 Q100 386 96 388 L58 388 Q54 382 64 370Z" fill="{sh}" {s}/><path d="M104 370 L136 370 Q146 382 142 388 L104 388 Q100 386 104 370Z" fill="{sh}" {s}/>'
    return f'<svg viewBox="0 0 200 400" width="230" height="460">{o}</svg>'
CSS='''*{box-sizing:border-box;margin:0;padding:0}body{font-family:"Noto Sans CJK KR",sans-serif;color:#1F1D1A}
.card{width:540px;height:675px;padding:36px;position:relative;overflow:hidden}
.no{position:absolute;top:34px;right:36px;font-size:14px;font-weight:700;color:#00000055;letter-spacing:1px}
.kick{font-size:14px;font-weight:700;letter-spacing:3px;color:#00000080}
'''
def cover():
    lv=d["level"]
    sc="".join(f'<div style="flex:1;border-radius:10px;padding:8px 4px;text-align:center;font-size:11px;background:{"#1F1D1A" if l==lv else "#ffffffb0"};color:{"#F4F1EC" if l==lv else "#7A746B"}"><b style="display:block;font-size:13px;color:{"#E8C27A" if l==lv else "#1F1D1A"}">{r}</b><b>{l}</b><br>{t}</div>' for r,l,t in [("~5mm","약한 비","우산 있으면 OK"),("5~20mm","보통 비","우산 필수"),("20~50mm","많은 비","신발 젖음"),("50mm~","매우 많은 비","외출 자제")])
    rows="".join(f'<tr><td style="color:#7A746B;width:96px;padding:3px 0">{e(k)}</td><td style="padding:3px 0">{e(v)}</td></tr>' for k,v in d["rain"])
    return f'''<div class="card" style="background:#F4F1EC"><div class="no">01 / 04</div>
<div class="kick">TODAY'S WEATHER</div><div style="font-size:26px;font-weight:900;margin-top:6px">{e(d["date"])}</div><div style="font-size:15px;color:#7A746B">서울 강동구 · {e(d["sky"])} · {e(d["sub"])}</div>
<div style="display:flex;gap:28px;margin:18px 0 16px"><div><div style="font-size:15px;color:#7A746B">최저</div><div style="font-size:84px;font-weight:900;line-height:1;color:#3E6E9E;letter-spacing:-3px">{e(d["tmin"])}°</div></div>
<div><div style="font-size:15px;color:#7A746B">최고</div><div style="font-size:84px;font-weight:900;line-height:1;color:#C0583A;letter-spacing:-3px">{e(d["tmax"])}°</div></div></div>
<div style="background:#fff;border-radius:16px;padding:16px 18px"><div style="font-size:17px;font-weight:700;margin-bottom:6px">{e(d["rain_title"])}</div><table style="font-size:15px;border-collapse:collapse;width:100%">{rows}</table>
<div style="font-size:11px;color:#9A9389;margin:10px 0 4px">하루 강수량 기준</div><div style="display:flex;gap:5px">{sc}</div></div>
<div style="background:#1F1D1A;color:#F4F1EC;border-radius:16px;padding:14px 18px;margin-top:14px;font-size:16px;line-height:1.55">{d["guide"].replace("<b>",'<b style="color:#E8C27A">')}</div></div>'''
BG=["#E9EEF3","#ECEDE4","#E8E9EE"]
def look(i,lk):
    its="".join(f'<div style="display:flex;align-items:center;gap:10px;font-size:17px;padding:6px 0;border-bottom:1px solid #00000012"><span style="width:20px;height:20px;border-radius:5px;background:{it["color"]};border:1px solid #00000025;flex:none"></span>{e(it["name"])}</div>' for it in lk["items"])
    return f'''<div class="card" style="background:{BG[i]}"><div class="no">0{i+2} / 04</div>
<div class="kick">LOOK {"ABC"[i]}</div><div style="font-size:30px;font-weight:900;margin-top:4px">{e(lk["title"])}</div>
<div style="display:flex;align-items:flex-end;gap:10px;margin-top:8px"><div style="flex:none;margin-left:-14px">{figure(lk["items"],lk.get("kind","tee"))}</div>
<div style="flex:1;padding-bottom:26px">{its}<div style="font-size:14px;color:#5A554D;line-height:1.5;margin-top:14px;background:#ffffff90;border-radius:10px;padding:10px 12px">💡 {e(lk["tip"])}</div></div></div></div>'''
cards=[cover()]+[look(i,l) for i,l in enumerate(d["looks"])]
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={"width":540,"height":675},device_scale_factor=1)
    for n,c in enumerate(cards):
        pg.set_content(f'<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>{c}</body></html>')
        f=f'card{n+1}.png'; pg.screenshot(path=f,clip={"x":0,"y":0,"width":540,"height":675})
        Image.open(f).convert('RGB').quantize(colors=32,dither=Image.Dither.NONE).save(f,optimize=True)
    b.close()
print("ok")
