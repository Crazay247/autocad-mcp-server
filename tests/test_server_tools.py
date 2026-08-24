def test_server_imports():
    import autocad_arch_mcp.server as s
    assert hasattr(s, "mcp")
    assert hasattr(s, "nbc_drawing")


def test_server_has_12_tools():
    import autocad_arch_mcp.server as s

    for name in [
        "nbc_drawing",
        "nbc_wall",
        "nbc_opening",
        "nbc_entity",
        "nbc_stair",
        "nbc_decor",
        "nbc_dimension",
        "nbc_section",
        "nbc_layer",
        "nbc_block",
        "nbc_view",
        "nbc_system",
    ]:
        assert hasattr(s, name), f"missing {name}"
