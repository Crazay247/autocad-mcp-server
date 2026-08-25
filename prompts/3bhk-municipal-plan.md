# 3BHK Municipal Plan — Master Prompt (NBC 206:2024)

> Autocad MCP Server — Municipal submission level. Footprint 10.5m x 8.5m. All units mm. Copy-paste into opencode (autocad-arch MCP).

You are driving AutoCAD 2021 via the autocad-arch MCP. Create a complete 3BHK residential ground-floor plan at municipal submission level. Follow IN ORDER, confirm each result before the next. If a YQArch command fails ("too many arguments" / dialog), fall back to nbc_entity(create_line/create_mtext) on the same layer/coordinates.

## PHASE 0 — Setup

1. `nbc_drawing(create_new)`
2. `nbc_drawing(setup_nbc_standards, jurisdiction=nepal, scale=1_50)` → creates NBC layers (A-WALL-230, A-WALL-115, A-DOOR, A-WIN, A-DIM-1, A-DIM-2, A-DIM-3, A-GRID, A-ANNO-TEXT, A-FURN, A-STRS, G-TTLB), dimstyles NBC-50/NBC-100 (ArchTick, text 2.5), text styles. If A-DIM-1/2/3 missing, `nbc_layer(create)` them first.

## PHASE 1 — Grid & Walls (mm)

3. `nbc_wall(draw_axis)` grid at x = 0, 3500, 7000, 10500 and y = 0, 3000, 5500, 8500, label A-D
4. `nbc_wall(draw_wall)` OUTER 230mm (A-WALL-230) closed rectangle: (0,0)→(10500,0)→(10500,8500)→(0,8500)→(0,0)
5. `nbc_wall(draw_wall)` INNER 115mm (A-WALL-115):
   - Living/Kitchen divider: (3500,0)→(3500,3000)
   - Bedroom partitions: (7000,0)→(7000,3000); (0,3000)→(3500,3000); (0,3000)→(0,5500)
   - Bath walls: (3500,3000)→(3500,5500); (3500,5500)→(5250,5500)
   - Stair enclosure: (7000,3000)→(7000,5500); (7000,5500)→(10500,5500)
6. Fallback: `nbc_entity(create_line)` on A-WALL-230/A-WALL-115 with same coordinates if yq_wall fails.

## PHASE 2 — Doors & Windows (NBC sizes)

7. `nbc_opening(open_door)`:
   - D1 main entry 1200×2100 at (900,0)
   - D2 bedroom 900×2100: three at (0,4100), (9100,0), (9100,4100)
   - D3 bath 750×2100: two at (4100,4750), (0,6500)
   - D4 kitchen 900×2100 at (4100,0)
8. `nbc_opening(open_window)` sill 900:
   - W1 1800×1200 living at (1750,8500)
   - W2 1500×1200 bedrooms at (0,1500), (9100,1500), (10500,6500)
   - W3 900×900 kitchen/bath high sill 1200 at (3500,8500), (4750,8500)
   - Fallback: represent windows as gap + sill line on A-WIN

## PHASE 3 — Stair (A-STRS)

9. `nbc_stair(stair_plan ltj)` at (7000..8200,3000..5500): width 1200, tread 250, riser 190 (16 risers, 2R+T=630), handrail 900, direction UP arrow

## PHASE 4 — YQArch Furnishing (A-FURN, use jj)

10. Living: 3-seat sofa 2200×900 at (0..2200,5500..6400), coffee table 1200×600, TV unit 1800×400 at (3500,5500)
11. Dining (3500..5600,0..3000): 6-seat table 1800×900 + 6 chairs, sideboard 1200×450
12. Kitchen (5600..10500,0..3000): L-shaped counter 600 deep, sink 900, stove 600, fridge 700×700
13. Master bedroom (7000..10500,5500..8500): double bed 1800×2000, wardrobe 600 deep full wall, 2 nightstands 450×450
14. Bedroom 2/3: single beds 1500×2000, wardrobes 600 deep
15. Both baths: WC pan, washbasin 550, shower 900×900 (`nbc_decor wc`)

Fallback if `jj` requires dialog: draw rectangles + `nbc_entity(create_mtext)` labels "SOFA", "BED", etc.

## PHASE 5 — Room Labels + Areas (A-ANNO-TEXT, height 125 = 2.5mm @1:50)

16. `nbc_entity(create_mtext)` at each room centre (height 125):
    - "LIVING 21.5 m²" at (1750,7000)
    - "DINING 10.8 m²" at (4550,1500)
    - "KITCHEN 14.1 m²" at (8300,1500)
    - "MASTER BEDROOM 14.0 m²" at (8750,7000)
    - "BEDROOM 2 10.5 m²" at (1750,4250)
    - "BEDROOM 3 10.5 m²" at (8750,1500)
    - "BATH 1 4.3 m²" at (4375,4250)
    - "BATH 2 3.9 m²" at (1750,7000) offset for bath zone
    - "STAIR" with UP arrow at (7600,4250)
17. Door tags D1-D4, window tags W1-W3 near openings (height 100)

## PHASE 6 — 3-Layer Dimensioning (municipal standard)

18. A-DIM-1 (innermost, openings): dimension every door/window width + offset from nearest grid line on each wall face (ArchTick, extension 1.6/3)
19. A-DIM-2 (middle, wall-face to wall-face): all room clear sizes
20. A-DIM-3 (outermost): overall 10500 × 8500 on all 4 sides + grid centreline chain via `nbc_dimension(axis_to_dim AZH)`
21. Use `nbc_dimension(quick_wall DDZ)` for wall chains; verify DIMSTYLE is NBC-50

## PHASE 7 — Municipal Dressing

22. `nbc_block(insert)` NORTH arrow (NORTH.dwg) top-right on A-NORTH at (10000,8000)
23. `nbc_section(add_level bg)` levels: FFL ±0.000, +3.000
24. `nbc_drawing(plot_pdf, path="%LOCALAPPDATA%/autocad-arch-mcp/3bhk_plan.pdf", sheet="A1")`
25. `nbc_view(zoom_extents + get_screenshot)` → confirm visually, non-black variance check

## FINAL CHECKLIST

- [ ] All walls on A-WALL-230/115 (outer 230, inner 115)
- [ ] Doors/windows NBC widths, sill 900/1200
- [ ] Stair 1200 wide, 250/190 compliant, UP arrow
- [ ] Furniture on A-FURN (jj or fallback rectangles)
- [ ] 3 dim layers present (opening → room clear → overall+grid)
- [ ] Room areas labelled, tags D/W
- [ ] North arrow, levels, A1 PDF plotted, screenshot non-black

## Notes

- Wall fallback is `create_line`; dimension fallback is `create_dimension_linear` with dim_x/y offset.
- Text heights are model units: 125 = 2.5mm plotted at 1:50; 100 for small tags.
- If a step times out, `(c:mcp-arch-dispatch)` in AutoCAD command line manually, then retry.
