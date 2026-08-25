"""Build 3BHK 1-floor 10.5x8.5 1:100 in current Drawing3.dwg - LIVE additive, no erase."""
import asyncio, sys
sys.path.insert(0, r"D:\6) Obsidian\AI Workspace\Tools\autocad-arch-mcp\src")
from autocad_arch_mcp.backends.file_ipc_arch import FileIPCArchBackend
from autocad_arch_mcp.rag.hama_store import hama_retrieve

print("Hama gold", hama_retrieve("3BHK 1-floor 10.5x8.5 1:100 plan Hama Architecture 77 layers", k=1)[0]["id"])

async def build():
    b = FileIPCArchBackend()
    await b.initialize()
    info = await b._dispatch('drawing-info', {})
    print("Before", info.to_dict() if hasattr(info,'to_dict') else info)
    cnt = await b._dispatch('entity-count', {})
    c = cnt.payload.get('count',0) if isinstance(cnt.payload, dict) else cnt.payload
    print("Count before", c)
    # Offset to avoid overlap if count>5, else at 0,0
    try:
        c_int = int(c)
    except:
        c_int = 0
    ox = 30000 if c_int and c_int > 5 else 0
    print(f"Building at ox={ox}")
    W, H = 10500, 8500
    # Ensure triad layers
    for name, color, ltype, lw in [("A-WALL-230","4","Continuous","0.50"),("A-WALL-115","3","Continuous","0.50"),("A-GRID","6","CENTER","0.25"),("A-DIM","2","Continuous","0.18"),("A-ANNO-TEXT","7","Continuous","0.18"),("A-STRS","2","Continuous","0.35"),("A-DOOR","1","Continuous","0.50"),("A-WIND","5","Continuous","0.50")]:
        await b._dispatch("layer-create", {"name": name, "color": color, "linetype": ltype, "lineweight": lw})
    # Outer 230
    r = await b._dispatch("create-polyline", {"points_str": f"{ox},0;{ox+W},0;{ox+W},{H};{ox},{H}", "closed":"1", "layer":"A-WALL-230"})
    print("outer", r.to_dict())
    # Inner 115 partitions
    for a,b_ in [((3500,0),(3500,3000)), ((7000,0),(7000,3000)), ((0,3000),(3500,3000)), ((3500,3000),(3500,5500)), ((7000,3000),(7000,5500)), ((7000,5500),(10500,5500))]:
        s = f"{ox+a[0]},{a[1]};{ox+b_[0]},{b_[1]}"
        r = await b._dispatch("create-polyline", {"points_str": s, "closed":"0", "layer":"A-WALL-115"})
        print("inner", r.to_dict())
    # Grid
    for x in [0,3500,7000,10500]:
        await b._dispatch("create-line", {"x1":ox+x,"y1":0,"x2":ox+x,"y2":H,"layer":"A-GRID"})
    for y in [0,3000,5500,8500]:
        await b._dispatch("create-line", {"x1":ox,"y1":y,"x2":ox+W,"y2":y,"layer":"A-GRID"})
    print("grid done")
    # Doors as arcs
    for x,y in [(ox+900,0),(ox,4100),(ox+9100,4100)]:
        r = await b._dispatch("create-arc", {"cx":x,"cy":y,"radius":900,"start_angle":0,"end_angle":90,"layer":"A-DOOR"})
        print("door", r.to_dict())
    # Windows
    for x,y,w in [(ox+1750,8500,1800),(ox,1500,1500),(ox+9100,1500,1500)]:
        # Represent as rectangle on A-WIND
        await b._dispatch("create-polyline", {"points_str": f"{x},{y};{x+w},{y};{x+w},{y+120};{x},{y+120}", "closed":"1", "layer":"A-WIND"})
    print("windows done")
    # Stair
    await b._dispatch("create-polyline", {"points_str": f"{ox+7000},3000;{ox+8200},3000;{ox+8200},5500;{ox+7000},5500", "closed":"1", "layer":"A-STRS"})
    print("stair done")
    # Labels
    await b._dispatch("create-text", {"x":ox+5250,"y":-1200,"text":"3BHK 10.5x8.5 1:100 LIVE Drawing3 Hama triad","height":250,"layer":"A-ANNO-TEXT"})
    print("label done")
    # Dimensions 3-layer simplified
    await b._dispatch("create-dimension-linear", {"x1":ox,"y1":H,"x2":ox+W,"y2":H,"dim_x":ox+5250,"dim_y":H+800,"layer":"A-DIM"})
    print("dim done")
    await b._dispatch("zoom-extents", {})
    print("zoom done")
    cnt2 = await b._dispatch('entity-count', {})
    print("Count after", cnt2.to_dict() if hasattr(cnt2,'to_dict') else cnt2)
    # Save to Drawing3's current file + backup
    r = await b._dispatch('drawing-save', {'path': 'C:/Temp/Drawing3_3BHK_1floor.dwg'})
    print("save", r.to_dict() if hasattr(r,'to_dict') else r)

if __name__ == "__main__":
    asyncio.run(build())
