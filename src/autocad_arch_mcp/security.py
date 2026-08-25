import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path

import structlog

ALLOWED_EXTS = {".dwg", ".dxf", ".pdf", ".json"}

log = structlog.get_logger()


def validate_path(p: str, allowed_roots=None):
    path = Path(p).resolve()
    if str(p).startswith("\\\\"):
        raise ValueError("UNC rejected")
    if ".." in Path(p).parts:
        raise ValueError("traversal")
    if path.suffix.lower() not in ALLOWED_EXTS:
        raise ValueError("ext not allowed")
    if allowed_roots:
        roots = [Path(r).resolve() for r in allowed_roots]
        inside = False
        for r in roots:
            try:
                # Python 3.9+ is_relative_to, fallback via relative_to
                if hasattr(path, "is_relative_to"):
                    if path.is_relative_to(r):
                        inside = True
                        break
                else:
                    path.relative_to(r)
                    inside = True
                    break
            except ValueError:
                continue
        if not inside:
            raise ValueError(f"path outside allowed roots: {roots}")
    return path


def hmac_sign(data: bytes, key: bytes) -> str:
    return hmac.new(key, data, hashlib.sha256).hexdigest()


AUDIT_LOG = Path(os.path.expandvars(r"%LOCALAPPDATA%\autocad-arch-mcp\security_audit.log"))


def audit_log(tool, operation, params):
    """Append audit entry to AUDIT_LOG (was no-op)."""
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {"ts": time.time(), "tool": tool, "operation": operation, "params": params}
        with AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        try:
            log.warning("audit_log_failed", error=str(e))
        except Exception:
            pass


def verify_trusted_hashes(trusted_path=None) -> dict:
    """Verify knowledge snapshot hashes against trusted_hashes.json.

    Computes sha256 of each pinned file where hash != PENDING; logs warning on mismatch.
    VLX entries keep PENDING_COMPUTE_ON_INIT placeholder (documented, skipped).
    Returns dict of per-file status for audit.
    """
    # locate trusted_hashes.json: cwd knowledge/ then package-relative fallbacks
    candidates = []
    if trusted_path:
        candidates.append(Path(trusted_path))
    candidates.extend(
        [
            Path("knowledge/trusted_hashes.json"),
            Path(__file__).resolve().parents[2] / "knowledge" / "trusted_hashes.json",
            Path(__file__).resolve().parents[3] / "knowledge" / "trusted_hashes.json",
        ]
    )
    trusted_file = next((p for p in candidates if p.exists()), None)
    if not trusted_file:
        log.warning("verify_trusted_hashes_no_file", candidates=[str(c) for c in candidates])
        return {}
    try:
        trusted = json.loads(trusted_file.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("verify_trusted_hashes_read_failed", error=str(e))
        return {}
    results: dict = {}
    # knowledge_snapshots: map filename -> expected hash
    snapshots = trusted.get("knowledge_snapshots", {})
    base_candidates = [
        Path("knowledge"),
        trusted_file.parent,
        Path(__file__).resolve().parents[2] / "knowledge",
    ]
    for fname, expected in snapshots.items():
        if expected.startswith("PENDING"):
            results[fname] = {"expected": expected, "skipped": True, "ok": True}
            continue
        # locate actual file
        fpath = None
        for base in base_candidates:
            cand = base / fname
            if cand.exists():
                fpath = cand
                break
        if not fpath:
            results[fname] = {"expected": expected, "actual": None, "ok": False, "error": "file not found"}
            log.warning("trusted_hash_missing_file", file=fname, expected=expected)
            continue
        actual = hashlib.sha256(fpath.read_bytes()).hexdigest()
        ok = actual.lower() == expected.lower()
        results[fname] = {"expected": expected, "actual": actual, "ok": ok, "skipped": False}
        if not ok:
            log.warning("trusted_hash_mismatch", file=fname, expected=expected, actual=actual)
    # yqarch_vlx stays PENDING — documented as intentionally not pinned until empirical sweep
    return results


# Run verification at import (fail-open: log warning, don't raise)
try:
    _trusted_check = verify_trusted_hashes()
except Exception:
    pass
