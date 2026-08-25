import asyncio, math, pathlib
from autocad_arch_mcp.backends.file_ipc_arch import FileIPCArchBackend

async def wall_rect(b, x1,y1,x2,y2, thick, layer="WALL"):
    dx=x2-x1; dy=y2-y1; l=math.hypot(dx,dy)
    if l==0: return None
    ux=-dy/l; uy=dx/l; ox=ux*thick/2; oy=uy*thick/2
    p1=(x1+ox,y1+oy); p2=(x2+ox,y2+oy); p3=(x2-ox,y2-oy); p4=(x1-ox,y1-oy)
    pts=f"{p1[0]},{p1[1]};{p2[0]},{p2[1]};{p3[0]},{p3[1]};{p4[0]},{p4[1]}"
    return await b._dispatch_unlocked("create-polyline", {"points_str": pts, "closed":"1", "layer":layer})

async def main():
    b=FileIPCArchBackend()
    await b.initialize()
    print(f"START twolines on template layers, hwnd={b._hwnd}")
    # Outer 230
    for seg in [(0,0,10500,0),(10500,0,10500,8500),(10500,8500,0,8500),(0,8500,0,0)]:
        r=await wall_rect(b, *seg, 230, "WALL")
        print(f"outer {seg} {r.to_dict() if r else 'none'}")
    # Inner 115
    inner=[(3500,0,3500,3000),(7000,0,7000,3000),(0,3000,3500,3000),(0,3000,0,5500),(3500,3000,3500,5500),(3500,5500,5250,5500),(7000,3000,7000,5500),(7000,5500,10500,5500)]
    for seg in inner:
        r=await wall_rect(b, *seg, 115, "WALL")
        print(f"inner {seg} {r.to_dict() if r else 'none'}")
    # Grid DOTE
    for seg in [(0,0,0,8500),(3500,0,3500,8500),(7000,0,7000,8500),(10500,0,10500,8500),(0,0,10500,0),(0,3000,10500,3000),(0,5500,10500,5500),(0,8500,10500,8500)]:
        r=await b._dispatch_unlocked("create-line", {"x1":seg[0],"y1":seg[1],"x2":seg[2],"y2":seg[3],"layer":"DOTE"})
        print(f"grid {seg} {r.to_dict()}")
    # Labels on text (template's text layer is 'text' color 5, also 'text_2')
    for x,y,txt in [(1750,7000,"LIVING 21.5 m2"),(4550,1500,"DINING 10.8 m2"),(8300,1500,"KITCHEN 14.1 m2"),(8750,7000,"MASTER BEDROOM 14.0 m2"),(1750,4250,"BEDROOM 2 10.5 m2"),(8750,1500,"BEDROOM 3 10.5 m2"),(4375,4250,"BATH 1 4.3 m2"),(1750,6250,"BATH 2 3.9 m2"),(7600,4250,"STAIR UP")]:
        r=await b._dispatch_unlocked("create-text", {"x":x,"y":y,"text":txt,"height":125,"rotation":0,"layer":"text"})
        print(f"label {txt} {r.to_dict()}")
    # Doors AD1 900 AD2 1200 on WINDOW (template's window layer) — use AD1/AD2 aliases but fallback to arc
    doors=[(900,0,1200,"AD2"),(4100,0,900,"AD1"),(0,4100,900,"AD1"),(9100,0,900,"AD1"),(9100,4100,900,"AD1"),(4100,4750,750,"AD1"),(0,6500,750,"AD1")]
    for x,y,w,typ in doors:
        # Try AD1/AD2 via dispatcher, fallback to arc
        r=await b._dispatch_unlocked(typ.lower(), {"x":x,"y":y,"width":w})
        print(f"door {typ} {x},{y} w={w} {r.to_dict()}")
        if not r.ok:
            r2=await b._dispatch_unlocked("create-arc", {"cx":x,"cy":y,"radius":w,"start_angle":0,"end_angle":90,"layer":"WINDOW"})
            print(f"  fallback arc {r2.to_dict()}")
            await b._dispatch_unlocked("create-text", {"x":x+100,"y":y+100,"text":typ,"height":100,"rotation":0,"layer":"WINDOW_TEXT"})
    # Windows on WINDOW
    for x,y,w in [(1750,8500,1800),(0,1500,1500),(9100,1500,1500),(3500,8500,900),(4750,8500,900)]:
        r=await b._dispatch_unlocked("create-line", {"x1":x,"y1":y,"x2":x+w,"y2":y,"layer":"WINDOW"})
        print(f"win {x},{y} {r.to_dict()}")
    # Stair on STAIRCASE
    r=await b._dispatch_unlocked("create-polyline", {"points_str":"7000,3000;8200,3000;8200,5500;7000,5500","closed":"1","layer":"STAIRCASE"})
    print(f"stair outline {r.to_dict()}")
    for i in range(1,10):
        y=3000+i*250
        r=await b._dispatch_unlocked("create-line", {"x1":7000,"y1":y,"x2":8200,"y2":y,"layer":"STAIRCASE"})
        print(f"tread {y} {r.to_dict()}")
    # Furniture on furniture
    for x,y,w,h in [(200,5700,2200,900),(3850,1050,1800,900),(7500,6000,1800,2000)]:
        r=await b._dispatch_unlocked("create-rectangle", {"x1":x,"y1":y,"x2":x+w,"y2":y+h,"layer":"furniture"})
        print(f"furn {x},{y} {r.to_dict()}")
    # 3-layer dims on DIMENSION (template's dim layer is DIMENSION, also D-DIM, 001-Archi-Dimension)
    for d in [(0,0,10500,0,5250,-800),(0,8500,10500,8500,5250,9300),(0,0,0,8500,-800,4250)]:
        r=await b._dispatch_unlocked("create-dimension-linear", {"x1":d[0],"y1":d[1],"x2":d[2],"y2":d[3],"dim_x":d[4],"dim_y":d[5]})
        print(f"dim {d} {r.to_dict()}")
    r=await b._dispatch_unlocked("create-text", {"x":500,"y":-1200,"text":"3BHK TWO-LINE 230/115  AD1 AD2  SCALE 1:50  WALL/DOTE/WINDOW/DIMENSION","height":200,"rotation":0,"layer":"text"})
    print(f"title {r.to_dict()}")
    await b._dispatch_unlocked("zoom-extents", {})
    info=await b._dispatch_unlocked("drawing-info", {})
    print(f"FINAL {info.to_dict()}")
    print("done twolines")

asyncio.run(main())
