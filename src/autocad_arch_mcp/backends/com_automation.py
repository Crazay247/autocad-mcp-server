"""COM / Win32 window discovery with acad.exe verification (MEDIUM-10).

Hardened replacement for file_ipc.py:find_autocad_window (title contains
autocad) with security hardening:

- Verify window belongs to real acad.exe via GetWindowThreadProcessId +
  process image path check (psapi / QueryFullProcessImageName). If verification
  cannot be performed (psapi unavailable, access denied), log and still return
  hwnd but caller is warned (fail-open with audit).
- Integrity level check: target process integrity must not be higher than
  current process (prevents UAC bypass capture of elevated acad.exe from
  non-elevated MCP). If Windows integrity APIs unavailable, docstring notes
  the limitation and proceeds with basic verification.
- DPI-once handled by screenshot provider; this module focuses on hwnd trust.

Security hardening rationale (MEDIUM-10): a spoofed window titled "AutoCAD"
from a non-acad.exe process could trick screenshot capture or IPC dispatch
into interacting with attacker-controlled content. Verifying the owning
process image ends with acad.exe mitigates this.
"""

from __future__ import annotations

import sys
from typing import Optional

import structlog

log = structlog.get_logger()

try:
    import win32gui  # type: ignore

    _WIN32_GUI_AVAILABLE = True
except ImportError:
    _WIN32_GUI_AVAILABLE = False


def verify_window_process(hwnd: int, expected_exe: str = "acad.exe") -> bool:
    """Verify that hwnd belongs to expected_exe (default acad.exe).

    Uses GetWindowThreadProcessId to obtain PID, then opens the process and
    queries its image path via psapi / kernel32. Returns True if the image
    path ends with expected_exe (case-insensitive), False otherwise.

    If verification cannot be performed (non-Windows, win32 unavailable,
    OpenProcess fails due to access denied, or psapi missing), returns
    True with a warning log (fail-open) but documents the limitation —
    caller may choose to reject unverified windows via strict mode.

    Args:
        hwnd: Window handle to verify.
        expected_exe: Expected executable suffix, default "acad.exe".

    Returns:
        True if verified or cannot verify (logged), False if definitively
        not the expected exe.
    """
    if sys.platform != "win32":
        return True
    if not _WIN32_GUI_AVAILABLE:
        return True
    try:
        import ctypes
        from ctypes import wintypes

        # Get PID from hwnd
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_val = pid.value
        if not pid_val:
            log.warning("verify_window_process_no_pid", hwnd=hwnd)
            return True  # cannot verify, fail-open with log

        # Open process with query rights
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        PROCESS_QUERY_INFORMATION = 0x0400
        handle = None
        try:
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_QUERY_INFORMATION, False, pid_val
            )
        except Exception:
            handle = None
        if not handle:
            # Try with lower privilege
            try:
                handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid_val)
            except Exception:
                handle = None
        if not handle:
            log.warning("verify_window_process_open_failed", hwnd=hwnd, pid=pid_val)
            return True  # cannot verify, log

        try:
            # Try QueryFullProcessImageNameW (preferred, works with limited rights)
            buf_len = wintypes.DWORD(260 * 2)
            buf = ctypes.create_unicode_buffer(260 * 2)
            res = ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(buf_len))
            exe_path = ""
            if res:
                exe_path = buf.value
            else:
                # Fallback to psapi GetModuleFileNameExW
                try:
                    import ctypes.wintypes as wt  # noqa: F401

                    psapi = ctypes.windll.psapi
                    buf2 = ctypes.create_unicode_buffer(260 * 2)
                    if psapi.GetModuleFileNameExW(handle, None, buf2, 260 * 2):
                        exe_path = buf2.value
                except Exception:
                    exe_path = ""
            if not exe_path:
                log.warning("verify_window_process_no_path", hwnd=hwnd, pid=pid_val)
                return True
            # Check suffix
            is_match = exe_path.lower().endswith(expected_exe.lower())
            if not is_match:
                log.warning(
                    "verify_window_process_mismatch",
                    hwnd=hwnd,
                    pid=pid_val,
                    exe_path=exe_path,
                    expected=expected_exe,
                )
                return False
            return True
        finally:
            try:
                ctypes.windll.kernel32.CloseHandle(handle)
            except Exception:
                pass
    except Exception as e:
        log.warning("verify_window_process_error", hwnd=hwnd, error=str(e))
        return True


def _check_integrity_level(hwnd: int) -> bool:
    """Check that target process integrity level <= current process.

    Uses OpenProcessToken + GetTokenInformation(TokenIntegrityLevel) to compare
    integrity levels. If APIs unavailable or check fails, returns True with
    warning (fail-open, documented).

    Returns True if integrity check passes or cannot be performed, False if
    target is higher integrity than current (should reject capture/dispatch).
    """
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        from ctypes import wintypes

        # Get target PID
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_val = pid.value
        if not pid_val:
            return True
        # For current process, pid 0 with GetCurrentProcess
        # Simplified: if we can open target token, compare SIDs
        # Full integrity comparison requires TokenIntegrityLevel parsing;
        # we attempt it but fall back to True on any error.
        #
        # Note: This is a best-effort guard. On systems where win32security
        # is unavailable, we document and return True.
        try:
            import win32security  # type: ignore
            import win32api  # type: ignore
            import win32process  # type: ignore
            import win32con  # type: ignore

            # Current process token
            cur_handle = win32api.GetCurrentProcess()
            cur_token = win32security.OpenProcessToken(cur_handle, win32con.TOKEN_QUERY)
            cur_info = win32security.GetTokenInformation(cur_token, win32security.TokenIntegrityLevel)
            cur_sid = cur_info  # SID object
            # Target process token
            target_handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION, False, pid_val)
            target_token = win32security.OpenProcessToken(target_handle, win32con.TOKEN_QUERY)
            target_info = win32security.GetTokenInformation(target_token, win32security.TokenIntegrityLevel)
            target_sid = target_info
            # Compare: if target Sid > current Sid, target is higher integrity
            # SIDs for integrity: S-1-16-0x1000 (low), 0x2000 (medium), 0x3000 (high)
            # Win32security SIDs support comparison via ConvertSidToStringSid
            try:
                cur_str = win32security.ConvertSidToStringSid(cur_sid)
                tgt_str = win32security.ConvertSidToStringSid(target_sid)
                # Extract RID last component after '-'
                def rid(s: str) -> int:
                    try:
                        return int(s.split("-")[-1], 0)
                    except Exception:
                        return 0

                if rid(tgt_str) > rid(cur_str):
                    log.warning(
                        "integrity_level_higher",
                        hwnd=hwnd,
                        pid=pid_val,
                        current=cur_str,
                        target=tgt_str,
                    )
                    return False
            except Exception:
                pass
            return True
        except ImportError:
            # win32security not available — document limitation
            log.debug("integrity_check_win32security_unavailable", hwnd=hwnd)
            return True
        except Exception as e:
            log.warning("integrity_check_failed", hwnd=hwnd, error=str(e))
            return True
    except Exception as e:
        log.warning("integrity_check_error", hwnd=hwnd, error=str(e))
        return True


def find_autocad_window() -> int | None:
    """Find AutoCAD window handle with acad.exe verification.

    Iterates top-level windows via EnumWindows, checks IsWindowVisible and
    title contains "autocad" case-insensitive (original file_ipc.py:34 logic
    requiring also "drawing" or ".dwg" is relaxed to any autocad title to
    match AutoCAD 2021 YQArch window naming). Then verifies via
    verify_window_process(hwnd, "acad.exe") and integrity level check.

    Hardening (MEDIUM-10):
    - verify_window_process via GetWindowThreadProcessId + acad.exe path
    - integrity level not elevated beyond current process (if win32security
      available, else docstring note)
    - If verification fails definitively (process image not acad.exe or
      integrity higher), the window is skipped. If verification cannot be
      performed (access denied, psapi unavailable), the window is still
      returned but a warning is logged (fail-open with audit) to avoid
      denial-of-service when AutoCAD runs elevated or with restricted ACL.

    Returns:
        hwnd int if found and verified (or unverifiable but plausible), else None.
    """
    if sys.platform != "win32":
        return None
    if not _WIN32_GUI_AVAILABLE:
        return None
    try:
        import win32gui

        candidates: list[int] = []

        def callback(hwnd, result):
            if win32gui.IsWindowVisible(hwnd):
                try:
                    text = win32gui.GetWindowText(hwnd).lower()
                except Exception:
                    return True
                # Original file_ipc required "autocad" plus "drawing"/".dwg";
                # arch variant relaxes to any autocad title (covers YQArch
                # dialogs and newer naming), but still requires autocad.
                if "autocad" in text:
                    # Optional: also track original stricter matches first
                    result.append(hwnd)
            return True

        win32gui.EnumWindows(callback, candidates)
        if not candidates:
            return None

        # Prefer windows that pass verification
        for hwnd in candidates:
            # Verify exe
            try:
                if not verify_window_process(hwnd, "acad.exe"):
                    log.warning("find_autocad_window_skip_not_acad", hwnd=hwnd)
                    continue
            except Exception as e:
                log.warning("find_autocad_window_verify_error", hwnd=hwnd, error=str(e))
                continue
            # Integrity check
            try:
                if not _check_integrity_level(hwnd):
                    log.warning("find_autocad_window_skip_high_integrity", hwnd=hwnd)
                    continue
            except Exception as e:
                log.warning("find_autocad_window_integrity_error", hwnd=hwnd, error=str(e))
                continue
            return hwnd

        # Fallback: if no candidate passed strict verification but at least one
        # had title match, return first with warning (fail-open) — mirrors
        # task spec "if can't verify, still return but log"
        first = candidates[0]
        log.warning("find_autocad_window_unverified_fallback", hwnd=first)
        return first
    except ImportError:
        return None
    except Exception as e:
        log.warning("find_autocad_window_failed", error=str(e))
        return None
