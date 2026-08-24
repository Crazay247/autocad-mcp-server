"""Screenshot providers: Win32 window capture and canvas-only hardening.

Hardened port of autocad-mcp screenshot.py (Win32 PrintWindow, GetWindowPlacement
minimized normal rect, PW_RENDERFULLCONTENT) with security and robustness fixes:

- DPI-awareness set once via ctypes.windll.user32.SetProcessDPIAware() guarded
  by class var _dpi_set (also _dpi_awareness_initialized alias).
- _get_capture_rect(hwnd) returns minimized normal rect via GetWindowPlacement
  when IsIconic, else GetWindowRect (MEDIUM-10).
- capture(hwnd) uses PrintWindow with PW_RENDERFULLCONTENT, crops to drawing
  canvas (excludes title bar / command line chrome), variance guard not-black,
  base64-encoded PNG, returns None on PrintWindow failure.
- WIN32_AVAILABLE flag for headless / non-Windows fallback.

Security note: caller should verify hwnd via com_automation.verify_window_process
before capturing (MEDIUM-10: verify window belongs to real acad.exe).
"""

from __future__ import annotations

import base64
import io
import sys
from abc import ABC, abstractmethod

import structlog

log = structlog.get_logger()

# --- Win32 availability flag ---
try:
    import win32con  # noqa: F401
    import win32gui  # noqa: F401
    import win32ui  # noqa: F401

    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


class BaseScreenshotProvider(ABC):
    """Abstract screenshot provider (alias for ScreenshotProvider).

    Provides common interface for headless / matplotlib / Win32 providers.
    """

    @abstractmethod
    def capture(self, hwnd: int | None = None) -> str | None:
        """Return base64-encoded PNG, or None if capture fails."""


# Backwards-compat alias used by autocad-mcp
class ScreenshotProvider(BaseScreenshotProvider):
    pass


class NullScreenshotProvider(BaseScreenshotProvider):
    """No-op provider — always returns None."""

    def capture(self, hwnd: int | None = None) -> str | None:
        return None


class Win32ScreenshotProvider(BaseScreenshotProvider):
    """Capture AutoCAD window via Win32 PrintWindow — canvas-only hardened.

    Hardening:
    - DPI-awareness initialized once (ctypes SetProcessDPIAware guarded by
      _dpi_set / _dpi_awareness_initialized).
    - _get_capture_rect(hwnd): when minimized (IsIconic) returns the normal
      placement rect (placement[-1]) rather than the minimized 0x0 rect.
    - capture(hwnd): PrintWindow with PW_RENDERFULLCONTENT (captures even when
      occluded), crops to drawing canvas to exclude title bar / command line
      chrome, variance guard rejects blank / not-black captures, returns
      base64 PNG string.
    """

    _dpi_set = False
    _dpi_awareness_initialized = False  # alias for compat

    def __init__(self, hwnd: int | None = None):
        self._hwnd = hwnd

    @classmethod
    def _ensure_dpi_awareness(cls) -> None:
        """Set process DPI awareness once (guarded by _dpi_set)."""
        if cls._dpi_set or cls._dpi_awareness_initialized:
            return
        try:
            import ctypes

            user32 = ctypes.windll.user32
            # Prefer Per-Monitor V2, fallback to shcore, then SetProcessDPIAware
            try:
                if hasattr(user32, "SetProcessDpiAwarenessContext"):
                    dpi_aware_v2 = ctypes.c_void_p(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
                    if user32.SetProcessDpiAwarenessContext(dpi_aware_v2):
                        cls._dpi_set = True
                        cls._dpi_awareness_initialized = True
                        return
            except Exception:
                pass
            try:
                shcore = ctypes.windll.shcore
                PROCESS_PER_MONITOR_DPI_AWARE = 2
                if shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE) == 0:
                    cls._dpi_set = True
                    cls._dpi_awareness_initialized = True
                    return
            except Exception:
                pass
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
        except Exception:
            pass
        finally:
            cls._dpi_set = True
            cls._dpi_awareness_initialized = True

    def _get_capture_rect(self, hwnd: int | None = None) -> tuple[int, int, int, int]:
        """Return window rect to capture.

        When the window is minimized (IsIconic), GetWindowRect returns a
        minimized placeholder. Instead return the normal placement rect
        (placement[-1]) from GetWindowPlacement, matching autocad-mcp
        screenshot.py:119-131 hardened behavior.
        """
        import win32gui

        target = hwnd if hwnd is not None else self._hwnd
        if target is None:
            raise ValueError("hwnd required for _get_capture_rect")
        if win32gui.IsIconic(target):
            placement = win32gui.GetWindowPlacement(target)
            # placement[-1] is the normal rect (rcNormalPosition)
            normal_rect = placement[-1]
            # Validate non-zero dimensions; fallback to GetWindowRect if degenerate
            width = normal_rect[2] - normal_rect[0]
            height = normal_rect[3] - normal_rect[1]
            if width > 0 and height > 0:
                return normal_rect  # type: ignore[return-value]
        return win32gui.GetWindowRect(target)  # type: ignore[return-value]

    def _crop_to_canvas(self, img):
        """Crop full window image to drawing canvas (exclude title/command chrome).

        AutoCAD window includes non-canvas chrome: title bar (~30px), ribbon,
        status bar / command line (~40-60px) and window borders (~8px). We crop
        to the central drawing area using proportional insets tuned for
        1920x1080+ AutoCAD 2021 layout. This is a best-effort heuristic; exact
        client rect could be obtained via GetClientRect + ClientToScreen, but
        PrintWindow returns the full window bitmap so we must crop.
        """
        try:
            w, h = img.size
            # Heuristic canvas insets: 8px border, 30px title+ribbon top, 50px command+status bottom
            # Left/right also 8px. Values are conservative to preserve canvas content.
            left = 8
            top = 70  # title (30) + ribbon/tabs (~40)
            right = w - 8
            bottom = h - 50  # command line + status bar
            # Guard degenerate crop
            if right - left < 100 or bottom - top < 100:
                return img
            # Clamp to image bounds
            left = max(0, left)
            top = max(0, top)
            right = min(w, right)
            bottom = min(h, bottom)
            if right <= left or bottom <= top:
                return img
            return img.crop((left, top, right, bottom))
        except Exception:
            return img

    def _is_blank(self, img, variance_threshold: float = 10.0) -> bool:
        """Variance guard: reject blank / near-black captures.

        Computes grayscale variance; low variance indicates uniform (blank or
        minimized window not captured). Returns True if image should be
        considered blank (caller should return None).
        """
        try:
            # Convert to grayscale and compute variance
            gray = img.convert("L")
            # Use histogram or pixel stats for variance
            # Simple variance via PIL ImageStat
            from PIL import ImageStat

            stat = ImageStat.Stat(gray)
            # stat.var is list with one element for L mode
            var = stat.var[0] if stat.var else 0
            # Also reject near-black (mean < 10) as PrintWindow failure mode
            mean = stat.mean[0] if stat.mean else 0
            if var < variance_threshold:
                log.warning("win32_screenshot_low_variance", variance=var, mean=mean)
                return True
            if mean < 5:  # near-black
                log.warning("win32_screenshot_near_black", mean=mean, variance=var)
                return True
            return False
        except Exception as e:
            log.warning("win32_screenshot_variance_check_failed", error=str(e))
            return False

    def capture(self, hwnd: int | None = None) -> str | None:
        """Capture window via PrintWindow PW_RENDERFULLCONTENT, canvas-crop, base64.

        Args:
            hwnd: Window handle to capture. If None, uses self._hwnd from
                  constructor (for compat with autocad-mcp FileIPCBackend).

        Returns:
            Base64-encoded PNG string, or None on failure (not Windows,
            WIN32 not available, PrintWindow returns 0, bad dimensions,
            or variance guard blank).
        """
        if not WIN32_AVAILABLE:
            return None
        if sys.platform != "win32":
            return None
        target = hwnd if hwnd is not None else self._hwnd
        if target is None:
            return None
        try:
            import ctypes

            import win32gui
            import win32ui
            from PIL import Image

            self._ensure_dpi_awareness()

            rect = self._get_capture_rect(target)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]

            if width <= 0 or height <= 0:
                log.warning("win32_screenshot_bad_dimensions", width=width, height=height)
                return None

            hwnd_dc = None
            mfc_dc = None
            save_dc = None
            bitmap = None

            try:
                hwnd_dc = win32gui.GetWindowDC(target)
                mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
                save_dc = mfc_dc.CreateCompatibleDC()

                bitmap = win32ui.CreateBitmap()
                bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
                save_dc.SelectObject(bitmap)

                PW_RENDERFULLCONTENT = 0x00000002
                result = ctypes.windll.user32.PrintWindow(
                    target,
                    save_dc.GetSafeHdc(),
                    PW_RENDERFULLCONTENT,
                )
                if result != 1:
                    # PrintWindow returns 0 on failure (also handles HWND=0 guard)
                    log.warning("win32_printwindow_failed", flag=PW_RENDERFULLCONTENT, result=result)
                    return None

                bmpinfo = bitmap.GetInfo()
                bmpstr = bitmap.GetBitmapBits(True)

                img = Image.frombuffer(
                    "RGB",
                    (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
                    bmpstr,
                    "raw",
                    "BGRX",
                    0,
                    1,
                )

                # Crop to drawing canvas (exclude title/command chrome)
                img = self._crop_to_canvas(img)

                # Variance guard: reject blank / not-black captures
                if self._is_blank(img):
                    # Return None for blank captures (caller can fallback)
                    # For debugging, still encode but log — here we return None
                    # to satisfy hardened spec: variance guard not-black.
                    # If caller prefers fallback, they can catch None.
                    return None

                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                return base64.b64encode(buf.read()).decode("ascii")
            finally:
                if bitmap is not None:
                    try:
                        win32gui.DeleteObject(bitmap.GetHandle())
                    except Exception:
                        pass
                if save_dc is not None:
                    try:
                        save_dc.DeleteDC()
                    except Exception:
                        pass
                if mfc_dc is not None:
                    try:
                        mfc_dc.DeleteDC()
                    except Exception:
                        pass
                if hwnd_dc is not None:
                    try:
                        win32gui.ReleaseDC(target, hwnd_dc)
                    except Exception:
                        pass

        except Exception as e:
            log.warning("win32_screenshot_failed", error=str(e))
            return None
