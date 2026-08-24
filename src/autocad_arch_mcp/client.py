"""Client singleton — double-checked asyncio.Lock + backend selection.

Mirrors autocad-mcp/client.py pattern with NBC extensions:
- Detects backend via config.detect_backend()
- Lazily instantiates FileIPCArchBackend / DotNetBridge / EzdxfNBCBackend
- HMAC session key lives inside backend; this module caches singleton
- Provides _json / _error / _safe helpers and screenshot hook
"""

from __future__ import annotations

import asyncio
import functools
import json

from .config import detect_backend

_backend = None
_init_lock = asyncio.Lock()


def _json(data: dict) -> str:
    """Serialize payload to JSON string (ensure_ascii False for Devanagari)."""
    return json.dumps(data, ensure_ascii=False, default=str)


def _error(message: str) -> str:
    """Serialize error envelope to JSON string."""
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False, default=str)


def _safe(func):
    """Decorator: map KeyError/ValueError to JSON error envelope.

    KeyError → "Missing param", ValueError → its message, other Exception → message.
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except KeyError as e:
            return _error(f"Missing param: {e}")
        except ValueError as e:
            return _error(str(e))
        except Exception as e:
            return _error(str(e))

    return wrapper


async def add_screenshot_if_available(result: dict, include_screenshot: bool) -> dict:
    """Stub: attach screenshot if requested and backend supports it.

    If include_screenshot is False, returns result unchanged.
    If True, attempts backend.get_screenshot() and injects 'screenshot' key.
    Never raises — returns original result on any failure.
    """
    if not include_screenshot:
        return result
    if not isinstance(result, dict):
        return result
    try:
        backend = await get_backend()
        if hasattr(backend, "get_screenshot"):
            scr = await backend.get_screenshot()
            # scr is CommandResult
            if scr and getattr(scr, "ok", False) and getattr(scr, "payload", None):
                out = dict(result)
                out["screenshot"] = scr.payload
                return out
    except Exception:
        pass
    return result


async def get_backend():
    """Double-checked locking singleton backend getter.

    Detects backend via config.detect_backend():
      - "file_ipc" -> FileIPCArchBackend
      - "dotnet"   -> DotNetBridge (fallback to FileIPCArchBackend if not available)
      - "ezdxf"    -> EzdxfNBCBackend (fallback to FileIPCArchBackend if module missing)

    Calls backend.initialize() and caches on success; raises RuntimeError
    if initialize returns not ok.
    """
    global _backend
    if _backend is not None:
        return _backend
    async with _init_lock:
        if _backend is not None:
            return _backend
        backend_name = detect_backend()
        if backend_name == "file_ipc":
            from .backends.file_ipc_arch import FileIPCArchBackend

            backend = FileIPCArchBackend()
        elif backend_name == "dotnet":
            try:
                from .backends.dotnet_bridge import DotNetBridge

                backend = DotNetBridge()
            except Exception:
                # fallback if dotnet bridge not available on this platform
                from .backends.file_ipc_arch import FileIPCArchBackend

                backend = FileIPCArchBackend()
        else:  # ezdxf
            try:
                from .backends.ezdxf_nbc import EzdxfNBCBackend

                backend = EzdxfNBCBackend()
            except ImportError:
                # ezdxf_nbc not yet implemented (Task 10) — fallback to file_ipc on win32
                try:
                    from .backends.file_ipc_arch import FileIPCArchBackend

                    backend = FileIPCArchBackend()
                except Exception as e:
                    raise RuntimeError(f"ezdxf backend requested but not available: {e}")
            except Exception as e:
                # any other import error, fallback
                from .backends.file_ipc_arch import FileIPCArchBackend

                backend = FileIPCArchBackend()

        result = await backend.initialize()
        # result is CommandResult
        ok = getattr(result, "ok", False)
        if not ok:
            err = getattr(result, "error", "unknown")
            raise RuntimeError(f"Backend {backend_name} initialize failed: {err}")
        _backend = backend
        return _backend


def _reset_backend_for_tests() -> None:
    """Reset singleton — for tests only."""
    global _backend
    _backend = None
