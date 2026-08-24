import asyncio


def test_command_result_to_dict():
    from autocad_arch_mcp.backends.base import CommandResult

    r = CommandResult(ok=True, payload={"x": 1})
    assert r.to_dict() == {"ok": True, "payload": {"x": 1}}


def test_command_result_error():
    from autocad_arch_mcp.backends.base import CommandResult

    r = CommandResult(ok=False, error="fail")
    assert r.to_dict() == {"ok": False, "error": "fail"}


def test_backend_capabilities_defaults():
    from autocad_arch_mcp.backends.base import BackendCapabilities

    c = BackendCapabilities()
    assert c.can_create is True
