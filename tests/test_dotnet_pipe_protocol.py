def test_frame_roundtrip():
    from autocad_arch_mcp.backends.dotnet_bridge import _frame_encode, _frame_decode
    assert _frame_decode(_frame_encode(b"hi")) == b"hi"


def test_frame_length_prefix():
    from autocad_arch_mcp.backends.dotnet_bridge import _frame_encode
    import struct

    data = b"test"
    framed = _frame_encode(data)
    assert struct.unpack(">I", framed[:4])[0] == len(data)


def test_bridge_exists():
    import pathlib

    assert pathlib.Path("dotnet/AutocadArch/Bridge.cs").exists()
