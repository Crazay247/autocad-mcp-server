# HAMA GOLD APPENDIX — Construction Set Perfection (L0 Extension)

Inject after `prompts/system-prompt.md` every run. Gold source: `D:\00) ARCHITECTURE\.REF\DWG\hama_CONSTRUCTION DRAWINGS\` 13 DWG 33.6MB `A001-A055` AC1021/AC1032 by `AR. Shirish` @ `3 DOTS` (Canon LBP3500.pc3 A3).

## Gold Trace (extract_hama_features via accoreconsole DXFOUT 16 -> ezdxf)
- **Sheets:** 12 layouts (01-13) + 10 layouts (020-029) = 55 sheets modular `A001-A013 Architecture 2.96MB`, `A020 Wall Detaills 1.69MB 1:5/1:16`, `A030 Stair 1.34MB 1:10`, `A037 Toilet 1.11MB`, `A043 Metal 1.99MB 664KB/sheet`, `A053 Site 1.66MB`. `ALL WORKS 8.46MB` compiled, `plot.log` A3 consistent.
- **Layers 77** all in table, triad enforced: `A-WALL 12/30 0.30, A-COLUMN 170/35, A-SITE BOUNDARY 95/PHANTOM2/50, SHEET border 160/50, A-CENTERLINE 251/CENTER/9, A-HIDDEN LINE 251/HIDDEN2/13, A-LEVEL LINE 8/ACAD_ISO07W100/9` - 0% implicit vs BARAL 89% LINE on Elevation 4.
- **DimStyles 9** scale-linked: `A 1-5 dimtxt 0.5 ->2.5mm plot, A 1-25 2.0, A 1-50 4.0, A 1-275 15.0` `plot_h = dimtxt/denom*25.4 ≈2.5mm` perfect. `DIMSTYLE A 1-150 active` LTSCALE 1.0.
- **Types balanced:** Hama `LINE 5338 LWPOLYLINE 3233 MTEXT 1325 DIMENSION 1118 INSERT 1085 HATCH 632 LEADER 167` vs BARAL `LINE 46709 97%`.
- **Blocks 1260** re-use `col 16x16 149x, wooden railing post 72x, Detail Tag 47x, SEC_CALLOUT 34x, SECTION NOTATION 22x, A-WALL SECTION LINE 195`.
- **Levels 40+:** `LOWER GROUND -10'-6", GROUND ±0'-0", FIRST +10'-6", SECOND +21'-0", ROOF +31'-6"` dual mm/feet.
- **Callouts:** `Detail Tag 47, A-WALL SCTION TAG 65, LEADER 600 wall` cross-ref.
- **Hatches 18 patterns:** `ANSI31 146, ANSI32 99, AR-CONC 89, SOLID 65, DOLMIT/CLAY/EARTH` scale 25.0@1:5 vs 118@1:275.
- **Scores:** validator `score_drawing` 98/100 (wall 20 triad 15 stair 15 etc), vision `wall_closure 20 + dim_chain 20 + text 15 + north 10 + alignment 20 + variance 15` 96/100, composite 97.

## HAMA vs BAD Few-Shot
GOOD (Hama trace): `nbc_entity LWPolyline closed A-WALL-230 4/Continuous/50 + HATCH AR-BRSTD Vermilion on A-WALL-PATT + nbc_dimension A-DIM-1 yellow 18 innermost openings + A-DIM-3 cyan outermost overall+grid AZH + viewport V-PORT locked 1:100 + title G-TTLB ISO7200 NEC + levels bg +/-0.000 + screenshot variance 42`
BAD (prior): `LINE on 0 Default exploded dims, missing A-DIM-2/3, text 1.0mm Standard dimstyle no ArchTick, no north, open polyline, hatch SOLID everywhere -> score 60 major`
GOOD wall detail 1:20: `A 1-5 style dimtxt 0.5 dimasz 0.25 dimgap 0.125 height 0.5, MTEXT 3.0/2.0 hierarchy, HATCH AR-SAND 0.3, ANSI31 25.0, CLAY 25`

## Every-Run Teaching
This appendix is auto-injected via `rag/hama_store.hama_retrieve(intent, k=3)` on every `nbc_*` call - top 3 Hama exemplars (BARAL municipal 98 + Hama A001 97 + Wall 1:5 96) by cosine `all-MiniLM-L6-v2` retrieval. LLM must cite `hama://BARAL` or `hama://A001` same as `drafting_standards.json:26`.

## Cite
`knowledge/drafting_standards.json:26 wall 0.5`, `nbc_compliance.yaml:34 stair T250/R190`, `anthropometry.json:60`, `validator.py:280 score_drawing`, `judge.py:score_drawing_heuristic`.
