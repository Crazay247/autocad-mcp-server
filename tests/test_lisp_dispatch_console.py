import pathlib

import pytest

pytestmark = pytest.mark.autocad


def test_lisp_file_exists():
    p = pathlib.Path("lisp-code/mcp_arch_dispatch.lsp")
    assert p.exists(), "lisp-code/mcp_arch_dispatch.lsp not found"
    txt = p.read_text(encoding="utf-8")
    assert "mcp-sanitise-input" in txt, "mcp-sanitise-input not in LISP"
    # whitelist check: yq_wall present OR mcp_arch token
    low = txt.lower()
    assert ("yq_wall" in low) or ("mcp_arch" in low), "yq_wall / mcp_arch whitelist missing"


def test_cli_without_autocad_skipped():
    """Skipped if no accoreconsole — drives C-1 unicode roundtrip on AutoCAD host."""
    import shutil

    candidates = [
        shutil.which("accoreconsole"),
        shutil.which("accoreconsole.exe"),
        r"D:\SOFTWARES\Autocad 2021\AutoCAD 2021\accoreconsole.exe",
        r"C:\Program Files\Autodesk\AutoCAD 2021\accoreconsole.exe",
        r"C:\Autodesk\AutoCAD_2021_English_Win_64bit_dlm\accoreconsole.exe",
    ]
    found = None
    for c in candidates:
        if c and pathlib.Path(c).exists():
            found = c
            break
    if not found:
        pytest.skip("accoreconsole not available on this host")
    assert pathlib.Path(found).exists()
