"""NBC 206:2024 validator — pure-Python, shared by MCP server and ezdxf backend.

Consumes: knowledge/anthropometry.json, nbc_compliance.yaml (version 1.0.0 mm)
Produces: validate_stair, validate_wall (+ extras: validate_door_width, validate_room_area)
Security: no I/O beyond knowledge loads at import; no RCE.
"""

from __future__ import annotations

import json
import pathlib

import yaml

# ── knowledge snapshots loaded once at import (idempotent) ──────────────
# Spec requires cwd-relative Path("knowledge/..."); keep that but also
# support package-relative fallback so installed/editable imports work
# when pytest's cwd differs.


def _load_json_knowledge(name: str) -> dict:
    for p in (
        pathlib.Path(f"knowledge/{name}"),
        pathlib.Path(__file__).resolve().parents[3] / "knowledge" / name,
        pathlib.Path(__file__).resolve().parents[4] / "knowledge" / name,
    ):
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _load_yaml_knowledge(name: str) -> dict:
    for p in (
        pathlib.Path(f"knowledge/{name}"),
        pathlib.Path(__file__).resolve().parents[3] / "knowledge" / name,
        pathlib.Path(__file__).resolve().parents[4] / "knowledge" / name,
    ):
        if p.exists():
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {}


_anthrop = _load_json_knowledge("anthropometry.json")
_nbc = _load_yaml_knowledge("nbc_compliance.yaml")
_draft = _load_json_knowledge("drafting_standards.json")

# Fallback inline defaults if knowledge files missing (keeps validator importable in CI)
if not _anthrop:
    _anthrop = {
        "version": "1.0.0",
        "unit": "mm",
        "building_category_minima": {
            "residential": {"habitable_room_area_m2": {"NBC206_2024_nepal": 4.0}}
        },
    }
if not _nbc:
    _nbc = {"version": "1.0.0", "unit": "mm"}
if not _draft:
    _draft = {"version": "1.0.0", "unit": "mm", "line_weights": {"ratio": "1:2:4", "groups": [], "mapping_1_100": {}}}

# ── core validators (spec § Task 2 Step 3 verbatim, extended) ────────────


def _nbc_stair_limits():
    """Read NBC stair limits from nbc_compliance.yaml; fallback to NBC206:2024 defaults."""
    # defaults per NBC206:2024 (residential)
    tread_min, tread_max, riser_min, riser_max = 250, 400, 100, 190
    try:
        for item in _nbc.get("NBC206_2024_content_triggers", []):
            if isinstance(item, dict) and "staircase" in item:
                sc = item["staircase"]
                tread_min = int(sc.get("tread_min", tread_min))
                # riser_max is the NBC residential limit (was 220 in anthropometry, corrected to 190 per NBC206)
                riser_max = int(sc.get("riser_max", riser_max))
                # optional overrides
                if "riser_min" in sc:
                    riser_min = int(sc["riser_min"])
                if "tread_max" in sc:
                    tread_max = int(sc["tread_max"])
                break
    except Exception:
        pass
    return tread_min, tread_max, riser_min, riser_max


def validate_stair(tread: int, riser: int, jurisdiction: str = "nepal") -> dict:
    """NBC Table 4 + 2R+T formula.

    - tread 250-400, riser 100-190 (NBC206:2024 residential; reads riser_max from nbc_compliance.yaml)
    - formula 2*riser+tread ∈ [600,650] (comfortable 630)
    - jurisdiction currently nepal-only, kept for future india toggle
    """
    t_min, t_max, r_min, r_max = _nbc_stair_limits()
    ok = (t_min <= tread <= t_max) and (r_min <= riser <= r_max)
    form = 2 * riser + tread
    compliant = ok and 600 <= form <= 650
    findings: list[str] = []
    if tread < t_min:
        findings.append(f"tread {tread} < min {t_min}")
    elif tread > t_max:
        findings.append(f"tread {tread} > max {t_max}")
    if riser < r_min:
        findings.append(f"riser {riser} < min {r_min}")
    elif riser > r_max:
        findings.append(f"riser {riser} > max {r_max}")
    if not 600 <= form <= 650:
        findings.append(f"2R+T={form} outside [600,650]")
    # keep findings empty when compliant to match spec's `[]`, but populate on fail for audit
    # spec's minimal returns findings=[] always; we expose findings when non-compliant
    # for backward-compat keep empty when compliant
    if compliant:
        findings = []
    return {"compliant": compliant, "findings": findings, "formula": form}


def validate_wall(thickness: int, jurisdiction: str = "nepal", layer: str | None = None, lineweight: float | int | str | None = None) -> dict:
    """Nepal loadbearing thickness per nbc_compliance.yaml + thickness->layer->weight triad per drafting_standards.json."""
    allowed = [115, 230, 350]
    # future: read dynamically from _nbc if present
    try:
        for rule in _nbc.get("validation_rules", []):
            if rule.get("id") == "wall_thickness_nepal_loadbearing":
                allowed = list(rule.get("allowed", allowed))
                break
    except Exception:
        pass
    findings: list[str] = []
    compliant = thickness in allowed
    if thickness not in allowed:
        findings.append(f"thickness {thickness} not in {allowed} (cite NBC206 Table4)")
    # Triad: thickness -> expected layer per NCS
    THICKNESS_LAYER = {115: "A-WALL-115", 230: "A-WALL-230", 350: "A-WALL"}
    expected_layer = THICKNESS_LAYER.get(thickness)
    # Triad: drafting mapping_1_100 wall_outline_cut 0.5mm
    expected_weight = 0.5
    try:
        mapping = _draft.get("line_weights", {}).get("mapping_1_100", {}).get("wall_outline_cut", {})
        expected_weight = float(mapping.get("weight", 0.5))
    except Exception:
        pass
    if layer is not None and expected_layer and layer != expected_layer:
        compliant = False
        findings.append(f"layer {layer} inconsistent with thickness {thickness} -> expected {expected_layer} (cite drafting_standards mapping_1_100)")
    if lineweight is not None:
        try:
            lw_val = float(str(lineweight).strip()) if isinstance(lineweight, str) and "." in str(lineweight) else float(lineweight) / 100 if float(lineweight) > 5 else float(lineweight)
            # normalize lineweight param: 50 -> 0.5, 0.5 -> 0.5
            if lw_val > 5:
                lw_val = lw_val / 100
            if abs(lw_val - expected_weight) > 0.01:
                compliant = False
                findings.append(f"lineweight {lineweight} != expected {expected_weight} for wall (cite IS962 line_weights)")
        except Exception:
            pass
    return {
        "compliant": compliant,
        "allowed": allowed,
        "findings": findings,
        "expected_layer": expected_layer,
        "expected_lineweight": expected_weight,
    }


def validate_layer(name: str) -> dict:
    """Validate NCS layer name against drafting_standards + NBC layers."""
    # Allowed: NBC 17 + NCS plugin_set 19 (union)
    allowed = [
        "A-WALL", "A-WALL-230", "A-WALL-115", "A-DOOR", "A-WIND", "A-DIM", "A-DIM-1", "A-DIM-2", "A-DIM-3",
        "A-GRID", "A-ANNO", "A-ANNO-TEXT", "A-FURN", "A-STRS", "A-NORTH", "G-TTLB", "V-PORT",
        "A-FLOR", "A-FLOR-HATCH", "A-WALL-PATT", "A-WALL-FULL", "A-GLAZ", "A-SECT", "A-SECT-HATCH",
    ]
    try:
        plugin = _draft.get("layers_AIA_NCS", {}).get("plugin_set", {})
        if isinstance(plugin, dict):
            allowed = list(set(allowed) | set(plugin.keys()))
        elif isinstance(plugin, list):
            # some versions store as list
            allowed = list(set(allowed) | set(plugin))
    except Exception:
        pass
    # Also include nbc layers_to_create
    try:
        for item in _nbc.get("layers_to_create", []):
            if item not in allowed:
                allowed.append(item)
    except Exception:
        pass
    compliant = name in allowed
    findings: list[str] = []
    if not compliant:
        findings.append(f"layer {name} not in allowed NCS/NBC set {sorted(allowed)} (cite NCS V6 + NBC layers_to_create)")
    if name == "0" or name.upper() == "DEFPOINTS":
        compliant = False
        findings.append(f"layer {name} forbidden (cite drafting_standards: use A-* NCS, not 0/DEFPOINTS)")
    return {"compliant": compliant, "findings": findings, "allowed": sorted(allowed)}


def validate_lineweight(weight, context: str = "wall_outline_cut") -> dict:
    """Validate lineweight per drafting_standards line_weights mapping_1_100."""
    try:
        mapping = _draft.get("line_weights", {}).get("mapping_1_100", {})
        ctx = mapping.get(context, {})
        expected = float(ctx.get("weight", 0.5))
    except Exception:
        expected = 0.5
    try:
        # normalize input: 50 -> 0.5, "0.50" -> 0.5, 0.25 -> 0.25
        if isinstance(weight, str) and "." in weight:
            val = float(weight)
        elif isinstance(weight, (int, float)) and float(weight) > 5:
            val = float(weight) / 100
        else:
            val = float(weight)
        compliant = abs(val - expected) < 0.01
        findings: list[str] = []
        if not compliant:
            findings.append(f"lineweight {weight} -> {val} != expected {expected} for {context} (cite drafting_standards line_weights)")
        return {"compliant": compliant, "expected": expected, "value": val, "findings": findings}
    except Exception as e:
        return {"compliant": False, "findings": [str(e)]}


def validate_door_width(width: int, jurisdiction: str = "nepal") -> dict:
    """Door clear width 600-1500 mm (yqarch 600-5400 clipped to NBC plausible)."""
    lo, hi = 600, 1500
    compliant = lo <= width <= hi
    findings: list[str] = []
    if not compliant:
        findings.append(f"door width {width} outside [{lo},{hi}]")
    return {"compliant": compliant, "allowed_range": [lo, hi], "width": width, "findings": findings}


def validate_room_area(area: float, jurisdiction: str = "nepal") -> dict:
    """Habitable room area minima per anthropometry building_category_minima.

    Nepal NBC206 4.0 m2, India SP7 9.5 m2, comfortable 12.0 — jurisdiction toggle.
    """
    try:
        minima = _anthrop["building_category_minima"]["residential"]["habitable_room_area_m2"]
        if jurisdiction == "india":
            min_area = float(minima.get("SP7_2016_india", 9.5))
        elif jurisdiction == "comfortable":
            min_area = float(minima.get("comfortable", 12.0))
        else:
            min_area = float(minima.get("NBC206_2024_nepal", 4.0))
    except Exception:
        min_area = 4.0 if jurisdiction == "nepal" else (9.5 if jurisdiction == "india" else 12.0)
    compliant = area >= min_area
    findings: list[str] = []
    if not compliant:
        findings.append(f"area {area} < min {min_area} for {jurisdiction}")
    return {"compliant": compliant, "min_area": min_area, "area": area, "findings": findings}
