import asyncio, math, pathlib
from autocad_arch_mcp.backends.file_ipc_arch import FileIPCArchBackend

async def wall_rect(b, x1,y1,x2,y2, thick, layer="WALL"):
    dx=x2-x1; dy=y2-y1; l=math.hypot(dx,dy)
    if l==0: return None
    ux=-dy/l; uy=dx/l; ox=ux*thick/2; oy=uy*thick/2
    p1=(x1+ox,y1+oy); p2=(x2+ox,y2+oy); p3=(x2-ox,y2-oy); p4=(x1-ox,y1-oy)
    pts = "{},{};{},{:.1f};{},{:.1f};{},{:.1f}".format(p1[0],p1[1],p2[0],p2[1],p3[0],p3[1],p4[0],p4[1])
    # Use simple string without formatting issues
    pts2 = str(p1[0])+","+str(p1[1])+";"+str(p2[0])+","+str(p2[1])+";"+str(p3[0])+","+str(p3[1])+";"+str(p4[0])+","+str(p4[1])
    return await b._dispatch_unlocked("create-polyline", {"points_str": pts2, "closed":"1", "layer":layer})

async def main():
    b=FileIPCArchBackend()
    await b.initialize()
    print("build final BHK at 0,30000 - two-line 230/115 on template layers")
    base_x, base_y = 0, 30000
    def off(x,y): return (x+base_x, y+base_y)
    # Outer 230
    for seg in [(0,0,10500,0),(10500,0,10500,8500),(10500,8500,0,8500),(0,8500,0,0)]:
        x1,y1,x2,y2 = seg
        x1,y1 = off(x1,y1); x2,y2 = off(x2,y2)
        r=await wall_rect(b, x1,y1,x2,y2, 230, "WALL")
        print("outer", seg, r.to_dict() if r else "none")
    # Inner 115
    inner=[(3500,0,3500,3000),(7000,0,7000,3000),(0,3000,3500,3000),(0,3000,0,5500),(3500,3000,3500,5500),(3500,5500,5250,5500),(7000,3000,7000,5500),(7000,5500,10500,5500)]
    for seg in inner:
        x1,y1,x2,y2 = seg
        x1,y1 = off(x1,y1); x2,y2 = off(x2,y2)
        r=await wall_rect(b, x1,y1,x2,y2, 115, "WALL")
        print("inner", seg, r.to_dict() if r else "none")
    # Grid DOTE
    for seg in [(0,0,0,8500),(3500,0,3500,8500),(7000,0,7000,8500),(10500,0,10500,8500),(0,0,10500,0),(0,3000,10500,3000),(0,5500,10500,5500),(0,8500,10500,8500)]:
        x1,y1,x2,y2 = seg
        x1,y1 = off(x1,y1); x2,y2 = off(x2,y2)
        r=await b._dispatch_unlocked("create-line", {"x1":x1,"y1":y1,"x2":x2,"y2":y2,"layer":"DOTE"})
        print("grid", r.to_dict())
    # Bubbles A-D top and 1-3 left/right (on text layer, arial narrow style if available)
    bubbles = [
        (0+base_x, 8500+base_y+300, "A"), (3500+base_x, 8500+base_y+300, "B"), (7000+base_x, 8500+base_y+300, "C"), (10500+base_x, 8500+base_y+300, "D"),
        (0+base_x-300, 0+base_y, "1"), (0+base_x-300, 3000+base_y, "2"), (0+base_x-300, 5500+base_y, "3"),
        (0+base_x, 0+base_y-300, "A"), (3500+base_x, 0+base_y-300, "B"), (7000+base_x, 0+base_y-300, "C"), (10500+base_x, 0+base_y-300, "D"),
    ]
    for x,y,txt in bubbles:
        r=await b._dispatch_unlocked("create-text", {"x":x,"y":y,"text":txt,"height":195,"rotation":0,"layer":"text"})
        print(f"bubble {txt} {r.to_dict()}")
    # Columns 230x230 red squares at intersections (30 COLUMN)
    cols = [(0,0),(3500,0),(7000,0),(10500,0),(0,3000),(3500,3000),(7000,3000),(10500,3000),(0,5500),(3500,5500),(7000,5500),(10500,5500),(0,8500),(3500,8500),(7000,8500),(10500,8500)]
    for x,y in cols:
        x,y = off(x,y)
        # Create rectangle 230x230 centered at intersection
        r=await b._dispatch_unlocked("create-rectangle", {"x1":x-115,"y1":y-115,"x2":x+115,"y2":y+115,"layer":"30 COLUMN"})
        print(f"col {x},{y} {r.to_dict()}")
        # Hatch inside column (use create-hatch on last entity)
        # Get last handle and hatch
        # For now, skip hatch, just rectangle
    # Labels on text
    for x,y,txt in [(1750,7000,"LIVING 3700 x 3735"),(4550,1500,"DINING 3700 x 3000"),(8300,1500,"KITCHEN 4800 x 3680"),(8750,7000,"MASTER BEDROOM 3700 x 3735"),(1750,4250,"BEDROOM 2 3700 x 3735"),(8750,1500,"BEDROOM 3 3605 x 3735"),(4375,4250,"TOILET 1980 x 1670"),(1750,6250,"BATH 1980 x 1670")]:
        x,y = off(x,y)
        r=await b._dispatch_unlocked("create-text", {"x":x,"y":y,"text":txt,"height":125,"rotation":0,"layer":"text"})
        print(f"label {txt} {r.to_dict()}")
    # Doors AD1 900 AD2 1200 (fallback arcs on WINDOW)
    for x,y,w,typ in [(900,0,1200,"AD2"),(4100,0,900,"AD1"),(0,4100,900,"AD1"),(9100,0,900,"AD1"),(9100,4100,900,"AD1"),(4100,4750,750,"AD1"),(0,6500,750,"AD1")]:
        x,y = off(x,y)
        r=await b._dispatch_unlocked("create-arc", {"cx":x,"cy":y,"radius":w,"start_angle":0,"end_angle":90,"layer":"WINDOW"})
        print(f"door {typ} {r.to_dict()}")
        await b._dispatch_unlocked("create-text", {"x":x+100,"y":y+100,"text":typ,"height":100,"rotation":0,"layer":"WINDOW_TEXT"})
    # Windows
    for x,y,w in [(1750,8500,1800),(0,1500,1500),(9100,1500,1500),(3500,8500,900),(4750,8500,900)]:
        x,y = off(x,y)
        r=await b._dispatch_unlocked("create-line", {"x1":x,"y1":y,"x2":x+w,"y2":y,"layer":"WINDOW"})
        print(f"win {x},{y} {r.to_dict()}")
    # Stair on STAIRCASE
    x1,y1 = off(7000,3000)
    x2,y2 = off(8200,5500)
    r=await b._dispatch_unlocked("create-polyline", {"points_str": f"{x1},{y1};{x3},{y1};{x3},{y4};{x1},{y4}", "closed":"1", "layer":"STAIRCASE"})
    print(f"stair outline {r.to_dict()}")
    for i in range(1,10):
        y=3000+base_y+i*250
        r=await b._dispatch_unlocked("create-line", {"x1":7000+base_x,"y1":y,"x2":8200+base_x,"y2":y,"layer":"STAIRCASE"})
        print(f"tread {r.to_dict()}")
    # Furniture on furniture
    for x,y,w,h in [(200,5700,2200,900),(3850,1050,1800,900),(7500,6000,1800,2000)]:
        x,y = off(x,y)
        r=await b._dispatch_unlocked("create-rectangle", {"x1":x,"y1":y,"x2":x+w,"y2":y+h,"layer":"furniture"})
        print(f"furn {r.to_dict()}")
    # 3-layer dims on DIMENSION (Baral's orange) â€” outer, middle, inner
    # Outer overall
    r=await b._dispatch_unlocked("create-dimension-linear", {"x1":0+base_x,"y1":0+base_y,"x2":10500+base_x,"y2":0+base_y,"dim_x":5250+base_x,"dim_y":-800+base_y})
    print(f"outer dim {r.to_dict()}")
    r=await b._dispatch_unlocked("create-dimension-linear", {"x1":0+base_x,"y1":0+base_y,"x2":0+base_x,"y2":8500+base_y,"dim_x":-800+base_x,"dim_y":4250+base_y})
    print(f"outer left dim {r.to_dict()}")
    # Middle room dims
    r=await b._dispatch_unlocked("create-dimension-linear", {"x1":0+base_x,"y1":0+base_y,"x2":3500+base_x,"y2":0+base_y,"dim_x":1750+base_x,"dim_y":-500+base_y})
    print(f"mid dim {r.to_dict()}")
    # Inner opening
    r=await b._dispatch_unlocked("create-dimension-linear", {"x1":900+base_x,"y1":0+base_y,"x2":2100+base_x,"y2":0+base_y,"dim_x":1500+base_x,"dim_y":-300+base_y})
    print(f"inner dim {r.to_dict()}")
    # Title
    r=await b._dispatch_unlocked("create-text", {"x":500+base_x,"y":-1200+base_y,"text":"3BHK GROUND FLOOR PLAN  SCALE 1:50  TWO-LINE WALLS 230/115  AD1 AD2  IMPROVED ON BARAL SECOND FLOOR","height":180,"rotation":0,"layer":"text"})
    print(f"title {r.to_dict()}")
    await b._dispatch_unlocked("zoom-extents", {})
    info=await b._dispatch_unlocked("drawing-info", {})
    print(f"FINAL {info.to_dict()}")
    print("done final BHK at 0,30000")

asyncio.run(main())

