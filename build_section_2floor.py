"""2-Floor Building Section — typical residence, A3 1:50, NBC heights, at 0,60000"""
import asyncio, math, pathlib
from autocad_arch_mcp.backends.file_ipc_arch import FileIPCArchBackend

async def wall_section_rect(b, x, y, w, h, layer="A-WALL"):
    # Section wall as hatched rectangle: x,y bottom-left, w=230, h=storey height
    pts = f"{x},{y};{x+w},{y};{x+w},{y+h};{x},{y+h}"
    r = await b._dispatch_unlocked("create-polyline", {"points_str": pts, "closed":"1", "layer":layer})
    # hatch solid
    if r.ok:
        # get handle from payload string
        import json
        try:
            data = json.loads(r.payload) if isinstance(r.payload, str) else r.payload
            hdl = data.get('handle')
            if hdl:
                hr = await b._dispatch_unlocked("create-hatch", {"entity_id": hdl, "pattern":"SOLID"})
                # ignore hatch result
        except: pass
    return r

async def main():
    b = FileIPCArchBackend()
    await b.initialize()
    base_x, base_y = 0, 60000
    print(f"Section at {base_x},{base_y} 2 floors, NBC: GF 3000, FF 3000, plinth 450, parapet 1000")

    # Ground level
    # Foundation: 230 wall thick, depth 900, plinth 450
    # Section ground line
    await b._dispatch_unlocked("create-line", {"x1":base_x-2000,"y1":base_y,"x2":base_x+13000,"y2":base_y,"layer":"A-GRID"})
    # Ground floor walls: outer 230, height 3000
    # Left outer
    await wall_section_rect(b, base_x, base_y+450, 230, 3000, "A-WALL")
    # Right outer
    await wall_section_rect(b, base_x+10500-230, base_y+450, 230, 3000, "A-WALL")
    # Internal wall at 3500
    await wall_section_rect(b, base_x+3500, base_y+450, 115, 3000, "A-WALL-PART")
    # First floor slab: 150 thick, 10500 wide
    await wall_section_rect(b, base_x, base_y+3450, 10500, 150, "A-WALL")
    # First floor walls height 3000
    await wall_section_rect(b, base_x, base_y+3600, 230, 3000, "A-WALL")
    await wall_section_rect(b, base_x+10500-230, base_y+3600, 230, 3000, "A-WALL")
    await wall_section_rect(b, base_x+3500, base_y+3600, 115, 3000, "A-WALL-PART")
    # Roof slab + parapet 1000
    await wall_section_rect(b, base_x, base_y+6600, 10500, 150, "A-WALL")
    await wall_section_rect(b, base_x, base_y+6750, 230, 1000, "A-WALL")
    await wall_section_rect(b, base_x+10500-230, base_y+6750, 230, 1000, "A-WALL")
    # Floor lines & level markers
    levels = [(base_y,"±0.000 GFL"), (base_y+450,"+0.450 PLINTH"), (base_y+3450,"+3.450 FFL FF"), (base_y+6600,"+6.600 ROOF"), (base_y+7750,"+7.750 PARAPET")]
    for y, label in levels:
        # level line
        await b._dispatch_unlocked("create-line", {"x1":base_x-500,"y1":y,"x2":base_x+11000,"y2":y,"layer":"A-GRID"})
        # level text
        await b._dispatch_unlocked("create-text", {"x":base_x+11200,"y":y,"text":label,"height":180,"rotation":0,"layer":"A-TEXT"})
        # tick
        await b._dispatch_unlocked("create-polyline", {"points_str":f"{base_x-500},{y};{base_x-300},{y+100};{base_x-300},{y-100}","closed":"1","layer":"A-DIMS"})

    # Stair in section: 900 wide flight, tread 250 riser 175, 17 risers to 3000
    # Show as sawtooth
    sx = base_x+7000
    sy = base_y+450
    pts = []
    for i in range(18):
        x = sx + i*70
        y = sy + i*175
        pts.append(f"{x},{y}")
        if i>0:
            # horizontal tread
            pass
    # Stair polyline sawtooth
    stair_pts = []
    for i in range(13):
        x = sx + i*70
        y = sy + i*175
        stair_pts.append(f"{x},{y}")
        stair_pts.append(f"{x+70},{y}")
        stair_pts.append(f"{x+70},{y+175}")
    # Simplify: just draw stair outline as polyline
    stair_str = ";".join(stair_pts[:6])  # first few
    # Instead draw full stair as lines
    for i in range(12):
        x = sx + i*70
        y = sy + i*175
        await b._dispatch_unlocked("create-line", {"x1":x,"y1":y,"x2":x+70,"y2":y,"layer":"A-STAIR"})
        await b._dispatch_unlocked("create-line", {"x1":x+70,"y1":y,"x2":x+70,"y2":y+175,"layer":"A-STAIR"})
    await b._dispatch_unlocked("create-text", {"x":sx+200,"y":sy+800,"text":"UP","height":200,"rotation":0,"layer":"A-STAIR"})
    # Window/door symbols in section
    # Ground floor window at mid
    await b._dispatch_unlocked("create-rectangle", {"x1":base_x+2000,"y1":base_y+1000,"x2":base_x+3500,"y2":base_y+2200,"layer":"A-WINDOW"})
    await b._dispatch_unlocked("create-rectangle", {"x1":base_x+7000,"y1":base_y+4150,"x2":base_x+8200,"y2":base_y+6350,"layer":"A-WINDOW"})

    # Dimensions on section: vertical storey heights on right
    # Overall height 7750
    await b._dispatch_unlocked("create-dimension-linear", {"x1":base_x+10500,"y1":base_y,"x2":base_x+10500,"y2":base_y+7750,"dim_x":base_x+11500,"dim_y":base_y+3875})
    # Floor to floor 3000 each
    await b._dispatch_unlocked("create-dimension-linear", {"x1":base_x+10500,"y1":base_y+450,"x2":base_x+10500,"y2":base_y+3450,"dim_x":base_x+11200,"dim_y":base_y+1950})
    await b._dispatch_unlocked("create-dimension-linear", {"x1":base_x+10500,"y1":base_y+3600,"x2":base_x+10500,"y2":base_y+6600,"dim_x":base_x+11200,"dim_y":base_y+5100})

    # Section title + hatch legend
    await b._dispatch_unlocked("create-text", {"x":base_x,"y":base_y-1000,"text":"SECTION A-A  1:50  SCALE","height":250,"rotation":0,"layer":"TITLEBLOCK"})
    await b._dispatch_unlocked("create-text", {"x":base_x,"y":base_y-1500,"text":"TYPICAL 2-STOREY RESIDENCE  WALL 230/115  FLOOR 3000  PARAPET 1000","height":180,"rotation":0,"layer":"A-TEXT"})

    # Section wall hatching (already solid via create-hatch, but also add ANSI31 for inner)
    # North arrow not needed in section — keep title

    await b._dispatch_unlocked("zoom-extents", {})
    info = await b._dispatch_unlocked("drawing-info", {})
    print("SECTION FINAL", info.to_dict())
    print("done section")

asyncio.run(main())
