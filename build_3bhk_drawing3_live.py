"""Build 3BHK plan 10.5x8.5 1:100 directly in current Drawing3.dwg (no erase, proper MCP)."""
import asyncio, sys
sys.path.insert(0, r"D:\6) Obsidian\AI Workspace\Tools\autocad-arch-mcp\src")
from autocad_arch_mcp.backends.file_ipc_arch import FileIPCArchBackend
from autocad_arch_mcp.rag.hama_store import hama_retrieve

# Hama gold every-run teaching
gold = hama_retrieve("3BHK 10.5x8.5 1:100 plan municipal Hama Architecture", k=1)
print("Hama gold", gold[0]["id"], gold[0]["score"])

async def build():
    b = FileIPCArchBackend()
    await b.initialize()
    info = await b._dispatch('drawing-info', {})
    print("Current Drawing3 info", info.to_dict() if hasattr(info,'to_dict') else info)
    # Do NOT erase - build additively at 0,0 (check if entities already exist, use offset if needed)
    # Check existing count to avoid overlap - if >0, offset new plan to x=30000
    cnt = await b._dispatch('entity-count', {})
    c = cnt.payload.get('count',0) if isinstance(cnt.payload, dict) else cnt.payload
    print("Existing count", c)
    ox = 30000 if c and int(c) > 5 else 0
    print(f"Building 3BHK at offset x={ox} in Drawing3.dwg (no erase)")
    W, H = 10500, 8500
    # Ensure layers triad
    for name, color, ltype, lw in [("A-WALL-230","4","Continuous","0.50"),("A-WALL-115","3","Continuous","0.50"),("A-GRID","6","CENTER","0.25"),("A-DIM","2","Continuous","0.18"),("A-ANNO-TEXT","7","Continuous","0.18"),("A-STRS","2","Continuous","0.35")]:
        await b._dispatch("layer-create", {"name": name, "color": color, "linetype": ltype, "lineweight": lw})
    # Outer 230
    pts = f"{ox},0;{ox+W},0;{ox+W},{H};{ox},{H}"
    r = await b._dispatch("create-polyline", {"points_str": pts, "closed":"1", "layer":"A-WALL-230"})
    print("outer", r.to_dict())
    # Inner 115
    for a,b_ in [((3500,0),(3500,3000)), ((7000,0),(7000,3000)), ((0,3000),(3500,3000)), ((3500,3000),(3500,5500)), ((7000,3000),(7000,5500)), ((7000,5500),(10500,5500))]:
        s = f"{ox+a[0]},{a[1]};{ox+b_[0]},{b_[1]}"
        await b._dispatch("create-polyline", {"points_str": s, "closed":"0", "layer":"A-WALL-115"})
    # Grid
    for x in [0,3500,7000,10500]:
        await b._dispatch("create-line", {"x1":ox+x,"y1":0,"x2":ox+x,"y2":H,"layer":"A-GRID"})
    for y in [0,3000,5500,8500]:
        await b._dispatch("create-line", {"x1":ox,"y1":y,"x2":ox+W,"y2":y,"layer":"A-GRID"})
    # Doors D1 1200 main at 900,0
    await b._dispatch("create-arc", {"cx":ox+900,"cy":0,"radius":900,"start_angle":0,"end_angle":90,"layer":"A-DOOR"})
    # Stair 1200x3000 at 7000,3000
    await b._dispatch("create-polyline", {"points_str": f"{ox+7000},3000;{ox+8200},3000;{ox+8200},5500;{ox+7000},5500", "closed":"1", "layer":"A-STRS"})
    # Labels
    await b._dispatch("create-text", {"x":ox+5250,"y":-1200,"text":"3BHK 10.5x8.5 1:100 Hama triad A-WALL-230 4/0.50","height":250,"layer":"A-ANNO-TEXT"})
    # Dimensions 3-layer (simplified)
    await b._dispatch("create-dimension-linear", {"x1":ox,"y1":H,"x2":ox+W,"y2":H,"dim_x":ox+5250,"dim_y":H+800,"layer":"A-DIM"})
    # Zoom
    await b._dispatch("zoom-extents", {})
    # Count
    cnt2 = await b._dispatch('entity-count', {})
    print("After count", cnt2.to_dict() if hasattr(cnt2,'to_dict') else cnt2)
    # Save Drawing3.dwg to temp for backup
    r = await b._dispatch('drawing-save', {'path': 'C:/Temp/Drawing3_3BHK.dwg'})
    print("save", r.to_dict() if hasattr(r,'to_dict') else r)

if __name__ == "__main__":
    asyncio.run(build())
