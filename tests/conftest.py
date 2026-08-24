import os

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "win32: Windows-only")
    config.addinivalue_line("markers", "autocad: requires AutoCAD 2021 + YQArch")
    config.addinivalue_line("markers", "e2e: live AutoCAD")


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    if "AUTOCAD_ARCH_BACKEND" not in os.environ:
        monkeypatch.setenv("AUTOCAD_ARCH_BACKEND", "ezdxf")
