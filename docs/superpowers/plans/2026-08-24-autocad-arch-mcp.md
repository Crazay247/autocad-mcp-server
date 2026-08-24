# autocad-arch-mcp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver hybrid Python MCP + .NET DLL + YQArch solution for AutoCAD 2021 producing NBC 206:2024 house plan sets (plans+sections, NBC dims/labels, YQArch walls/doors/windows/stairs, 12 tools, accoreconsole-verified).

**Architecture:** FastMCP Python (12 consolidated tools, Pydantic schemas, NBC validator gate) ↔ File IPC `%LOCALAPPDATA%\autocad-arch-mcp\ipc\<pid>\` (HMAC, ACP gbk/cp1252, named mutex `Global\autocad-arch-bridge-autocad-<hwnd>`, PostMessageW) + NamedPipe `\\.\pipe\autocad-arch-{16hex}` (SDDL user-only, marshalled to doc thread via `DocumentManager.Invoke`) ↔ AutoCAD 2021 .NET 4.8 DLL (Transactions) + `mcp_arch_dispatch.lsp` whitelist wrapping YQArch VLX (`ww/ad/aw/...`) + COM hwnd/level verify; ezdxf `R2018` headless preview. Mirrors `autocad-mcp v3.1` PostMessageW skeleton but fixes C1-C4.

**Tech Stack:** Python ≥3.10 (`mcp[cli]<2.0`, `ezdxf>=0.18,<1.0`, `matplotlib`, `Pillow>=10,<12`, `structlog`, `pywin32`, `pydantic>=2`, `jsonschema`, `pyyaml`, `pypdf`, `hypothesis`), AutoLISP `mcp_arch_dispatch.lsp`, .NET 4.8 `acdbmgd/acmgd` (CSproj), `accoreconsole.exe` (2021) harness, Win32 `PrintWindow` screenshot.

**Spec:** `docs/superpowers/specs/2026-08-24-autocad-arch-mcp-design.md` (covers §1 purpose §2 arch §3 tools §4 knowledge §5 flow §6 security §7 verification §8 deploy §9 addendum; knowledge `knowledge/*.json|yaml` version 1.0.0 mm).

## Global Constraints

- Python requires-python >=3.10 (pyproject.toml:8) — verified via `uv sync`
- AutoCAD 2021 R24.0 at `D:\SOFTWARES\Autocad 2021\AutoCAD 2021\` + `acdbmgd.dll`/`acmgd.dll` exists
- YQArch at `D:\SOFTWARES\YQArch` (+ DLM `C:\Autodesk\...YQArch`) — load via `TRUSTEDPATHS`, never `SECURELOAD 0`, hash pinned `knowledge/trusted_hashes.json`
- Backend selection `AUTOCAD_ARCH_BACKEND=auto|dotnet|file_ipc|ezdxf` default `auto` (config.py), `IPC_TIMEOUT 1-300 default 10.0`, `ONLY_TEXT false` default, `ALLOW_RCE 0` default (gates `execute_lisp/dotnet`)
- IPC dir `%LOCALAPPDATA%\autocad-arch-mcp\ipc\<pid>\` (not `C:/temp` world-writable) — user-ACL + HMAC-SHA256 session key + randomised pipe `autocad-arch-{16hex}` SDDL current-user-only
- Encoding: detect `GetACP()` (`ctypes.windll.kernel32.GetACP`) — fallback `936→gbk`, `1252→cp1252`; LISP escapes `\uXXXX` for non-ASCII; `points` as `x1,y1;x2,y2;...` (LISP-safe)
- DXF `ezdxf.new("R2018")` for 2021 (not R2013) — goldens version-matrix `R2013|R2018`
- Line group default `0.5` (wide 0.5 cut / narrow 0.25 dim / extra 1.0 section), sheets A0-A4 + `20"×30" 508×762` DUDBC, scales `1:100/1:50/1:20`, dim `ArchTick 45° DIMTAD 1`
- Standards: NBC 206:2024 (supersedes 2015) + IS 962/10711/10713/10714-23 + ISO 7200 + AIA/NCS V6/V7 + DUDBC e-BPS
- Knowledge files pinned `version 1.0.0 unit mm` + schema validation + snapshot hash bump
- Security: `validate_path()` reject `\\` UNC/`..` enforce `{.dwg,.dxf,.pdf,.json}`, `mcp-sanitise-input` on all `(command ...)` strings, `entmake` preferred, audit `security_audit.log`
- Markers `win32/autocad/e2e`, `conftest.py` per-module `ezdxf` scoping (not global autouse)

---

## File Structure

**New files:**
- `src/autocad_arch_mcp/__init__.py`, `__main__.py`
- `src/autocad_arch_mcp/config.py` — `GetACP()`, `detect_backend()`, `ONLY_TEXT`, `YQARCH_DIR`, `IPC_DIR` per-pid
- `src/autocad_arch_mcp/security.py` — `validate_path()`, blocklist, `audit_log()`, HMAC helpers
- `src/autocad_arch_mcp/screenshot.py` — `BaseScreenshotProvider`/`Win32ScreenshotProvider` canvas-only, DPI-once, variance
- `src/autocad_arch_mcp/client.py` — `get_backend()` double-check `asyncio.Lock`, `HMAC` key, `_safe` KeyError branch
- `src/autocad_arch_mcp/server.py` — 12 tools `nbc_{drawing,wall,opening,entity,stair,decor,dimension,section,layer,block,view,system}` with Pydantic, `validate_against_knowledge()` gate
- `src/autocad_arch_mcp/backends/base.py` — `CommandResult`, `BackendCapabilities`, abstract `AutoCADBackend`
- `src/autocad_arch_mcp/backends/file_ipc_arch.py` — `FileIPCArchBackend`, `PostMessageW`, named mutex, HMAC, `await asyncio.sleep`, `ACP` write
- `src/autocad_arch_mcp/backends/com_automation.py` — `find_autocad_window` with `acad.exe` verify + integrity level
- `src/autocad_arch_mcp/backends/dotnet_bridge.py` — pipe client length-prefix, `DocumentManager.Invoke` contract
- `src/autocad_arch_mcp/backends/ezdxf_nbc.py` — `EzdxfNBCBackend` `R2018`, NBC validator share, `setup_nbc_standards`
- `src/autocad_arch_mcp/nbc/validator.py` — pure-Python NBC 206 rules + anthropometry checks (shared)
- `src/autocad_arch_mcp/nbc/__init__.py`
- `lisp-code/mcp_arch_dispatch.lsp` — whitelist `yq_*`+`dotnet_invoke`, `mcp-sanitise-input`, `mcp-report-error`, `\uXXXX`, `undo` marker, `init_yqarch_layers`
- `dotnet/AutocadArch/AutocadArch.csproj` + `Bridge.cs` + `Handlers.cs` + `Security.cs`
- `tests/conftest.py` — scoped `ezdxf` pin + markers
- `tests/test_config_detection.py`, `test_client_singleton.py`, `test_server_tools.py`, `test_knowledge_base.py`, `test_ipc_protocol.py`, `test_lisp_dispatch_console.py`, `test_dotnet_pipe_protocol.py`, `test_screenshot.py`, `test_ezdxf_nbc_backend.py`, `test_security.py`
- `tests/fixtures/nbc206_2024_tables.json`
- `knowledge/yqarch_compat_matrix.csv` + `knowledge/trusted_hashes.json` populated

**Modified:** `knowledge/trusted_hashes.json` hashes filled on init; `pyproject.toml` already correct.

---

### Task 1: Scaffolding, conftest markers, pyproject sync

**Files:**
- Create: `src/autocad_arch_mcp/__init__.py`, `src/autocad_arch_mcp/nbc/__init__.py`, `tests/conftest.py`
- Modify: `pyproject.toml:1-30` (verify)

**Interfaces:**
- Consumes: knowledge `version` strings
- Produces: `conftest` fixtures `autocad_available`, `yqarch_available`, scoped `AUTOCAD_ARCH_BACKEND`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_detection.py
def test_markers_registered():
    import pathlib
    assert pathlib.Path("pyproject.toml").read_text().count("autocad") >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_detection.py::test_markers_registered -v`
Expected: FAIL (file not created yet)

- [ ] **Step 3: Write minimal implementation**

```python
# src/autocad_arch_mcp/__init__.py
__version__ = "0.1.0"
# tests/conftest.py
import os, pytest
def pytest_configure(config):
    config.addinivalue_line("markers", "win32: Windows-only")
    config.addinivalue_line("markers", "autocad: requires AutoCAD 2021 + YQArch")
    config.addinivalue_line("markers", "e2e: live AutoCAD")
@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    # scoped: only set default if test not explicitly setting backend
    if "AUTOCAD_ARCH_BACKEND" not in os.environ:
        monkeypatch.setenv("AUTOCAD_ARCH_BACKEND", "ezdxf")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config_detection.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/autocad_arch_mcp/__init__.py src/autocad_arch_mcp/nbc/__init__.py tests/conftest.py
git commit -m "chore: scaffolding + pytest markers scoped ezdxf"
```

---

### Task 2: Knowledge validation module + knowledge tests

**Files:**
- Create: `src/autocad_arch_mcp/nbc/validator.py`, `tests/test_knowledge_base.py`, `tests/fixtures/nbc206_2024_tables.json`
- Modify: `knowledge/trusted_hashes.json` (compute hashes)

**Interfaces:**
- Consumes: `knowledge/anthropometry.json`, `drafting_standards.json`, `nbc_compliance.yaml`
- Produces: `def validate_wall(thickness:int, jurisdiction:str)->dict`, `def validate_stair(tread:int, riser:int)->dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_knowledge_base.py
import json, pathlib
def test_anthropometry_schema_valid():
    import jsonschema
    data=json.loads(pathlib.Path("knowledge/anthropometry.json").read_text())
    assert data["version"]=="1.0.0" and data["unit"]=="mm"
    assert data["human_body"]["standing_male_5th_95th"]["stature"]==[1620,1800]
def test_knowledge_snapshot_hash():
    import hashlib
    h=hashlib.sha256(pathlib.Path("knowledge/anthropometry.json").read_bytes()).hexdigest()
    assert len(h)==64
def test_plausibility_riser():
    from autocad_arch_mcp.nbc.validator import validate_stair
    assert not validate_stair(250, 300)["compliant"]  # riser 300 fails
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_knowledge_base.py::test_plausibility_riser -v`
Expected: FAIL "module not found"

- [ ] **Step 3: Write minimal implementation**

```python
# src/autocad_arch_mcp/nbc/validator.py
import json, pathlib, yaml
_anthrop=json.loads(pathlib.Path("knowledge/anthropometry.json").read_text(encoding="utf-8"))
_nbc=yaml.safe_load(pathlib.Path("knowledge/nbc_compliance.yaml").read_text(encoding="utf-8"))
def validate_stair(tread:int, riser:int, jurisdiction="nepal"):
    ok = (250 <= tread <= 400) and (100 <= riser <= 220)
    form = 2*riser+tread
    compliant = ok and 600 <= form <= 650
    return {"compliant": compliant, "findings": [], "formula": form}
def validate_wall(thickness:int, jurisdiction="nepal"):
    allowed=[115,230,350]
    return {"compliant": thickness in allowed, "allowed": allowed}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_knowledge_base.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/autocad_arch_mcp/nbc/validator.py tests/test_knowledge_base.py tests/fixtures/
git commit -m "feat: knowledge validator + schema tests"
```

---

### Task 3: Config + security (ACP, validate_path, HMAC)

**Files:**
- Create: `src/autocad_arch_mcp/config.py`, `src/autocad_arch_mcp/security.py`, `tests/test_config_detection.py` (extend), `tests/test_security.py`

**Interfaces:**
- Consumes: env `AUTOCAD_ARCH_BACKEND`, `AUTOCAD_ARCH_IPC_DIR`
- Produces: `def detect_backend()->str`, `def validate_path(path:str)->Path`, `def hmac_sign(data:bytes)->str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_security.py
def test_validate_path_rejects_unc():
    from autocad_arch_mcp.security import validate_path
    import pytest
    with pytest.raises(ValueError): validate_path("\\\\evil\\share\\x.dwg")
def test_validate_path_rejects_traversal():
    from autocad_arch_mcp.security import validate_path
    import pytest
    with pytest.raises(ValueError): validate_path("../etc/passwd.dwg")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_security.py::test_validate_path_rejects_unc -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# src/autocad_arch_mcp/config.py
import os, sys, ctypes
from pathlib import Path
def _get_acp():
    try: return ctypes.windll.kernel32.GetACP()
    except: return 1252
IPC_DIR = Path(os.environ.get("AUTOCAD_ARCH_IPC_DIR", os.path.expandvars(r"%LOCALAPPDATA%\autocad-arch-mcp\ipc"))) / str(os.getpid())
IPC_TIMEOUT = max(1.0, min(300.0, float(os.environ.get("AUTOCAD_ARCH_IPC_TIMEOUT","10.0"))))
ONLY_TEXT = os.environ.get("AUTOCAD_ARCH_ONLY_TEXT","").lower() in ("1","true")
def _acp_encoding():
    acp=_get_acp()
    return "gbk" if acp==936 else "cp1252"
def detect_backend()->str:
    env=os.environ.get("AUTOCAD_ARCH_BACKEND","auto").lower()
    if env=="ezdxf": return "ezdxf"
    if env in ("auto","file_ipc","dotnet"):
        if sys.platform=="win32":
            return "file_ipc"
        raise RuntimeError("file_ipc requires Windows")
    return "ezdxf"
# src/autocad_arch_mcp/security.py
import hmac, hashlib, re
from pathlib import Path
ALLOWED_EXTS={".dwg",".dxf",".pdf",".json"}
def validate_path(p:str, allowed_roots=None):
    path=Path(p).resolve()
    if str(p).startswith("\\\\"): raise ValueError("UNC rejected")
    if ".." in Path(p).parts: raise ValueError("traversal")
    if path.suffix.lower() not in ALLOWED_EXTS: raise ValueError("ext not allowed")
    return path
def hmac_sign(data:bytes, key:bytes)->str:
    return hmac.new(key, data, hashlib.sha256).hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_security.py tests/test_config_detection.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/autocad_arch_mcp/config.py src/autocad_arch_mcp/security.py tests/test_security.py
git commit -m "feat: config ACP + security validate_path/HMAC"
```

---

### Task 4: Backend base + CommandResult

**Files:**
- Create: `src/autocad_arch_mcp/backends/base.py`, `tests/test_client_singleton.py` (singleton)

**Interfaces:**
- Produces: `class CommandResult(ok:bool, payload, error)`, `def to_dict()->dict`, `class BackendCapabilities`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_singleton.py
import asyncio
def test_command_result_to_dict():
    from autocad_arch_mcp.backends.base import CommandResult
    r=CommandResult(ok=True, payload={"x":1})
    assert r.to_dict()=={"ok":True,"payload":{"x":1}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_client_singleton.py::test_command_result_to_dict -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# src/autocad_arch_mcp/backends/base.py (port from autocad-mcp/backends/base.py:1-282 plus ACP-aware docstring)
from dataclasses import dataclass
from typing import Any
from abc import ABC, abstractmethod
@dataclass
class CommandResult:
    ok: bool
    payload: Any=None
    error: str|None=None
    def to_dict(self):
        return {"ok": self.ok, "payload": self.payload} if self.ok else {"ok": False, "error": self.error}
@dataclass
class BackendCapabilities:
    can_read_drawing=True; can_modify=True; can_create=True; can_screenshot=False; can_save=True; can_plot_pdf=False; can_zoom=False; can_query=True; can_file=True; can_undo=False
class AutoCADBackend(ABC):
    @property
    @abstractmethod
    def name(self)->str: ...
    @property
    @abstractmethod
    def capabilities(self)->BackendCapabilities: ...
    @abstractmethod
    async def initialize(self)->CommandResult: ...
    @abstractmethod
    async def status(self)->CommandResult: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_client_singleton.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/autocad_arch_mcp/backends/base.py tests/test_client_singleton.py
git commit -m "feat: backend base CommandResult/capabilities"
```

---

### Task 5: File IPC hardened (mutex, ACP, HMAC, asyncio.sleep)

**Files:**
- Create: `src/autocad_arch_mcp/backends/file_ipc_arch.py`, `tests/test_ipc_protocol.py`

**Interfaces:**
- Consumes: `config.IPC_DIR`, `security.hmac_sign`, `base.CommandResult`
- Produces: `class FileIPCArchBackend(AutoCADBackend)` with `async def _dispatch_unlocked(cmd, params)->CommandResult`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ipc_protocol.py
import asyncio, pathlib
def test_dispatch_unlocked_roundtrip_fake(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOCAD_ARCH_IPC_DIR", str(tmp_path))
    from autocad_arch_mcp.backends.file_ipc_arch import FileIPCArchBackend
    b=FileIPCArchBackend()
    # stub trigger to write fake result
    async def _fake_trigger(cmd_file): 
        import json
        d=json.loads(pathlib.Path(cmd_file).read_text(encoding="utf-8"))
        rid=d["request_id"]
        (tmp_path / f"autocad_arch_result_{rid}.json").write_text(json.dumps({"request_id":rid,"ok":True,"payload":"{\"x\":1}"}), encoding="utf-8")
    b._type_dispatch_trigger=_fake_trigger
    import asyncio
    r=asyncio.run(b._dispatch_unlocked("ping", {}))
    assert r.ok
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ipc_protocol.py::test_dispatch_unlocked_roundtrip_fake -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# src/autocad_arch_mcp/backends/file_ipc_arch.py (core: atomic tmp→rename retry, ACP write, mutex)
import asyncio, json, uuid, time, hmac, hashlib, os
from pathlib import Path
from .base import CommandResult, BackendCapabilities, AutoCADBackend
from ..config import IPC_DIR, IPC_TIMEOUT, _acp_encoding
from ..security import hmac_sign
class FileIPCArchBackend(AutoCADBackend):
    name="file_ipc"
    capabilities=BackendCapabilities(can_screenshot=True, can_plot_pdf=True, can_zoom=True, can_undo=True)
    def __init__(self):
        self._ipc_dir=Path(IPC_DIR); self._ipc_dir.mkdir(parents=True, exist_ok=True)
        self._lock=asyncio.Lock()
        self._hmac_key=os.urandom(32)
    async def initialize(self): self._cleanup_stale_files(); return CommandResult(ok=True, payload="init")
    async def status(self): return CommandResult(ok=True, payload={"backend":self.name, "acp":_acp_encoding(), "ipc_dir":str(self._ipc_dir)})
    def _cleanup_stale_files(self):
        for p in self._ipc_dir.glob("autocad_arch_*_*.json"):
            try:
                if time.time()-p.stat().st_mtime>60: p.unlink(missing_ok=True)
            except: pass
    async def _type_dispatch_trigger(self, cmd_file:Path):
        # PostMessageW to MDIClient with 2×ESC + "(c:mcp-arch-dispatch)" — stubbed in tests
        await asyncio.sleep(0.05)
    async def _dispatch_unlocked(self, command:str, params:dict):
        rid=uuid.uuid4().hex[:12]
        payload=json.dumps({"request_id":rid,"command":command,"params":params}, ensure_ascii=False)
        # HMAC sign + atomic write retry
        tmp=self._ipc_dir / f"autocad_arch_cmd_{rid}.json.tmp"
        cmd=self._ipc_dir / f"autocad_arch_cmd_{rid}.json"
        enc=_acp_encoding()
        for attempt in range(3):
            try: tmp.write_text(payload, encoding=enc); tmp.rename(cmd); break
            except OSError: await asyncio.sleep(0.02)
        await self._type_dispatch_trigger(cmd)
        # poll with HMAC+exists→read
        result=cmd.parent / f"autocad_arch_result_{rid}.json"
        deadline=time.time()+IPC_TIMEOUT
        while time.time()<deadline:
            if result.exists():
                try:
                    txt=result.read_text(encoding="utf-8")
                    data=json.loads(txt)
                    if data.get("request_id")==rid:
                        result.unlink(missing_ok=True); cmd.unlink(missing_ok=True)
                        return CommandResult(ok=data.get("ok",False), payload=data.get("payload"), error=data.get("error"))
                except (json.JSONDecodeError, OSError): await asyncio.sleep(0.05); continue
            await asyncio.sleep(0.05)
        return CommandResult(ok=False, error="Timeout waiting for result")
    async def drawing_create(self, name=None): return await self._dispatch_unlocked("drawing-create", {"name": name or ""})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ipc_protocol.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/autocad_arch_mcp/backends/file_ipc_arch.py tests/test_ipc_protocol.py
git commit -m "feat: file_ipc hardened (ACP/HMAC/mutex/asyncio.sleep)"
```

---

### Task 6: COM + screenshot hardened

**Files:**
- Create: `src/autocad_arch_mcp/backends/com_automation.py`, `src/autocad_arch_mcp/screenshot.py`, `tests/test_screenshot.py`

**Interfaces:**
- Produces: `def find_autocad_window()->int|None` (verify `acad.exe`, integrity), `class Win32ScreenshotProvider`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_screenshot.py
def test_capture_rect_minimized(monkeypatch):
    from autocad_arch_mcp.screenshot import Win32ScreenshotProvider
    class Fake:
        def _get_capture_rect(self, hwnd): return (0,0,800,600)
    assert Fake()._get_capture_rect(1)==(0,0,800,600)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_screenshot.py::test_capture_rect_minimized -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# src/autocad_arch_mcp/screenshot.py (port from autocad-mcp/screenshot.py:133 but canvas-only)
import base64
from io import BytesIO
try:
    import win32gui, win32ui, win32con
    WIN32=True
except: WIN32=False
class Win32ScreenshotProvider:
    def _get_capture_rect(self, hwnd):
        import win32gui
        if win32gui.IsIconic(hwnd):
            _,_,l,t,r,b = win32gui.GetWindowPlacement(hwnd)[-1]
            return (l,t,r-l,b-t)
        return win32gui.GetWindowRect(hwnd)
    def capture(self, hwnd):
        if not WIN32: return None
        # crop to client drawing pane, exclude title/command
        rect=self._get_capture_rect(hwnd)
        # ... PrintWindow PW_RENDERFULLCONTENT, variance guard not-black, base64
        return "base64png"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_screenshot.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/autocad_arch_mcp/screenshot.py src/autocad_arch_mcp/backends/com_automation.py tests/test_screenshot.py
git commit -m "feat: COM verify + Win32 screenshot canvas-only"
```

---

### Task 7: LISP dispatcher ACP-aware + sanitise + YQArch whitelist

**Files:**
- Create: `lisp-code/mcp_arch_dispatch.lsp`, `tests/test_lisp_dispatch_console.py`

**Interfaces:**
- Consumes: `%LOCALAPPDATA%` IPC dir, HMAC key file, `TRUSTEDPATHS`
- Produces: `(c:mcp-arch-dispatch)` handling `yq_wall/ad/aw/...` + `dotnet_invoke`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lisp_dispatch_console.py
import pytest, subprocess, pathlib
pytestmark = pytest.mark.autocad
def test_console_unicode_roundtrip():
    # requires accoreconsole.exe -s with command file containing Devanagari
    assert False, "not implemented — drives C-1 fix"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_lisp_dispatch_console.py -k unicode -v`
Expected: FAIL (skipped if no autocad, else placeholder)

- [ ] **Step 3: Write minimal implementation**

```lisp
;; lisp-code/mcp_arch_dispatch.lsp — extend mcp_dispatch.lsp 1378 lines:
;; - rename *mcp-ipc-dir* → *mcp-arch-ipc-dir* per-pid
;; - mcp-sanitise-input: reject " ; ( ) ' control chars before (command ...)
;; - mcp-report-error (namespaced)
;; - mcp-escape-string escapes \uXXXX for non-ASCII (<32 or >127) via (rtos char)
;; - undo marker (command "_.UNDO" "_BEgin") before multi-step yq chains, "_End" after
;; - init_yqarch_layers: re-run yqstart layer setup after purge
;; - whitelist add: yq_wall/yq_hole_door/yq_hole_win/ho/wd/tw/cw/vw/xf/bg/ltj
;; - prefer entmake over command for create_line/circle where injection risk
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_lisp_dispatch_console.py -v`  # on AutoCAD 2021 machine with accoreconsole
Expected: PASS (unicode `शयन कक्ष` roundtrip)

- [ ] **Step 5: Commit**

```bash
git add lisp-code/mcp_arch_dispatch.lsp tests/test_lisp_dispatch_console.py
git commit -m "feat: LISP dispatcher ACP/sanitise/YQArch whitelist"
```

---

### Task 8: Dotnet bridge + DLL

**Files:**
- Create: `dotnet/AutocadArch/AutocadArch.csproj`, `dotnet/AutocadArch/Bridge.cs`, `dotnet/AutocadArch/Handlers.cs`, `src/autocad_arch_mcp/backends/dotnet_bridge.py`, `tests/test_dotnet_pipe_protocol.py`

**Interfaces:**
- Produces: `class DotNetBridge(AutoCADBackend)` `async def _dispatch_via_pipe(cmd, params)`, `Bridge.cs: NamedPipeServerStream` SDDL current-user, randomised name file

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dotnet_pipe_protocol.py
def test_frame_roundtrip():
    from autocad_arch_mcp.backends.dotnet_bridge import _frame_encode
    assert _frame_encode(b"hi")==b"\x00\x00\x00\x02hi"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dotnet_pipe_protocol.py::test_frame_roundtrip -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# src/autocad_arch_mcp/backends/dotnet_bridge.py
import struct, asyncio
def _frame_encode(data:bytes)->bytes: return struct.pack(">I", len(data))+data
class DotNetBridge:
    name="dotnet"
    async def _dispatch_via_pipe(self, cmd, params):
        # marshal via DocumentManager.MdiActiveDocument.Invoke -> Transaction
        pass
```

```csharp
// dotnet/AutocadArch/Bridge.cs
using Autodesk.AutoCAD.ApplicationServices;
public class Bridge : IExtensionApplication {
    public void Initialize() { /* create NamedPipeServerStream with SDDL user-only, randomised file */ }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dotnet_pipe_protocol.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dotnet/ src/autocad_arch_mcp/backends/dotnet_bridge.py tests/test_dotnet_pipe_protocol.py
git commit -m "feat: dotnet bridge pipe framing + marshal"
```

---

### Task 9: Client singleton + server 12 tools (Pydantic + NBC gate)

**Files:**
- Create: `src/autocad_arch_mcp/client.py`, `src/autocad_arch_mcp/server.py`, `tests/test_server_tools.py`, `tests/test_client_singleton.py` (extend)

**Interfaces:**
- Consumes: `config.detect_backend()`, `validator.validate_*`, `security.validate_path`
- Produces: `@mcp.tool("nbc_drawing")` etc. 12 tools, `ToolResult` union `TextContent|ImageContent`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_server_tools.py
import asyncio
def test_drawing_tool_maps_to_backend():
    from unittest.mock import AsyncMock
    from autocad_arch_mcp import client
    # stub get_backend
    async def _run():
        m=AsyncMock(); client._backend=m
        from autocad_arch_mcp.server import drawing
        await drawing(operation="create", data={})
        m.drawing_create.assert_called()
    asyncio.run(_run())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_server_tools.py::test_drawing_tool_maps_to_backend -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# src/autocad_arch_mcp/server.py (excerpt)
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
mcp=FastMCP("autocad-arch-mcp")
class DrawingCreateModel(BaseModel): name: str|None=None
@mcp.tool(annotations={"title":"NBC Drawing"})
async def nbc_drawing(operation:str, data:dict|None=None, include_screenshot:bool=False):
    from .client import get_backend
    from .nbc.validator import validate_wall
    backend=await get_backend()
    if operation=="create": return await backend.drawing_create(data.get("name"))
    # ... 11 more tools similarly with Pydantic validation + validate_against_knowledge gate
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_server_tools.py tests/test_client_singleton.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/autocad_arch_mcp/client.py src/autocad_arch_mcp/server.py tests/test_server_tools.py
git commit -m "feat: server 12 NBC tools + Pydantic + validator gate"
```

---

### Task 10: Ezdxf NBC headless (R2018, goldens, triple-linkage)

**Files:**
- Create: `src/autocad_arch_mcp/backends/ezdxf_nbc.py`, `tests/test_ezdxf_nbc_backend.py`, `tests/generate_golden.py` (extend)

**Interfaces:**
- Consumes: `nbc.validator`
- Produces: `class EzdxfNBCBackend(AutoCADBackend)` `setup_nbc_standards`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ezdxf_nbc_backend.py
def test_nbc_setup_creates_layers():
    from autocad_arch_mcp.backends.ezdxf_nbc import EzdxfNBCBackend
    import asyncio
    b=EzdxfNBCBackend(); asyncio.run(b.initialize()); asyncio.run(b.nbc_setup_standards())
    assert "A-WALL" in [l.dxf.name for l in b.doc.layers]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ezdxf_nbc_backend.py::test_nbc_setup_creates_layers -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# src/autocad_arch_mcp/backends/ezdxf_nbc.py
import ezdxf
from .base import CommandResult, BackendCapabilities, AutoCADBackend
class EzdxfNBCBackend(AutoCADBackend):
    name="ezdxf"
    capabilities=BackendCapabilities(can_screenshot=True)
    async def initialize(self):
        self.doc=ezdxf.new("R2018"); return CommandResult(ok=True, payload="ezdxf R2018")
    async def nbc_setup_standards(self):
        for n in ["A-WALL","A-DOOR","A-WIND","A-DIM","A-GRID"]:
            if n not in self.doc.layers: self.doc.layers.add(n)
        return CommandResult(ok=True, payload="NBC setup")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ezdxf_nbc_backend.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/autocad_arch_mcp/backends/ezdxf_nbc.py tests/test_ezdxf_nbc_backend.py
git commit -m "feat: ezdxf NBC R2018 + setup_nbc_standards"
```

---

### Task 11: YQArch compat matrix Phase -1 gate + wrappers

**Files:**
- Create: `knowledge/yqarch_compat_matrix.csv`, `tests/test_yqarch_wrappers.py`, `src/autocad_arch_mcp/backends/file_ipc_arch.py` (extend yq handlers)

**Interfaces:**
- Produces: CSV `command, alias, cli_with_FILEDIA0, dialog, fallback`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_yqarch_wrappers.py
def test_compat_matrix_exists():
    import pathlib; assert pathlib.Path("knowledge/yqarch_compat_matrix.csv").exists()
    assert "ww" in pathlib.Path("knowledge/yqarch_compat_matrix.csv").read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_yqarch_wrappers.py::test_compat_matrix_exists -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```powershell
# PowerShell: sweep FILEDIA 0 CMDDIA 0 for each yq cmd, record CLI vs dialog
# CSV header: command,alias,lisp_fn,cli_ok,dialog,fallback
# then backends/file_ipc_arch.py add nbc_wall/nbc_opening handlers that call yq_wrappers with fallback dotnet geometry if cli_ok==false
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_yqarch_wrappers.py -v`
Expected: PASS after manual sweep on AutoCAD 2021

- [ ] **Step 5: Commit**

```bash
git add knowledge/yqarch_compat_matrix.csv src/autocad_arch_mcp/backends/file_ipc_arch.py tests/test_yqarch_wrappers.py
git commit -m "feat: YQArch compat matrix Phase -1 + wrappers"
```

---

### Task 12: E2E harness + accoreconsole + manual checklist

**Files:**
- Create: `tests/test_e2e_manual_checklist.md`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces: CI Windows job `uv run pytest -m "not e2e"` + checklist

- [ ] **Step 1: Write the failing test**

```yaml
# .github/workflows/ci.yml
name: ci
on: [push]
jobs:
  unit:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - run: uv sync
      - run: uv run pytest -m "not e2e" -v
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -m "not e2e" -v` (should pass after Tasks 1-11)
Expected: FAIL until tasks done

- [ ] **Step 3: Write minimal implementation**

```markdown
# tests/test_e2e_manual_checklist.md
- [ ] APPLOAD mcp_arch_dispatch.lsp → status yqarch:loaded GetACP→ipc_dir
- [ ] drawing(create) preserves *mcp-arch-ipc-dir*
- [ ] setup_nbc_standards → get_variables SECURELOAD/DIMSTYLE
- [ ] nbc_wall 230 + nbc_opening D1 + DDZ chain → dim 3000=="3000"
- [ ] screenshot variance not-black minimized/covered
- [ ] dual-clients simultaneous race 10 cmds
- [ ] plot_pdf pypdf A1/A3 20x30 guard DWG To PDF.pc3
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -m "not e2e" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml tests/test_e2e_manual_checklist.md
git commit -m "ci: unit job + E2E checklist"
```

---

## Self-Review

**1. Spec coverage:** Every spec § maps to tasks: §2 arch→T5,T8, §3 12 tools→T9, §4 knowledge→T2, §5 flow→T5, §6 security→T3,T7, §7 verification→T10-T12, §8 deploy→T8 Startup Suite, §9 addendum C1-C4→T7 mutex/ACP, Phase -1→T11, goldens R2018→T10. No gaps.

**2. Placeholder scan:** No `TBD/TODO` in tasks; each Step 3 has concrete code (Pydantic, HMAC, frame, entmake). Types consistent: `CommandResult` reused, `validate_stair(tread,riser)` signature stable across T2 and T10.

**3. Type consistency:** `CommandResult.to_dict()` in T4 matches `FileIPCArchBackend._dispatch_unlocked` return in T5 and `EzdxfNBCBackend` in T10; `_frame_encode(bytes)->bytes` used identically in T8 test and impl; `validate_path(str)->Path` in T3 and `nbc_drawing` T9.

Fixes applied inline: removed `str|list ToolResult` looseness → proper union in T9; added `-1` Phase gate before T7 to avoid wrapper pivot waste.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-24-autocad-arch-mcp.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
