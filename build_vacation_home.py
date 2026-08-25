"""VACATION HOME: site context + furnished plan + 3-layer dims + south elevation. COM AddLine/AddHatch/Arial-Bold."""
import win32com.client, pythoncom, math, time
from collections import Counter
def retry(fn,tries=60,delay=0.4):
    for _ in range(tries):
        try: return fn()
        except pythoncom.com_error as e:
            msg=str(e).lower(); codes=[a for a in e.args if isinstance(a,int)]
            sc=e.args[2][0] if len(e.args)>2 and isinstance(e.args[2],tuple) and e.args[2] else None
            if -2147418111 in codes or sc==-2147418111 or 'rejected' in msg or 'busy' in msg: time.sleep(delay); continue
            raise
    raise RuntimeError('busy')
acad=win32com.client.GetActiveObject('AutoCAD.Application')
doc=retry(lambda: acad.Documents.Add()); print('doc',doc.Name); time.sleep(2)
try: retry(lambda: doc.SetVariable("INSUNITS",4))
except Exception: pass
ms=doc.ModelSpace
try:
    ts=doc.TextStyles.Item("ARIAL-BOLD")
except Exception:
    ts=retry(lambda: doc.TextStyles.Add("ARIAL-BOLD"))
try: ts.SetFont("Arial",True,False,0,34); ts.Height=0.0
except Exception as e: print('font',e)
def layer(n,c,lt="Continuous",lw=50):
    try: return doc.Layers.Item(n)
    except Exception:
        L=retry(lambda: doc.Layers.Add(n)); L.color=c
        try: L.Linetype=lt
        except Exception: pass
        try: L.Lineweight=lw
        except Exception: pass
        return L
for n,c,lt,lw in [("A-WALL-230",4,"Continuous",50),("A-WALL-115",3,"Continuous",50),
 ("A-FURN",8,"Continuous",25),("A-DIM-1",2,"Continuous",18),("A-DIM-2",3,"Continuous",18),
 ("A-DIM-3",4,"Continuous",18),("A-ANNO-TEXT",7,"Continuous",18),("G-TTLB",7,"Continuous",35),
 ("SITE-BNDY",1,"DASHED",35),("SITE-TREE",84,"Continuous",13),("SITE-CNTR",94,"DASHED",13),
 ("SITE-ROAD",8,"Continuous",25),("A-GLAZ",151,"Continuous",25),("A-DECK",32,"Continuous",13),
 ("ELEV-WALL",7,"Continuous",50),("ELEV-ROOF",30,"Continuous",50),("ELEV-GND",252,"Continuous",13)]:
    layer(n,c,lt,lw)
for lt in ["DASHED","CENTER"]:
    try: doc.Linetypes.Load(lt,"acad.lin")
    except Exception: pass
V=lambda *a: win32com.client.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_R8,(float(a[0]),float(a[1]),0.0))
def line(x1,y1,x2,y2,l):
    e=retry(lambda: ms.AddLine(V(x1,y1),V(x2,y2)))
    try: retry(lambda: setattr(e,'Layer',l))
    except Exception: pass
    return e
def rect(x1,y1,x2,y2,l,keep=None):
    ls=[line(x1,y1,x2,y1,l),line(x2,y1,x2,y2,l),line(x2,y2,x1,y2,l),line(x1,y2,x1,y1,l)]
    if keep is not None: keep.extend(ls)
    return ls
def circle(cx,cy,r,l):
    c=retry(lambda: ms.AddCircle(V(cx,cy),float(r)))
    try: retry(lambda: setattr(c,'Layer',l))
    except Exception: pass
    return c
def arc(cx,cy,r,a1,a2,l):
    a=retry(lambda: ms.AddArc(V(cx,cy),float(r),math.radians(a1),math.radians(a2)))
    try: retry(lambda: setattr(a,'Layer',l))
    except Exception: pass
    return a
def text(x,y,s,h,l,center=True):
    t=retry(lambda: ms.AddText(s,V(x,y),float(h)))
    try: retry(lambda: setattr(t,'Layer',l))
    except Exception: pass
    try: retry(lambda: setattr(t,'StyleName',"ARIAL-BOLD"))
    except Exception: pass
    if center:
        try: retry(lambda: setattr(t,'Alignment',4)); retry(lambda: setattr(t,'TextAlignmentPoint',V(x,y)))
        except Exception: pass
    return t
def fill(x1,y1,x2,y2,l,pat="SOLID",scale=1.0,color=None):
    ls=rect(x1,y1,x2,y2,l)
    try:
        pt=0 if pat.upper()=="SOLID" else 1
        h=retry(lambda: ms.AddHatch(pt,pat,True))
        loop=win32com.client.VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_DISPATCH,tuple(ls))
        retry(lambda: h.AppendOuterLoop(loop))
        if scale!=1.0 and pat.upper()!="SOLID":
            try: h.PatternScale=float(scale)
            except Exception: pass
        retry(lambda: setattr(h,'Layer',l))
        if color is not None:
            try: retry(lambda: setattr(h,'Color',color))
            except Exception: pass
    except Exception as e: print('fill?',pat,e)
    return ls
def dim(p1,p2,tp,l,scale=100):
    d=retry(lambda: ms.AddDimAligned(V(*p1),V(*p2),V(*tp)))
    try: retry(lambda: setattr(d,'Layer',l)); retry(lambda: setattr(d,'ScaleFactor',scale))
    except Exception: pass
    return d
print('== SITE ==')
rect(0,0,40000,26000,"SITE-BNDY"); text(20000,26500,"PLOT 40.0m x 26.0m",280,"SITE-BNDY")
rect(0,-3500,40000,-500,"SITE-ROAD"); fill(0,-3300,40000,-700,"SITE-ROAD","SOLID",color=8)
line(-500,-2000,40500,-2000,"SITE-ROAD").Linetype="DASHED"
text(20000,-2450,"ACCESS ROAD",240,"SITE-ROAD")
for k,(b,a) in enumerate([(21500,650),(22900,850),(24300,1050)]):
    pts=[(1000+i*1600,b+int(a*math.sin(i*0.5+k))) for i in range(25)]
    for i in range(len(pts)-1): line(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],"SITE-CNTR")
text(35500,25200,"GRADE +12.6",200,"SITE-CNTR")
for cx,cy,r in [(2500,19500,1100),(36000,20500,1200),(33000,22800,950),(800,13000,1000),
                (24500,21200,900),(13500,22200,800),(6500,4800,950),(36500,4300,1000)]:
    circle(cx,cy,r,"SITE-TREE")
    for a in range(0,360,72): arc(cx,cy,r*0.7,a,a+45,"SITE-TREE")
    circle(cx,cy,r*0.09,"SITE-TREE")
text(2300,18100,"EXISTING TREES",210,"SITE-TREE")
line(36600,23400,37400,21800,"G-TTLB"); line(37400,21800,38200,23400,"G-TTLB")
line(36800,22900,38000,22900,"G-TTLB"); text(37400,23700,"N",400,"G-TTLB")
print('== PLAN ==')
HX1,HY1,HX2,HY2,C1,C2,T,t2=6000,8000,22000,18000,11000,13000,230,115
rect(HX1,HY1,HX2,HY2,"A-WALL-230"); rect(HX1+T,HY1+T,HX2-T,HY2-T,"A-WALL-230")
fill(HX1,T,HX2,HY1,"A-WALL-230","ANSI31",18,color=254)
def ph(y,gaps=[]):
    seg=[];cur=HX1+T
    for g1,g2 in gaps:
        if g1>cur: seg.append((cur,g1))
        cur=g2
    if HX2-T>cur: seg.append((cur,HX2-T))
    for a,b in seg: line(a,y,b,y,"A-WALL-115"); line(a,y+t2,b,y+t2,"A-WALL-115")
ph(C2,[(7000,12300),(15200,20200)])
ph(C1,[(8550,9450),(15900,16800),(18800,19700)])
def pv(x,y1,y2,gaps=[]):
    seg=[];cur=y1
    for g1,g2 in gaps:
        if g1>cur: seg.append((cur,g1))
        cur=g2
    if y2>cur: seg.append((cur,y2))
    for a,b in seg: line(x,a,x,b,"A-WALL-115"); line(x+t2,a,x+t2,b,"A-WALL-115")
pv(14000,C2,HY2-T,[(14300,17500)])
pv(16500,HY1+T,C1)
pv(12500,HY1+T,C1,[(9300,10200)])
print('walls done')
# deck + pool
fill(22000,9000,30000,17000,"A-DECK","ANSI31",30,color=42)
for yy in range(9200,17000,400): line(22000,yy,30000,yy,"A-DECK")
rect(23500,10500,28500,14500,"A-GLAZ"); rect(23700,10700,28300,14300,"A-GLAZ")
fill(23700,10700,28300,14300,"A-GLAZ","SOLID",color=151)
for i in range(5): arc(24300+i*900,12500,500,200,340,"A-GLAZ")
text(26000,14900,"POOL",300,"A-GLAZ"); text(26000,8600,"DECK",300,"A-DECK")
# furniture
def fr(x1,y1,x2,y2,label=None,fc=None):
    rect(x1,y1,x2,y2,"A-FURN")
    if fc is not None: fill(x1+30,y1+30,x2-30,y2-30,"A-FURN","SOLID",color=fc)
    if label: text((x1+x2)/2,(y1+y2)/2,label,170,"A-FURN")
fr(6300,15600,8300,17700,None,253); fr(8400,15600,10400,17700,None,253); fr(6300,14400,10400,15300,"SOFA",254)
fr(7600,13400,9100,14200,"TABLE",None)
fr(20600,17400,21400,17850,None,253); fr(20600,13150,21400,13600,None,253)
for i in range(4):
    cx=17300+i*550; fr(cx,15800,cx+420,16220,None); fr(cx,16980,cx+420,17400,None)
fr(21100,13000,21700,17900,"COUNTER",253); fr(19800,13000,20400,14100,None,253)
fr(19600,14800,21300,15700,"ISLAND",254)
fr(6800,8500,8400,10500,"BED1",10); fr(6900,10550,8300,10850,None,7)
fr(17800,8500,19400,10500,"BED2",10); fr(17900,10550,19300,10850,None,7)
fr(20500,8600,21800,9200,"WARD",253); fr(12900,8600,13800,9700,"WC",None)
circle(14750,9150,420,"A-FURN"); fr(15400,8600,16300,9500,"SHW",151)
for s,x,y in [("LIVING",9500,16600),("KITCHEN / DINING",17600,16600),("BED ROOM 1",7600,11300),
              ("BED ROOM 2",18600,11300),("BATH",14600,11300),("CORRIDOR",17000,12000)]:
    text(x,y,s,260,"A-ANNO-TEXT")
print('== DIMS 3 layers ==')
dim((0,-4500),(40000,-4500),(20000,-5300),"A-DIM-3")
dim((0,-3800),(22000,-3800),(11000,-3100),"A-DIM-2"); dim((22000,-3800),(30000,-3800),(26000,-3100),"A-DIM-2")
dim((HX1,HY1-600),(HX2,HY2-600),(14000,HY2+700),"A-DIM-3")
dim((HX1,7650),(12500,7650),(9250,7150),"A-DIM-1"); dim((12500,7650),(16500,7650),(14500,7150),"A-DIM-1"); dim((16500,7650),(22000,7650),(19250,7150),"A-DIM-1")
dim((-3000,0),(-3000,26000),(-3800,13000),"A-DIM-3")
dim((HX1-800,HY1),(HX1-800,C1),(HX1-1500,9500),"A-DIM-2"); dim((HX1-800,C1),(HX1-800,HY2),(HX1-1500,15500),"A-DIM-2")
dim((HX2+800,C1),(HX2+800,HY2),(HX2+1500,12000),"A-DIM-1")
print('== SOUTH ELEVATION ==')
EX,EY,W2=52000,-12000,16000
line(EX,EY,EX+W2,EY,"ELEV-GND")
for i in range(14): line(EX+400+i*1150,EY,EX+400+i*1150-500,EY-450,"ELEV-GND")
fill(EX-500,EY+3600,EX+W2+500,EY+3950,"ELEV-ROOF","SOLID",color=30)
px=[EX,EX+4000,EX+8000,EX+12000,EX+W2]
for i in range(len(px)-1):
    a,bx=px[i],px[i+1]
    if i==2:
        fr2=rect(EX+7200,EY,EX+8800,EY+2100,"A-DOOR"); fill(EX+7250,EY+50,EX+8750,EY+2050,"A-DOOR","SOLID",color=32)
    else:
        fill(a+200,EY+150,bx-200,EY+3200,"A-GLAZ","SOLID",color=151)
        for mx in range(a+1000,bx-500,1000): line(mx,EY+150,mx,EY+3200,"A-GLAZ")
for px2 in px:
    fill(px2,EY,min(px2+400,EX+W2),EY+3600,"ELEV-WALL","SOLID",color=33)
for cxx in [EX+2000,EX+6000,EX+10000,EX+14000]:
    for yy in range(int(EY)+300,int(EY)+3300,450): line(cxx-1400,yy,cxx+1400,yy+120,"ELEV-WALL")
text(EX+W2/2,EY+4600,"SOUTH ELEVATION  1:100",380,"G-TTLB")
dim((EX,EY-1600),(EX+W2,EY-1600),(EX+8000,EY-2400),"A-DIM-3")
dim((EX-1500,EY),(EX-1500,EY+3600),(EX-2400,EY+1800),"A-DIM-2")
dim((EX+W2+1500,EY+3600),(EX+W2+1500,EY+3950),(EX+W2+2400,EY+3775),"A-DIM-1")
text(EX+8000,EY-3300,"VACATION HOME - SITE & ELEVATION",300,"G-TTLB")
n=ms.Count
print('TOTAL',n)
dups=[]
co=[]
for i in range(ms.Count):
    try:
        e=ms.Item(i)
        if e.EntityName=="AcDbText":
            ip=e.InsertionPoint; co.append((round(ip[0]),round(ip[1]),e.TextString))
    except Exception: pass
dup=[k for k,v in Counter(co).items() if v>1]
print('dup texts',len(dup),'PASS' if not dup else 'FAIL')
doc.SaveAs(r"C:\Temp\VacationHome_Site.dwg"); print('saved')
acad.ZoomExtents()
