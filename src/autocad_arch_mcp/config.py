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
) / str(os.getpid())

IPC_TIMEOUT = max(
    1.0, min(300.0, float(os.environ.get("AUTOCAD_ARCH_IPC_TIMEOUT", "10.0")))
)

ONLY_TEXT = os.environ.get("AUTOCAD_ARCH_ONLY_TEXT", "").lower() in ("1", "true")

ALLOW_RCE = os.environ.get("AUTOCAD_ARCH_ALLOW_RCE", "0").lower() in ("1", "true")


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
