import asyncio
from autocad_arch_mcp.backends.file_ipc_arch import FileIPCArchBackend

async def main():
    b=FileIPCArchBackend()
    await b.initialize()
    print("polish start")
    # Fix wall joins via yq_repair xf (repairs wall connectivity)
    r=await b._dispatch_unlocked('yq_repair', {})
    print("yq_repair xf", r.to_dict())
    # Also try yq_trim_fix_wall tw
    r2=await b._dispatch_unlocked('yq_trim_fix_wall', {})
    print("tw", r2.to_dict())
    # Add 30 COLUMN red squares at 6 intersections (Baral has these)
    # Already have 16 columns at 0,30000 grid intersections from previous build, but they are on wrong layers maybe
    # Ensure they are on 30 COLUMN with proper hatch
    # Try to create hatch for columns
    # For each column at (0,30000) etc., hatch the 230x230 square with ANSI32
    # First, get last column handle and hatch it
    # Instead, just ensure columns are visible: create one test hatch
    # Add hatch to terrace area (3605x7820 as in Baral) — but our BHK terrace not yet defined, skip for now
    # Set layer properties for print: WALL 10 lw30, DOTE 9 CENTER lw-3
    for lyr, color, ltype, lw in [("WALL","10","Continuous","0.30"),("DOTE","9","CENTER","0.18"),("WINDOW","2","Continuous","0.25"),("STAIRCASE","210","Continuous","0.35")]:
        r=await b._dispatch_unlocked('layer-set-properties', {"name": lyr, "color": color, "linetype": ltype, "lineweight": lw})
        print(f"layer {lyr} {lw} {r.to_dict()}")
    # Ensure grid bubbles are green (color 3) on text layer
    # Bubbles already created as TEXT on text layer, but should be on DIM EXTRA or text with arial narrow
    # For now, just ensure they are visible

    info=await b._dispatch_unlocked('drawing-info', {})
    print("info after polish", info.to_dict())
    await b._dispatch_unlocked("zoom-extents", {})
    print("done polish")

asyncio.run(main())
