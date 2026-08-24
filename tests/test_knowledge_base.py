"""Task 2 — knowledge validation + schema tests (TDD).

Mandatory 3 tests from plan § Task 2 Step 1 (verbatim) plus spirit extras:
- bounds for riser 100-220 tread 250-400 (with formula 2R+T 600-650)
- door width 600-1500
- load idempotent (repeated validator calls + knowledge snapshot hash stability)
"""

import hashlib
import json
import pathlib


def test_anthropometry_schema_valid():
    import jsonschema

    data = json.loads(pathlib.Path("knowledge/anthropometry.json").read_text(encoding="utf-8"))
    assert data["version"] == "1.0.0" and data["unit"] == "mm"
    assert data["human_body"]["standing_male_5th_95th"]["stature"] == [1620, 1800]


def test_knowledge_snapshot_hash():
    h = hashlib.sha256(pathlib.Path("knowledge/anthropometry.json").read_bytes()).hexdigest()
    assert len(h) == 64


def test_plausibility_riser():
    from autocad_arch_mcp.nbc.validator import validate_stair

    assert not validate_stair(250, 300)["compliant"]  # riser 300 fails


# ── extra tests from plan spirit (keep mandatory 3 above, these are additive) ──


def test_stair_bounds_tread_riser():
    """Tread 250-400, riser 100-220, formula 2R+T 600-650 (NBC206 + anthropometry)."""
    from autocad_arch_mcp.nbc.validator import validate_stair

    # valid NBC residential: tread 250 riser 190 => 2*190+250=630 compliant
    assert validate_stair(250, 190)["compliant"] is True
    # valid middle: tread 300 riser 170 => 640
    assert validate_stair(300, 170)["compliant"] is True
    # tread too small (200 < 250) => not compliant even if formula would be ok
    assert not validate_stair(200, 175)["compliant"]
    # tread too large (>400)
    assert not validate_stair(450, 150)["compliant"]
    # riser too small (<100)
    assert not validate_stair(300, 90)["compliant"]
    # riser too large (>220) — also fails formula but first gate is bounds
    assert not validate_stair(300, 300)["compliant"]
    # formula out of range despite in-bounds: 2*100+400=600 edge PASS, 2*220+250=690 FAIL
    assert validate_stair(400, 100)["compliant"] is True  # 600 lower edge
    assert not validate_stair(250, 220)["compliant"]  # 690 >650
    # formula value exposed
    r = validate_stair(250, 190)
    assert r["formula"] == 630


def test_door_width_bounds():
    """Door width 600-1500 mm (yqarch_reference + NBC)."""
    from autocad_arch_mcp.nbc.validator import validate_door_width

    assert validate_door_width(600)["compliant"] is True  # lower edge
    assert validate_door_width(900)["compliant"] is True  # bedroom internal
    assert validate_door_width(1500)["compliant"] is True  # upper edge
    assert not validate_door_width(599)["compliant"]
    assert not validate_door_width(1501)["compliant"]
    assert not validate_door_width(5400)["compliant"]  # yqarch max but not plausible


def test_validate_wall_allowed():
    """Wall thickness Nepal loadbearing per nbc_compliance.yaml."""
    from autocad_arch_mcp.nbc.validator import validate_wall

    for good in [115, 230, 350]:
        assert validate_wall(good)["compliant"] is True
    for bad in [100, 120, 200, 240, 360]:
        assert not validate_wall(bad)["compliant"]
    # allowed list exposed
    assert validate_wall(230)["allowed"] == [115, 230, 350]


def test_load_idempotent():
    """Repeated loads/calls must be stable (knowledge file + validator)."""
    from autocad_arch_mcp.nbc.validator import validate_stair, validate_wall

    # validator pure functions — same inputs => same outputs
    a = validate_stair(250, 190)
    b = validate_stair(250, 190)
    assert a == b
    c = validate_wall(230)
    d = validate_wall(230)
    assert c == d
    # knowledge file hash stable across two reads
    p = pathlib.Path("knowledge/anthropometry.json")
    h1 = hashlib.sha256(p.read_bytes()).hexdigest()
    h2 = hashlib.sha256(p.read_bytes()).hexdigest()
    assert h1 == h2 and len(h1) == 64


def test_nbc_fixture_exists():
    """Fixture tests/fixtures/nbc206_2024_tables.json minimal smoke."""
    p = pathlib.Path("tests/fixtures/nbc206_2024_tables.json")
    assert p.exists(), "fixture missing — Task 2 requires tests/fixtures/nbc206_2024_tables.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["version"] == "2024"
    assert data["stair"]["res_tread_min"] == 250
    assert data["stair"]["res_riser_max"] == 190
