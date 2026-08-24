# autocad-arch-mcp

Architectural MCP for **AutoCAD 2021** + **YQArch** (NBC Standard) — hybrid `dotnet` + `file_ipc` + `com` + `ezdxf`.

Spec: `docs/superpowers/specs/2026-08-24-autocad-arch-mcp-design.md`  
Knowledge: `knowledge/master_knowledge.md` + `knowledge/*.json|yaml`

## Prereqs

- Windows 10/11, AutoCAD 2021 Full (R24.0) at `D:\SOFTWARES\Autocad 2021\AutoCAD 2021\`
- YQArch at `D:\SOFTWARES\YQArch` (or `C:\Autodesk\...YQArch`)
- Python 3.10+ Windows native, `uv` ([install](https://docs.astral.sh/uv/getting-started/installation/))

## Install

```powershell
cd "D:\6) Obsidian\AI Workspace\Tools\autocad-arch-mcp"
uv sync
```

## Load in AutoCAD

1. `APPLOAD` → `lisp-code/mcp_arch_dispatch.lsp` → `=== MCP Arch Dispatch v1 loaded ===`
2. `NETLOAD` → `dotnet/AutocadArch.dll`
3. Add both to Startup Suite.

## MCP config (opencode)

See spec §8 `autocad-arch` snippet.

## Knowledge

Run `uv run python -c "import json, jsonschema; ..."` to validate. Phase -1 gate: `knowledge/yqarch_compat_matrix.csv` must be produced before wrappers.

## Dev

```powershell
uv run pytest tests/ -v
uv run pytest -m "not e2e" -v
```
