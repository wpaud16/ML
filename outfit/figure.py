# Fashion-illustration style figure (SVG) for outfit cards.
# figure_svg(items, kind, uid) -> <svg> string. items: [{name, color, role, type?}]
import re

def _rgb(h):
    h = h.lstrip('#')
    if len(h) == 3: h = ''.join(c*2 for c in h)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def _hex(r, g, b): return '#%02x%02x%02x' % tuple(max(0, min(255, int(v))) for v in (r, g, b))
def shade(h, f):  # f<0 darker, f>0 lighter
    r, g, b = _rgb(h)
    if f < 0: return _hex(r*(1+f), g*(1+f), b*(1+f))
    return _hex(r+(255-r)*f, g+(255-g)*f, b+(255-b)*f)
def lum(h):
    r, g, b = _rgb(h); return (0.299*r + 0.587*g + 0.114*b)/255

TYPES = [
    ('denim', r'데님|청바지|진$|생지'), ('slacks', r'슬랙스'), ('chino', r'치노|면바지'),
    ('sweat', r'스웨트|조거|트레이닝'), ('loafer', r'로퍼|더비|구두'), ('runner', r'러닝화|트레이너'),
    ('boots', r'부츠|첼시'), ('sneaker', r'스니커즈|운동화|캔버스'),
    ('shirt_jacket', r'셔츠 ?재킷|오버셔츠|셔켓'), ('cardigan', r'카디건|가디건'),
    ('blazer', r'블레이저|재킷'), ('coat', r'코트'), ('knit', r'니트|스웨터'), ('hoodie', r'후드'),
    ('polo', r'폴로|피케'), ('shirt', r'셔츠'), ('tee', r'티셔츠|티$|맨투맨|스웨트셔츠'),
]
def itype(it):
    if it.get('type'): return it['type']
    nm = it['name'].split('·')[0]
    for t, pat in TYPES:
        if re.search(pat, nm): return t
    return {'top': 'tee', 'outer': 'shirt_jacket', 'bottom': 'chino', 'shoes': 'sneaker'}.get(it.get('role'), 'tee')

SKIN, SKIN_D, HAIR = '#E8C4A2', '#D2A783', '#26211D'

def figure_svg(items, kind='tee', uid='f'):
    by = {}
    for it in items: by.setdefault(it.get('role'), it)
    top = by.get('top', {'name': '티셔츠', 'color': '#DDDDDD', 'role': 'top'})
    outer = by.get('outer'); bot = by.get('bottom', {'name': '치노', 'color': '#555555', 'role': 'bottom'})
    sh = by.get('shoes', {'name': '스니커즈', 'color': '#EEEEEE', 'role': 'shoes'})
    nm = top['name'].split('·')[0]
    knit_top = '니트' in nm or '스웨터' in nm
    if '폴로' in nm or '피케' in nm: tt = 'polo'
    elif '셔츠' in nm and '티셔츠' not in nm: tt = 'shirt'
    elif knit_top: tt = 'knit'
    else: tt = kind if kind in ('shirt', 'polo') and itype(top) not in ('tee',) else 'tee'
    ot = itype(outer) if outer else None
    bt = itype(bot); st = itype(sh)
    T, O, B, S = top['color'], (outer or {}).get('color'), bot['color'], sh['color']
    defs, g = [], []

    def grad(name, c, dark=-0.22, light=0.10):
        defs.append(f'<linearGradient id="{uid}{name}" x1="0" x2="1" y1="0" y2="0">'
                    f'<stop offset="0" stop-color="{shade(c, dark)}"/><stop offset=".38" stop-color="{shade(c, light)}"/>'
                    f'<stop offset=".62" stop-color="{c}"/><stop offset="1" stop-color="{shade(c, dark)}"/></linearGradient>')
        return f'url(#{uid}{name})'
    def pattern(name, kindp, c):
        lc = shade(c, -0.35) if lum(c) > 0.35 else shade(c, 0.35)
        if kindp == 'rib':
            body = f'<rect width="5" height="5" fill="none"/><line x1="1" y1="0" x2="1" y2="5" stroke="{lc}" stroke-width="1" opacity=".22"/>'
            w = h = 5
        elif kindp == 'twill':
            body = f'<path d="M0 4 L4 0 M-1 1 L1 -1 M3 5 L5 3" stroke="{shade(c, 0.45)}" stroke-width=".8" opacity=".22"/>'
            w = h = 4
        elif kindp == 'oxford':
            body = f'<circle cx="1" cy="1" r=".6" fill="{lc}" opacity=".16"/><circle cx="3" cy="3" r=".6" fill="{lc}" opacity=".16"/>'
            w = h = 4
        else:
            body = f'<line x1="0" y1="2" x2="6" y2="2" stroke="{lc}" stroke-width=".6" opacity=".10"/>'
            w = h = 6
        defs.append(f'<pattern id="{uid}{name}" width="{w}" height="{h}" patternUnits="userSpaceOnUse">{body}</pattern>')
        return f'url(#{uid}{name})'
    def fold(d, c, w=1.4, op=.45): g.append(f'<path d="{d}" fill="none" stroke="{shade(c, -0.35)}" stroke-width="{w}" stroke-linecap="round" opacity="{op}"/>')
    def hil(d, c, w=2, op=.35): g.append(f'<path d="{d}" fill="none" stroke="{shade(c, 0.5)}" stroke-width="{w}" stroke-linecap="round" opacity="{op}"/>')
    edge = 'stroke="#00000033" stroke-width="1.2" stroke-linejoin="round"'

    # ground shadow
    g.append('<ellipse cx="150" cy="598" rx="88" ry="9" fill="#000" opacity=".10"/>')

    # ---------- bottoms ----------
    wide = bt in ('slacks', 'sweat') or '와이드' in bot['name']
    straight = bt == 'denim' and '와이드' not in bot['name']
    hemL, hemR = (98, 148) if wide else ((104, 146) if not straight else (106, 145))
    taper = bt == 'sweat' and '와이드' not in bot['name']
    if taper: hemL, hemR = 110, 142
    bfill = grad('b', B, -0.25, 0.08)
    lp = f'M100 300 L150 300 L150 330 L{hemR} 578 L{hemL} 578 Z'
    rp = f'M150 300 L200 300 L{300-hemL} 578 L{300-hemR} 578 L150 330 Z'
    for p in (lp, rp): g.append(f'<path d="{p}" fill="{bfill}" {edge}/>')
    if bt == 'denim':
        tw = pattern('tw', 'twill', B)
        for p in (lp, rp): g.append(f'<path d="{p}" fill="{tw}"/>')
        st_c = '#C99A45'
        g.append(f'<path d="M104 312 Q118 330 134 318 M196 312 Q182 330 166 318" fill="none" stroke="{st_c}" stroke-width="1" stroke-dasharray="2 2" opacity=".8"/>')
        g.append(f'<path d="M150 302 L150 340" stroke="{st_c}" stroke-width="1" stroke-dasharray="2 2" opacity=".8"/>')
        for x in (126, 174): fold(f'M{x-8} 452 Q{x} 458 {x+8} 452', B, 1.2, .5)
        for x in (124, 176): fold(f'M{x-12} 560 Q{x} 552 {x+12} 560', B, 1.2, .55)
    elif bt == 'slacks':
        fold(f'M125 318 L{(hemL+hemR)/2:.0f} 576', B, 1, .55); fold(f'M175 318 L{300-(hemL+hemR)/2:.0f} 576', B, 1, .55)
        hil(f'M127 330 L{(hemL+hemR)/2+2:.0f} 570', B, 1, .25); hil(f'M177 330 L{300-(hemL+hemR)/2+2:.0f} 570', B, 1, .25)
        fold('M108 306 Q118 322 132 316 M192 306 Q182 322 168 316', B, 1.1, .5)
    elif bt == 'sweat':
        g.append(f'<path d="M100 300 L200 300 L200 312 L100 312 Z" fill="{shade(B, -0.1)}"/>')
        g.append(f'<path d="M146 312 Q144 330 140 336 M154 312 Q156 330 160 336" stroke="#F2F2F2" stroke-width="1.5" fill="none"/>')
        for y in (380, 440, 500): fold(f'M{112} {y} Q125 {y+8} 140 {y}', B, 1.2, .4); fold(f'M{160} {y} Q175 {y+8} 188 {y}', B, 1.2, .4)
        if taper:
            for x0 in (hemL, 300-hemR): g.append(f'<rect x="{x0-1}" y="564" width="{hemR-hemL+2}" height="14" rx="3" fill="{shade(B, -0.12)}"/>')
    else:  # chino
        fold('M106 306 Q118 326 132 316 M194 306 Q182 326 168 316', B, 1.1, .5)
        for x in (126, 174): fold(f'M{x-10} 455 Q{x} 462 {x+10} 455', B, 1.1, .4)
        for x in (124, 176): fold(f'M{x-12} 562 Q{x} 554 {x+12} 562', B, 1.1, .45)
    # waistband / belt
    if bt in ('slacks', 'chino', 'denim'):
        g.append(f'<rect x="100" y="296" width="100" height="12" fill="{shade(B, -0.08)}" {edge}/>')
        if bt != 'denim':
            g.append('<rect x="100" y="298" width="100" height="8" fill="#3A2A20"/><rect x="144" y="297" width="12" height="10" rx="1" fill="none" stroke="#B8B2A6" stroke-width="1.6"/>')

    # ---------- shoes ----------
    def shoe(x0, flip):
        sgn = -1 if flip else 1; cx = x0
        if st == 'loafer':
            up = f'M{cx-24*sgn} 578 Q{cx-26*sgn} 568 {cx-12*sgn} 566 L{cx+14*sgn} 568 Q{cx+34*sgn} 574 {cx+36*sgn} 586 L{cx-24*sgn} 588 Z'
            g.append(f'<path d="{up}" fill="{grad("s"+str(x0), S, -0.3, 0.15)}" {edge}/>')
            g.append(f'<path d="M{cx-22*sgn} 589 L{cx+37*sgn} 589" stroke="{shade(S, -0.45)}" stroke-width="3"/>')
            g.append(f'<path d="M{cx-4*sgn} 572 L{cx+16*sgn} 574" stroke="{shade(S, -0.4)}" stroke-width="2"/>')
            hil(f'M{cx+12*sgn} 575 Q{cx+24*sgn} 576 {cx+30*sgn} 582', S, 1.6, .5)
        else:
            chunky = st == 'runner'
            up = f'M{cx-24*sgn} 582 Q{cx-26*sgn} 566 {cx-10*sgn} 564 L{cx+10*sgn} 566 Q{cx+32*sgn} 572 {cx+36*sgn} 584 L{cx-24*sgn} 586 Z'
            g.append(f'<path d="{up}" fill="{grad("s"+str(x0), S, -0.2, 0.12)}" {edge}/>')
            sole_h = 8 if chunky else 6
            sole_c = '#F4F4F2' if lum(S) < 0.85 or chunky else '#E6E3DC'
            g.append(f'<path d="M{cx-26*sgn} 584 L{cx+38*sgn} 584 L{cx+37*sgn} {584+sole_h} L{cx-25*sgn} {584+sole_h} Z" fill="{sole_c}" stroke="#00000040" stroke-width="1"/>')
            for k in range(3):
                xx = cx + (0 + k*6)*sgn
                g.append(f'<path d="M{xx} {568+k} L{xx+5*sgn} {570+k}" stroke="{shade(S, -0.4) if lum(S) > .5 else "#EDEDED"}" stroke-width="1.4"/>')
            if chunky: g.append(f'<path d="M{cx-18*sgn} 580 Q{cx+6*sgn} 574 {cx+28*sgn} 581" stroke="{shade(S, -0.35)}" stroke-width="2" fill="none"/>')
    shoe(124, True); shoe(176, False)

    # ---------- arms (skin hands) ----------
    for hx in (72, 228): g.append(f'<ellipse cx="{hx}" cy="318" rx="9" ry="12" fill="{SKIN}" stroke="{SKIN_D}" stroke-width="1"/>')

    # ---------- top ----------
    tfill = grad('t', T)
    hem_y = 312
    torso = f'M97 124 Q150 106 203 124 Q211 150 206 200 Q202 250 206 {hem_y} Q150 {hem_y+8} 94 {hem_y} Q98 250 94 200 Q89 150 97 124 Z'
    g.append(f'<path d="M96 {hem_y-2} Q150 {hem_y+10} 204 {hem_y-2} L204 {hem_y+10} Q150 {hem_y+20} 96 {hem_y+10} Z" fill="#000" opacity=".14"/>')
    sleeveL = 'M98 124 Q80 128 76 150 L64 304 Q72 310 82 306 L104 176 Z'
    sleeveR = 'M202 124 Q220 128 224 150 L236 304 Q228 310 218 306 L196 176 Z'
    arm_c = O if outer else T
    if not outer:
        for p in (sleeveL, sleeveR): g.append(f'<path d="{p}" fill="{grad("sl", T, -0.28, 0.06)}" {edge}/>')
    g.append(f'<path d="{torso}" fill="{tfill}" {edge}/>')
    if tt == 'knit' or knit_top:
        rib = pattern('rib', 'rib', T)
        g.append(f'<path d="{torso}" fill="{rib}"/>')
        if not outer:
            for p in (sleeveL, sleeveR): g.append(f'<path d="{p}" fill="{rib}"/>')
        g.append(f'<path d="M92 {hem_y-12} L208 {hem_y-12} L208 {hem_y} Q150 {hem_y+8} 92 {hem_y} Z" fill="{shade(T, -0.1)}"/>')
    elif tt == 'shirt':
        g.append(f'<path d="{torso}" fill="{pattern("ox", "oxford", T)}"/>')
    if tt == 'shirt':
        g.append(f'<path d="M150 112 L150 {hem_y+4}" stroke="{shade(T, -0.25)}" stroke-width="1.4"/>')
        for y in (140, 172, 204, 236, 268, 298): g.append(f'<circle cx="153" cy="{y}" r="2" fill="{shade(T, -0.3)}"/>')
        g.append(f'<path d="M122 118 Q150 134 178 118 L178 124 Q150 142 122 124 Z" fill="#000" opacity=".10"/>')
        g.append(f'<path d="M120 112 L140 106 L150 128 L132 136 Z" fill="{shade(T, 0.08)}" {edge}/><path d="M180 112 L160 106 L150 128 L168 136 Z" fill="{shade(T, 0.08)}" {edge}/>')
        g.append(f'<rect x="164" y="160" width="22" height="24" rx="2" fill="none" stroke="{shade(T, -0.28)}" stroke-width="1.1"/>')
        fold('M110 220 Q126 236 120 262', T); fold('M190 214 Q176 238 184 262', T)
    elif tt == 'polo':
        g.append(f'<path d="M128 110 L150 132 L172 110 L166 104 L150 118 L134 104 Z" fill="{shade(T, -0.06)}" {edge}/>')
        g.append(f'<path d="M150 118 L150 160" stroke="{shade(T, -0.3)}" stroke-width="1.4"/>')
        for y in (128, 142, 156): g.append(f'<circle cx="153" cy="{y}" r="1.8" fill="{shade(T, -0.35)}"/>')
        fold('M112 230 Q126 246 120 270', T); fold('M188 226 Q174 248 182 270', T)
    else:
        g.append(f'<path d="M130 112 Q150 132 170 112" fill="none" stroke="{shade(T, -0.2)}" stroke-width="5" opacity=".8"/>')
        g.append(f'<path d="M134 114 Q150 128 166 114" fill="{SKIN}"/>')
        fold('M112 236 Q124 252 118 276', T); fold('M188 232 Q176 252 182 276', T)
    if not outer:
        fold('M84 200 Q92 212 86 226', T, 1.3); fold('M216 200 Q208 212 214 226', T, 1.3)
        if tt in ('knit', 'polo') or knit_top:
            for x in (64, 218): g.append(f'<rect x="{x}" y="292" width="18" height="10" rx="3" fill="{shade(T, -0.12)}" transform="rotate({4 if x<100 else -4} {x+9} 297)"/>')

    # ---------- outer ----------
    if outer:
        ofill = grad('o', O, -0.24, 0.10)
        for p in (sleeveL, sleeveR): g.append(f'<path d="{p}" fill="{ofill}" {edge}/>')
        long_ = ot == 'coat'
        oh = 420 if long_ else 330
        panL = f'M96 122 Q118 112 136 110 L138 {oh} L90 {oh} Z'
        panR = f'M204 122 Q182 112 164 110 L162 {oh} L210 {oh} Z'
        for p in (panL, panR): g.append(f'<path d="{p}" fill="{ofill}" {edge}/>')
        if ot in ('shirt_jacket',):
            g.append(f'<path d="M136 110 L120 150 L140 156 Z M164 110 L180 150 L160 156 Z" fill="{shade(O, 0.06)}" {edge}/>')
            for x in (100, 172): g.append(f'<rect x="{x}" y="168" width="28" height="30" rx="2" fill="none" stroke="{shade(O, -0.3)}" stroke-width="1.2"/><path d="M{x} 168 L{x+28} 168 L{x+28} 178 L{x} 178 Z" fill="{shade(O, -0.08)}" stroke="{shade(O, -0.3)}" stroke-width="1"/>')
            for y in (160, 200, 240, 280): g.append(f'<circle cx="132" cy="{y}" r="2.2" fill="{shade(O, -0.4)}"/>')
        elif ot == 'cardigan':
            g.append(f'<path d="{panL}" fill="{pattern("orib", "rib", O)}"/><path d="{panR}" fill="url(#{uid}orib)"/>')
            for y in (180, 220, 260, 300): g.append(f'<circle cx="133" cy="{y}" r="2.4" fill="{shade(O, -0.4)}"/>')
            g.append(f'<path d="M136 110 L136 {oh} M164 110 L164 {oh}" stroke="{shade(O, -0.15)}" stroke-width="5"/>')
        else:  # blazer / coat
            g.append(f'<path d="M136 110 L112 180 L138 214 Z M164 110 L188 180 L162 214 Z" fill="{shade(O, 0.06)}" {edge}/>')
            g.append(f'<path d="M106 262 L128 262 M172 262 L194 262" stroke="{shade(O, -0.35)}" stroke-width="1.6"/>')
            g.append(f'<circle cx="134" cy="250" r="2.4" fill="{shade(O, -0.4)}"/>')
        fold('M84 200 Q92 212 86 226', O, 1.4); fold('M216 200 Q208 212 214 226', O, 1.4)
        fold(f'M104 {oh-40} Q112 {oh-24} 108 {oh-6}', O); fold(f'M196 {oh-40} Q188 {oh-24} 192 {oh-6}', O)
        for x in (62, 220): g.append(f'<rect x="{x}" y="292" width="20" height="9" rx="2" fill="{shade(O, -0.1)}" transform="rotate({4 if x<100 else -4} {x+10} 296)"/>')

    # ---------- neck / head ----------
    g.append(f'<path d="M138 84 L162 84 L164 114 Q150 120 136 114 Z" fill="{SKIN}"/>')
    g.append(f'<path d="M138 98 Q150 106 162 98 L162 104 Q150 112 138 104 Z" fill="{SKIN_D}" opacity=".6"/>')
    g.append(f'<ellipse cx="123" cy="62" rx="4" ry="8" fill="{SKIN_D}"/><ellipse cx="177" cy="62" rx="4" ry="8" fill="{SKIN_D}"/>')
    g.append(f'<ellipse cx="150" cy="58" rx="27" ry="33" fill="{SKIN}"/>')
    g.append(f'<path d="M124 52 Q122 22 150 20 Q180 20 177 52 Q172 36 156 34 Q146 40 132 38 Q126 42 124 52 Z" fill="{HAIR}"/>')
    g.append(f'<path d="M150 22 Q170 22 175 40" stroke="#4A423B" stroke-width="2" fill="none" opacity=".6"/>')
    g.append(f'<path d="M140 80 Q150 86 160 80" stroke="{SKIN_D}" stroke-width="1.6" fill="none" opacity=".5"/>')

    return f'<svg viewBox="0 0 300 610" width="230" height="468"><defs>{"".join(defs)}</defs>{"".join(g)}</svg>'
