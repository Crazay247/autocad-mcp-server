# E2E Manual Checklist — autocad-arch-mcp

## Pre-conditions
- AutoCAD 2021 R24.0 at D:\SOFTWARES\Autocad 2021\AutoCAD 2021\acad.exe (acad PID live)
- YQArch at D:\SOFTWARES\YQArch\sys\yqarch.vlx loaded (c:yq_about exists)
- .NET DLL built: dotnet build dotnet/AutocadArch.sln

## Checklist

- [ ] APPLOAD mcp_arch_dispatch.lsp — APPLOAD `lisp-code/mcp_arch_dispatch.lsp` → `(c:mcp-arch-dispatch)` present, alias `c:mcp-dispatch`
- [ ] NETLOAD `dotnet/AutocadArch/bin/Debug/net48/AutocadArch.dll` → Editor.WriteMessage [AutocadArch] Bridge loaded
- [ ] `uv run python -m autocad_arch_mcp` with `AUTOCAD_ARCH_BACKEND=auto` → `nbc_system(status)` shows backend file_ipc|dotnet, GetACP, ipc_dir %LOCALAPPDATA%/autocad-arch-mcp/ipc/<pid>
- [ ] `nbc_drawing(create)` preserves *mcp-arch-ipc-dir*
- [ ] `nbc_drawing(setup_nbc_standards jurisdiction=nepal scale=1_100)` → layers A-WALL... + dimstyle NBC-100 + textstyle ARCH
- [ ] `get_variables ["SECURELOAD","TRUSTEDPATHS","DIMSTYLE"]` → SECURELOAD restored, DIMSTYLE NBC-100 current
- [ ] `nbc_wall(draw_wall axis_points=[[0,0],[5000,0]] thickness=230)` → wall on A-WALL-230
- [ ] `nbc_opening(open_door wall_handle last offset 1000 width 900)` → door
- [ ] Unicode: `nbc_entity(create_mtext x=0 y=0 width 200 text="शयन कक्ष – ३.०×३.६" height 2.5)` → no mojibake
- [ ] `nbc_dimension(quick_wall DDZ)` → chain dims 3000=="3000" with ArchTick
- [ ] `nbc_section(add_level bg levels=[{name:FFL,height:0}])` → generate cut
- [ ] `nbc_view(zoom_extents) + nbc_view(get_screenshot)` → PNG not black, variance >10, decode base64
- [ ] Minimized + covered window screenshot → not black (PrintWindow PW_RENDERFULLCONTENT normal rect)
- [ ] Dual MCP clients simultaneous 10 cmds → each request_id matched or at least no crash (C-2 fix)
- [ ] `nbc_drawing(plot_pdf path="%LOCALAPPDATA%/autocad-arch-mcp/test.pdf" sheet="A3")` → pypdf pagesize A3 guard DWG To PDF.pc3 exists
- [ ] accoreconsole.exe -s tests/accoreconsole_smoke.scr → result JSON ok + devanagari + SECURELOAD 2 restore

## accoreconsole
Run: `"C:\Program Files\Autodesk\AutoCAD 2021\accoreconsole.exe" /i NUL /s tests/accoreconsole_smoke.scr`
Script (tests/accoreconsole_smoke.scr) should load dispatch, send ping, verify result.
