# autocad-arch-mcp — Architectural MCP for AutoCAD 2021 + YQArch (NBC Standard)

**Date:** 2026-08-24  
**Version:** 1.0 (design)  
**Repo:** `D:\6) Obsidian\AI Workspace\Tools\autocad-arch-mcp` (new, clean — keep `autocad-mcp v3.1` as fallback)  
**Target host:** `AutoCAD 2021 R24.0 24.0.47.0` at `D:\SOFTWARES\Autocad 2021\AutoCAD 2021\` (`acdbmgd.dll/acmgd.dll` present, `acad` PID live) + `YQArch` at `D:\SOFTWARES\YQArch\` (support path injected, `yqarch.vlx` via `yqstart.lsp`, commands `ww/ad/aw/ho/wd/tw/cw/vw/xf/bg/ltj/ltp/jj/DDZ/AZH` etc.)  
**Client:** opencode (stdio MCP) — parity with `C:\Users\Predator\.config\opencode\opencode.json:59-68` `sketchup:mcp2 uvx` enabled, `autocad:mcp` currently `enabled:false backend:ezdxf`  
**Standards:** NBC 206:2024 (DUDBC MoUD, supersedes 2015) + NBC 105:2020 + IS 962:1989 / IS 10711:2001 / IS 10713:1983 / IS 10714-23:2006 (ISO 5457/5455/128-23/3098/7200) + AIA/NCS V6/V7 layer format + DUDBC e-BPS 20"×30" sheet  
**Knowledge source:** `knowledge/*.json|yaml` (anthropometry + drafting + NBC compliance, version-pinned, hash-verified)

---

## 1. Purpose and scope

**Goal:** a feature-rich MCP server that lets an LLM drive AutoCAD 2021 to produce *production-ready house plan sets* — ground/first floor plans + auto sections + elevations, NBC-compliant wall/door/window/stair libraries, chain dimensioning with NBC styles, grid/bubbles/levels, room/door-window schedules, title blocks, layouts/paper-space viewports, `PLOT` to PDF on the Nepal DUDBC submission sheet.

**In scope (v1):**
- NBC Standard set (Wall 115/230/350, column `zzr/zzc/zzl/zzt/zzx`, door `D1 900×2100 / SD 1200` double, window `W1 1500×1200 / sill 900/1200`, stair `T≥250 R≤190 res` / `T≥279 R≤175 other`, storey 2400–3200mm, corridor 2000mm, light/vent `1/10 hills 1/8 other`, parapet 1000–1200) — jurisdiction toggle Nepal `NBC 206:2024` vs India `SP 7:2016 Pt3`.
- Full drafting stack: `IS 962` sheets/scales/line-weights/dim/hatch symbols, `AIA/NCS` layers (`A-WALL/A-DOOR/A-WIND/A-DIM/A-GRID/A-ANNO/G-TTLB/V-PORT`), line-group `0.5` (wide 0.5/cut, narrow 0.25/dim), dim `ArchTick 45°` `DIMTAD=1`, hatch `AR-* / ANSI31`, title block `ISO 7200`, north arrow paper-space.
- YQArch as accelerator: `ww/ad/aw/ho/wd/tw/cw/vw/xf/bg/ltj/ltp/jj/wc/DDZ/DDZZ/AZH` etc. wrapped with NBC layer/style pre-sets.
- Backends: live `dotnet` (primary) + `file_ipc` fallback + `com` lock + `ezdxf` headless preview (geometry-only, no YQArch semantics).

**Out of scope v1:** 3D BIM/Civil MEP full (separate Phase 2), structural NBC 105 rebar detailing, services quantification beyond schedule CSV, headless YQArch reimplementation.

---

## 2. Architecture

### 2.1 Topology (hybrid B, recommended)

```
MCP Client (opencode / Claude) — stdio JSON-RPC —► FastMCP (Python 3.10+, mcp[cli]<2.0)
  config.py: AUTOCAD_ARCH_BACKEND=auto|dotnet|file_ipc|ezdxf, IPC_DIR=%LOCALAPPDATA%\autocad-arch-mcp\ipc\<pid>\
  client.py: lazy singleton get_backend() + asyncio.Lock + HMAC session key + screenshot mux
  backends/
   ├─ dotnet_bridge.py — NamedPipe client ↔ .NET 4.8 DLL (acdbmgd/acmgd) Transactions
   ├─ file_ipc_arch.py — PostMessageW WM_CHAR → mcp_arch_dispatch.lsp (fallback)
   ├─ com_automation.py — pywin32 Autocad.Application (doc lock, integrity level, hwnd verify)
   └─ ezdxf_nbc.py — headless NBC DXF (R2018) + matplotlib screenshot

AutoCAD 2021 side:
  acaddoc.lsp → yqstart.lsp (TRUSTEDPATHS, not SECURELOAD 0) → yqarch.vlx (hash-pinned) → mcp_arch_dispatch.lsp (whitelist) → AutocadArch.dll (IExtensionApplication, NETLOAD startup suite)
  %LOCALAPPDATA%\autocad-arch-mcp\ipc\<pid>\autocad_arch_cmd_{uuid}.json ↔ result_{uuid}.json (HMAC, ACP-aware)
  Layers: A-WALL-230/A-WALL-115/A-COL/A-BEAM/A-DOOR/A-WIN/A-DIM/A-HATCH/A-GRID/A-ANNO per NBC
```

Divergence from `autocad-mcp v3.1`: new dispatcher `mcp_arch_dispatch.lsp` whitelists `yq_*` + `dotnet_invoke`, supports `vlax-*` (full, not LT), semicolon `points_str`, `ACP`-aware I/O, pipe ACK.

### 2.2 Component map

| Component | File | Role | Depends |
|-----------|------|------|---------|
| MCP Server | `src/autocad_arch_mcp/server.py` | 12 consolidated tools (see §3), FastMCP registration, `ToolResult union` fixes `str\|list` 21 | `client.py`, backends |
| Backend Singleton | `src/autocad_arch_mcp/client.py` | `get_backend()` double-check `asyncio.Lock`, `detect_backend()`, `HMAC` key gen, `_safe` with `KeyError` branch, `add_screenshot_if_available` | `config.py` |
| Config | `src/autocad_arch_mcp/config.py` | `GetACP()` detection, `BACKEND_DEFAULT auto`, `IPC_TIMEOUT 1-300`, `ONLY_TEXT`, `YQARCH_DIR`, `WIN32_AVAILABLE` | env |
| Dotnet Bridge | `src/autocad_arch_mcp/backends/dotnet_bridge.py` | pipe client, framing length-prefix, marshal via `DocumentManager.Invoke`, `Transaction` rollback, `DimStyleTable/Layout/Viewport` | `backends/base.py` |
| File IPC | `src/autocad_arch_mcp/backends/file_ipc_arch.py` | atomic `.tmp→rename` retry, `await asyncio.sleep`, named mutex `Global\autocad-arch-bridge-autocad-<hwnd>`, ACP write, stale cleanup skip in-flight, `result HMAC` | `screenshot.py` |
| COM | `src/autocad_arch_mcp/backends/com_automation.py` | `GetWindowThreadProcessId→acad.exe` verify, integrity level check, `LockDocument` | pywin32 |
| Ezdxf NBC | `src/autocad_arch_mcp/backends/ezdxf_nbc.py` | `ezdxf.new("R2018")` (not R2013), NBC validator share, geometry-only fallback, `matplotlib` screenshot | `knowledge/*.json` |
| Security | `src/autocad_arch_mcp/security.py` | `validate_path()`, blocklist, audit log | — |
| Screenshot | `src/autocad_arch_mcp/screenshot.py` | `PrintWindow PW_RENDERFULLCONTENT` canvas-only (exclude title/command), DPI-aware once, variance guard not-black | Win32 |
| LISP Dispatcher | `lisp-code/mcp_arch_dispatch.lsp` | whitelist, `mcp-sanitise-input`, `mcp-report-error`, `\uXXXX` escape, `undo` marker `_.UNDO _BEgin/_End`, `init_yqarch_layers` after purge | `TRUSTEDPATHS` |
| .NET DLL | `dotnet/AutocadArch.dll` | `IExtensionApplication`, pipe server SDDL user-only randomised name, `System.Text.Json`, handlers per tool | acdbmgd/acmgd |
| Knowledge | `knowledge/*.json|yaml` | `anthropometry.json`, `drafting_standards.json`, `nbc_compliance.yaml`, `yqarch_reference.json`, `trusted_hashes.json` | jsonschema |

---

## 3. MCP Tool surface (12 consolidated, `operation` dispatch — mirrors `autocad-mcp` 8-tool shape)

All tools: `async def tool(operation:str, data:dict|None, include_screenshot:bool=False) -> ToolResult` where `ToolResult = str | list` fixed to `Union[TextContent, list[TextContent|ImageContent]]`. Each validates `Pydantic BaseModel` before dispatch; `knowledge` pre-check via `validate_against_knowledge(op, params)` returning structured `{"compliant":bool, "findings":[...cite:NBC clause...]}`.

| # | Tool | Operations (selected) | Backend | YQArch cmd |
|---|------|-----------------------|---------|------------|
| 1 | `nbc_drawing` | `create_new{name?}` (erase+purge+keep dispatcher), `open{path}`, `save{path?}`, `save_as_dxf{path}`, `plot_pdf{path, sheet:A1|A3|20x30}`, `purge`, `get_variables{names}`, `undo/redo`, `setup_nbc_standards{jurisdiction:nepal|india, scale:1_50|1_100}` → creates DimStyles `NBC-100/50`, TextStyles `ARCH-2.5/3.5`, layers, linetypes, `yqarch.lin/ctb`, title block | dotnet+file_ipc+com | — |
| 2 | `nbc_wall` | `draw_axis{points}`, `draw_grid_axis{points, label}`, `draw_wall{axis_points, thickness:115|230|350, height, justify:center|left|right}`, `axis_to_wall(xww)`, `wall_offset(wwo){distance}`, `change_thickness(wwt){thickness}`, `trim_fix(tw)`, `rebuild_axis(wwa)`, `fill_wall(wwf)`, `rect_col(zzr){w,h}`, `o_col(zzc){d}`, `l_col(zzl)`, `t_col(zzt)`, `cross_col(zzx)`, `arrange_cols(zzbz)`, `pline_to_col(xxzz)`, `fill_col(zzf)` | dotnet primary, file_ipc fallback | `ww, zxbz, zzr/zzc/zzl/zzt/zzx, wwt, xww, wwo, tw, wwa, wwf` |
| 3 | `nbc_opening` | `open_door(ad){wall_handle, offset, width:600-5400, height:2100, swing:L|R, door_type:single|double|sliding}`, `draw_door(ad2)`, `open_window(aw){width,height,sill}`, `draw_window(aw2)`, `replace(td)`, `auto_hole(ho)`, `pocket(adt)`, `param_win(wd)`, `corner(wdz)`, `change_width(cw)`, `move(vw)`, `repair(xf)`, `sills(mkx,mdx)`, `to_window(xwd)` | dotnet+file_ipc | `ad/ad2, aw/aw2, td, ho, adt, wd, wdz, cw, vw, xf, mkx, mdx` |
| 4 | `nbc_entity` | `create_line{x1,y1,x2,y2,layer}`, `create_circle{cx,cy,r}`, `create_polyline{points,closed}`, `create_rectangle{x1,y1,x2,y2}`, `create_arc{cx,cy,r,sa,ea}`, `create_ellipse{cx,cy,mx,my,ratio}`, `create_mtext{x,y,width,text,height}`, `create_hatch{entity_id,pattern:ANSI31|CROSS|AR-*}`, `list{layer?}`, `count{layer?}`, `get{entity_id}`, `erase/copy/move/rotate/scale/mirror/offset/array/fillet/chamfer` | dotnet `.NET Transaction` | — |
| 5 | `nbc_stair` | `stair_plan(ltj){width, tread, riser, flights}`, `arc_stair(lta)`, `elevator(dtj){1200×2400}`, `escalator(ltf)`, `stair_section(ltp)`, `step_section(lxtb)` — validates `2R+T 600-650`, `max 15 risers/flight`, headroom 2000, handrail 900, width per Table 3 | dotnet+file_ipc | `ltj/lta/dtj/ltf/ltp/lxtb` |
| 6 | `nbc_decor` | `auto_furniture(jj){category, symbol}`, `wc(wc){type}`, `chest(yg)`, `cupboard(gz)`, `curtain(clp)`, `stone_tile(stb)`, `wooden_frame(mf)` | file_ipc+ezdxf | `jj, wc, yg, gz, clp` |
| 7 | `nbc_dimension` | `quick_wall(DDZ)`, `quick(DDZZ)`, `continue(DDSS)`, `axis_to_dim(AZH)`, `linear{x1,y1,x2,y2,dim_x,dim_y}`, `aligned{x1,y1,x2,y2,offset}`, `angular{cx,cy,x1,y1,x2,y2}`, `radius{cx,cy,radius,angle}`, `leader{points,text}` — forces `NBC-*-*` style (`DIMTXT 2.5, DIMSCALE×, ArchTick`) | dotnet | `DDZ/DDZZ/DDSS/AZH` |
| 8 | `nbc_section` | `add_level(bg){levels:[{name,height,tag}]}`, `generate{cut_line:[x1,y1,x2,y2], scale, depth}` → `A-SECT` layout, `VIEWPORT 1:100`, level markers `±0.000/+3.000`, hatches `CROSS/ST4.8*/AR-CONC`, waterproof `fsc`+stucco `fn` | dotnet | `bg/bg2, fsc, fn, mqs` |
| 9 | `nbc_layer` | `list`, `create{name,color,linetype}`, `set_current{name}`, `set_properties{name,color?,linetype?,lw?}`, `freeze/thaw/lock/unlock` — NCS `A-WALL/A-DOOR/A-WIND/A-FLOR/A-ANNO-DIMS/G-TTLB` | dotnet+file_ipc | — |
| 10 | `nbc_block` | `list`, `insert{name,x,y,scale?,rot?,block_id?}`, `insert_with_attributes{name,x,y,attrs}`, `get_attributes{entity_id}`, `update_attribute{tag,value}`, `define{name,entities}` (ezdxf only) — `WD_*.dwg` window library, `NORTH.dwg` | dotnet+ezdxf | `yq*` blocks |
| 11 | `nbc_view` | `zoom_extents`, `zoom_window{x1,y1,x2,y2}`, `get_screenshot` (canvas-only, variance guard, minimized `GetWindowPlacement` normal rect) | dotnet+Win32 | — |
| 12 | `nbc_system` | `status` (backend, caps, yqarch:loaded, `GetACP`, `ipc_dir`), `health`, `get_backend`, `runtime`, `init{reinit pipe+layers+hash check}`, `execute_lisp{code}` (gated `ALLOW_RCE=1`), `execute_dotnet{code}` (gated). `include_screenshot` supported on `status/draw` | all | — |

Encoding: `points` → `x1,y1;x2,y2;...`; `names` → `names_str` `;` delimited (LISP-safe). All string params through `mcp-sanitise-input` (`" \ ; ( ) ' \n\r\0` stripped/escaped); prefer `entmake` over `(command ...)`.

---

## 4. NBC + Anthropometry + Drafting Knowledge (master source)

**Is-not:** `IS 962` is drawing conventions (how to draw), NBC 206 is content (what to show), `IS 4445` is medical—avoid miscites. Anthropometry via Neufert + Chakrabarti 1997, Nepal heights via NBC 206:2024 Tables 3-4.

### 4.1 Anthropometry (mm, 5th–95th South Asian)

Standing stature 1620–1800M/1500–1620F, eye 1500–1650/1400–1500, elbow 1000–1100/950–1050, shoulder breadth 450–520/400–470; seated seat→crown 850–950, eye 1100–1200 AFF, knee 500–600, popliteal 400–450; reach prime `750–1600 AFF`, overhead `1800–2100`, corridor envelope `600` (comfortable 800–900, 2-person 1200–1500); wheelchair `630×1075`, turning Ø1500, high reach 1715M/1575F.

### 4.2 Building minima (jurisdiction toggle)

| Param | Nepal `NBC 206:2024` | India `SP 7:2016 Pt3` | Comfortable | Notes |
|-------|---------------------|----------------------|-------------|-------|
| Habitable area | 4m² (2000×2000) | 9.5m² w≥2400 | 12m²+ | select stricter |
| Room height | 2400 | 2750 | 3000 | Nepal 2400 is lenient |
| Kitchen | — | 5.0m² w≥1800; combi 7.5 w≥2100 | — | — |
| Bath 1.8m² w≥1200 h2100, WC 1.1 w≥900, combi 2.8 w≥1200 | per NBC Table | — | — |
| Plinth 450 | 450 | — | — | — |
| Door exit gen 1000×2100, resid 900×2000, bath 750, assy max shutter 1200 | per NBC India | — | — |
| Stair res T250 R190, other T279 R175, max 15/flight, headroom 2000, handrail 900, `2R+T≈630` | per Table 4 | ergonomic | — |
| Stair width row 1000, A1/A3/A4 1250, hotel 1500, edu 1500, assy 1500/2000 | — | — | — |
| Corridor 2000 (India) / Table 3 (Nepal) | — | — | — | — |
| Light/vent hills 1/10 habitable 1/8 kitchen 1/16 vent; other 1/8,1/6,1/16; hospitals 1/8 | — | — | — | — |
| Furniture counter 850–900×600d, desk 720–760, table 750, chair 420–450, bed single 900×2000 double 1800×2000, wardrobe 600d, kitchen aisle 1050–1200, WC front 750–900 | — | — | Neufert |
| Storey cat / parking `L×B` / parapet 1000–1200 / disabled Cat1/2/3 ramp `1:12` | per NBC Table | — | — |

### 4.3 Drafting standards (IS 962 bundle)

* **Sheets:** A0 841×1189, A1 594×841, A2 420×594, A3 297×420, A4 210×297 (first choice), + **DUDBC 20″×30″ 508×762** custom — borders 20 left/10 others, frame 0.7, centring 0.35, title block bottom-right.
* **Scales:** reduction `1:2/1:5/1:10/1:20/1:50/1:100/1:200/1:500...` — house plans `1:100`, details `1:50/1:20`, `SCALE 1:X`.
* **Line groups** `1:2:4` (narrow/wide/extra-wide): `0.5` group for A1/A2 `narrow 0.25 / wide 0.5 / extra 1.0` — cut 0.5, hidden dashed 0.25, axis CENTER 0.25, dim/leader 0.18, section cut extra-wide 0.7–1.0, hatch 0.13.
* **Dimensioning:** extension thin perp + gap `DIMEXO`, extend `DIMEXE`, tick 45° `DIMBLK=ArchTick`, running dims open 90° arrow, text above `DIMTAD=1` readable bottom/right `DIMTIH/TOH 0`, mm `DIMLUNIT 2`, column centres vs wall faces per framed/bearing.
* **Hatches:** `Brick AR-BRSTD, CONC AR-CONC, Steel ANSI31, Wood AR-WOOD, Glass GLASS, Gravel GRAVEL, Earth EARTH, Plaster AR-SAND, Insulation INSUL`.
* **Layers AIA/NCS** `Discipline(2)-Major(4)-Minor(4)-Minor(4)-Status(1)` — plugin set `A-WALL/A-WALL-FULL/A-DOOR/A-WIND/A-FLOR/A-FLOR-HATCH/A-WALL-PATT/A-ANNO-DIMS/A-ANNO-TEXT/A-GRID(DISCRETE CENTER 1)/A-GLAZ/A-STRS/A-SECT/A-SECT-HATCH/A-NORTH/G-TTLB(A1)/V-PORT(no-plot)`.
* **Title block ISO 7200** `legal owner/id/date/sheet/title/approval/creator/doc type` + Nepal optional `scale/units NEC licence north DO NOT SCALE` ≤170 wide.
* **Grid/section/north:** `CENTER` 0.25, bubbles Ø10–12 letters A…/numerals 1…, section `A-A` extra-wide dash-dot arrows, elevation face arrows, door swing arcs, stair `UP/DN`, level `▼±0.000`.
* **Paper:** model `1:1 mm`, layout per sheet, viewport `V-PORT` locked `1:100/1:50`, annotative dim/text preferred, `CTB` plot.
* **NBC content triggers:** purpose group, exit `w×h`, stair `T/R/flights/width/handrail`, travel `30m/40m ext`, plinth `mm`, light/vent ratio, parking `L×B ramp`, disabled cat.

### 4.4 YQArch reference (live install `D:\SOFTWARES\YQArch`)

Layers `DOTE 1 CENTER, WALL 80, WALL_FILL 8, COLUMN 40, DOOR 2, OPENING 7, WINDOW 2, STAIR 2, FURNITURE 53...`, thickness `50/60/90/100/120/140/150/180/200/240/250/300/360/480 default 120`, door widths `600–5400`, scales `1–10000`, blocks `sys/blocks/**`, windows `sys/windows/WD_*.dwg`, frames `JUI→A0–A4`.

Full data in `knowledge/*.json|yaml` with `source_ledger`.

---

## 5. Data flow and error handling

`tool(operation,data)` → `client.get_backend()` (auto: dotnet pipe liveness `ping→pong` else `file_ipc` else `ezdxf`) → `validate_against_knowledge(op,params)` (findings cite `NBC clause`/Neufert) → `security.validate_path` where `path` → write `%LOCALAPPDATA%\...cmd_{uuid}.json` (HMAC, ACP) → `PostMessageW WM_CHAR "(c:mcp-arch-dispatch)"` (2×ESC prefix, no focus steal) *or* pipe `length-prefix JSON` (marshalled to doc thread) → `whitelist dispatcher vl-catch-all-apply` with `_.UNDO _BEgin/_End` around multi-step YQArch chains → atomic `result_{uuid}.json` (`ok/payload|error`) rename → poll `1-300s` (distinguish `JSONDecodeError` fail-fast vs not-yet-written) → `CommandResult.to_dict()` → optional canvas-only screenshot → MCP union response.

Errors: `KeyError/TypeError → "Missing param: k (check schema)"` (not misleading `AutoCAD not responsive`), whitelist miss `Unknown command: k`, `handent nil → Entity not found: handle`, `yqarch not loaded→fallback NET`, pipe dead→fallback file_ipc. All strings `mcp-sanitise-input`; `entmake` preferred.

---

## 6. Security (STRIDE/OWASP audit applied)

* `execute_lisp/dotnet` **removed from default**; gated `AUTOCAD_ARCH_MCP_ALLOW_RCE=1` env at startup + blocklist `startapp/vlax-create-object/shell/NETLOAD/arxload`; audit `security_audit.log` append-only (hash `code`).
* `validate_path()%LOCALAPPDATA% allowlist`, reject `\\` UNC, `..`, enforce `{.dwg,.dxf,.pdf,.json}`, `REMEMBERFOLDERS 0`.
* IPC dir `%LOCALAPPDATA%\autocad-arch-mcp\ipc\<pid>\` user-ACL (not `C:/temp` world-writable); command+result HMAC `SHA256` session key; randomised pipe name `autocad-arch-{16hex}` + handshake SDDL current-user-only; never `ImpersonateNamedPipeClient`.
* YQArch VLX SHA-256 pinned `knowledge/trusted_hashes.json`; never `SECURELOAD=0` → add `D:\SOFTWARES\YQArch` + ipc subdir to `TRUSTEDPATHS` keep `SECURELOAD=1`; load once at startup.
* Injection: `mcp-sanitise-input` on all `(command ...)` strings; `pydantic` strict typing on `knowledge/*.json`; fuzz adversarial `";()\"` coverage.
* TOCTOU: `st_mtime` check `exists→read_text`, `os.open 0o600` temp `.lsp` + immediate delete + `atexit/SIGTERM` cleanup for crashes; `tmp→rename` retry on AV lock.
* COM: verify `GetWindowThreadProcessId→acad.exe` path, integrity level refuse elevated-AutoCAD from non-elevated server.
* Screenshots: crop to drawing canvas (exclude title/command/ribbon), `include_screenshot false` default, rate-limit 1/10s, `ONLY_TEXT` prod flag (NDA drawings).

---

## 7. Verification (accoreconsole-first, pytest)

**Run:** `uv run pytest tests/ -v` (unit) + `pytest -m e2e --autocad` (live) — no `npm test`.

| Layer | Suite (loc) | Gate |
|-------|-------------|------|
| File-IPC | `tests/test_ipc_protocol.py` real `FileIPCBackend` + stub typing + `tmp_path` HMAC/partial/mismatch/rename-lock/rapid-10/2-backends race (C-2) | unit |
| Config/singl | `tests/test_config_detection.py` `file_ipc` non-Windows/pywin32 ImportError/WSL branches; `tests/test_client_singleton.py` `asyncio.gather` once | unit |
| Server dispatch | `tests/test_server_tools.py` stub backend mapping for all 12 tools + triple-linkage AST scan `server↔backends↔LISP` | unit |
| LISP | `tests/test_lisp_dispatch_console.py` via `accoreconsole.exe` (2021): Devanagari `शयन कक्ष – ३×३.६`, control `\n/"`, `two_pending_files_processes_car`, `SECURELOAD 2` restore, dimstyle `NBC-1-50 tblsearch`, unknown error JSON | integration (`@pytest.mark.autocad`) |
| KB | `tests/test_knowledge_base.py` jsonschema Draft-07 `version/unit`, bounds `riser 100-220 tread 200-400 door 600-1500 eye 1300-1800`, snapshot hash bump, load idempotent | unit |
| NBC | `tests/test_ezdxf_nbc_backend.py` `setup_nbc_standards` layers/dimstyles, wall/stair/door property-based (hypothesis), goldens `basic_shapes_r2013|R2018.dxf` + `generate_golden.py` version-matrix, dim `3000→"3000"`, unicode `\U+` roundtrip | unit+integration |
| Pipe | `tests/test_dotnet_pipe_protocol.py` fake pipe server: framing length-prefix, serialized single-in-flight, correlation, timeout/reconnect | unit (win32) |
| Screenshot | `tests/test_screenshot.py` `Win32ScreenshotProvider._get_capture_rect` minimized/normal, `PrintWindow 0`, variance not-black/white, DPI once | unit+e2e |
| Plot | e2e `plot_pdf` pypdf page size (fix ANSI_A hardcode → A1/A3/20x30 param, guard `DWG To PDF.pc3`) | e2e |
| Manual flows | `APPLOAD mcp_arch_dispatch.lsp + NETLOAD AutocadArch.dll` → `system(status)∩backend=yqarch:loaded∩GetACP→capabilities/ipc_dir` → `drawing(create→status get_variables SECURELOAD/DIMSTYLE)` → `nbc_wall(230)→nbc_opening(D1)→nbc_dimension(DDZ chain)→nbc_section(bg)` → `view(zoom_extents/get_screenshot variance)→plot_pdf` + minimized/covered `PrintWindow` + YQArch modal 2×ESC recovery + dual-MCP-clients simultaneous race | checklist |

**Markers:** `win32`, `autocad`, `e2e`; fix `conftest.py` per-module `ezdxf` scoping; `pytest -m "not e2e"` for CI GH Actions Windows job.

---

## 8. Deployment and config (SketchUp parity)

**Repo init:** `D:\6) Obsidian\AI Workspace\Tools\autocad-arch-mcp` `uv sync` `pyproject.toml: python>=3.10, deps mcp[cli]>=1.2.1,<2.0 ezdxf>=0.18,<1.0 matplotlib>=3.7 Pillow>=10,<12 structlog>=24 pywin32>=305;sys_platform win32, dev pytest>=7 pytest-asyncio hypothesis jsonschema pypdf`.

**opencode.json** (alongside `sketchup`):
```json
"autocad-arch": {
  "type": "local",
  "command": ["D:\\6) Obsidian\\AI Workspace\\Tools\\autocad-arch-mcp\\.venv\\Scripts\\python.exe","-m","autocad_arch_mcp"],
  "enabled": true,
  "env": {
    "AUTOCAD_ARCH_BACKEND": "auto",
    "AUTOCAD_ARCH_IPC_DIR": "%LOCALAPPDATA%\\autocad-arch-mcp\\ipc",
    "AUTOCAD_ARCH_IPC_TIMEOUT": "10.0",
    "AUTOCAD_ARCH_ONLY_TEXT": "false",
    "YQARCH_DIR": "D:/SOFTWARES/YQArch",
    "AUTOCAD_ARCH_MCP_ALLOW_RCE": "0"
  }
}
```
WSL clients: `cmd.exe /d /s /c cd /d D:\...autocad-arch-mcp && .venv\Scripts\python.exe -m autocad_arch_mcp`.

**Startup Suite** (AutoCAD 2021 `APPLOAD` Startup Suite): add `lisp-code/mcp_arch_dispatch.lsp` + `dotnet/AutocadArch.dll` (IExtensionApplication auto `NETLOAD`); `drawing(create)` uses erase+purge (not `_.NEW`—preserves dispatcher) + `init_yqarch_layers()`.

**Env:** `BACKEND auto|dotnet|file_ipc|ezdxf`, `IPC_TIMEOUT 1-300 default 10`, `ONLY_TEXT 1|true`, `YQARCH true|false`, `DEBUG_DETECT_FILE` optional.

---

## 9. Robustness addendum (from 3 reviewers)

Applied to baseline `autocad-mcp v3.1` latent defects + new surfaces: `C1 ACP` fix (critical for Chinese Windows `GBK` YQArch block names), `C2` doc-thread marshal, `C3` named mutex, `C4` pre-code YQArch matrix go/no-go (Phase -1 before any wrapper), plus `M1→Pydantic`, `M3` undo-marker, `M4` post-purge layer rebuild, `M5` parser substring collision fix (flat-prefixed keys or `System.Text.Json` side), `M6 await asyncio.sleep`, `M11` ping liveness + locked `init`. Full matrix in `references/_collection_log.md`.

---

## 10. Phases and acceptance gates

| Phase | Deliverable | Gate |
|-------|-------------|------|
| **-1 Pre-code** | `knowledge/yqarch_compat_matrix.csv` (sweep `ww/ad/aw/ho/wd/ltj/ltp/jj/DDZ` `FILEDIA0/CMDDIA0`) | go/no-go pivot |
| **0 Knowledge** | `knowledge/*.json|yaml` + `references/` collection log, schemas+hashes+bounds pass `validate_manifest+check_traceability` | knowledge tests green |
| **1 Spec** | this doc | self-review `TBD/placeholder` scan + internal consistency + scope + user approval |
| **2 Plans** | `writing-plans` tickets ordered (pipe framing before DLL, harness before wrappers, KB before validator) | tickets merged |
| **3 Build** | server+backends+dispatcher+dotnet+screenshot+security, `pytest -m "not e2e"` green | QA review |
| **4 E2E** | `accoreconsole` + live AutoCAD YQArch matrix + minimized screenshot + A1/A3 plot | manual checklist signed |

---

## 11. Risks and mitigations

* YQArch VLX compile per-version brittle → matrix as first gate; fallback .NET wall generator NBC-faithful.
* `PrintWindow` black on minimized/HW-accelerated → `GetWindowPlacement` normal rect + `PW_RENDERFULLCONTENT` + variance guard + fallback `WM_PRINT` flag 2→0.
* `C:/temp` race/AV lock → per-pid IPC + retry `rename` + HMAC; 60s cleanup skips in-flight `claimed`.
* `SECURELOAD 2` origin `2` restore covered, `TRUSTEDPATHS` whitelist avoids global 0.

---

## 12. File map

```
autocad-arch-mcp/
├─ pyproject.toml / uv.lock / README.md / LICENSE (MIT)
├─ docs/superpowers/specs/2026-08-24-autocad-arch-mcp-design.md  ← this file
├─ knowledge/
│  ├─ master_knowledge.md / anthropometry.json / drafting_standards.json / nbc_compliance.yaml / yqarch_reference.json / trusted_hashes.json
│  └─ references/{_collection_log.md, references.bib, source_ledger.csv, survey_*.md}
├─ src/autocad_arch_mcp/
│  ├─ server.py / client.py / config.py / screenshot.py / security.py
│  └─ backends/{base.py, dotnet_bridge.py, file_ipc_arch.py, com_automation.py, ezdxf_nbc.py}
├─ lisp-code/mcp_arch_dispatch.lsp
├─ dotnet/AutocadArch/{AutocadArch.csproj, Bridge.cs, Handlers.cs}
├─ tests/{conftest.py, test_*_*.py, fixtures/*.dxf, golden/*.dxf, generate_golden.py}
└─ opencode.json snippet (see §8)
```

---

## 13. References (verified, see `knowledge/references/` for ledger)

* DUDBC MoUD *NBC 206:2024* & *NBC 105:2020* (gov.np) — supersedes 2015, architectural & seismic.
* BIS *SP 7:2016 Pt3* (NBC India), *IS 962:1989* (law.resource.org), *IS 10711/10713/10714-23* (ISO 5457/5455/128-23), *ISO 7200:2004* (title block), *AIA/NCS V6/V7* (layer format).
* Neufert *Architects' Data* 4th ed + Chakrabarti 1997 (IIT-G), Autodesk 2021 help `acdbmgd/acmgd` & dimension `DIM*` vars, LANL CSM200 §204/205 north, SourceCAD NCS dims.
* YQArch `yqarch.vlx/cuix/mnl` + `D:\SOFTWARES\YQArch\sys\user1\{layers,config,shortcut}.txt`, live support-path `HKCU:\SOFTWARE\Autodesk\AutoCAD\R24.0\...\General\ACAD`.

---

*Self-review: placeholders `TBD/TODO` scan clean; internal consistency §2→§3→§6 pipe/ACP/mutex alignment verified; scope §1 bounded to single house plan set (§9 phases keep headless preview separate from live YQArch). Ready for `writing-plans`.*
