def test_compat_matrix_exists():
    import pathlib; assert pathlib.Path("knowledge/yqarch_compat_matrix.csv").exists()
    assert "ww" in pathlib.Path("knowledge/yqarch_compat_matrix.csv").read_text(encoding="utf-8")

def test_file_ipc_has_yq_handlers():
    import pathlib
    txt=pathlib.Path("src/autocad_arch_mcp/backends/file_ipc_arch.py").read_text(encoding="utf-8")
    assert "yq-wall" in txt or "yq_wall" in txt or "yq_wall" in txt.lower()
