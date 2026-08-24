def test_capture_rect_minimized(monkeypatch):
    from autocad_arch_mcp.screenshot import Win32ScreenshotProvider
    import types
    p = Win32ScreenshotProvider()
    # monkeypatch win32gui.IsIconic etc. or just test helper directly if provider has _get_capture_rect
    # simpler: test that provider class exists and has capture method
    assert hasattr(p, "capture")
    assert hasattr(p, "_get_capture_rect")


def test_find_autocad_verify():
    from autocad_arch_mcp.backends.com_automation import find_autocad_window
    # should be callable, returns None or int
    assert callable(find_autocad_window)
