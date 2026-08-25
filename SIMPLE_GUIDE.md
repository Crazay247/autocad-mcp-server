# YOUR AUTOCAD MCP — SIMPLE GUIDE

You are done with the hard part. APPLOAD worked. NETLOAD is NOT needed.

## What you have
- AutoCAD 2021 + YQArch (ww/ad/aw walls/doors) ready
- New MCP: autocad-arch (12 tools nbc_*) — uses simple file_ipc (no DLL)
- Old MCP: autocad (disabled, ignore it)

## How to use (3 steps every time)
1. OPEN AutoCAD 2021
2. It auto-loads: lisp-code\mcp_arch_dispatch.lsp (you added to Startup Suite)
   If not auto, type APPLOAD → pick that file → Load (you saw 'loaded successfully')
3. OPEN opencode — it auto-connects to autocad-arch

## Restart needed
Close and reopen opencode after I changed opencode.json just now — so it sees autocad-arch enabled.

## What to say to opencode (examples)
Copy-paste these:

**Check it works:**
> Use nbc_system status

Should reply: backend file_ipc, yqarch:loaded, acp cp1252

**Make a house (try this):**
> Use nbc_drawing create_new, then nbc_drawing setup_nbc_standards with nepal 1_100, then nbc_wall draw_wall from 0,0 to 9000,0 thickness 230, then zoom_extents and get_screenshot

**Add door:**
> Use nbc_opening open_door on last wall offset 1000 width 900

**Dimension:**
> Use nbc_dimension quick_wall DDZ

## If something fails
- 'No AutoCAD window found' → Make sure AutoCAD is open with a drawing
- 'Timeout' → Type APPLOAD again, load mcp_arch_dispatch.lsp
- 'YQArch not loaded' → Check YQArch at D:\SOFTWARES\YQArch — should show c:yq_about command exists

## Files to remember
- MCP code: D:\6) Obsidian\AI Workspace\Tools\autocad-arch-mcp
- Knowledge: knowledge/master_knowledge.md (simple human summary)
- LISP: lisp-code\mcp_arch_dispatch.lsp (the file you APPLOAD)
- GitHub: https://github.com/ri3292zone7-cloud/autocad-mcp-server (will be Crazay247 after transfer)

That's it — you talk to opencode in plain English, it draws in AutoCAD.

