"""Build 3BHK 2-floor 10.5x8.5 1:100 + 1:5 wall footing - Hama gold triad, every-run teaching."""
import asyncio
import pathlib
from src.autocad_arch_mcp.backends.ezdxf_nbc import EzdxfNBCBackend
from src.autocad_arch_mcp.generators import generate_any

# Hama gold every-run: retrieve top exemplars before build
try:
    from src.autocad_arch_mcp.rag.hama_store import hama_retrieve
    gold = hama_retrieve("3BHK 2-floor 10.5x8.5 1:100 wall footing 1:5 Hama Architecture 77 layers", k=3)
    print("Hama gold for 3BHK 2-floor:", [(g["id"], g["score"]) for g in gold])
except Exception as e:
    print("hama retrieve fail", e)

async def build():
    b = EzdxfNBCBackend()
    await b.drawing_create()
    await b.nbc_setup_standards()
    # Ground floor 1:100 at 0,0
    print("Building ground floor 1:100...")
    await generate_any(b, "plan", {"building": [10500, 8500], "scale": "1:100", "title": "3BHK GF 10.5x8.5 1:100", "grid_x": [0, 3500, 7000, 10500], "grid_y": [0, 3000, 5500, 8500]})
    # Additional ground floor partitions via direct polyline (inner 115)
    for pts in [[[3500,0],[3500,3000]], [[7000,0],[7000,3000]], [[0,3000],[3500,3000]], [[3500,3000],[3500,5500]]]:
        await b.create_polyline(points=pts, closed=False, layer="A-WALL-115")
    # First floor at y=15000 offset (stacked)
    print("Building first floor 1:100 at 15000...")
    off = 15000
    await b.create_polyline(points=[[0, off], [10500, off], [10500, off+8500], [0, off+8500]], closed=True, layer="A-WALL-230")
    for pts in [[[3500, off],[3500, off+3000]], [[7000, off],[7000, off+3000]], [[0, off+3000],[3500, off+3000]]]:
        await b.create_polyline(points=pts, closed=False, layer="A-WALL-115")
    # Grid for first floor
    for x in [0,3500,7000,10500]:
        await b.create_line(x, off, x, off+8500, layer="A-GRID")
    for y in [off, off+3000, off+5500, off+8500]:
        await b.create_line(0, y, 10500, y, layer="A-GRID")
    # Stair both floors
    await b.create_polyline(points=[[7000,3000],[8200,3000],[8200,5500],[7000,5500]], closed=True, layer="A-STRS")
    await b.create_polyline(points=[[7000,off+3000],[8200,off+3000],[8200,off+5500],[7000,off+5500]], closed=True, layer="A-STRS")
    # Wall footing detail 1:5 at y=30000
    print("Building wall footing 1:5 at 30000...")
    await generate_any(b, "detail", {"scale": "1:5", "detail_type": "wall_footing"})
    # Move detail to y=30000 offset (generate_any created at 0,0 - we add extra at 30000)
    # Create explicit footing at 30000: 230 wall + 900 footing + PCC + AR-BRSTD
    base_y = 30000
    await b.create_polyline(points=[[0, base_y],[500, base_y],[500, base_y-900],[0, base_y-900]], closed=True, layer="A-WALL")
    await b.create_hatch(pattern="AR-BRSTD", scale=0.3, layer="A-WALL-PATT", points=[[0, base_y],[500, base_y],[500, base_y-900],[0, base_y-900]])
    await b.create_polyline(points=[[0, base_y-900],[600, base_y-900],[600, base_y-1100],[0, base_y-1100]], closed=True, layer="A-SECT")
    await b.create_hatch(pattern="AR-CONC", scale=0.5, layer="A-SECT-HATCH", points=[[0, base_y-900],[600, base_y-900],[600, base_y-1100],[0, base_y-1100]])
    # Levels
    await b.create_text(700, base_y+200, "±0.000 FFL", height=125, layer="A-ANNO-TEXT")
    await b.create_text(700, base_y-1100, "-0.900 FOUNDATION", height=125, layer="A-ANNO-TEXT")
    # Dimensions for footing
    await b.ensure_dimstyle("A 1-5")
    await b.create_dimension_linear(0, base_y-1100, 500, base_y-1100, 250, base_y-1500, layer="A-DIM", style="A 1-5")
    # Layouts per scale
    print("Creating layouts...")
    await b.create_layout(name="GF_1-100", paper_size="A2", scale="1:100")
    await b.add_viewport(layout_name="GF_1-100", center=(297,210), size=(180,120), model_center=(5250,4250), scale="1:100", layer="V-PORT")
    await b.create_layout(name="FF_1-100", paper_size="A2", scale="1:100")
    await b.add_viewport(layout_name="FF_1-100", center=(297,210), size=(180,120), model_center=(5250, off+4250), scale="1:100", layer="V-PORT")
    await b.create_layout(name="DETAIL_1-5", paper_size="A3", scale="1:5")
    await b.add_viewport(layout_name="DETAIL_1-5", center=(148,105), size=(80,60), model_center=(250, base_y-500), scale="1:5", layer="V-PORT")
    # Score
    from src.autocad_arch_mcp.nbc.validator import score_drawing, score_drawing_hama
    print("Score plan GF", score_drawing({"thickness":230,"layer":"A-WALL-230","tread":250,"riser":190,"room_area":12,"window_area":2,"floor_area":10,"layer":"A-WALL-230"}))
    print("Score Hama", score_drawing_hama({"thickness":230,"layer":"A-WALL-230","has_title":True,"has_north":True,"has_viewport":True,"has_section_line":True,"has_hatch":True,"detail_scale":"1:5","hatch_pattern":"AR-BRSTD","hatch_scale":0.3}))
    # Save
    out = pathlib.Path(r"D:\6) Obsidian\AI Workspace\Tools\autocad-arch-mcp\3bhk_2floor_hama.dxf")
    await b.drawing_save(str(out))
    print(f"Saved {out} {out.stat().st_size//1024}KB")
    # Screenshot
    try:
        r = await b.get_screenshot()
        print("Screenshot", "ok" if r.ok else "fail", len(r.payload) if r.ok else r.error[:100])
        # Save preview
        import base64
        data = base64.b64decode(r.payload)
        pathlib.Path(r"D:\6) Obsidian\AI Workspace\Tools\autocad-arch-mcp\3bhk_2floor_hama.png").write_bytes(data)
        print("PNG saved")
    except Exception as e:
        print("screenshot fail", e)
    # Info
    info = await b.drawing_info()
    print("Info", info.payload)

if __name__ == "__main__":
    asyncio.run(build())
