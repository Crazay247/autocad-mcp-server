def test_validate_path_rejects_unc():
    from autocad_arch_mcp.security import validate_path
    import pytest
    with pytest.raises(ValueError): validate_path("\\\\evil\\share\\x.dwg")


def test_validate_path_rejects_traversal():
    from autocad_arch_mcp.security import validate_path
    import pytest
    with pytest.raises(ValueError): validate_path("../etc/passwd.dwg")


def test_validate_path_allows_normal():
    from autocad_arch_mcp.security import validate_path
    p = validate_path("C:/Users/Predator/test.dwg")
    assert p.suffix.lower() == ".dwg"


def test_hmac_sign_deterministic():
    from autocad_arch_mcp.security import hmac_sign
    key = b"secretkey1234567890secretkey12345678"
    data = b"hello world"
    assert hmac_sign(data, key) == hmac_sign(data, key)
    # also check different data differs
    assert hmac_sign(b"other", key) != hmac_sign(data, key)
