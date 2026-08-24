# Master Knowledge Source — autocad-arch-mcp

> Human-readable companion to `knowledge/*.json|yaml`. Machine source of truth is JSON/YAML; this file orients quickly and points to verified sources. All values trace to `knowledge/references/_collection_log.md`.

## How to use

- **LLM / MCP tools** import `anthropometry.json` + `drafting_standards.json` + `nbc_compliance.yaml` + `yqarch_reference.json` at startup, validate with `jsonschema Draft-07`, enforce bounds.
- **Jurisdiction toggle** `nepal` (NBC 206:2024) vs `india` (SP 7:2016 Pt3) vs `comfortable` (Neufert) controls which minima the validator applies; default stricter (India 2750/9.5m²) unless user selects `nepal`.
- **Phase -1 gate** before any YQArch wrapper: `yqarch_compat_matrix.csv` decides wrapper vs .NET fallback per command.

## 1. Anthropometry essentials

- Standing 5th–95th: M 1620–1800mm, F 1500–1620mm; eye M 1500–1650; elbow M 1000–1100; shoulder breadth 450–520M / 400–470F.
- Seated: seat→crown 850–950, eye 1100–1200 AFF, knee 500–600, popliteal 400–450.
- Reach prime 750–1600 AFF, overhead 1800–2100, corridor envelope 600 (comfortable 800–900, two-person 1200–1500).
- Wheelchair 630×1075, turning Ø1500, over-table reach 580M/510F.
- See `anthropometry.json:human_body` + `furniture_mm` for full tables; sources: Neufert 4th ed, Chakrabarti 1997, ADA/RPwD.

## 2. Building minima by purpose

- **Residential:** habitable 4m² Nepal / 9.5m² India (w≥2400 comfortable 12m²), height 2400 Nepal / 2750 India, kitchen 5m² w≥1800, bath 1.8m² w1200 h2100, WC 1.1 w900, combi 2.8 w1200, plinth 450, parapet 1000–1200, mezzanine 2200.
- **Educational/Healthcare:** heights 2750–3600 Terai, loads 4m² edu / 14m² health, stair 1500, operation door 1500 two-leaf, lift 1200×2400.
- **Stairs:** T250 R190 res / T279 R175 other, max 15/flight, headroom 2000, handrail 900, `2R+T≈630`; widths row 1000 → edu/assy 1500–2000.
- **Light/vent:** hills 1/10 habitable 1/8 kitchen 1/16 vent; other 1/8,1/6,1/16.
- Full map `anthropometry.json:building_category_minima` + `nbc_compliance.yaml`.

## 3. Drafting that ships

- **Sheets:** A0–A4 + DUDBC 20"×30" (508×762) filing left 20 / others 10, frame 0.7, grid 50.
- **Scales:** 1:100 plans, 1:50/1:20 details; designation `SCALE 1:X`.
- **Lines 0.5 group:** wide 0.5 (cut), narrow 0.25 (dim/grid/axis CENTER), hatch 0.13, section extra 0.7–1.0.
- **Dims:** ArchTick 45°, extension thin 0.18 gap 1.6 beyond 3, text above `DIMTAD 1` 2.5mm, mm `DIMLUNIT 2`.
- **Hatches:** Brick/Conc/Steel ANSI31/Wood/Glass/Gravel/Earth per `IS 962 Table 7`.
- **Layers NCS:** `A-WALL/A-DOOR/A-WIND/A-DIM/A-GRID/G-TTLB/V-PORT` etc. — see `drafting_standards.json:layers_AIA_NCS`.
- **Title ISO 7200:** owner/id/date/sheet/title/approval/creator/type + Nepal NEC/north/units ≤170 wide.
- **Grid/section:** CENTER 0.25 bubbles Ø10–12, section `A-A` dash-dot arrows, levels `▼±0.000`.
- **Paper:** model 1:1 mm, layouts viewports `V-PORT` locked `1:100/1:50`, CTB by colour.

## 4. YQArch as accelerator

- Install at `D:\SOFTWARES\YQArch` + DLM, layers `WALL 80 / DOTE 1 CENTER / DOOR 2 / WINDOW 2`, thickness list 50–480 default 120, doors 600–5400, scales 1–10000, blocks `sys/windows/WD_*.dwg`, CTB/lin `sys/library/yqarch.*`.
- Commands `ww/ad/aw/ho/wd/tw/cw/vw/xf/bg/ltj/ltp/jj/DDZ` — Phase -1 matrix decides CLI vs dialog; sanitiser `mcp-sanitise-input` + `entmake` preferred.
- See `yqarch_reference.json` + `knowledge/yqarch_compat_matrix.csv`.

## 5. Where to look up

- `knowledge/anthropometry.json` — percentile & furniture & door/stair tables with `source` & `cite`
- `knowledge/drafting_standards.json` — sheets/scales/line/dim/hatch/layers/title
- `knowledge/nbc_compliance.yaml` — validation rules + layers/dimstyles/sheets to create
- `knowledge/yqarch_reference.json` — live YQArch layers/commands/paths
- `knowledge/references/_collection_log.md` — ledger, `references.bib`, per-paper notes

## 6. Provenance

All entries pinned to primary PDFs: `NBC 206:2024` gov.np, `SP 7:2016 Pt3` bis.gov.in, `IS 962:1989` law.resource.org, `IS 10711/10713/10714-23`, `ISO 7200`, `NCS V6/V7` ncs6_clg_lnf.pdf, Neufert, Chakrabarti via IIT-G, Autodesk help, YQArch live `layers.txt/config.txt`. Hashes in `trusted_hashes.json`.
