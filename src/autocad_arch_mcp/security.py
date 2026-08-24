import hashlib
import hmac
import os
import re
from pathlib import Path

ALLOWED_EXTS = {".dwg", ".dxf", ".pdf", ".json"}


def validate_path(p: str, allowed_roots=None):
    path = Path(p).resolve()
    if str(p).startswith("\\\\"):
        raise ValueError("UNC rejected")
    if ".." in Path(p).parts:
        raise ValueError("traversal")
    if path.suffix.lower() not in ALLOWED_EXTS:
        raise ValueError("ext not allowed")
    return path


def hmac_sign(data: bytes, key: bytes) -> str:
    return hmac.new(key, data, hashlib.sha256).hexdigest()


AUDIT_LOG = Path(os.path.expandvars(r"%LOCALAPPDATA%\autocad-arch-mcp\security_audit.log"))


def audit_log(tool, operation, params):
    pass
