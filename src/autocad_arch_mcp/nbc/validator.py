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


# ── composite scoring (0-100) + additional validators for strong instruction ──


def validate_light_vent(window_area: float, floor_area: float, hills: bool = True) -> dict:
    """Light 1/10 hills 1/8 other, vent 1/16, hospitals 1/8 per nbc_compliance light_ventilation."""
    try:
        ratio = window_area / floor_area if floor_area > 0 else 0
        exp = 0.10 if hills else 0.125  # 1/10 vs 1/8
        compliant = ratio >= exp
        findings: list[str] = []
        if not compliant:
            findings.append(f"window/floor {ratio:.3f} < {exp:.3f} ({'1/10 hills' if hills else '1/8 other'} cite NBC S3.3)")
        # vent: at least half of light? simplified
        vent_ok = ratio >= 0.0625  # 1/16
        if not vent_ok:
            findings.append(f"vent ratio {ratio:.3f} < 0.0625 (1/16 cite NBC)")
        return {"compliant": compliant and vent_ok, "ratio": ratio, "expected": exp, "findings": findings}
    except Exception as e:
        return {"compliant": False, "findings": [str(e)]}


def validate_circulation(corridor_width: float, travel_distance: float, hills: bool = True) -> dict:
    """Corridor 2000 India / Table3 Nepal, travel 30000/40000 per NBC."""
    findings: list[str] = []
    compliant = True
    if corridor_width < 2000:
        compliant = False
        findings.append(f"corridor {corridor_width} < 2000 (cite NBC corridor_min)")
    limit = 30000 if not hills else 30000  # simplified 30m, 40m external
    if travel_distance > limit:
        compliant = False
        findings.append(f"travel {travel_distance} > {limit} (cite NBC travel_max)")
    return {"compliant": compliant, "findings": findings}


def validate_vastu(room: str, quadrant: str, vastu_enabled: bool = False) -> dict:
    """Vastu guidance: NE kitchen SW master, NE entry, Brahmasthana void. Only if enabled."""
    if not vastu_enabled:
        return {"compliant": True, "findings": [], "note": "vastu disabled (secular NBC-only)"}
    ideal = {"kitchen": "NE", "master": "SW", "entry": "NE", "toilet": "NW", "living": "N"}
    exp = ideal.get(room.lower())
    findings: list[str] = []
    compliant = True
    if exp and quadrant.upper() != exp:
        compliant = False
        findings.append(f"vastu: {room} in {quadrant} expected {exp} (opt-in, weight 10)")
    return {"compliant": compliant, "findings": findings, "expected": exp}


# Weights sum 100 per system-prompt rubric
SCORE_WEIGHTS = {
    "wall_thickness": 20,
    "wall_triad": 15,
    "stair": 15,
    "door": 5,
    "room_area": 10,
    "light_vent": 10,
    "lineweight": 10,
    "layer_naming": 5,
    "circulation": 5,
    "screenshot": 5,
}


def score_drawing(features: dict) -> dict:
    """Composite 0-100 score. features: dict with keys like thickness, layer, lineweight, tread, riser, door_width, room_area, window_area, floor_area, hills, corridor_width, travel_distance, layers_ok, screenshot_ok etc."""
    total = 0
    breakdown: dict[str, int] = {}
    all_findings: list[str] = []
    severities: list[str] = []

    # Wall thickness 20
    t = features.get("thickness")
    if t is not None:
        r = validate_wall(int(t), layer=features.get("layer"), lineweight=features.get("lineweight"))
        s = SCORE_WEIGHTS["wall_thickness"] if r["compliant"] and not any("thickness" in f for f in r["findings"]) else 0
        # partial if only thickness ok but triad fails -> separate bucket
        breakdown["wall_thickness"] = s
        if r["findings"]:
            all_findings.extend(r["findings"])
            severities.append("critical" if s == 0 else "major")
        total += s
    else:
        breakdown["wall_thickness"] = SCORE_WEIGHTS["wall_thickness"]

    # Wall triad 15 (layer/weight)
    layer = features.get("layer")
    lw = features.get("lineweight")
    if t is not None and layer is not None:
        r = validate_wall(int(t), layer=layer, lineweight=lw)
        # if thickness ok but triad fails -> deduct
        if any("layer" in f or "lineweight" in f for f in r["findings"]):
            breakdown["wall_triad"] = 0
            all_findings.extend([f for f in r["findings"] if "layer" in f or "lineweight" in f])
            severities.append("major")
        else:
            breakdown["wall_triad"] = SCORE_WEIGHTS["wall_triad"]
            total += SCORE_WEIGHTS["wall_triad"]
    else:
        breakdown["wall_triad"] = SCORE_WEIGHTS["wall_triad"]
        total += SCORE_WEIGHTS["wall_triad"] if t is None else 0

    # Stair 15
    if "tread" in features and "riser" in features:
        r = validate_stair(int(features["tread"]), int(features["riser"]))
        s = SCORE_WEIGHTS["stair"] if r["compliant"] else 0
        breakdown["stair"] = s
        total += s
        if r["findings"]:
            all_findings.extend(r["findings"])
            severities.append("major" if s == 0 else "minor")
    else:
        breakdown["stair"] = SCORE_WEIGHTS["stair"]
        total += SCORE_WEIGHTS["stair"]  # no stair -> neutral

    # Door 5
    if "door_width" in features:
        r = validate_door_width(int(features["door_width"]))
        s = SCORE_WEIGHTS["door"] if r["compliant"] else 0
        breakdown["door"] = s
        total += s
        if r["findings"]:
            all_findings.extend(r["findings"])
    else:
        breakdown["door"] = SCORE_WEIGHTS["door"]
        total += SCORE_WEIGHTS["door"]

    # Room area 10
    if "room_area" in features:
        r = validate_room_area(float(features["room_area"]), jurisdiction=features.get("jurisdiction", "nepal"))
        s = SCORE_WEIGHTS["room_area"] if r["compliant"] else 0
        breakdown["room_area"] = s
        total += s
        if r["findings"]:
            all_findings.extend(r["findings"])
    else:
        breakdown["room_area"] = SCORE_WEIGHTS["room_area"]
        total += SCORE_WEIGHTS["room_area"]

    # Light/vent 10
    if "window_area" in features and "floor_area" in features:
        r = validate_light_vent(float(features["window_area"]), float(features["floor_area"]), hills=features.get("hills", True))
        s = SCORE_WEIGHTS["light_vent"] if r["compliant"] else 0
        breakdown["light_vent"] = s
        total += s
        if r["findings"]:
            all_findings.extend(r["findings"])
    else:
        breakdown["light_vent"] = SCORE_WEIGHTS["light_vent"]
        total += SCORE_WEIGHTS["light_vent"]

    # Lineweight 10 (standalone)
    if "lineweight" in features and "context" in features:
        r = validate_lineweight(features["lineweight"], context=features["context"])
        s = SCORE_WEIGHTS["lineweight"] if r["compliant"] else 0
        breakdown["lineweight"] = s
        total += s
        if r["findings"]:
            all_findings.extend(r["findings"])
    else:
        breakdown["lineweight"] = SCORE_WEIGHTS["lineweight"]
        total += SCORE_WEIGHTS["lineweight"]

    # Layer naming 5
    if "layer" in features:
        r = validate_layer(str(features["layer"]))
        s = SCORE_WEIGHTS["layer_naming"] if r["compliant"] else 0
        breakdown["layer_naming"] = s
        total += s
        if r["findings"]:
            all_findings.extend(r["findings"])
    else:
        breakdown["layer_naming"] = SCORE_WEIGHTS["layer_naming"]
        total += SCORE_WEIGHTS["layer_naming"]

    # Circulation 5
    if "corridor_width" in features or "travel_distance" in features:
        r = validate_circulation(float(features.get("corridor_width", 2000)), float(features.get("travel_distance", 0)))
        s = SCORE_WEIGHTS["circulation"] if r["compliant"] else 0
        breakdown["circulation"] = s
        total += s
        if r["findings"]:
            all_findings.extend(r["findings"])
    else:
        breakdown["circulation"] = SCORE_WEIGHTS["circulation"]
        total += SCORE_WEIGHTS["circulation"]

    # Screenshot 5
    if "screenshot_ok" in features:
        s = SCORE_WEIGHTS["screenshot"] if features["screenshot_ok"] else 0
        breakdown["screenshot"] = s
        total += s
        if not features["screenshot_ok"]:
            all_findings.append("screenshot variance fail (not-black check)")
    else:
        breakdown["screenshot"] = SCORE_WEIGHTS["screenshot"]
        total += SCORE_WEIGHTS["screenshot"]

    # Cap at 100
    total = min(100, total)
    compliant = total >= 85
    severity = "critical" if total < 50 else "major" if total < 85 else "minor" if total < 95 else "ok"
    return {"score": total, "compliant": compliant, "findings": all_findings, "breakdown": breakdown, "severity": severity}


# ── Hama gold composite (95 gate for plot) ──


def validate_section(scale: str, has_section_line: bool, has_hatch: bool) -> dict:
    """Section at 1:20/1:50 needs cut line extra-wide 0.7 dash-dot + hatch AR-BRSTD/AR-CONC per Hama 1:5."""
    findings: list[str] = []
    compliant = True
    if scale in ("1:20", "1:10", "1:5") and not has_section_line:
        compliant = False
        findings.append(f"section {scale} missing cut line extra-wide 0.7 dash-dot (cite Hama A020 1:5)")
    if has_hatch is False and scale in ("1:20", "1:5"):
        compliant = False
        findings.append("section hatch missing AR-BRSTD/AR-CONC (cite IS962 Table7 + Hama Wall 1:5)")
    return {"compliant": compliant, "findings": findings}


def validate_hatch(pattern: str, scale: float, detail_scale: str = "1:100") -> dict:
    """Hatch pattern per IS962 Table7 + Hama scale discipline AR-SAND 0.3@1:5 vs ANSI31 118@1:275."""
    allowed = ["AR-BRSTD", "AR-CONC", "ANSI31", "ANSI32", "AR-SAND", "DOLMIT", "CLAY", "EARTH", "SOLID", "AR-B816", "GRAVEL"]
    compliant = pattern.upper() in [a.upper() for a in allowed]
    findings: list[str] = []
    if not compliant:
        findings.append(f"hatch {pattern} not in Hama/IS962 {allowed}")
    # Scale discipline: 1:5 wall hatches 0.3-25, 1:275 plan 100+
    if detail_scale == "1:5" and pattern.upper() in ("AR-SAND", "ANSI31", "CLAY") and not (0.2 <= scale <= 30):
        compliant = False
        findings.append(f"hatch {pattern} scale {scale} wrong for {detail_scale} (Hama 0.3-25)")
    if detail_scale == "1:275" and pattern.upper() == "ANSI31" and not (80 <= scale <= 150):
        compliant = False
        findings.append(f"hatch ANSI31 scale {scale} wrong for 1:275 (Hama 118)")
    return {"compliant": compliant, "findings": findings}


def validate_title_block(has_title: bool, has_north: bool, has_viewport: bool, viewport_scale: str | None = None) -> dict:
    """ISO7200 title block + north + viewport 1:100/1:50/1:20 per Hama 12 layouts."""
    findings: list[str] = []
    compliant = True
    if not has_title:
        compliant = False
        findings.append("title block G-TTLB missing (cite ISO7200 + Hama SHEET A2)")
    if not has_north:
        compliant = False
        findings.append("north A-NORTH missing (Hama has North Arrow layer)")
    if not has_viewport:
        compliant = False
        findings.append("viewport V-PORT locked missing (Hama 2-4 per layout)")
    if viewport_scale and viewport_scale not in ("1:100", "1:50", "1:20", "1:10", "1:5", "1:275", "1:200", "1:150"):
        compliant = False
        findings.append(f"viewport scale {viewport_scale} not in Hama ladder 1:275/1:200/1:150/1:100/1:50/1:20/1:10/1:5")
    return {"compliant": compliant, "findings": findings}


def score_drawing_hama(features: dict) -> dict:
    """Hama gold 0-100. Extends base score_drawing with sections/hatches/title/viewport for 95 plot gate."""
    base = score_drawing(features)
    # Hama weights: redistribute for construction detail focus
    # Keep base score as foundation, then add Hama-specific checks as bonus/penalty to reach 95
    hama_findings: list[str] = list(base["findings"])
    hama_score = base["score"]
    breakdown = dict(base["breakdown"])

    # Section discipline (if features indicates detail scale)
    if features.get("detail_scale") in ("1:20", "1:10", "1:5", "1:100"):
        r = validate_section(features.get("detail_scale", "1:100"), has_section_line=features.get("has_section_line", True), has_hatch=features.get("has_hatch", True))
        if not r["compliant"]:
            hama_findings.extend(r["findings"])
            hama_score = max(0, hama_score - 10)
        breakdown["hama_section"] = 10 if r["compliant"] else 0

    # Hatch pattern gate
    if features.get("hatch_pattern"):
        r = validate_hatch(features["hatch_pattern"], float(features.get("hatch_scale", 1.0)), detail_scale=features.get("detail_scale", "1:100"))
        if not r["compliant"]:
            hama_findings.extend(r["findings"])
            hama_score = max(0, hama_score - 5)
        breakdown["hama_hatch"] = 5 if r["compliant"] else 0

    # Title/viewport/north
    if any(k in features for k in ("has_title", "has_north", "has_viewport")):
        r = validate_title_block(bool(features.get("has_title", True)), bool(features.get("has_north", True)), bool(features.get("has_viewport", True)), viewport_scale=features.get("viewport_scale"))
        if not r["compliant"]:
            hama_findings.extend(r["findings"])
            hama_score = max(0, hama_score - 5)
        breakdown["hama_title"] = 5 if r["compliant"] else 0

    # Re-cap, Hama requires 95 to plot
    hama_score = min(100, hama_score)
    compliant = hama_score >= 95
    severity = "critical" if hama_score < 50 else "major" if hama_score < 85 else "minor" if hama_score < 95 else "ok"
    return {"score": hama_score, "compliant": compliant, "findings": hama_findings, "breakdown": breakdown, "severity": severity, "base": base}


def score_drawing_any(features: dict, drawing_type: str = "plan") -> dict:
    """Type-aware 0-100 for any drawing: plan/section/detail/schedule/site."""
    # Dispatch to base or hama per type
    if drawing_type in ("section", "detail"):
        return score_drawing_hama(features)
    if drawing_type in ("schedule",):
        # Schedule: table grid + text, no wall check
        findings: list[str] = []
        score = 0
        breakdown: dict[str, int] = {}
        # Text legibility 30
        if features.get("text_ok", True):
            breakdown["text"] = 30
            score += 30
        else:
            findings.append("schedule text <2.5mm")
        # Table grid 25
        if features.get("has_table", True):
            breakdown["table"] = 25
            score += 25
        else:
            findings.append("schedule grid missing")
        # Layer 15
        if features.get("layer_ok", True):
            breakdown["layer"] = 15
            score += 15
        # Viewport 15 + title 15
        for k, w in [("has_viewport", 15), ("has_title", 15)]:
            if features.get(k, True):
                breakdown[k] = w
                score += w
            else:
                findings.append(f"{k} missing")
                breakdown[k] = 0
        compliant = score >= 85
        severity = "critical" if score < 50 else "major" if score < 85 else "minor" if score < 95 else "ok"
        return {"score": min(100, score), "compliant": compliant, "findings": findings, "breakdown": breakdown, "severity": severity}
    if drawing_type in ("site",):
        # Site: boundary + spot levels + grid + viewport
        findings = []
        score = 0
        breakdown = {}
        for k, w in [("has_boundary", 25), ("has_spot", 20), ("has_grid", 15), ("has_viewport", 20), ("layer_ok", 10), ("text_ok", 10)]:
            if features.get(k, True):
                breakdown[k] = w
                score += w
            else:
                findings.append(f"site {k} missing")
                breakdown[k] = 0
        compliant = score >= 85
        severity = "critical" if score < 50 else "major" if score < 85 else "minor" if score < 95 else "ok"
        return {"score": min(100, score), "compliant": compliant, "findings": findings, "breakdown": breakdown, "severity": severity}
    # Default plan
    return score_drawing(features)
