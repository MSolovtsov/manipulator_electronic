#!/usr/bin/env python3
"""Проверка сгенерированной схемы KiCad (собственные символы manipulator:*):
  * каждый вывод стоит на конце провода (или помечен no_connect);
  * нет висящих концов, концов на середине чужого провода, лишних/недостающих junction;
  * нет ортогональных пересечений проводов без соединения;
  * подписи не накладываются друг на друга, на корпуса других символов и на провода;
    провода не проходят сквозь корпуса;
  * всё содержимое — внутри рабочего поля рамки ГОСТ (lib/worksheets/gost_portrait.kicad_wks)
    с запасом MARGIN и вне основной надписи (185 × 55 мм справа внизу).
Ширина текста оценивается как 0,95·размер шрифта на символ — оценка, не точный рендер.

Запуск: python3 scripts/check_sch.py boards/PS/PS.kicad_sch
Код возврата 1, если найдены проблемы.
"""
import re, sys

path = sys.argv[1] if len(sys.argv) > 1 else "boards/PS/PS.kicad_sch"
s = open(path, encoding="utf-8").read()
PAPER = {"A4": (297, 210), "A3": (420, 297), "A2": (594, 420), "A1": (841, 594)}
pw, ph = PAPER[re.search(r'\(paper "(A\d)"', s).group(1)]
FRAME = (20.0, 5.0, pw - 5.0, ph - 5.0)      # рабочее поле рамки: слева поле 8 + графы 12
TITLE = (pw - 5.0 - 185.0, ph - 5.0 - 55.0)  # левый верхний угол основной надписи
MARGIN = 8.0

# ---- геометрия и связность ----
libpins={}
for m in re.finditer(r'\(symbol "manipulator:([^"]+)"(.*?)\n  \)\n', s, re.S):
    pins=re.findall(r'\(pin (\w+) line \(at ([-\d.]+) ([-\d.]+) (\d+)\) \(length ([-\d.]+)\)( hide)?', m.group(2))
    libpins[m.group(1)]=[(k,float(x),float(y),bool(h)) for k,x,y,a,l,h in pins]
inst=re.findall(r'\(symbol \(lib_id "manipulator:([^"]+)"\) \(at ([-\d.]+) ([-\d.]+) (\d+)\)(.*?)\n  \)', s, re.S)
pinpts=[]; pwrpts=[]
for name,x,y,rot,body in inst:
    x,y,rot=float(x),float(y),int(rot)
    ref=re.search(r'\(property "Reference" "([^"]+)"',body).group(1)
    for k,px,py,h in libpins[name]:
        X,Y=(x+px,y-py) if rot==0 else (x-px,y+py)
        (pwrpts if h else pinpts).append((ref,k,round(X,3),round(Y,3)))
wires=[tuple(map(float,m)) for m in re.findall(r'\(wire \(pts \(xy ([-\d.]+) ([-\d.]+)\) \(xy ([-\d.]+) ([-\d.]+)\)\)', s)]
ncs=[tuple(map(float,m)) for m in re.findall(r'\(no_connect \(at ([-\d.]+) ([-\d.]+)\)', s)]
juncs=[tuple(map(float,m)) for m in re.findall(r'\(junction \(at ([-\d.]+) ([-\d.]+)\)', s)]
eq=lambda a,b: abs(a[0]-b[0])<1e-6 and abs(a[1]-b[1])<1e-6
def ends_at(p): return sum(1 for x1,y1,x2,y2 in wires if eq(p,(x1,y1)) or eq(p,(x2,y2)))
def on_mid(p): return any(abs((x2-x1)*(p[1]-y1)-(y2-y1)*(p[0]-x1))<1e-6 and min(x1,x2)-1e-6<=p[0]<=max(x1,x2)+1e-6 and min(y1,y2)-1e-6<=p[1]<=max(y1,y2)+1e-6 and not eq(p,(x1,y1)) and not eq(p,(x2,y2)) for x1,y1,x2,y2 in wires)
bad=[]
allp=pinpts+pwrpts
for ref,k,X,Y in allp:
    if ends_at((X,Y))==0 and not any(eq((X,Y),n) for n in ncs): bad.append(('вывод без провода',ref,k,X,Y))
    if on_mid((X,Y)): bad.append(('вывод на середине провода',ref,k,X,Y))
ends=set((x1,y1) for x1,y1,_,_ in wires)|set((x2,y2) for _,_,x2,y2 in wires)
for e in ends:
    npins=sum(1 for _,_,X,Y in allp if eq(e,(X,Y)))
    n=ends_at(e)+npins
    if on_mid(e): bad.append(('конец провода на середине другого',e))
    if n<2: bad.append(('висящий конец',e))
    if ends_at(e)>=2 and n>=3 and not any(eq(e,j) for j in juncs): bad.append(('узел без junction',e,n))
for j in juncs:
    if ends_at(j)+sum(1 for _,_,X,Y in allp if eq(j,(X,Y)))<3: bad.append(('лишний junction',j))
# пересечения проводов (ортогональные) без общего конца
for i,(a1,b1,a2,b2) in enumerate(wires):
    for (c1,d1,c2,d2) in wires[i+1:]:
        if a1==a2 and d1==d2:  # вертикаль x=a1 и горизонталь y=d1
            if min(c1,c2)<a1<max(c1,c2) and min(b1,b2)<d1<max(b1,b2): bad.append(('пересечение проводов',(a1,d1)))
        if b1==b2 and c1==c2:
            if min(a1,a2)<c1<max(a1,a2) and min(d1,d2)<b1<max(d1,d2): bad.append(('пересечение проводов',(c1,b1)))
geo_bad=list(bad); print('связность/геометрия — проблем:',len(geo_bad)); [print(' ',b) for b in geo_bad]

# ---- тексты и наложения ----
# библиотечные графики → bbox символа
libbox={}
libtexts={}
for m in re.finditer(r'\n  \(symbol "manipulator:([^"]+)"(.*?)\n  \)', s, re.S):
    name, body = m.group(1), m.group(2)
    xs=[];ys=[]
    for a,b in re.findall(r'\(xy ([-\d.]+) ([-\d.]+)\)',body): xs.append(float(a)); ys.append(float(b))
    for a,b,c,d in re.findall(r'\(start ([-\d.]+) ([-\d.]+)\) \(end ([-\d.]+) ([-\d.]+)\)',body): xs+= [float(a),float(c)]; ys+=[float(b),float(d)]
    for a,b,c,d in re.findall(r'\(pin \w+ line \(at ([-\d.]+) ([-\d.]+) (\d+)\) \(length ([-\d.]+)\)',body):
        xs.append(float(a)); ys.append(float(b))
    libbox[name]=(min(xs),min(ys),max(xs),max(ys)) if xs else (0,0,0,0)
    libtexts[name]=[(t,float(x),float(y)) for t,x,y in re.findall(r'\(text "([^"]+)" \(at ([-\d.]+) ([-\d.]+) \d+\)',body)]
W=0.95  # ширина символа ≈ 0.95·size (шрифт KiCad)
boxes=[]  # (x1,y1,x2,y2, label)
bodies=[]
inst=re.findall(r'\n  \(symbol \(lib_id "manipulator:([^"]+)"\) \(at ([-\d.]+) ([-\d.]+) (\d+)\)(.*?)\n  \)', s, re.S)
for name,x,y,rot,body in inst:
    x,y,rot=float(x),float(y),int(rot)
    bx1,by1,bx2,by2=libbox[name]
    if rot==0: bb=(x+bx1,y-by2,x+bx2,y-by1)
    else: bb=(x-bx2,y+by1,x-bx1,y+by2)
    ref=re.search(r'\(property "Reference" "([^"]+)"',body).group(1)
    bodies.append((bb,ref))
    for pm in re.finditer(r'\(property "(\w+)" "([^"]*)" \(at ([-\d.]+) ([-\d.]+) (\d+)\) \(show_name no\) \(do_not_autoplace no\)( \(hide yes\))? \(effects \(font (?:\(face "[^"]*"\) )?\(size ([-\d.]+) [-\d.]+\)(?: \(italic yes\))?\)(?: \(justify (\w+)\))?\)',body):
        pname,val,px,py,prot,hide,size,just=pm.groups()
        if hide or not val: continue
        px,py,size=float(px),float(py),float(size)
        w=len(val)*size*W; h=size
        if just=='left': x1,x2=px,px+w
        elif just=='right': x1,x2=px-w,px
        else: x1,x2=px-w/2,px+w/2
        boxes.append((x1,py-h/2,x2,py+h/2,f'{ref}.{pname}={val}'))
    for t,tx,ty in libtexts[name]:
        X,Y=(x+tx,y-ty) if rot==0 else (x-tx,y+ty); w=len(t)*1.27*W
        boxes.append((X-w/2,Y-0.635,X+w/2,Y+0.635,f'{ref}.text={t}'))
for m in re.finditer(r'\n  \(text "([^"]*)" \(exclude_from_sim no\) \(at ([-\d.]+) ([-\d.]+) 0\) \(effects \(font (?:\(face "[^"]*"\) )?\(size ([-\d.]+) [-\d.]+\)(?: \(italic yes\))?\) \(justify left bottom\)\)',s):
    t,x,y,size=m.group(1),float(m.group(2)),float(m.group(3)),float(m.group(4))
    boxes.append((x,y-size,x+len(t)*size*W,y,f'note={t[:30]}'))
wires=[tuple(map(float,m)) for m in re.findall(r'\(wire \(pts \(xy ([-\d.]+) ([-\d.]+)\) \(xy ([-\d.]+) ([-\d.]+)\)\)', s)]
def inter(a,b,eps=0.3):
    return not (a[2]<b[0]+eps or b[2]<a[0]+eps or a[3]<b[1]+eps or b[3]<a[1]+eps)
def seg_in_box(seg,b,eps=0.3):
    x1,y1,x2,y2=seg; bx1,by1,bx2,by2=b[0]+eps,b[1]+eps,b[2]-eps,b[3]-eps
    if bx1>=bx2 or by1>=by2: return False
    if x1==x2: return bx1<x1<bx2 and max(y1,y2)>by1 and min(y1,y2)<by2
    if y1==y2: return by1<y1<by2 and max(x1,x2)>bx1 and min(x1,x2)<bx2
    return False
bad=[]
for i in range(len(boxes)):
    for j in range(i+1,len(boxes)):
        if inter(boxes[i],boxes[j]): bad.append(('текст×текст',boxes[i][4],boxes[j][4]))
for b in boxes:
    for w in wires:
        if seg_in_box(w,b): bad.append(('провод через текст',b[4],w))
    for bb,ref in bodies:
        if ref.startswith('#'): continue
        if b[4].startswith(ref+'.'): continue
        if inter(b,bb,eps=0.3): bad.append(('текст на корпусе',b[4],ref))
for bb,ref in bodies:
    if ref.startswith('#'): continue
    for w in wires:
        x1,y1,x2,y2=w
        # провод, проходящий сквозь корпус (оба конца вне)
        inside=lambda px,py: bb[0]+0.3<px<bb[2]-0.3 and bb[1]+0.3<py<bb[3]-0.3
        if x1==x2 and bb[0]+0.3<x1<bb[2]-0.3 and min(y1,y2)<bb[1] and max(y1,y2)>bb[3]: bad.append(('провод сквозь корпус',ref,w))
        if y1==y2 and bb[1]+0.3<y1<bb[3]-0.3 and min(x1,x2)<bb[0] and max(x1,x2)>bb[2]: bad.append(('провод сквозь корпус',ref,w))
print('тексты/наложения — проблем:',len(bad)); [print(' ',b) for b in bad]

# ---- поля рамки ----
frame_bad = []
def in_field(x, y):
    if not (FRAME[0] + MARGIN <= x <= FRAME[2] - MARGIN and FRAME[1] + MARGIN <= y <= FRAME[3] - MARGIN): return False
    if x >= TITLE[0] - MARGIN and y >= TITLE[1] - MARGIN: return False
    return True
for b in boxes:
    for (x, y) in ((b[0], b[1]), (b[2], b[3])):
        if not in_field(x, y): frame_bad.append(('текст у рамки/на основной надписи', b[4], (round(x,1), round(y,1)))); break
for bb, ref in bodies:
    for (x, y) in ((bb[0], bb[1]), (bb[2], bb[3])):
        if not in_field(x, y): frame_bad.append(('символ у рамки/на основной надписи', ref, (round(x,1), round(y,1)))); break
for w in wires:
    for (x, y) in ((w[0], w[1]), (w[2], w[3])):
        if not in_field(x, y): frame_bad.append(('провод у рамки/на основной надписи', (round(x,1), round(y,1)))); break
print('поля рамки — проблем:', len(frame_bad)); [print(' ', b) for b in frame_bad]
sys.exit(1 if (geo_bad or bad or frame_bad) else 0)
