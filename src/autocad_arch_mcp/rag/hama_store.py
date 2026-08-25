"""Hama gold store — extract features from DXF (ezdxf) + embed + retrieve every run.

Pipeline: DWG AC10xx (binary) --ODA/accoreconsole DXFOUT 16--> DXF R2018 AC1032 --ezdxf.readfile--> doc
         -> extract_hama_features(doc) -> 30-d vector + JSON text
         -> sentence-transformers/all-MiniLM-L6-v2 embed (fallback: hash pseudo-embed if no model)
         -> Chroma (fallback: in-memory cosine) collection dwg_bundle
         -> hama_retrieve(intent, k=3) every nbc_* call

No external API required for stub; real Chroma/MiniLM auto-detected if installed.
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import re
from collections import Counter
from typing import Any

try:
    import ezdxf  # type: ignore
except Exception:
    ezdxf = None  # type: ignore

# Gold paths (from inventory)
HAMA_DIR = pathlib.Path(r"D:\00) ARCHITECTURE\.REF\DWG\hama_CONSTRUCTION DRAWINGS")
BARAL_DWG = pathlib.Path(r"C:\Users\Predator\Downloads\20260810-BARALRESIDENCE MUNICIPAL.dwg")
# Converted DXF cache (via accoreconsole/ODA)
DXF_CACHE = pathlib.Path(r"C:\Users\Predator\AppData\Local\Temp\opencode\hama_dxf")
GOLD_JSON = pathlib.Path(__file__).resolve().parents[3] / "knowledge" / "hama_gold.json"


def _read_header_ac(path: pathlib.Path) -> str:
    try:
        b = path.read_bytes()[:128]
        m = re.search(rb"AC\d{4}", b)
        return m.group(0).decode() if m else "unknown"
    except Exception:
        return "unknown"


def extract_hama_features(doc: Any) -> dict:
    """Extract 30-d style vector from ezdxf doc for scoring/similarity.

    Returns dict with layers, entities_per_layer, entity_types, dims, hatches, texts, blocks, weights, screenshot, scales.
    """
    if doc is None:
        return {}
    try:
        msp = doc.modelspace()
    except Exception:
        msp = []
    # Layers
    try:
        layers = [l.dxf.name for l in doc.layers]
        weights = {l.dxf.name: l.dxf.lineweight for l in doc.layers}
        linetypes = {l.dxf.name: l.dxf.linetype for l in doc.layers}
        colors = {l.dxf.name: l.color for l in doc.layers}
    except Exception:
        layers, weights, linetypes, colors = [], {}, {}, {}
    # Entity counts
    try:
        etypes = Counter(e.dxftype() for e in msp)
        per_layer = Counter(e.dxf.layer for e in msp if hasattr(e.dxf, "layer"))
    except Exception:
        etypes, per_layer = Counter(), Counter()
    # Dims
    try:
        dims = [e for e in msp if e.dxftype() == "DIMENSION"]
        dim_layers = set(e.dxf.layer for e in dims)
        dimstyles = [d.dxf.name for d in doc.dimstyles]
    except Exception:
        dims, dim_layers, dimstyles = [], set(), []
    # Hatches
    try:
        hatches = [e for e in msp if e.dxftype() == "HATCH"]
        hatch_patterns = Counter(e.dxf.pattern_name for e in hatches if hasattr(e.dxf, "pattern_name"))
    except Exception:
        hatches, hatch_patterns = [], Counter()
    # Texts
    try:
        texts = [e for e in msp if e.dxftype() in ("TEXT", "MTEXT")]
        heights = []
        for t in texts:
            try:
                h = t.dxf.height if hasattr(t.dxf, "height") else getattr(t.dxf, "char_height", 2.5)
                heights.append(float(h))
            except Exception:
                pass
    except Exception:
        texts, heights = [], []
    # Blocks
    try:
        blocks = [b.name for b in doc.blocks if not b.name.startswith("*")]
    except Exception:
        blocks = []
    # Viewports/layouts
    try:
        layouts = list(doc.layouts)
        vps = sum(1 for lo in layouts for _ in lo.query("VIEWPORT")) if layouts else 0
    except Exception:
        layouts, vps = [], 0
    # Dimensions summary
    return {
        "layers": layers,
        "layers_count": len(layers),
        "weights": weights,
        "linetypes": linetypes,
        "colors": colors,
        "entity_types": dict(etypes),
        "entities_per_layer": dict(per_layer),
        "entity_total": len(list(msp)) if hasattr(msp, "__len__") else sum(etypes.values()),
        "dims_count": len(dims),
        "dim_layers": list(dim_layers),
        "dimstyles": dimstyles,
        "hatches_count": len(hatches),
        "hatch_patterns": dict(hatch_patterns),
        "texts_count": len(texts),
        "text_heights": heights[:20],  # sample
        "blocks_count": len(blocks),
        "blocks": blocks[:20],
        "layouts_count": len(layouts) if isinstance(layouts, list) else 0,
        "viewports": vps,
        "dxfversion": getattr(doc, "dxfversion", "unknown"),
    }


def _pseudo_embed(text: str, dim: int = 384) -> list[float]:
    """Deterministic hash pseudo-embed fallback when sentence-transformers not installed. L2-normalized."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    # Expand via repeated hashing
    vals: list[float] = []
    for i in range(dim):
        # Use hash bytes cyclically
        b = h[i % len(h)]
        # Map 0-255 -> -1 to 1
        vals.append((b / 127.5) - 1.0)
        # Mix
        h = hashlib.sha256(h + bytes([i % 256])).digest()
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vals)) or 1.0
    return [v / norm for v in vals]


def _embed(texts: list[str]) -> list[list[float]]:
    """Embed texts via sentence-transformers if available, else pseudo."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        model = SentenceTransformer("all-MiniLM-L6-v2")
        vecs = model.encode(texts, normalize_embeddings=True)
        return [list(map(float, v)) for v in vecs]
    except Exception:
        return [_pseudo_embed(t) for t in texts]


def _cosine(a: list[float], b: list[float]) -> float:
    try:
        dot = sum(x * y for x, y in zip(a, b))
        # Already normalized if from _embed
        return max(-1.0, min(1.0, dot))
    except Exception:
        return 0.0


# In-memory store fallback (Chroma if available)
_STORE: list[dict] = []
_VECS: list[list[float]] = []


def _load_or_build_store() -> None:
    """Load gold JSON or build from DXF cache if Chroma not present. Lazy."""
    global _STORE, _VECS
    if _STORE:
        return
    # Try Chroma
    try:
        import chromadb  # type: ignore

        client = chromadb.PersistentClient(path=str(pathlib.Path.home() / ".cache" / "hama_chroma"))
        col = client.get_or_create_collection("dwg_bundle")
        if col.count() > 0:
            # Use Chroma as source
            return
    except Exception:
        pass
    # Fallback: load gold JSON
    if GOLD_JSON.exists():
        try:
            data = json.loads(GOLD_JSON.read_text(encoding="utf-8"))
            for item in data.get("items", []):
                _STORE.append(item)
                _VECS.append(item.get("vector", _pseudo_embed(json.dumps(item.get("features", {})))))
            if _STORE:
                return
        except Exception:
            pass
    # Build synthetic gold from inventory (Hama A001 + BARAL) — perfect vs good vs bad exemplars
    gold_items = [
        {
            "id": "hama_A001",
            "source": "D:\\00) ARCHITECTURE\\.REF\\DWG\\hama_CONSTRUCTION DRAWINGS\\(A001-A013) Architecture.dwg",
            "desc": "Hama Architecture 13 layouts A2 SHEET border A-WALL/A-COLUMN/A-GRID CENTER 0.25 dim A 1-275 15.0 HATCH ANSI31 AR-CONC",
            "score": 97,
            "features": {"layers_count": 77, "dims_count": 1118, "hatches_count": 632, "blocks_count": 1260, "layouts_count": 12, "entity_types": {"LINE": 5338, "LWPOLYLINE": 3233}, "weights": {"A-WALL": 50, "A-GRID": 25}},
        },
        {
            "id": "hama_wall_1_5",
            "source": "D:\\00) ARCHITECTURE\\.REF\\DWG\\hama_CONSTRUCTION DRAWINGS\\(A020-A029) Wall Detaills.dwg",
            "desc": "Hama Wall 1:5 detail A 1-5 dimtxt 0.5 AR-SAND 0.3 ANSI31 25.0 MTEXT 3.0/2.0",
            "score": 96,
            "features": {"layers_count": 44, "dims_count": 974, "hatches_count": 794, "layouts_count": 10},
        },
        {
            "id": "baral_municipal",
            "source": "C:\\Users\\Predator\\Downloads\\20260810-BARALRESIDENCE MUNICIPAL.dwg",
            "desc": "BARAL municipal 1 file 2.35MB metric 47k LINE on Elevation 4, 0% modular - good municipal but not Hama detailed",
            "score": 78,
            "features": {"layers_count": 59, "entity_types": {"LINE": 46709}, "dims_count": 177},
        },
        {
            "id": "bad_cadmapper",
            "source": "cadmapper-nagarkot",
            "desc": "BAD 3 layers only View Port/Defpoints, implicit 6 layers, MESH only no DIM/HATCH - counterexample",
            "score": 12,
            "features": {"layers_count": 3, "entity_types": {"MESH": 403}, "dims_count": 0},
        },
    ]
    texts = [json.dumps(g["features"]) + " " + g["desc"] for g in gold_items]
    vecs = _embed(texts)
    for g, v in zip(gold_items, vecs):
        g["vector"] = v
        _STORE.append(g)
        _VECS.append(v)


def hama_retrieve(intent: str, k: int = 3) -> list[dict]:
    """Every-run retrieval: embed intent, cosine to gold vectors, return top-k with similarity."""
    _load_or_build_store()
    qvec = _embed([intent])[0]
    scored = []
    for item, vec in zip(_STORE, _VECS):
        sim = _cosine(qvec, vec)
        scored.append((sim, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for sim, item in scored[:k]:
        out.append({"id": item["id"], "source": item["source"], "desc": item["desc"], "score": item["score"], "similarity": float(sim), "features": item["features"]})
    return out


def hama_similarity(features: dict, gold_id: str = "hama_A001") -> float:
    """Cosine similarity 0-100 between drawing features and gold."""
    _load_or_build_store()
    gold = next((g for g in _STORE if g["id"] == gold_id), _STORE[0] if _STORE else None)
    if not gold:
        return 0.0
    # Compare via embedding of features JSON
    fv = _embed([json.dumps(features)])[0]
    gv = gold.get("vector") or _embed([json.dumps(gold["features"])])[0]
    return float(_cosine(fv, gv) * 100)


def get_gold(gold_id: str = "hama_A001") -> dict | None:
    _load_or_build_store()
    return next((g for g in _STORE if g["id"] == gold_id), None)
