import pathlib


def test_ci_yaml_exists():
    assert pathlib.Path(".github/workflows/ci.yml").exists()
    assert 'uv run pytest -m "not e2e"' in pathlib.Path(".github/workflows/ci.yml").read_text()


def test_manual_checklist_exists():
    assert pathlib.Path("tests/test_e2e_manual_checklist.md").exists()
    txt = pathlib.Path("tests/test_e2e_manual_checklist.md").read_text(encoding="utf-8")
    assert "APPLOAD mcp_arch_dispatch.lsp" in txt
    assert "accoreconsole" in txt.lower() or "accoreconsole.exe" in txt.lower()
