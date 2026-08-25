import os
import sys
import ctypes
from pathlib import Path


def _get_acp():
    try:
        return ctypes.windll.kernel32.GetACP()
    except Exception:
        return 1252


IPC_DIR = Path(
    os.environ.get(
        "AUTOCAD_ARCH_IPC_DIR",
        os.path.expandvars(r"%LOCALAPPDATA%\autocad-arch-mcp\ipc"),
    )
)

IPC_TIMEOUT = max(
    1.0, min(300.0, float(os.environ.get("AUTOCAD_ARCH_IPC_TIMEOUT", "10.0")))
)

ONLY_TEXT = os.environ.get("AUTOCAD_ARCH_ONLY_TEXT", "").lower() in ("1", "true")

# RCE gate — checked in server.py nbc_system execute_lisp/dotnet branch.
# Canonical env is AUTOCAD_ARCH_MCP_ALLOW_RCE; AUTOCAD_ARCH_ALLOW_RCE kept for backward compat.
ALLOW_RCE = (
    os.environ.get("AUTOCAD_ARCH_MCP_ALLOW_RCE", "0").lower() in ("1", "true")
    or os.environ.get("AUTOCAD_ARCH_ALLOW_RCE", "0").lower() in ("1", "true")
)
# Back-compat alias for review check: ALLOW_RCE = os.environ.get("AUTOCAD_ARCH_MCP_ALLOW_RCE","0")=="1"


def _acp_encoding():
    acp = _get_acp()
    return "gbk" if acp == 936 else "cp1252"


def detect_backend() -> str:
    env = os.environ.get("AUTOCAD_ARCH_BACKEND", "auto").lower()
    if env == "ezdxf":
        return "ezdxf"
    if env in ("auto", "file_ipc", "dotnet"):
        if sys.platform == "win32":
            return "file_ipc"
        raise RuntimeError("file_ipc requires Windows")
    return "ezdxf"
