import asyncio, math
from autocad_arch_mcp.backends.file_ipc_arch import FileIPCArchBackend

async def wall_rect(b, x1,y1,x2,y2, thick, layer="WALL"):
    dx=x2-x1; dy=y2-y1; l=math.hypot(dx,dy)
    if l==0: return None
    ux=-dy/l; uy=dx/l; ox=ux*thick/2; oy=uy*thick/2
    p1=(x1+ox,y1+oy); p2=(x2+ox,y2+oy); p3=(x2-ox,y2-oy); p4=(x1-ox,y1-oy)
    pts = "{},{:.1f};{},{:.1f};{},{:.1f};{},{:.1f}".format(p1[0],p1[1],p2[0],p2[1],p3[0],p3[1],p4[0],p4[1])
    # Use format to avoid f-string brace issues in PowerShell
    pts2 = str(p1[0])+","+str(p1[1])+";"+str(p2[0])+","+str(p2[1])+";"+str(p3[0])+","+str(p3[1])+";"+str(p4[0])+","+str(p4[1])
    # Use simple
    return await b._dispatch_unlocked("create-polyline", {"points_str": pts2, "closed":"1", "layer":layer})

async def main():
    b=FileIPCArchBackend()
    await b.initialize()
    print("rebuild start hwnd", b._hwnd)
    base_x, base_y = 0, 15000
    def off(x,y): return (x+base_x, y+base_y)
    for seg in [(0,0,10500,0),(10500,0,10500,8500),(10500,8500,0,8500),(0,8500,0,0)]:
        x1,y1,x2,y2 = seg
        x1,y1 = off(x1,y1); x2,y2 = off(x2,y2)
        r=await wall_rect(b, x1,y1,x2,y2, 230, "WALL")
        print("outer", seg, r.to_dict() if r else "none")
    inner=[(3500,0,3500,3000),(7000,0,7000,3000),(0,3000,3500,3000),(0,3000,0,5500),(3500,3000,3500,5500),(3500,5500,5250,5500),(7000,3000,7000,5500),(7000,5500,10500,5500)]
    for seg in inner:
        x1,y1,x2,y2 = seg
        x1,y1 = off(x1,y1); x2,y2 = off(x2,y2)
        r=await wall_rect(b, x1,y1,x2,y2, 115, "WALL")
        print("inner", seg, r.to_dict() if r else "none")
    for x,y,txt in [(1750,7000,"LIVING 21.5 m2"),(4550,1500,"DINING 10.8 m2"),(8300,1500,"KITCHEN 14.1 m2"),(8750,7000,"MASTER BEDROOM 14.0 m2")]:
        x,y = off(x,y)
        r=await b._dispatch_unlocked("create-text", {"x":x,"y":y,"text":txt,"height":125,"rotation":0,"layer":"text"})
        print("label", txt, r.to_dict())
    for x,y,w,typ in [(900,0,1200,"AD2"),(4100,0,900,"AD1"),(0,4100,900,"AD1"),(9100,0,900,"AD1")]:
        x,y = off(x,y)
        r=await b._dispatch_unlocked("create-arc", {"cx":x,"cy":y,"radius":w,"start_angle":0,"end_angle":90,"layer":"WINDOW"})
        print("door", typ, x,y, r.to_dict())
    for seg in [(0,0,0,8500),(3500,0,3500,8500),(7000,0,7000,8500),(10500,0,10500,8500),(0,0,10500,0),(0,3000,10500,3000),(0,5500,10500,5500),(0,8500,10500,8500)]:
        x1,y1,x2,y2 = seg
        x1,y1 = off(x1,y1); x2,y2 = off(x2,y2)
        r=await b._dispatch_unlocked("create-line", {"x1":x1,"y1":y1,"x2":x2,"y2":y2,"layer":"DOTE"})
        print("grid", r.to_dict())
    for d in [(0,0,10500,0,5250,-800),(0,0,0,8500,-800,4250)]:
        x1,y1,x2,y2,dx,dy = d
        x1+=base_x; y1+=base_y; x2+=base_x; y2+=base_y; dx+=base_x; dy+=base_y
        r=await b._dispatch_unlocked("create-dimension-linear", {"x1":x1,"y1":y1,"x2":x2,"y2":y2,"dim_x":dx,"dim_y":dy})
        print("dim", r.to_dict())
    await b._dispatch_unlocked("zoom-extents", {})
    info=await b._dispatch_unlocked("drawing-info", {})
    print("FINAL", info.to_dict())
    print("done rebuild")

asyncio.run(main())
