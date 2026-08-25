"""Build 3BHK 2-floor 10.5x8.5 1:100 + 1:5 footing DIRECTLY IN LIVE AutoCAD 2021 via file_ipc."""
import asyncio
import sys
sys.path.insert(0, r"D:\6) Obsidian\AI Workspace\Tools\autocad-arch-mcp\src")
from autocad_arch_mcp.backends.file_ipc_arch import FileIPCArchBackend

async def build_live():
    b = FileIPCArchBackend()
    print("Init", (await b.initialize()).to_dict())
    print("Status", (await b.status()).to_dict())
    # Purge and setup - use drawing_create via file_ipc (erase all)
    print("Drawing create (erase all)...")
    # Use nbc_drawing create via dispatch
    r = await b._dispatch("drawing-create", {})
    print("drawing-create", r.to_dict())
    # Setup layers via ezdxf? For live, we need to ensure layers exist via LISP
    # Create Hama triad layers via file_ipc layer-create
    for name, color, ltype, lw in [
        ("A-WALL-230","4","Continuous","0.50"), ("A-WALL-115","3","Continuous","0.50"),
        ("A-GRID","6","CENTER","0.25"), ("A-DIM","2","Continuous","0.18"),
        ("A-ANNO-TEXT","7","Continuous","0.18"), ("A-STRS","2","Continuous","0.35"),
        ("A-WALL-PATT","7","Continuous","0.13"), ("A-SECT-HATCH","7","Continuous","0.13"),
        ("G-TTLB","7","Continuous","0.35"), ("V-PORT","7","Continuous","0.13"),
    ]:
        r = await b._dispatch("layer-create", {"name": name, "color": color, "linetype": ltype, "lineweight": lw})
        print(f"layer {name}", r.to_dict())

    W, H = 10500, 8500
    off = 15000
    base_y = 30000

    # Ground floor outer 230
    print("Ground outer...")
    for pts in [[[0,0],[W,0],[W,H],[0,H]]]:
        r = await b._dispatch("create-polyline", {"points_str": ";".join(f"{x},{y}" for x,y in pts), "closed":"1", "layer":"A-WALL-230"})
        print("poly", r.to_dict())
    # Ground inner 115
    for pts in [[[3500,0],[3500,3000]], [[7000,0],[7000,3000]], [[0,3000],[3500,3000]]]:
        s = ";".join(f"{x},{y}" for x,y in pts)
        r = await b._dispatch("create-polyline", {"points_str": s, "closed":"0", "layer":"A-WALL-115"})
        print("inner", r.to_dict())
    # Grid ground
    for x in [0,3500,7000,10500]:
        r = await b._dispatch("create-line", {"x1":x,"y1":0,"x2":x,"y2":H,"layer":"A-GRID"})
        print("grid x", r.to_dict())
    for y in [0,3000,5500,8500]:
        r = await b._dispatch("create-line", {"x1":0,"y1":y,"x2":W,"y2":y,"layer":"A-GRID"})
        print("grid y", r.to_dict())
    # First floor at off
    print("First floor...")
    r = await b._dispatch("create-polyline", {"points_str": f"0,{off};{W},{off};{W},{off+H};0,{off+H}", "closed":"1", "layer":"A-WALL-230"})
    print("FF outer", r.to_dict())
    for pts in [[[3500,off],[3500,off+3000]], [[7000,off],[7000,off+3000]]]:
        s = ";".join(f"{x},{y}" for x,y in pts)
        await b._dispatch("create-polyline", {"points_str": s, "closed":"0", "layer":"A-WALL-115"})
    # Stair
    print("Stair...")
    await b._dispatch("create-polyline", {"points_str": "7000,3000;8200,3000;8200,5500;7000,5500", "closed":"1", "layer":"A-STRS"})
    await b._dispatch("create-polyline", {"points_str": f"7000,{off+3000};8200,{off+3000};8200,{off+5500};7000,{off+5500}", "closed":"1", "layer":"A-STRS"})
    # Wall footing detail at base_y
    print("Wall footing 1:5...")
    await b._dispatch("create-polyline", {"points_str": f"0,{base_y};500,{base_y};500,{base_y-900};0,{base_y-900}", "closed":"1", "layer":"A-WALL"})
    # Hatch would need entity handle, use create-hatch on last
    r = await b._dispatch("create-hatch", {"entity_id":"last","pattern":"AR-BRSTD"})
    print("hatch BRSTD", r.to_dict())
    await b._dispatch("create-polyline", {"points_str": f"0,{base_y-900};600,{base_y-900};600,{base_y-1100};0,{base_y-1100}", "closed":"1", "layer":"A-SECT"})
    r = await b._dispatch("create-hatch", {"entity_id":"last","pattern":"AR-CONC"})
    print("hatch CONC", r.to_dict())
    await b._dispatch("create-text", {"x":700,"y":base_y+200,"text":"±0.000 FFL","height":125,"layer":"A-ANNO-TEXT"})
    await b._dispatch("create-text", {"x":700,"y":base_y-1100,"text":"-0.900 FOUNDATION","height":125,"layer":"A-ANNO-TEXT"})
    # Levels and title
    await b._dispatch("create-text", {"x":5250,"y":-2000,"text":"3BHK GF 10.5x8.5 1:100 Hama Gold","height":250,"layer":"A-ANNO-TEXT"})
    await b._dispatch("create-text", {"x":5250,"y":off-2000,"text":"3BHK FF 10.5x8.5 1:100","height":250,"layer":"A-ANNO-TEXT"})
    # Zoom
    print("Zoom extents...")
    await b._dispatch("zoom-extents", {})
    # Screenshot
    r = await b._dispatch("get_screenshot", {})
    print("screenshot", r.to_dict().get("ok"))
    # Save
    r = await b._dispatch("drawing-save", {"path": r"D:\6) Obsidian\AI Workspace\Tools\autocad-arch-mcp\3bhk_2floor_live.dwg"})
    print("save", r.to_dict())

if __name__ == "__main__":
    asyncio.run(build_live())
