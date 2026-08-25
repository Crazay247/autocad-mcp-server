import asyncio
from autocad_arch_mcp.backends.file_ipc_arch import FileIPCArchBackend

async def main():
    b=FileIPCArchBackend()
    await b.initialize()
    base_x, base_y = 0, 30000
    # Add green bubbles A-D top and bottom, 1-3 left/right on text layer with arial narrow style
    # Bubbles are TEXT with height 180 (approx 195h in Baral)
    bubbles = [
        (0,8500+300, "A"), (3500,8500+300, "B"), (7000,8500+300, "C"), (10500,8500+300, "D"),
        (0,0-300, "A"), (3500,0-300, "B"), (7000,0-300, "C"), (10500,0-300, "D"),
        (-300,0, "1"), (-300,3000, "2"), (-300,5500, "3"), (-300,8500, "4"),
        (10500+300,0, "1"), (10500+300,3000, "2"), (10500+300,5500, "3"), (10500+300,8500, "4"),
    ]
    for x,y,txt in bubbles:
        x+=base_x; y+=base_y
        r=await b._dispatch_unlocked("create-text", {"x":x,"y":y,"text":txt,"height":195,"rotation":0,"layer":"text"})
        print(f"bubble {txt} at {x},{y} {r.to_dict()}")
    # 3-tier dims on MLK_dim (orange) as per Baral: outer 10500, middle wall-face, inner openings
    # Outer overall bottom
    r=await b._dispatch_unlocked("create-dimension-linear", {"x1":0+base_x,"y1":0+base_y,"x2":10500+base_x,"y2":0+base_y,"dim_x":5250+base_x,"dim_y":-1200+base_y})
    print("outer bottom", r.to_dict())
    # Top
    r=await b._dispatch_unlocked("create-dimension-linear", {"x1":0+base_x,"y1":8500+base_y,"x2":10500+base_x,"y2":8500+base_y,"dim_x":5250+base_x,"dim_y":9700+base_y})
    print("top", r.to_dict())
    # Left
    r=await b._dispatch_unlocked("create-dimension-linear", {"x1":0+base_x,"y1":0+base_y,"x2":0+base_x,"y2":8500+base_y,"dim_x":-1200+base_x,"dim_y":4250+base_y})
    print("left", r.to_dict())
    # Right
    r=await b._dispatch_unlocked("create-dimension-linear", {"x1":10500+base_x,"y1":0+base_y,"x2":10500+base_x,"y2":8500+base_y,"dim_x":11700+base_x,"dim_y":4250+base_y})
    print("right", r.to_dict())
    # Middle wall-face dims (example)
    for seg in [(0,0,3500,0),(3500,0,7000,0),(7000,0,10500,0)]:
        x1,y1,x2,y2 = seg
        x1+=base_x; y1+=base_y; x2+=base_x; y2+=base_y
        r=await b._dispatch_unlocked("create-dimension-linear", {"x1":x1,"y1":y1,"x2":x2,"y2":y2,"dim_x":(x1+x2)/2,"dim_y":-800+base_y})
        print(f"mid {seg} {r.to_dict()}")
    # Inner opening dims
    for seg in [(900,0,2100,0),(4100,0,5000,0)]:
        x1,y1,x2,y2 = seg
        x1+=base_x; y1+=base_y; x2+=base_x; y2+=base_y
        r=await b._dispatch_unlocked("create-dimension-linear", {"x1":x1,"y1":y1,"x2":x2,"y2":y2,"dim_x":(x1+x2)/2,"dim_y":-500+base_y})
        print(f"inner {seg} {r.to_dict()}")

    await b._dispatch_unlocked("zoom-extents", {})
    print("done dims/bubbles")

asyncio.run(main())
