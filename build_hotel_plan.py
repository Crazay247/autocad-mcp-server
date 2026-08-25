"""HOTEL typical floor plan - LIVE AutoCAD COM, AddLine-only, new document (Drawing3 3BHK untouched).
Double-loaded corridor: south 8 guest rooms, north lobby/core/service, corridor y6600-8400.
"""
import win32com.client, pythoncom, math, time
from collections import Counter

def retry(fn, tries=40, delay=0.5):
    for k in range(tries):
        try:
            return fn()
        except pythoncom.com_error as e:
            msg = str(e).lower()
            codes = [a for a in e.args if isinstance(a, int)]
            scode = e.args[2][0] if len(e.args) > 2 and isinstance(e.args[2], tuple) and e.args[2] else None
            if -2147418111 in codes or -2147418111 == scode or 'rejected' in msg or 'busy' in msg:
                time.sleep(delay)
                continue
            raise
    raise RuntimeError('COM busy too long')

acad = win32com.client.GetActiveObject('AutoCAD.Application')
doc = retry(lambda: acad.Documents.Add())
print('new doc', doc.Name)
time.sleep(2)
try:
    retry(lambda: doc.SetVariable("INSUNITS", 4))  # mm
except Exception as e:
    print('insunits skip', e)
ms = doc.ModelSpace

# ---- layers triad ----
def layer(name, color, ltype="Continuous", lw=50):
    try:
        return retry(lambda: doc.Layers.Item(name))
    except Exception:
        L = retry(lambda: doc.Layers.Add(name)); L.color = color
        try: L.Linetype = ltype
        except Exception: pass
        try: L.Lineweight = lw
        except Exception: pass
        return L

for n,c,lt,lw in [("A-WALL-230",4,"Continuous",50),("A-WALL-115",3,"Continuous",50),
                  ("A-WALL-HATCH",8,"Continuous",13),("A-GRID",6,"CENTER",25),
                  ("A-DOOR",1,"Continuous",50),("A-WIND",5,"Continuous",50),
                  ("A-ANNO-TEXT",7,"Continuous",18),("G-TTLB",7,"Continuous",35)]:
    layer(n,c,lt,lw)
try: doc.Linetypes.Load("CENTER","acad.lin")
except Exception: pass
print('layers ok')

# ---- helpers ----
def line(x1,y1,x2,y2,layer):
    p1=win32com.client.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_R8,(float(x1),float(y1),0.0))
    p2=win32com.client.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_R8,(float(x2),float(y2),0.0))
    e=retry(lambda: ms.AddLine(p1,p2))
    try: retry(lambda: setattr(e,'Layer',layer))
    except Exception: pass
    return e
def rect(x1,y1,x2,y2,layer):  # 4 lines closed
    line(x1,y1,x2,y1,layer); line(x2,y1,x2,y2,layer); line(x2,y2,x1,y2,layer); line(x1,y2,x1,y1,layer)
def circle(cx,cy,r,layer):
    p=win32com.client.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_R8,(float(cx),float(cy),0.0))
    c=retry(lambda: ms.AddCircle(p,float(r)))
    try: retry(lambda: setattr(c,'Layer',layer))
    except Exception: pass
    return c
def arc(cx,cy,r,a1,a2,layer):
    c=win32com.client.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_R8,(float(cx),float(cy),0.0))
    a=retry(lambda: ms.AddArc(c,float(r),math.radians(a1),math.radians(a2)))
    try: retry(lambda: setattr(a,'Layer',layer))
    except Exception: pass
    return a
def text(x,y,s,h,layer,center=True):
    p=win32com.client.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_R8,(float(x),float(y),0.0))
    t=retry(lambda: ms.AddText(s,p,float(h)))
    try: retry(lambda: setattr(t,'Layer',layer))
    except Exception: pass
    if center:
        try:
            retry(lambda: setattr(t,'Alignment',4)); retry(lambda: setattr(t,'TextAlignmentPoint',p))
        except Exception: pass
    return t
def count(layer=None, ename=None):
    n=0
    for i in range(ms.Count):
        try:
            e=ms.Item(i)
            if layer and e.Layer!=layer: continue
            if ename and e.EntityName!=ename: continue
            n+=1
        except Exception: pass
    return n

W,H=30000,15000
CY1,CY2=6600,8400          # corridor band
T=230                       # outer thickness
t=115                       # inner thickness

# room module south: 8 rooms between x230..29770
xs=[230+i*3442.5 for i in range(9)]           # 230..29770
room_c=[round(xs[i]+(xs[i+1]-xs[i])/2) for i in range(8)]
door_w=900
gaps=[(c-door_w//2,c+door_w//2) for c in room_c]

print('== STEP 1 outer double 230 ==')
rect(0,0,W,H,"A-WALL-230")
rect(T,T,W-T,H-T,"A-WALL-230")
print('count',ms.Count,'A-WALL-230',count(layer="A-WALL-230"),'(expect 8)')
assert count(layer="A-WALL-230")==8

print('== STEP 2 partitions/corridor double 115 with door gaps ==')
def wall_h(y1,y2,gaps,x1=T,x2=W-T):
    segs=[]; cur=x1
    for g1,g2 in gaps:
        if g1>cur: segs.append((cur,g1))
        cur=g2
    if x2>cur: segs.append((cur,x2))
    for a,b in segs:
        line(a,y1,b,y1,"A-WALL-115"); line(a,y2,b,y2,"A-WALL-115")
    return len(segs)*2
def wall_v(x1,x2,gaps,y1=T,y2=CY1):
    segs=[]; cur=y1
    for g1,g2 in gaps:
        if g1>cur: segs.append((cur,g1))
        cur=g2
    if y2>cur: segs.append((cur,y2))
    for a,b in segs:
        line(x1,a,x1,b,"A-WALL-115"); line(x2,a,x2,b,"A-WALL-115")
    return len(segs)*2

n=wall_h(CY1,CY1+t,gaps)                    # corridor south face
n+=wall_h(CY2-t,CY2,[(11000,12600),(19000,19900),(25000,25900)])   # corridor north face
print('corridor walls lines',n)
# room partitions vertical (no gaps)
for x in xs[1:-1]:
    line(x,T,x,CY1,"A-WALL-115"); line(x+t,T,x+t,CY1,"A-WALL-115")
print('room partitions done')
# north zone dividers x=7500,16500,22500 (double)
for xd in [7500,16500,22500]:
    line(xd,CY2+t,xd,H-T,"A-WALL-115"); line(xd+t,CY2+t,xd+t,H-T,"A-WALL-115")
# core: stair + 2 lifts rectangles double-line
rect(8000,9000,11000,11600,"A-WALL-115")     # stair
rect(12000,CY2+t,14000,CY2+t+2000,"A-WALL-115")   # lift 1
rect(14400,CY2+t,16400,CY2+t+2000,"A-WALL-115")   # lift 2
cnt115=count(layer="A-WALL-115")
print('A-WALL-115',cnt115,'total',ms.Count)

print('== STEP 3 hatch ticks every 500 ==')
step=500
# outer cavities
for y in range(T+100,H-T,step):
    line(0,y,T,min(y+t,H-T),"A-WALL-HATCH"); line(W-T,y,W,min(y+t,H-T),"A-WALL-HATCH")
for x in range(T+100,W-T,step):
    line(x,0,min(x+t,W-T),T,"A-WALL-HATCH"); line(x,H-T,min(x+t,W-T),H,"A-WALL-HATCH")
# corridor cavities (skip gaps roughly by drawing full then it's fine visually behind doors)
y=CY1
x=T
while x<W-T-step:
    skip=any(g1-50<x<g2+50 or g1-50<x+step<g2+50 for g1,g2 in gaps+[(11000,12600),(19000,19900),(25000,25900)])
    if not skip:
        line(x,y,x+int(t*0.9),y+t,"A-WALL-HATCH"); line(x,CY2-t,x+int(t*0.9),CY2,"A-WALL-HATCH")
    x+=step
# room partitions ticks
for xd in xs[1:-1]:
    yy=T+100
    while yy<CY1-step:
        line(xd,yy,xd+t,yy+int(t*0.9),"A-WALL-HATCH"); yy+=step
print('ticks',count(layer="A-WALL-HATCH"),'total',ms.Count)

print('== STEP 4 grid 9 lines + 18 bubbles ==')
gv=[(0,"A"),(7500,"B"),(15000,"C"),(22500,"D"),(30000,"E")]
gh=[(0,"1"),(CY1,"2"),(CY2,"3"),(15000,"4")]
for x,l in gv:
    line(x,-700,x,H+700,"A-GRID"); circle(x,-700,250,"A-GRID"); text(x,-700,l,200,"A-GRID")
    circle(x,H+700,250,"A-GRID"); text(x,H+700,l,200,"A-GRID")
for y,l in gh:
    line(-700,y,W+700,y,"A-GRID"); circle(-700,y,250,"A-GRID"); text(-700,y,l,200,"A-GRID")
    circle(W+700,y,250,"A-GRID"); text(W+700,y,l,200,"A-GRID")
print('grid lines',count(layer="A-GRID",ename="AcDbLine"),'(expect 9)',
      'circles',count(ename="AcDbCircle"),'(expect 18)')

print('== STEP 5 doors leaf+arc / windows ticks ==')
# guest room doors on corridor south face, hinge at gap-left, swing into room (south)
for c,(g1,g2) in zip(room_c,gaps):
    line(g1,CY1,g1,CY1-door_w,"A-DOOR")            # leaf down
    arc(g1,CY1,door_w,270,360,"A-DOOR")            # swing
# entrance double door west wall into lobby
line(T,10500,T+door_w*2,10500,"A-DOOR"); arc(T,10500,1800,270,360,"A-DOOR")
line(T,12300,T+1800,12300,"A-DOOR") if False else None
# core opening door
line(11000,CY2,11000,CY2-door_w,"A-DOOR"); arc(11000,CY2,door_w,180,270,"A-DOOR")
# laundry + gym doors on corridor north face
for gx in [(19000,19900),(25000,25900)]:
    line(gx[0],CY2,gx[0],CY2+door_w,"A-DOOR"); arc(gx[0],CY2,door_w,0,90,"A-DOOR")
# windows: south wall ticks per room centered w=1500
for c in room_c:
    line(c-750,0,c-750,T,"A-WIND"); line(c+750,0,c+750,T,"A-WIND")
    line(c-750,H-T,c-750,H,"A-WIND"); line(c+750,H-T,c+750,H,"A-WIND")   # north lights too
# lobby west glazing ticks
for yy in [10200,12600]:
    line(0,yy,T,yy,"A-WIND")
print('doors arcs',count(layer="A-DOOR",ename="AcDbArc"),'wind ticks',count(layer="A-WIND"))

print('== STEP 6 labels ==')
labels=[("LOBBY",3800,11500),("STAIR",9500,10300),("LIFT",13000,CY2+t+1000),("LIFT",15400,CY2+t+1000),
        ("SERVICE",19500,11500),("GYM",26100,11500),("CORRIDOR",W/2,(CY1+CY2)/2)]
for i,c in enumerate(room_c):
    labels.append((f"GUEST ROOM {101+i}\n21.9 m2" if False else f"GUEST RM {101+i}", c, 3400))
for s,x,y in labels:
    text(x,y,s,220,"A-ANNO-TEXT")
print('texts total',count(ename="AcDbText"))

print('== STEP 7 title single ==')
# delete any title at target first
for i in range(ms.Count-1,-1,-1):
    try:
        e=ms.Item(i)
        if e.EntityName=="AcDbText" and abs(e.InsertionPoint[0]-200)<1 and abs(e.InsertionPoint[1]+1350)<1:
            e.Delete()
    except Exception: pass
text(200,-1350,"HOTEL TYPICAL FLOOR PLAN 30000x15000 SCALE 1:100",300,"G-TTLB")

print('== FINAL CHECKLIST ==')
print('1 outer A-WALL-230:',count(layer="A-WALL-230"),'PASS' if count(layer="A-WALL-230")==8 else 'FAIL')
print('2 partitions A-WALL-115:',count(layer="A-WALL-115"))
print('3 hatch ticks:',count(layer="A-WALL-HATCH"))
gl=count(layer="A-GRID",ename="AcDbLine"); cc=count(ename="AcDbCircle")
print(f'4 grid {gl}/9 {"PASS" if gl==9 else "FAIL"} circles {cc}/18 {"PASS" if cc==18 else "FAIL"}')
da=count(layer="A-DOOR",ename="AcDbArc"); wt=count(layer="A-WIND")
print(f'5 door arcs {da} wind ticks {wt}')
bt=0
coords=[]
for i in range(ms.Count):
    try:
        e=ms.Item(i)
        if e.EntityName=="AcDbText":
            ins=e.InsertionPoint; coords.append((round(ins[0]),round(ins[1]),e.TextString))
            if e.Layer=="G-TTLB": bt+=1
    except Exception: pass
dup=[k for k,v in Counter(coords).items() if v>1]
print(f'6 duplicate texts {len(dup)} {"PASS" if not dup else "FAIL"}')
print(f'7 title G-TTLB count {bt} {"PASS" if bt==1 else "FAIL"}')
print('TOTAL', ms.Count)
doc.SaveAs(r"C:\Temp\Hotel_TypicalFloor.dwg")
print('saved C:\\Temp\\Hotel_TypicalFloor.dwg')
acad.ZoomExtents()
print('zoomed')
