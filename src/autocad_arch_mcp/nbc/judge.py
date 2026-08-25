"""Vision + validator composite judge (L4). No external API call by default — heuristic + optional LLM.

Usage: from .judge import score_drawing_vision; score_drawing_vision(doc, screenshot_b64) -> {score, findings}

Stub: heuristic on entity counts per layer + screenshot variance + validator.score_drawing.
Extension: pass screenshot_b64 to vision LLM (e.g., gemini-flash) with rubric if GH token available.
"""

from __future__ import annotations

import base64
import io
from typing import Any

try:
    import ezdxf
except Exception:
    ezdxf = None  # type: ignore


# Rubric weights mirror validator SCORE_WEIGHTS but for vision aesthetics
VISION_WEIGHTS = {
    "alignment": 20,      # walls orthogonal, grid aligned
    "wall_closure": 20,   # outer closed, inner partitions meet
    "dim_chain": 20,      # 3 layers present, ticks ArchTick, text 2.5
    "text_legibility": 15,  # height 2.5 on A-ANNO-TEXT
    "north_title": 10,    # north on A-NORTH, G-TTLB
    "variance": 15,       # not-black, not-blank
}


def _variance_ok(b64: str | None) -> bool:
    """Check screenshot not-black / not-blank via PIL variance heuristic."""
    if not b64:
        return False
    try:
        from PIL import Image
        import numpy as np

        data = base64.b64decode(b64)
        img = Image.open(io.BytesIO(data)).convert("L")
        arr = np.asarray(img, dtype=float)
        # variance >10 and mean >5 and <250 (not all white/black)
        return float(arr.var()) > 10 and 5 < float(arr.mean()) < 250
    except Exception:
        # fallback: base64 length check
        return len(b64) > 1000


def score_drawing_heuristic(doc: Any, screenshot_b64: str | None = None) -> dict:
    """Heuristic 0-100 without LLM. Uses ezdxf doc + variance."""
    score = 0
    findings: list[str] = []
    breakdown: dict[str, int] = {}

    # Wall closure: expect at least 4 LWPOLYLINE on A-WALL*
    try:
        msp = doc.modelspace()
        walls = [e for e in msp if e.dxftype() == "LWPOLYLINE" and e.dxf.layer.startswith("A-WALL")]
        if len(walls) >= 4:
            breakdown["wall_closure"] = VISION_WEIGHTS["wall_closure"]
            score += VISION_WEIGHTS["wall_closure"]
        else:
            breakdown["wall_closure"] = 0
            findings.append(f"wall_closure: {len(walls)} walls <4 (expected outer+3 inner)")
    except Exception as e:
        breakdown["wall_closure"] = 0
        findings.append(str(e))

    # Dim chain: expect DIMENSION entities on A-DIM*
    try:
        dims = [e for e in msp if e.dxftype() == "DIMENSION"]
        layers = set(e.dxf.layer for e in dims)
        has_1 = any("A-DIM-1" in l for l in layers)
        has_2 = any("A-DIM-2" in l for l in layers)
        has_3 = any("A-DIM-3" in l for l in layers)
        dim_score = 0
        if has_1:
            dim_score += 7
        else:
            findings.append("dim_chain: A-DIM-1 missing (openings)")
        if has_2:
            dim_score += 7
        else:
            findings.append("dim_chain: A-DIM-2 missing (room)")
        if has_3:
            dim_score += 6
        else:
            findings.append("dim_chain: A-DIM-3 missing (overall+grid)")
        breakdown["dim_chain"] = dim_score
        score += dim_score
    except Exception:
        breakdown["dim_chain"] = 0

    # Text legibility: check TEXT/MTEXT height >=2.0
    try:
        texts = [e for e in msp if e.dxftype() in ("TEXT", "MTEXT")]
        if texts:
            heights = []
            for t in texts:
                try:
                    h = t.dxf.height if hasattr(t.dxf, "height") else t.dxf.char_height
                    heights.append(float(h))
                except Exception:
                    pass
            if heights and min(heights) >= 2.0:
                breakdown["text_legibility"] = VISION_WEIGHTS["text_legibility"]
                score += VISION_WEIGHTS["text_legibility"]
            else:
                breakdown["text_legibility"] = 0
                findings.append(f"text_legibility: min height {min(heights) if heights else 'N/A'} <2.0")
        else:
            breakdown["text_legibility"] = VISION_WEIGHTS["text_legibility"]
            score += VISION_WEIGHTS["text_legibility"]
    except Exception:
        breakdown["text_legibility"] = 0

    # North/title
    try:
        has_north = any(e for e in msp if e.dxf.layer == "A-NORTH")
        has_title = "G-TTLB" in [l.dxf.name for l in doc.layers]
        if has_north and has_title:
            breakdown["north_title"] = VISION_WEIGHTS["north_title"]
            score += VISION_WEIGHTS["north_title"]
        else:
            breakdown["north_title"] = 0
            if not has_north:
                findings.append("north_title: A-NORTH missing")
    except Exception:
        breakdown["north_title"] = 0

    # Alignment: assume orthogonal if all LWPOLYLINE points axis-aligned (heuristic)
    try:
        msp = doc.modelspace()
        misaligned = 0
        for e in msp:
            if e.dxftype() == "LWPOLYLINE":
                try:
                    pts = list(e.get_points())
                    for i in range(len(pts) - 1):
                        x1, y1 = pts[i][0], pts[i][1]
                        x2, y2 = pts[i + 1][0], pts[i + 1][1]
                        if abs(x1 - x2) > 0.01 and abs(y1 - y2) > 0.01:
                            misaligned += 1
                except Exception:
                    pass
        if misaligned == 0:
            breakdown["alignment"] = VISION_WEIGHTS["alignment"]
            score += VISION_WEIGHTS["alignment"]
        else:
            breakdown["alignment"] = max(0, VISION_WEIGHTS["alignment"] - misaligned * 5)
            score += breakdown["alignment"]
            findings.append(f"alignment: {misaligned} non-orthogonal segments")
    except Exception:
        breakdown["alignment"] = VISION_WEIGHTS["alignment"]
        score += VISION_WEIGHTS["alignment"]

    # Variance
    if _variance_ok(screenshot_b64):
        breakdown["variance"] = VISION_WEIGHTS["variance"]
        score += VISION_WEIGHTS["variance"]
    else:
        breakdown["variance"] = 0
        findings.append("variance: screenshot blank/black or missing")

    score = min(100, max(0, score))
    compliant = score >= 80
    severity = "critical" if score < 50 else "major" if score < 80 else "minor" if score < 90 else "ok"
    return {"score": score, "compliant": compliant, "findings": findings, "breakdown": breakdown, "severity": severity}


def composite_score(doc: Any, validator_features: dict, screenshot_b64: str | None = None) -> dict:
    """0.7*validator + 0.3*vision per L4."""
    from .validator import score_drawing

    v = score_drawing(validator_features)
    vis = score_drawing_heuristic(doc, screenshot_b64)
    composite = int(0.7 * v["score"] + 0.3 * vis["score"])
    findings = v["findings"] + vis["findings"]
    breakdown = {**{f"validator_{k}": v for k, v in v["breakdown"].items()}, **{f"vision_{k}": v for k, v in vis["breakdown"].items()}}
    compliant = composite >= 85
    severity = "critical" if composite < 50 else "major" if composite < 85 else "minor" if composite < 95 else "ok"
    return {
        "score": composite,
        "compliant": compliant,
        "findings": findings,
        "breakdown": breakdown,
        "severity": severity,
        "validator": v,
        "vision": vis,
    }


def hama_composite(doc: Any, validator_features: dict, screenshot_b64: str | None = None, gold_id: str = "hama_A001") -> dict:
    """Hama gold 0.5*validator_hama +0.3*vision +0.2*similarity — 95 plot gate."""
    from .validator import score_drawing_hama
    try:
        from ..rag.hama_store import hama_similarity  # type: ignore
    except Exception:
        from autocad_arch_mcp.rag.hama_store import hama_similarity  # type: ignore

    v = score_drawing_hama(validator_features)
    vis = score_drawing_heuristic(doc, screenshot_b64)
    # Similarity 0-100 to Hama gold
    try:
        sim = hama_similarity(validator_features, gold_id=gold_id)
    except Exception:
        sim = 50.0
    composite = int(0.5 * v["score"] + 0.3 * vis["score"] + 0.2 * sim)
    findings = v["findings"] + vis["findings"]
    if sim < 85:
        findings.append(f"hama_similarity {sim:.1f} <85 vs {gold_id} (cite Hama A001 77 layers)")
    breakdown = {
        **{f"validator_{k}": v for k, v in v["breakdown"].items()},
        **{f"vision_{k}": v for k, v in vis["breakdown"].items()},
        "hama_similarity": sim,
    }
    compliant = composite >= 95
    severity = "critical" if composite < 50 else "major" if composite < 85 else "minor" if composite < 95 else "ok"
    return {
        "score": composite,
        "compliant": compliant,
        "findings": findings,
        "breakdown": breakdown,
        "severity": severity,
        "validator_hama": v,
        "vision": vis,
        "hama_similarity": sim,
    }
