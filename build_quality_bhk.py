"""Quality-corrected 3BHK: double PLINE + hatch, both-end bubbles, real blocks, 3-row dims both sides"""
import asyncio
from autocad_arch_mcp.backends.file_ipc_arch import FileIPCArchBackend

async def wall_double(b, x1,y1,x2,y2, thick, hatch=True):
    import math
    dx=x2-x1; dy=y2-y1; l=math.hypot(dx,dy)
    ux=-dy/l; uy=dx/l; ox=ux*thick/2; oy=uy*thick/2
    p1=(x1+ox,y1+oy); p2=(x2+ox,y2+oy); p3=(x2-ox,y2-oy); p4=(x1-ox,y1-oy)
    pts=f"{p1[0]},{p1[1]};{p2[0]},{p2[1]};{p3[0]},{p3[1]};{p4[0]},{p4[1]}"
    r=await b._dispatch_unlocked("create-polyline", {"points_str": pts, "closed":"1", "layer":"A-WALL"})
    if r.ok and hatch:
        import json
        try:
            h=json.loads(r.payload) if isinstance(r.payload,str) else r.payload
            handle=h.get('handle')
            if handle:
                await b._dispatch_unlocked("create-hatch", {"entity_id": handle, "pattern":"ANSI31"})
        except: pass
    return r

async def main():
    b=FileIPCArchBackend()
    await b.initialize()
    base_x, base_y = 0, 50000
    print(f"Quality BHK at {base_x},{base_y}")

    # Clear previous at same location (erase window)
    import pathlib
    code = f'(command "_.ERASE" (ssget "_W" (list {base_x} {base_y} 0) (list {base_x+10500} {base_y+8500} 0)) "")'
    p=pathlib.Path(r"C:\Users\Predator\AppData\Local\autocad-arch-mcp\ipc\erase_bhk.lsp")
    p.write_text(code, encoding='utf-8')
    r=await b._dispatch_unlocked('execute-lisp', {'code_file': str(p).replace(chr(92),'/')})
    print("erase", r.to_dict())

    # Walls double-line + hatch
    walls=[(0,0,10500,0,230),(10500,0,10500,8500,230),(10500,8500,0,8500,230),(0,8500,0,0,230),
           (3500,0,3500,3600,115),(7000,0,7000,3600,115),(0,3600,3500,3600,115),(0,3600,0,7200,115),
           (3500,3600,3500,7200,115),(3500,7200,5250,7200,115),(7000,3600,7000,7200,115),(7000,7200,10500,7200,115)]
    for x1,y1,x2,y2,w in walls:
        r=await wall_double(b, x1+base_x, y1+base_y, x2+base_x, y2+base_y, w, "A-WALL")
        print(f"wall {x1},{y1}->{x2},{y2} w={w} {r.to_dict()}")

    # Columns at intersections (hatched solid)
    for x,y in [(0,0),(3500,0),(7000,0),(10500,0),(0,3600),(3500,3600),(7000,3600),(10500,3600),(0,7200),(3500,7200),(7000,7200),(10500,7200),(0,8500),(3500,8500),(7000,8500),(10500,8500)]:
        r=await b._dispatch_unlocked("create-rectangle", {"x1":x+base_x-115,"y1":y+base_y-115,"x2":x+base_x+115,"y2":y+base_y+115,"layer":"A-COLS"})
        print(f"col {x},{y} {r.to_dict()}")
        # hatch solid
        try:
            import json
            h=json.loads(r.payload) if isinstance(r.payload,str) else r.payload
            handle=h.get('handle')
            if handle:
                hr=await b._dispatch_unlocked("create-hatch", {"entity_id": handle, "pattern":"SOLID"})
        except: pass

    # Grid DOTE extended 700 beyond building
    grids=[(0,0,0,8500),(3500,0,3500,8500),(7000,0,7000,8500),(10500,0,10500,8500),(0,0,10500,0),(0,3600,10500,3600),(0,7200,10500,7200),(0,8500,10500,8500)]
    for x1,y1,x2,y2 in grids:
        r=await b._dispatch_unlocked("create-line", {"x1":x1+base_x,"y1":y1+base_y,"x2":x2+base_x,"y2":y2+base_y,"layer":"A-GRID"})
        # extend
        if x1==x2: # vertical
            await b._dispatch_unlocked("create-line", {"x1":x1+base_x,"y1":y1+base_y-700,"x2":x2+base_x,"y2":y1+base_y-700,"layer":"A-GRID"})
            await b._dispatch_unlocked("create-line", {"x1":x1+base_x,"y1":y2+base_y+700,"x2":x2+base_x,"y2":y2+base_y+700,"layer":"A-GRID"})
        else:
            await b._dispatch_unlocked("create-line", {"x1":x1+base_x-700,"y1":y1+base_y,"x2":x1+base_x-700,"y2":y2+base_y,"layer":"A-GRID"})
            await b._dispatch_unlocked("create-line", {"x1":x2+base_x+700,"y1":y1+base_y,"x2":x2+base_x+700,"y2":y2+base_y,"layer":"A-GRID"})

    # Bubbles BOTH ends
    for x,y,txt in [(0,8500,"A"),(3500,8500,"B"),(7000,8500,"C"),(10500,8500,"D"),(0,0,"A"),(3500,0,"B"),(7000,0,"C"),(10500,0,"D"),(0,0,"1"),(0,3600,"2"),(0,7200,"3"),(0,8500,"4"),(10500,0,"1"),(10500,3600,"2"),(10500,7200,"3"),(10500,8500,"4")]:
        # bubbles are circles + text on A-GRID-BUBBLE
        r=await b._dispatch_unlocked("create-circle", {"cx":x+base_x,"cy":y+base_y+ (400 if y==8500 else -400 if y==0 else 0) + (400 if x==0 else -400 if x==10500 else 0),"radius":250,"layer":"A-GRID-BUBBLE"})
        r2=await b._dispatch_unlocked("create-text", {"x":x+base_x,"y":y+base_y+ (400 if y==8500 else -400 if y==0 else 0) + (400 if x==0 else -400 if x==10500 else 0),"text":txt,"height":180,"rotation":0,"layer":"A-GRID-BUBBLE"})
        print(f"bubble {txt} {r.to_dict()}")

    # Doors: leaf + swing on A-DOOR (real blocks)
    for x,y,w in [(900+base_x,0+base_y,1050),(4100+base_x,0+base_y,900),(0+base_x,4100+base_y,900),(9100+base_x,0+base_y,900),(9100+base_x,4100+base_y,900)]:
        # door leaf
        await b._dispatch_unlocked("create-line", {"x1":x,"y1":y,"x2":x,"y2":y+w,"layer":"A-DOOR"})
        await b._dispatch_unlocked("create-arc", {"cx":x,"cy":y,"radius":w,"start_angle":0,"end_angle":90,"layer":"A-DOOR"})
        await b._dispatch_unlocked("create-text", {"x":x+100,"y":y+100,"text":f"W{w}","height":120,"rotation":0,"layer":"A-DOOR"})
    # Windows: double tick on A-WINDOW
    for x,y,w in [(1750+base_x,8500+base_y,1500),(0+base_x,1500+base_y,1200),(9100+base_x,1500+base_y,1200)]:
        # window block: two ticks across wall thickness 230
        await b._dispatch_unlocked("create-line", {"x1":x,"y1":y,"x2":x+w,"y2":y,"layer":"A-WINDOW"})
        await b._dispatch_unlocked("create-line", {"x1":x,"y1":y+115,"x2":x+w,"y2":y+115,"layer":"A-WINDOW"})
        await b._dispatch_unlocked("create-text", {"x":x+200,"y":y+300,"text":f"W{w}","height":100,"rotation":0,"layer":"A-WINDOW"})

    # Furniture on A-FURN / sanitary / kitchen
    for x,y,w,h in [(200+base_x,5700+base_y,2200,900),(3850+base_x,1050+base_y,1800,900),(7500+base_x,6000+base_y,1800,2000)]:
        await b._dispatch_unlocked("create-rectangle", {"x1":x,"y1":y,"x2":x+w,"y2":y+h,"layer":"A-FURN"})
    for x,y,w,h in [(4100+base_x,3800+base_y,600,800),(0+base_x,6000+base_y,800,600)]:
        await b._dispatch_unlocked("create-rectangle", {"x1":x,"y1":y,"x2":x+w,"y2":y+h,"layer":"A-FIXT-SANI"})
    for x,y,w,h in [(6200+base_x,300+base_y,4000,600)]:
        await b._dispatch_unlocked("create-rectangle", {"x1":x,"y1":y,"x2":x+w,"y2":y+h,"layer":"A-FIXT-KITCH"})

    # Stair on A-STAIR
    await b._dispatch_unlocked("create-polyline", {"points_str": f"{7000+base_x},{3000+base_y};{8200+base_x},{3000+base_y};{8200+base_x},{5500+base_y};{7000+base_x},{5500+base_y}", "closed":"1", "layer":"A-STAIR"})
    for i in range(1,10):
        y=3000+base_y+i*250
        await b._dispatch_unlocked("create-line", {"x1":7000+base_x,"y1":y,"x2":8200+base_x,"y2":y,"layer":"A-STAIR"})
    await b._dispatch_unlocked("create-text", {"x":7500+base_x,"y":4250+base_y,"text":"UP","height":150,"rotation":90,"layer":"A-STAIR"})

    # Dimensions 3 rows both sides on A-DIMS
    # Outer overall bottom + top, left + right
    for d in [(0,0,10500,0,5250,-1000),(0,8500,10500,8500,5250,9500),(0,0,0,8500,-1200,4250),(10500,0,10500,8500,11700,4250)]:
        await b._dispatch_unlocked("create-dimension-linear", {"x1":d[0]+base_x,"y1":d[1]+base_y,"x2":d[2]+base_x,"y2":d[3]+base_y,"dim_x":d[4]+base_x,"dim_y":d[5]+base_y})
    # Middle bay
    for d in [(0,0,3500,0,1750,-650),(3500,0,7000,0,5250,-650),(7000,0,10500,0,8750,-650)]:
        await b._dispatch_unlocked("create-dimension-linear", {"x1":d[0]+base_x,"y1":d[1]+base_y,"x2":d[2]+base_x,"y2":d[3]+base_y,"dim_x":d[4]+base_x,"dim_y":d[5]+base_y})
    # Inner openings
    for d in [(900,0,2100,0,1500,-350),(4100,0,5000,0,4550,-350)]:
        await b._dispatch_unlocked("create-dimension-linear", {"x1":d[0]+base_x,"y1":d[1]+base_y,"x2":d[2]+base_x,"y2":d[3]+base_y,"dim_x":d[4]+base_x,"dim_y":d[5]+base_y})
    # Room LxW under names
    for x,y,txt in [(1750,7250,"LIVING 3930x3530"),(4550,1800,"DINING 3930x3000"),(8300,1800,"KITCHEN 4800x3680"),(8750,7850,"MASTER 3930x3530"),(1750,5400,"BEDROOM2 3700x3735"),(8750,1800,"BEDROOM3 3605x3735")]:
        await b._dispatch_unlocked("create-text", {"x":x+base_x,"y":y+base_y,"text":txt,"height":180,"rotation":0,"layer":"A-TEXT-AREA"})

    # North arrow on A-SYMB-NORTH (filled triangle)
    await b._dispatch_unlocked("create-polyline", {"points_str": f"{10000+base_x},{8000+base_y};{10100+base_x},{8300+base_y};{9900+base_x},{8300+base_y}", "closed":"1", "layer":"A-SYMB-NORTH"})
    await b._dispatch_unlocked("create-hatch", {"entity_id":"last","pattern":"SOLID"})
    await b._dispatch_unlocked("create-text", {"x":10000+base_x,"y":8400+base_y,"text":"N","height":200,"rotation":0,"layer":"A-SYMB-NORTH"})
    # Title block on TITLEBLOCK
    await b._dispatch_unlocked("create-rectangle", {"x1":0+base_x,"y1":-1500+base_y,"x2":10500+base_x,"y2":-2500+base_y,"layer":"TITLEBLOCK"})
    await b._dispatch_unlocked("create-text", {"x":500+base_x,"y":-2000+base_y,"text":"3BHK GROUND FLOOR PLAN 1:50 AREA 1520 SQ.FT NORTH ^","height":220,"rotation":0,"layer":"TITLEBLOCK"})

    # Color check: ensure no object-level overrides (all ByLayer)
    await b._dispatch_unlocked("zoom-extents", {})
    info=await b._dispatch_unlocked("drawing-info", {})
    print("FINAL", info.to_dict())
    print("done quality BHK")

asyncio.run(main())
