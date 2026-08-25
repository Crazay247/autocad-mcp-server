"""Build 3BHK municipal plan in AutoCAD via file_ipc_arch — fallback to ezdxf not needed."""
import asyncio, sys, traceback
from pathlib import Path

# Ensure src on path for editable not needed, but keep
sys.path.insert(0, str(Path(__file__).parent / "src"))

from autocad_arch_mcp.backends.file_ipc_arch import FileIPCArchBackend

async def build():
    b = FileIPCArchBackend()
    await b.initialize()
    print(f"Backend {b.name} hwnd={b._hwnd} ipc={b._ipc_dir}")

    # Helper with retry on timeout
    async def send(cmd, params, retries=1):
        for attempt in range(retries+1):
            r = await b._dispatch_unlocked(cmd, params)
            if r.ok:
                print(f"  OK {cmd}: {r.payload}")
                return r
            else:
                print(f"  FAIL {cmd} attempt {attempt}: {r.error}")
                if attempt < retries:
                    await asyncio.sleep(0.5)
                    continue
                return r

    # Phase 0 — create_new (we already have rectangle, but redo clean)
    print("\nPhase 0: create_new + setup")
    # Instead of create_new which does erase+purge, we do drawing-create
    await send("drawing-create", {})
    # Create needed layers explicitly (in case setup_nbc_standards not via IPC)
    layers = ["A-WALL-230","A-WALL-115","A-DOOR","A-WIN","A-DIM-1","A-DIM-2","A-DIM-3","A-GRID","A-ANNO-TEXT","A-FURN","A-STRS","G-TTLB","A-NORTH"]
    for lyr in layers:
        await send("layer-create", {"name": lyr, "color": "white", "linetype": "CONTINUOUS"})

    # Check info
    info = await send("drawing-info", {})
    print("info after setup", info.to_dict() if info else "none")

    # Phase 1 — Outer rectangle 10500x8500 (already have 9000x7000, now correct to 10500x8500)
    print("\nPhase 1: Outer + inner walls")
    # Outer 230
    outer = [(0,0,10500,0),(10500,0,10500,8500),(10500,8500,0,8500),(0,8500,0,0)]
    for x1,y1,x2,y2 in outer:
        await send("create-line", {"x1":x1,"y1":y1,"x2":x2,"y2":y2,"layer":"A-WALL-230"})
    # Inner 115
    inner = [
        (3500,0,3500,3000),
        (7000,0,7000,3000),
        (0,3000,3500,3000),
        (0,3000,0,5500),
        (3500,3000,3500,5500),
        (3500,5500,5250,5500),
        (7000,3000,7000,5500),
        (7000,5500,10500,5500),
        # Living/kitchen divider already done
        # Bedroom partitions etc.
    ]
    for x1,y1,x2,y2 in inner:
        await send("create-line", {"x1":x1,"y1":y1,"x2":x2,"y2":y2,"layer":"A-WALL-115"})

    # Grid lines on A-GRID (center)
    grids = [
        (0,0,0,8500, "A-GRID"), (3500,0,3500,8500,"A-GRID"), (7000,0,7000,8500,"A-GRID"), (10500,0,10500,8500,"A-GRID"),
        (0,0,10500,0,"A-GRID"), (0,3000,10500,3000,"A-GRID"), (0,5500,10500,5500,"A-GRID"), (0,8500,10500,8500,"A-GRID"),
    ]
    for x1,y1,x2,y2,lyr in grids:
        await send("create-line", {"x1":x1,"y1":y1,"x2":x2,"y2":y2,"layer":lyr})

    # Phase 5 — Room labels (before dimensions so they don't overlap)
    print("\nPhase 5: Labels")
    labels = [
        (1750,7000, "LIVING 21.5 m2"),
        (4550,1500, "DINING 10.8 m2"),
        (8300,1500, "KITCHEN 14.1 m2"),
        (8750,7000, "MASTER BEDROOM 14.0 m2"),
        (1750,4250, "BEDROOM 2 10.5 m2"),
        (8750,1500, "BEDROOM 3 10.5 m2"),
        (4375,4250, "BATH 1 4.3 m2"),
        (1750,6250, "BATH 2 3.9 m2"),
        (7600,4250, "STAIR UP"),
    ]
    for x,y,txt in labels:
        await send("create-text", {"x":x,"y":y,"text":txt,"height":125,"rotation":0,"layer":"A-ANNO-TEXT"})
    # Door/window tags small
    tags = [
        (900,200, "D1 1200"), (4100,200, "D4 900"), (200,4100, "D2 900"), (9100,200, "D2 900"), (9100,4100, "D2 900"),
        (4100,4750, "D3 750"), (200,6500, "D3 750"),
        (2650,8300, "W1 1800"), (750,1500, "W2 1500"), (9100,1300, "W2 1500"), (10300,6500, "W2 1500"),
        (3700,8300, "W3 900"), (4950,8300, "W3 900"),
    ]
    for x,y,txt in tags:
        await send("create-text", {"x":x,"y":y,"text":txt,"height":100,"rotation":0,"layer":"A-ANNO-TEXT"})

    # Phase 2 simplified doors — represent as gaps: we already have walls, add door swing arcs (approx)
    print("\nPhase 2: Door swings (A-DOOR)")
    # Door swings as arcs: use create-arc where possible, else line
    # Simple: D1 at (900,0) main entry swing inside
    # We'll create arc with center at hinge, radius = width
    doors = [
        (900,0,1200), # D1 bottom wall hinge at 900, width 1200 swinging in (north)
        (0,4100,900), # D2 left wall
        (9100,0,900), # D2 bottom of bedroom3
        (9100,4100,900), # D2 master
        (4100,4750,750), # D3 bath
        (0,6500,750), # D3 bath2
        (4100,0,900), # D4 kitchen
    ]
    for x,y,w in doors:
        # Door line on A-DOOR, swing arc
        await send("create-arc", {"cx":x,"cy":y,"radius":w,"start_angle":0,"end_angle":90,"layer":"A-DOOR"})

    # Windows on A-WIN: sill lines
    windows = [
        (1750,8500,1800), # W1
        (0,1500,1500), # W2 left
        (9100,1500,1500), # W2 bottom
        (10500,6500,1500), # W2 right (vertical)
        (3500,8500,900), # W3
        (4750,8500,900), # W3
    ]
    for x,y,w in windows:
        await send("create-line", {"x1":x,"y1":y,"x2":x+w,"y2":y,"layer":"A-WIN"})

    # Phase 3 stair: simple polyline representation for stair
    print("\nPhase 3: Stair")
    # Stair outline 1200 wide (7000..8200)
    await send("create-polyline", {"points_str":"7000,3000;8200,3000;8200,5500;7000,5500","closed":"1","layer":"A-STRS"})
    # Treads: 16 risers ~250 tread? height 2500 span 4000? Simplify 10 treads
    for i in range(1,10):
        y = 3000 + i*250
        await send("create-line", {"x1":7000,"y1":y,"x2":8200,"y2":y,"layer":"A-STRS"})
    # Arrow
    await send("create-text", {"x":7500,"y":4250,"text":"UP","height":150,"rotation":90,"layer":"A-STRS"})

    # Furniture fallback rectangles on A-FURN
    print("\nPhase 4: Furniture")
    furn = [
        # Living sofa
        (200,5700,2200,900),
        # Dining table 1800x900
        (3850,1050,1800,900),
        # Kitchen counter L
        (6200,300,4000,600), (9600,300,600,2700),
        # Master bed 1800x2000
        (7500,6000,1800,2000),
        # Wardrobes 600 deep
        (9900,6000,600,2000), (100,3400,600,1800), (9200,100,600,2100),
        # Bedroom beds 1500x2000
        (400,3500,1500,2000), (7500,500,1500,2000),
        # Bath fixtures: WC
        (4000,4000,600,800),
    ]
    for x,y,w,h in furn:
        await send("create-rectangle", {"x1":x,"y1":y,"x2":x+w,"y2":y+h,"layer":"A-FURN"})

    # Zoom
    print("\nZoom extents")
    await send("zoom-extents", {})
    info2 = await send("drawing-info", {})
    print("FINAL info", info2.to_dict() if info2 else "none")
    lst = await send("entity-list", {})
    print("entities count", len(lst.payload["entities"]) if lst and lst.ok else "fail")
    print("Done")

if __name__ == "__main__":
    asyncio.run(build())
