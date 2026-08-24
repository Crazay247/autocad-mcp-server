import pathlib


def test_markers_registered():
    assert pathlib.Path("pyproject.toml").read_text(encoding="utf-8").count("autocad") >= 1


def test_package_version():
    import autocad_arch_mcp

    assert autocad_arch_mcp.__version__ == "0.1.0"
