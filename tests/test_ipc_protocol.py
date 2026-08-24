import asyncio
import json
import pathlib
import inspect


def test_dispatch_unlocked_roundtrip_fake(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOCAD_ARCH_IPC_DIR", str(tmp_path))
    from autocad_arch_mcp.backends.file_ipc_arch import FileIPCArchBackend

    b = FileIPCArchBackend()

    async def _fake_trigger(cmd_file):
        # cmd_file may be Path or str; handle both
        p = pathlib.Path(cmd_file)
        # Try utf-8 first, fallback to ACP encoding
        try:
            txt = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            from autocad_arch_mcp.config import _acp_encoding
            txt = p.read_text(encoding=_acp_encoding())
        d = json.loads(txt)
        rid = d["request_id"]
        payload = json.dumps({"request_id": rid, "ok": True, "payload": '{"x":1}'})
        # Write to same directory as cmd_file (robust for pid suffix handling)
        (p.parent / f"autocad_arch_result_{rid}.json").write_text(payload, encoding="utf-8")
        # Also satisfy legacy test expectation that writes to tmp_path root
        (tmp_path / f"autocad_arch_result_{rid}.json").write_text(payload, encoding="utf-8")

    b._type_dispatch_trigger = _fake_trigger
    r = asyncio.run(b._dispatch_unlocked("ping", {}))
    assert r.ok


def test_acp_encoding():
    from autocad_arch_mcp.config import _acp_encoding

    assert _acp_encoding() in ("gbk", "cp1252")


def test_asyncio_sleep_used():
    src = pathlib.Path("src/autocad_arch_mcp/backends/file_ipc_arch.py").read_text(encoding="utf-8")
    assert "asyncio.sleep" in src, "file must use asyncio.sleep"
    # Ensure trigger does not use blocking time.sleep
    # If time.sleep appears at all, it must not be in _type_dispatch_trigger
    # For hardening M6, no time.sleep should remain
    assert "time.sleep" not in src, "file must not use time.sleep (use asyncio.sleep)"


def test_hmac_key_exists():
    import os

    # Use a temp IPC dir to avoid polluting
    os.environ.pop("AUTOCAD_ARCH_IPC_DIR", None)
    from autocad_arch_mcp.backends.file_ipc_arch import FileIPCArchBackend

    b = FileIPCArchBackend()
    # Check attribute exists
    assert hasattr(b, "_hmac_key"), "FileIPCArchBackend must have _hmac_key"
    key = getattr(b, "_hmac_key")
    assert isinstance(key, bytes), "_hmac_key must be bytes"
    assert len(key) == 32, "_hmac_key must be 32 bytes (os.urandom(32))"
    # Also verify hmac_sign helper works
    from autocad_arch_mcp.security import hmac_sign

    sig = hmac_sign(b"test-payload", key)
    assert isinstance(sig, str) and len(sig) == 64
