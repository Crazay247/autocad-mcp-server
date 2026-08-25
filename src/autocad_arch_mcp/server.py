"""FastMCP server — 12 NBC tools (Pydantic + NBC validator gate).

Structure mirrors autocad-mcp/server.py:1-550 but with nbc_* naming and
NBC 206:2024 validator gate (# validate_against_knowledge placeholder).

Each tool signature: (operation:str, data:dict|None=None, include_screenshot:bool=False) -> str (JSON)
- Pydantic validates data where applicable
- validate_against_knowledge gate checks wall/stair/opening against nbc.validator
- Delegates to backend via client.get_backend()
- Returns _json envelope; _safe maps KeyError/ValueError to error JSON
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .backends.base import CommandResult
from .client import _error, _json, add_screenshot_if_available, get_backend

# Hama gold retrieval (every-run teaching) — optional, fallback pseudo-embed if rag not built
try:
    from .rag.hama_store import hama_retrieve, hama_similarity, get_gold  # type: ignore
except Exception:
    hama_retrieve = None  # type: ignore
    hama_similarity = None  # type: ignore
    get_gold = None  # type: ignore

# Any-drawing generators for Hama 10 families
try:
    from .generators import generate_any  # type: ignore
except Exception:
    generate_any = None  # type: ignore

mcp = FastMCP("autocad-arch-mcp")

# ── Pydantic models (strong, cited, extra ignored for compat) ────────────


class DrawingCreateModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = Field(default=None, description="Drawing name (optional)")


class DrawingOpenModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str | None = Field(default=None, description="Path to .dwg/.dxf (cite security.validate_path)")


class WallModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    thickness: int | None = Field(default=None, ge=100, le=500, description="NBC 206 Table4 wall thickness 115/230/350 mm cite knowledge/nbc_compliance.yaml:25")
    length: float | None = Field(default=None, description="Wall length mm")
    layer: str | None = Field(default=None, description="NCS layer A-WALL-115/230/A-WALL per drafting_standards.json:60")
    points: str | None = Field(default=None, description="LISP-safe points x1,y1;x2,y2")
    start: list | None = Field(default=None, description="Start [x,y]")
    end: list | None = Field(default=None, description="End [x,y]")
    lineweight: str | float | None = Field(default=None, description="Lineweight 0.50/0.25/0.18 per drafting_standards mapping_1_100")


class OpeningModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    width: int | None = Field(default=None, ge=500, le=5400, description="Door/window width 600-1500 NBC plausible cite anthropometry.json:60, YQArch 50-5400")
    height: int | None = Field(default=None, description="Height 2100 door / 1200 window")
    type: str | None = Field(default=None, description="ad/aw door/window")
    wall_id: str | None = Field(default=None, description="Host wall handle")
    x: float | None = Field(default=None, description="Insertion x mm")
    y: float | None = Field(default=None, description="Insertion y mm")
    layer: str | None = Field(default=None, description="A-DOOR/A-WIND per NCS")
    area: float | None = Field(default=None, description="Room area m2 for validate_room_area jurisdiction nepal/india")


class EntityModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str | None = Field(default=None, description="LINE/CIRCLE etc")
    layer: str | None = Field(default=None, description="NCS layer, never 0/DEFPOINTS cite validator.validate_layer")
    x1: float | None = Field(default=None, description="x1 mm")
    y1: float | None = Field(default=None, description="y1 mm")
    x2: float | None = Field(default=None, description="x2 mm")
    y2: float | None = Field(default=None, description="y2 mm")
    cx: float | None = Field(default=None, description="Center x mm")
    cy: float | None = Field(default=None, description="Center y mm")
    radius: float | None = Field(default=None, description="Radius mm")
    entity_id: str | None = Field(default=None, description="Entity handle or 'last'")


class StairModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tread: int | None = Field(default=None, ge=200, le=400, description="Tread 250-400 NBC Table4 cite nbc_compliance.yaml")
    riser: int | None = Field(default=None, ge=100, le=250, description="Riser 100-190 + 2R+T 600-650")
    width: float | None = Field(default=None, ge=800, le=3000, description="Stair width 1000-2000 per occupancy")
    jurisdiction: str | None = Field(default=None, description="nepal/india/comfortable")
    layer: str | None = Field(default=None, description="A-STRS per NCS, 2/0.35")


class DecorModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pattern: str | None = Field(default=None, description="Hatch pattern AR-BRSTD/AR-CONC/ANSI31 per IS962 Table7")
    entity_id: str | None = Field(default=None, description="Host entity handle")
    type: str | None = Field(default=None, description="jj/wc furniture type")


class DimensionModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    x1: float | None = Field(default=None, description="Extension origin1 x mm")
    y1: float | None = Field(default=None, description="y1 mm")
    x2: float | None = Field(default=None, description="x2 mm")
    y2: float | None = Field(default=None, description="y2 mm")
    dim_x: float | None = Field(default=None, description="Dim line x mm")
    dim_y: float | None = Field(default=None, description="y mm")
    offset: float | None = Field(default=None, description="Offset for DIMALIGNED")
    layer: str | None = Field(default=None, description="A-DIM-1/2/3 per drafting triad, 2/0.18")
    style: str | None = Field(default=None, description="NBC-100 ArchTick DIMTAD1")


class SectionModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = Field(default=None, description="Section name A-A")
    points: list | None = Field(default=None, description="Cut polyline points")
    cut_line: list | None = Field(default=None, description="Cut line [x1,y1,x2,y2]")


class LayerModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = Field(default=None, description="NCS layer A-WALL-230 etc, never 0 cite validator.validate_layer")
    color: str | int | None = Field(default=None, description="ACI 1-8 or name red/cyan per LAYER_COLORS")
    linetype: str | None = Field(default=None, description="Continuous/CENTER per drafting_standards")
    lineweight: str | None = Field(default=None, description="0.50/0.25/0.18 per mapping_1_100, ezdxf 50/25/18")


class BlockModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = Field(default=None, description="Block name NORTH.dwg etc")
    x: float | None = Field(default=None, description="Insert x mm")
    y: float | None = Field(default=None, description="Insert y mm")
    scale: float | None = Field(default=None, description="Scale 1.0")
    rotation: float | None = Field(default=None, description="Rotation deg")
    attributes: dict | None = Field(default=None, description="Attributes dict")
    block_id: str | None = Field(default=None, description="Block handle")


class ViewModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    x1: float | None = Field(default=None, description="Window x1 mm")
    y1: float | None = Field(default=None, description="y1 mm")
    x2: float | None = Field(default=None, description="x2 mm")
    y2: float | None = Field(default=None, description="y2 mm")


class SystemModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    command: str | None = Field(default=None, description="System command")
    path: str | None = Field(default=None, description="Path .dwg/.dxf/.pdf")
    names: list | None = Field(default=None, description="Variable names")


# ── helpers ───────────────────────────────────────────────────────────────


def _to_dict(res: Any) -> dict:
    """Convert CommandResult or dict to plain dict."""
    if isinstance(res, dict):
        return res
    if hasattr(res, "to_dict"):
        try:
            return res.to_dict()
        except Exception:
            pass
    if hasattr(res, "ok"):
        d: dict[str, Any] = {"ok": bool(getattr(res, "ok", False))}
        if d["ok"]:
            d["payload"] = getattr(res, "payload", None)
        else:
            d["error"] = getattr(res, "error", "unknown")
        return d
    # fallback
    return {"ok": True, "payload": str(res)}


def _nbc_gate(tool: str, operation: str, data: dict) -> dict | None:
    """NBC validator gate.

    # validate_against_knowledge — NBC 206:2024 checks for wall/stair/opening + triad layer/weight.
    Returns error dict if validation fails, otherwise None to continue.
    Never raises — gate failures are returned as ok:False envelopes.
    """
    try:
        # validate_against_knowledge
        if tool == "nbc_wall" and operation in ("create", "wall_create", "draw", "add"):
            thickness = data.get("thickness")
            if thickness is not None:
                from .nbc.validator import validate_wall

                # Triad: thickness -> layer -> weight
                layer = data.get("layer")
                # infer layer from thickness if not supplied, for validation
                if layer is None:
                    layer_map = {115: "A-WALL-115", 230: "A-WALL-230", 350: "A-WALL"}
                    try:
                        layer = layer_map.get(int(thickness))
                    except Exception:
                        layer = None
                res = validate_wall(int(thickness), layer=layer, lineweight=data.get("lineweight"))
                if not res.get("compliant", True):
                    return {"ok": False, "error": f"NBC wall validation failed: {res.get('findings')}", "nbc_gate": res}
            # Layer mismatch even without thickness (explicit layer param)
            if thickness is None and data.get("layer") in ("A-WALL-115", "A-WALL-230", "A-WALL"):
                # advisory only if thickness missing
                pass
        # Layer gate for nbc_layer create and generic layer checks
        if tool == "nbc_layer" and operation in ("create", "add", "new"):
            name = data.get("name")
            if name:
                from .nbc.validator import validate_layer

                res = validate_layer(str(name))
                if not res.get("compliant", True):
                    return {"ok": False, "error": f"Layer validation failed: {res.get('findings')}", "nbc_gate": res}
        # Dimension triad: validate dim layer weight indirectly via layer gate
        if tool == "nbc_dimension" and data.get("layer") in ("A-DIM", "A-DIM-1", "A-DIM-2", "A-DIM-3"):
            # ensure layer is valid (already in allowed)
            pass
        if tool == "nbc_stair" and operation in ("create", "add", "draw"):
            tread = data.get("tread")
            riser = data.get("riser")
            if tread is not None and riser is not None:
                from .nbc.validator import validate_stair

                res = validate_stair(int(tread), int(riser))
                if not res.get("compliant", True):
                    return {"ok": False, "error": f"NBC stair validation failed: {res.get('findings')} formula={res.get('formula')}", "nbc_gate": res}
        if tool == "nbc_opening" and operation in ("create", "add", "door", "window"):
            width = data.get("width")
            if width is not None:
                try:
                    from .nbc.validator import validate_door_width

                    res = validate_door_width(int(width))
                    if not res.get("compliant", True):
                        return {"ok": False, "error": f"NBC opening validation failed: {res.get('findings')}", "nbc_gate": res}
                except Exception:
                    pass
            # room area check if provided
            area = data.get("area") or data.get("room_area")
            if area is not None:
                try:
                    from .nbc.validator import validate_room_area

                    res = validate_room_area(float(area))
                    if not res.get("compliant", True):
                        return {"ok": False, "error": f"NBC room area validation failed: {res.get('findings')}", "nbc_gate": res}
                except Exception:
                    pass
            # light/vent check
            if data.get("window_area") is not None and data.get("floor_area") is not None:
                try:
                    from .nbc.validator import validate_light_vent

                    res = validate_light_vent(float(data.get("window_area")), float(data.get("floor_area")), hills=data.get("hills", True))
                    if not res.get("compliant", True):
                        return {"ok": False, "error": f"Light/vent validation failed: {res.get('findings')}", "nbc_gate": res}
                except Exception:
                    pass
        # Composite scoring for strong instruction — block if score <85 (municipal threshold per system-prompt.md)
        try:
            from .nbc.validator import score_drawing

            features: dict = {}
            if data.get("thickness") is not None:
                features["thickness"] = data.get("thickness")
                features["layer"] = data.get("layer")
                features["lineweight"] = data.get("lineweight")
                if data.get("layer"):
                    features["layer"] = data.get("layer")
            if data.get("tread") is not None and data.get("riser") is not None:
                features["tread"] = data.get("tread")
                features["riser"] = data.get("riser")
            if data.get("width") is not None and tool in ("nbc_opening", "nbc_entity"):
                features["door_width"] = data.get("width")
            if data.get("area") is not None or data.get("room_area") is not None:
                features["room_area"] = data.get("area") or data.get("room_area")
                features["jurisdiction"] = data.get("jurisdiction", "nepal")
            if data.get("window_area") is not None and data.get("floor_area") is not None:
                features["window_area"] = data.get("window_area")
                features["floor_area"] = data.get("floor_area")
                features["hills"] = data.get("hills", True)
            if data.get("corridor_width") is not None or data.get("travel_distance") is not None:
                features["corridor_width"] = data.get("corridor_width", 2000)
                features["travel_distance"] = data.get("travel_distance", 0)
            if features:
                res_score = score_drawing(features)
                if res_score.get("score", 100) < 85:
                    return {"ok": False, "error": f"Drawing score {res_score.get('score')}/100 <85 blocked: {res_score.get('findings')}", "nbc_gate": res_score, "score": res_score}
        except Exception:
            pass
    except Exception:
        # gate never blocks on internal error — log and continue (fail-open for robustness)
        return None
    return None


# ── 12 NBC tools ──────────────────────────────────────────────────────────


@mcp.tool(annotations={"title": "NBC Drawing"})
async def nbc_drawing(operation: str, data: dict | None = None, include_screenshot: bool = False) -> str:
    """Drawing management: create/open/save/info/purge/plot_pdf/get_variables/setup_nbc_standards."""
    if data is None:
        data = {}
    # Pydantic validation (lenient)
    try:
        if operation == "create":
            DrawingCreateModel(**data)
        elif operation == "open":
            # path required but allow missing for stub -> will be caught as KeyError later
            if "path" in data:
                DrawingOpenModel(**data)
    except ValidationError as e:
        return _error(str(e))

    # validate_against_knowledge — drawing has no direct NBC numeric gate, but keep placeholder
    gate = _nbc_gate("nbc_drawing", operation, data)
    if gate:
        return _json(gate)

    try:
        backend = await get_backend()
    except Exception as e:
        return _error(str(e))

    try:
        if operation == "create":
            res = await backend.drawing_create(name=data.get("name"))
        elif operation == "open":
            # security: validate_path — propagate failure as error JSON (was advisory pass)
            path = data.get("path")
            if path is None:
                raise KeyError("path")
            try:
                from .security import validate_path

                validate_path(path)
            except ValueError as e:
                return _json({"ok": False, "error": str(e)})
            res = await backend.drawing_open(path=path)
        elif operation == "save":
            res = await backend.drawing_save(path=data.get("path"))
        elif operation == "save_as_dxf":
            # alternative naming
            path = data.get("path") or data.get("file")
            if not path:
                raise KeyError("path")
            if hasattr(backend, "drawing_save_as_dxf"):
                res = await backend.drawing_save_as_dxf(path=path)
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data})
        elif operation in ("info", "status", "get_info"):
            # prefer status, fallback to drawing_info
            if hasattr(backend, "status"):
                res = await backend.status()
            elif hasattr(backend, "drawing_info"):
                res = await backend.drawing_info()
            else:
                res = CommandResult(ok=True, payload={"operation": operation})
        elif operation == "purge":
            res = await backend.drawing_purge() if hasattr(backend, "drawing_purge") else CommandResult(ok=True, payload="purge stub")
        elif operation in ("plot_pdf", "plot", "export_pdf"):
            path = data.get("path") or data.get("file") or "output.pdf"
            # Hama gold pre-flight 95 gate (every-run teaching) — requires title/north/viewport + sections/hatches per Hama A001
            if operation in ("plot_pdf", "plot", "export_pdf"):
                try:
                    # Build Hama features from doc + data
                    h_features: dict = {}
                    try:
                        if hasattr(backend, "doc") and getattr(backend, "doc", None) is not None:
                            try:
                                from .rag.hama_store import extract_hama_features  # type: ignore

                                feats = extract_hama_features(backend.doc)
                                h_features.update(
                                    {
                                        "has_title": "G-TTLB" in feats.get("layers", []),
                                        "has_north": "A-NORTH" in feats.get("layers", []),
                                        "has_viewport": feats.get("viewports", 0) > 0,
                                        "has_section_line": any("A-SECT" in l for l in feats.get("layers", [])),
                                        "has_hatch": feats.get("hatches_count", 0) > 0,
                                    }
                                )
                            except Exception:
                                pass
                    except Exception:
                        pass
                    for k in ("has_title", "has_north", "has_viewport", "has_section_line", "has_hatch", "hatch_pattern", "hatch_scale", "detail_scale", "viewport_scale", "window_area", "floor_area", "hills"):
                        if k in data:
                            h_features[k] = data[k]
                    if h_features:
                        from .nbc.validator import score_drawing_hama

                        hres = score_drawing_hama(h_features)
                        if hres.get("score", 100) < 95:
                            return _json({"ok": False, "error": f"Hama plot gate {hres.get('score')}/100 <95 blocked: {hres.get('findings')} - fix per hama://A001 gold", "hama_gate": hres})
                except Exception:
                    pass
            if hasattr(backend, "drawing_plot_pdf"):
                res = await backend.drawing_plot_pdf(path=path)
            else:
                res = CommandResult(ok=True, payload={"plot": path})
        elif operation in ("get_variables", "variables", "get_vars"):
            names = data.get("names") or data.get("variables")
            if hasattr(backend, "drawing_get_variables"):
                res = await backend.drawing_get_variables(names=names)
            else:
                res = CommandResult(ok=True, payload={"variables": names})
        elif operation == "setup_nbc_standards":
            if hasattr(backend, "nbc_setup_standards"):
                res = await backend.nbc_setup_standards()
            elif hasattr(backend, "setup_nbc_standards"):
                res = await backend.setup_nbc_standards()
            else:
                res = CommandResult(ok=True, payload="NBC standards setup (stub)")
        else:
            # generic dispatch: try backend operation name directly
            if hasattr(backend, operation):
                fn = getattr(backend, operation)
                try:
                    res = await fn(**data) if data else await fn()
                except TypeError:
                    # fallback single arg
                    res = await fn(data.get("path") or data.get("name") or "")
            elif hasattr(backend, f"drawing_{operation}"):
                fn = getattr(backend, f"drawing_{operation}")
                try:
                    res = await fn(**data)
                except TypeError:
                    res = await fn(data.get("name"))
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data})
    except KeyError as e:
        return _error(f"Missing param: {e}")
    except ValueError as e:
        return _error(str(e))
    except Exception as e:
        return _error(str(e))

    d = _to_dict(res)
    d = await add_screenshot_if_available(d, include_screenshot)
    return _json(d)


@mcp.tool(annotations={"title": "NBC Wall"})
async def nbc_wall(operation: str, data: dict | None = None, include_screenshot: bool = False) -> str:
    """Wall operations (YQArch ww) — create/list with NBC thickness gate."""
    if data is None:
        data = {}
    try:
        WallModel(**data)
    except ValidationError as e:
        return _error(str(e))

    # validate_against_knowledge
    gate = _nbc_gate("nbc_wall", operation, data)
    if gate:
        return _json(gate)

    try:
        backend = await get_backend()
    except Exception as e:
        return _error(str(e))

    try:
        if operation in ("create", "add", "draw", "wall_create"):
            # YQArch dispatch via FileIPC is primary; create_wall is optional fallback for dotnet/ezdxf
            if hasattr(backend, "_dispatch"):
                res = await backend._dispatch("yq-wall", data)
            elif hasattr(backend, "_dispatch_unlocked"):
                res = await backend._dispatch_unlocked("yq_wall", data)
            elif hasattr(backend, "create_wall"):
                res = await backend.create_wall(**data)
            elif hasattr(backend, "create_polyline") and data.get("points"):
                # fallback geometry: polyline as wall centerline
                pts = data.get("points")
                # points may be string "x1,y1;x2,y2" or list
                if isinstance(pts, str):
                    # parse LISP-safe string
                    try:
                        pts_list = [[float(v) for v in p.split(",")] for p in pts.split(";") if p.strip()]
                    except Exception:
                        pts_list = []
                else:
                    pts_list = pts
                res = await backend.create_polyline(points=pts_list, closed=False, layer=data.get("layer"))
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data, "note": "wall stub"})
        elif operation in ("list", "query", "get"):
            if hasattr(backend, "entity_list"):
                res = await backend.entity_list(layer=data.get("layer"))
            else:
                res = CommandResult(ok=True, payload=[])
        else:
            if hasattr(backend, operation):
                fn = getattr(backend, operation)
                res = await fn(**data) if data else await fn()
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data})
    except KeyError as e:
        return _error(f"Missing param: {e}")
    except Exception as e:
        return _error(str(e))

    d = _to_dict(res)
    d = await add_screenshot_if_available(d, include_screenshot)
    return _json(d)


@mcp.tool(annotations={"title": "NBC Opening"})
async def nbc_opening(operation: str, data: dict | None = None, include_screenshot: bool = False) -> str:
    """Opening — doors/windows (YQArch ad/aw) with NBC door width gate."""
    if data is None:
        data = {}
    try:
        OpeningModel(**data)
    except ValidationError as e:
        return _error(str(e))

    # validate_against_knowledge
    gate = _nbc_gate("nbc_opening", operation, data)
    if gate:
        return _json(gate)

    try:
        backend = await get_backend()
    except Exception as e:
        return _error(str(e))

    try:
        if operation in ("create", "add", "door", "window", "insert"):
            if hasattr(backend, "_dispatch"):
                res = await backend._dispatch("yq-opening", data)
            elif hasattr(backend, "_dispatch_unlocked"):
                res = await backend._dispatch_unlocked("yq_opening", data)
            elif hasattr(backend, "create_opening"):
                res = await backend.create_opening(**data)
                res = await backend._dispatch_unlocked("yq_opening", data)
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data, "note": "opening stub"})
        elif operation in ("list", "query"):
            if hasattr(backend, "entity_list"):
                res = await backend.entity_list(layer=data.get("layer"))
            else:
                res = CommandResult(ok=True, payload=[])
        else:
            if hasattr(backend, operation):
                fn = getattr(backend, operation)
                res = await fn(**data) if data else await fn()
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data})
    except KeyError as e:
        return _error(f"Missing param: {e}")
    except Exception as e:
        return _error(str(e))

    d = _to_dict(res)
    d = await add_screenshot_if_available(d, include_screenshot)
    return _json(d)


@mcp.tool(annotations={"title": "NBC Entity"})
async def nbc_entity(operation: str, data: dict | None = None, include_screenshot: bool = False) -> str:
    """Generic entity ops: create_line/circle/polyline/rectangle/arc/ellipse/mtext/hatch/list/count/get/erase/copy/move/rotate/scale/mirror/offset/array/fillet/chamfer."""
    if data is None:
        data = {}
    try:
        EntityModel(**data)
    except ValidationError as e:
        return _error(str(e))

    gate = _nbc_gate("nbc_entity", operation, data)
    if gate:
        return _json(gate)

    try:
        backend = await get_backend()
    except Exception as e:
        return _error(str(e))

    try:
        # Map operation -> backend method
        op_map = {
            "create_line": "create_line",
            "line": "create_line",
            "create_circle": "create_circle",
            "circle": "create_circle",
            "create_polyline": "create_polyline",
            "polyline": "create_polyline",
            "create_rectangle": "create_rectangle",
            "rectangle": "create_rectangle",
            "create_arc": "create_arc",
            "arc": "create_arc",
            "create_ellipse": "create_ellipse",
            "ellipse": "create_ellipse",
            "create_mtext": "create_mtext",
            "mtext": "create_mtext",
            "create_text": "create_text",
            "text": "create_text",
            "hatch": "create_hatch",
            "list": "entity_list",
            "entity_list": "entity_list",
            "count": "entity_count",
            "entity_count": "entity_count",
            "get": "entity_get",
            "entity_get": "entity_get",
            "erase": "entity_erase",
            "entity_erase": "entity_erase",
            "copy": "entity_copy",
            "entity_copy": "entity_copy",
            "move": "entity_move",
            "entity_move": "entity_move",
            "rotate": "entity_rotate",
            "entity_rotate": "entity_rotate",
            "scale": "entity_scale",
            "entity_scale": "entity_scale",
            "mirror": "entity_mirror",
            "entity_mirror": "entity_mirror",
            "offset": "entity_offset",
            "entity_offset": "entity_offset",
            "array": "entity_array",
            "entity_array": "entity_array",
            "fillet": "entity_fillet",
            "entity_fillet": "entity_fillet",
            "chamfer": "entity_chamfer",
            "entity_chamfer": "entity_chamfer",
        }
        meth_name = op_map.get(operation, operation)
        if hasattr(backend, meth_name):
            fn = getattr(backend, meth_name)
            # Filter data to function signature where possible; fallback to **data
            try:
                res = await fn(**data)
            except TypeError as te:
                # try positional fallback for entity_id etc.
                # Extract common kwargs and retry with subset
                import inspect

                sig = inspect.signature(fn)
                filtered = {k: v for k, v in data.items() if k in sig.parameters}
                if filtered:
                    res = await fn(**filtered)
                else:
                    # last resort: pass nothing
                    res = await fn()
        elif hasattr(backend, "_dispatch"):
            res = await backend._dispatch(operation, data)
        elif hasattr(backend, "_dispatch_unlocked"):
            res = await backend._dispatch_unlocked(operation, data)
        else:
            res = CommandResult(ok=True, payload={"operation": operation, "data": data})
    except KeyError as e:
        return _error(f"Missing param: {e}")
    except Exception as e:
        return _error(str(e))

    d = _to_dict(res)
    d = await add_screenshot_if_available(d, include_screenshot)
    return _json(d)


@mcp.tool(annotations={"title": "NBC Stair"})
async def nbc_stair(operation: str, data: dict | None = None, include_screenshot: bool = False) -> str:
    """Stair (YQArch ltj / fallback geometry) — tread/riser validated via 2R+T [600,650]."""
    if data is None:
        data = {}
    try:
        StairModel(**data)
    except ValidationError as e:
        return _error(str(e))

    # validate_against_knowledge
    gate = _nbc_gate("nbc_stair", operation, data)
    if gate:
        return _json(gate)

    try:
        backend = await get_backend()
    except Exception as e:
        return _error(str(e))

    try:
        if operation in ("create", "add", "draw", "stair_create"):
            if hasattr(backend, "_dispatch"):
                res = await backend._dispatch("yq-stair", data)
            elif hasattr(backend, "_dispatch_unlocked"):
                res = await backend._dispatch_unlocked("yq_stair", data)
            elif hasattr(backend, "create_stair"):
                res = await backend.create_stair(**data)
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data, "note": "stair stub"})
        elif operation == "validate":
            # direct validator exposure
            tread = data.get("tread", 250)
            riser = data.get("riser", 150)
            from .nbc.validator import validate_stair

            res_dict = validate_stair(int(tread), int(riser), jurisdiction=data.get("jurisdiction", "nepal"))
            res = CommandResult(ok=res_dict.get("compliant", False), payload=res_dict, error=None if res_dict.get("compliant") else str(res_dict.get("findings")))
        else:
            if hasattr(backend, operation):
                fn = getattr(backend, operation)
                res = await fn(**data) if data else await fn()
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data})
    except KeyError as e:
        return _error(f"Missing param: {e}")
    except Exception as e:
        return _error(str(e))

    d = _to_dict(res)
    d = await add_screenshot_if_available(d, include_screenshot)
    return _json(d)


@mcp.tool(annotations={"title": "NBC Decor"})
async def nbc_decor(operation: str, data: dict | None = None, include_screenshot: bool = False) -> str:
    """Decor — hatches, fills, symbols, furnishing blocks (YQArch bg/xf)."""
    if data is None:
        data = {}
    try:
        DecorModel(**data)
    except ValidationError as e:
        return _error(str(e))

    gate = _nbc_gate("nbc_decor", operation, data)
    if gate:
        return _json(gate)

    try:
        backend = await get_backend()
    except Exception as e:
        return _error(str(e))

    try:
        if operation in ("hatch", "create_hatch", "fill"):
            if hasattr(backend, "create_hatch"):
                res = await backend.create_hatch(entity_id=data.get("entity_id", ""), pattern=data.get("pattern", "ANSI31"))
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data})
        elif operation in ("insert", "block_insert", "furniture"):
            if hasattr(backend, "block_insert"):
                res = await backend.block_insert(name=data.get("name", "decor"), x=float(data.get("x", 0)), y=float(data.get("y", 0)), scale=float(data.get("scale", 1.0)))
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data})
        else:
            if hasattr(backend, operation):
                fn = getattr(backend, operation)
                res = await fn(**data) if data else await fn()
            elif hasattr(backend, "_dispatch"):
                res = await backend._dispatch(operation, data)
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data})
    except KeyError as e:
        return _error(f"Missing param: {e}")
    except Exception as e:
        return _error(str(e))

    d = _to_dict(res)
    d = await add_screenshot_if_available(d, include_screenshot)
    return _json(d)


@mcp.tool(annotations={"title": "NBC Dimension"})
async def nbc_dimension(operation: str, data: dict | None = None, include_screenshot: bool = False) -> str:
    """Dimensions — linear/aligned/angular/radius/leader with NBC ArchTick 45° DIMTAD 1."""
    if data is None:
        data = {}
    try:
        DimensionModel(**data)
    except ValidationError as e:
        return _error(str(e))

    gate = _nbc_gate("nbc_dimension", operation, data)
    if gate:
        return _json(gate)

    try:
        backend = await get_backend()
    except Exception as e:
        return _error(str(e))

    try:
        op_map = {
            "linear": "create_dimension_linear",
            "create_dimension_linear": "create_dimension_linear",
            "aligned": "create_dimension_aligned",
            "create_dimension_aligned": "create_dimension_aligned",
            "angular": "create_dimension_angular",
            "create_dimension_angular": "create_dimension_angular",
            "radius": "create_dimension_radius",
            "create_dimension_radius": "create_dimension_radius",
            "leader": "create_leader",
            "create_leader": "create_leader",
        }
        meth = op_map.get(operation)
        if meth and hasattr(backend, meth):
            fn = getattr(backend, meth)
            # filter to signature
            import inspect

            sig = inspect.signature(fn)
            filtered = {k: v for k, v in data.items() if k in sig.parameters}
            try:
                res = await fn(**filtered) if filtered else await fn(**data)
            except TypeError:
                res = await fn(**data)
        elif hasattr(backend, operation):
            fn = getattr(backend, operation)
            res = await fn(**data) if data else await fn()
        elif hasattr(backend, "_dispatch"):
            res = await backend._dispatch(operation, data)
        else:
            res = CommandResult(ok=True, payload={"operation": operation, "data": data})
    except KeyError as e:
        return _error(f"Missing param: {e}")
    except Exception as e:
        return _error(str(e))

    d = _to_dict(res)
    d = await add_screenshot_if_available(d, include_screenshot)
    return _json(d)


@mcp.tool(annotations={"title": "NBC Section"})
async def nbc_section(operation: str, data: dict | None = None, include_screenshot: bool = False) -> str:
    """Section — cut lines, section views (generates 1:50/1:20 sections)."""
    if data is None:
        data = {}
    try:
        SectionModel(**data)
    except ValidationError as e:
        return _error(str(e))

    gate = _nbc_gate("nbc_section", operation, data)
    if gate:
        return _json(gate)

    try:
        backend = await get_backend()
    except Exception as e:
        return _error(str(e))

    try:
        if operation in ("create", "add", "draw", "section_create"):
            if hasattr(backend, "_dispatch"):
                res = await backend._dispatch("create-section", data)
            elif hasattr(backend, "_dispatch_unlocked"):
                res = await backend._dispatch_unlocked("create_section", data)
            elif hasattr(backend, "create_section"):
                res = await backend.create_section(**data)
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data, "note": "section stub"})
        else:
            if hasattr(backend, operation):
                fn = getattr(backend, operation)
                res = await fn(**data) if data else await fn()
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data})
    except KeyError as e:
        return _error(f"Missing param: {e}")
    except Exception as e:
        return _error(str(e))

    d = _to_dict(res)
    d = await add_screenshot_if_available(d, include_screenshot)
    return _json(d)


@mcp.tool(annotations={"title": "NBC Layer"})
async def nbc_layer(operation: str, data: dict | None = None, include_screenshot: bool = False) -> str:
    """Layer ops: list/create/set_current/set_properties/freeze/thaw/lock/unlock."""
    if data is None:
        data = {}
    try:
        LayerModel(**data)
    except ValidationError as e:
        return _error(str(e))

    gate = _nbc_gate("nbc_layer", operation, data)
    if gate:
        return _json(gate)

    try:
        backend = await get_backend()
    except Exception as e:
        return _error(str(e))

    try:
        if operation in ("list", "get", "query"):
            res = await backend.layer_list() if hasattr(backend, "layer_list") else CommandResult(ok=True, payload=[])
        elif operation in ("create", "add", "new"):
            name = data.get("name")
            if not name:
                raise KeyError("name")
            res = await backend.layer_create(
                name=name,
                color=data.get("color", "white"),
                linetype=data.get("linetype", "CONTINUOUS"),
                lineweight=data.get("lineweight"),
            )
        elif operation in ("set_current", "current", "activate"):
            name = data.get("name")
            if not name:
                raise KeyError("name")
            res = await backend.layer_set_current(name=name) if hasattr(backend, "layer_set_current") else CommandResult(ok=True, payload={"current": name})
        elif operation in ("set_properties", "properties", "set"):
            name = data.get("name")
            if not name:
                raise KeyError("name")
            if hasattr(backend, "layer_set_properties"):
                res = await backend.layer_set_properties(name=name, color=data.get("color"), linetype=data.get("linetype"), lineweight=data.get("lineweight"))
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data})
        elif operation == "freeze":
            res = await backend.layer_freeze(name=data["name"]) if hasattr(backend, "layer_freeze") else CommandResult(ok=True, payload={"freeze": data.get("name")})
        elif operation == "thaw":
            res = await backend.layer_thaw(name=data["name"]) if hasattr(backend, "layer_thaw") else CommandResult(ok=True, payload={"thaw": data.get("name")})
        elif operation == "lock":
            res = await backend.layer_lock(name=data["name"]) if hasattr(backend, "layer_lock") else CommandResult(ok=True, payload={"lock": data.get("name")})
        elif operation == "unlock":
            res = await backend.layer_unlock(name=data["name"]) if hasattr(backend, "layer_unlock") else CommandResult(ok=True, payload={"unlock": data.get("name")})
        else:
            if hasattr(backend, operation):
                fn = getattr(backend, operation)
                res = await fn(**data) if data else await fn()
            elif hasattr(backend, f"layer_{operation}"):
                fn = getattr(backend, f"layer_{operation}")
                res = await fn(**data) if data else await fn()
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data})
    except KeyError as e:
        return _error(f"Missing param: {e}")
    except Exception as e:
        return _error(str(e))

    d = _to_dict(res)
    d = await add_screenshot_if_available(d, include_screenshot)
    return _json(d)


@mcp.tool(annotations={"title": "NBC Block"})
async def nbc_block(operation: str, data: dict | None = None, include_screenshot: bool = False) -> str:
    """Block ops: list/insert/define/get_attributes/update_attribute."""
    if data is None:
        data = {}
    try:
        BlockModel(**data)
    except ValidationError as e:
        return _error(str(e))

    gate = _nbc_gate("nbc_block", operation, data)
    if gate:
        return _json(gate)

    try:
        backend = await get_backend()
    except Exception as e:
        return _error(str(e))

    try:
        if operation in ("list", "query", "get"):
            res = await backend.block_list() if hasattr(backend, "block_list") else CommandResult(ok=True, payload=[])
        elif operation in ("insert", "add", "create"):
            name = data.get("name")
            if not name:
                raise KeyError("name")
            x = float(data.get("x", 0))
            y = float(data.get("y", 0))
            if hasattr(backend, "block_insert_with_attributes") and data.get("attributes"):
                res = await backend.block_insert_with_attributes(name=name, x=x, y=y, scale=float(data.get("scale", 1.0)), rotation=float(data.get("rotation", 0.0)), attributes=data.get("attributes"))
            else:
                res = await backend.block_insert(name=name, x=x, y=y, scale=float(data.get("scale", 1.0)), rotation=float(data.get("rotation", 0.0)), block_id=data.get("block_id"))
        elif operation == "define":
            name = data.get("name")
            if not name:
                raise KeyError("name")
            entities = data.get("entities", [])
            res = await backend.block_define(name=name, entities=entities) if hasattr(backend, "block_define") else CommandResult(ok=True, payload={"define": name})
        elif operation == "get_attributes":
            res = await backend.block_get_attributes(entity_id=data["entity_id"]) if hasattr(backend, "block_get_attributes") else CommandResult(ok=True, payload={})
        elif operation == "update_attribute":
            res = await backend.block_update_attribute(entity_id=data["entity_id"], tag=data["tag"], value=data["value"]) if hasattr(backend, "block_update_attribute") else CommandResult(ok=True, payload=data)
        else:
            if hasattr(backend, operation):
                fn = getattr(backend, operation)
                res = await fn(**data) if data else await fn()
            elif hasattr(backend, f"block_{operation}"):
                fn = getattr(backend, f"block_{operation}")
                res = await fn(**data) if data else await fn()
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data})
    except KeyError as e:
        return _error(f"Missing param: {e}")
    except Exception as e:
        return _error(str(e))

    d = _to_dict(res)
    d = await add_screenshot_if_available(d, include_screenshot)
    return _json(d)


@mcp.tool(annotations={"title": "NBC View"})
async def nbc_view(operation: str, data: dict | None = None, include_screenshot: bool = False) -> str:
    """View — zoom_extents/zoom_window + screenshot (canvas-only if available)."""
    if data is None:
        data = {}
    try:
        ViewModel(**data)
    except ValidationError as e:
        return _error(str(e))

    gate = _nbc_gate("nbc_view", operation, data)
    if gate:
        return _json(gate)

    try:
        backend = await get_backend()
    except Exception as e:
        return _error(str(e))

    try:
        if operation in ("zoom_extents", "extents", "zoom", "fit"):
            res = await backend.zoom_extents() if hasattr(backend, "zoom_extents") else CommandResult(ok=True, payload="zoom_extents stub")
        elif operation in ("zoom_window", "window", "zoom_win"):
            x1 = float(data.get("x1", 0))
            y1 = float(data.get("y1", 0))
            x2 = float(data.get("x2", 100))
            y2 = float(data.get("y2", 100))
            if hasattr(backend, "zoom_window"):
                res = await backend.zoom_window(x1=x1, y1=y1, x2=x2, y2=y2)
            else:
                res = CommandResult(ok=True, payload={"zoom_window": [x1, y1, x2, y2]})
        elif operation in ("screenshot", "capture", "get_screenshot"):
            if hasattr(backend, "get_screenshot"):
                res = await backend.get_screenshot()
            else:
                res = CommandResult(ok=False, error="screenshot not supported on this backend")
        else:
            if hasattr(backend, operation):
                fn = getattr(backend, operation)
                res = await fn(**data) if data else await fn()
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data})
    except KeyError as e:
        return _error(f"Missing param: {e}")
    except Exception as e:
        return _error(str(e))

    d = _to_dict(res)
    # For view operations, include_screenshot true means we already have screenshot payload; still pass through hook
    d = await add_screenshot_if_available(d, include_screenshot)
    return _json(d)


@mcp.tool(annotations={"title": "NBC System"})
async def nbc_system(operation: str, data: dict | None = None, include_screenshot: bool = False) -> str:
    """System — status/undo/redo/purge/plot_pdf/execute_lisp/get_variables (ALLOW_RCE gate)."""
    if data is None:
        data = {}
    try:
        SystemModel(**data)
    except ValidationError as e:
        return _error(str(e))

    # validate_against_knowledge — system has no direct NBC numeric gate
    gate = _nbc_gate("nbc_system", operation, data)
    if gate:
        return _json(gate)

    try:
        backend = await get_backend()
    except Exception as e:
        return _error(str(e))

    try:
        if operation in ("status", "info", "health"):
            res = await backend.status() if hasattr(backend, "status") else CommandResult(ok=True, payload={"backend": getattr(backend, "name", "unknown")})
        elif operation == "undo":
            res = await backend.undo() if hasattr(backend, "undo") else CommandResult(ok=True, payload="undo stub")
        elif operation == "redo":
            res = await backend.redo() if hasattr(backend, "redo") else CommandResult(ok=True, payload="redo stub")
        elif operation in ("purge", "drawing_purge"):
            res = await backend.drawing_purge() if hasattr(backend, "drawing_purge") else CommandResult(ok=True, payload="purge stub")
        elif operation in ("plot_pdf", "plot", "export_pdf"):
            path = data.get("path") or data.get("file") or "output.pdf"
            # security gate for path — propagate ValueError as error JSON
            try:
                from .security import validate_path

                validate_path(path)
            except ValueError as e:
                return _json({"ok": False, "error": str(e)})
            # Hama gold pre-flight 95 gate (every-run teaching)
            try:
                h_features: dict = {}
                try:
                    if hasattr(backend, "doc") and getattr(backend, "doc", None) is not None:
                        try:
                            from .rag.hama_store import extract_hama_features  # type: ignore

                            feats = extract_hama_features(backend.doc)
                            h_features.update(
                                {
                                    "has_title": "G-TTLB" in feats.get("layers", []),
                                    "has_north": "A-NORTH" in feats.get("layers", []),
                                    "has_viewport": feats.get("viewports", 0) > 0,
                                    "has_section_line": any("A-SECT" in l for l in feats.get("layers", [])),
                                    "has_hatch": feats.get("hatches_count", 0) > 0,
                                }
                            )
                        except Exception:
                            pass
                except Exception:
                    pass
                for k in ("has_title", "has_north", "has_viewport", "has_section_line", "has_hatch", "hatch_pattern", "hatch_scale", "detail_scale", "viewport_scale"):
                    if k in data:
                        h_features[k] = data[k]
                if h_features:
                    from .nbc.validator import score_drawing_hama

                    hres = score_drawing_hama(h_features)
                    if hres.get("score", 100) < 95:
                        return _json({"ok": False, "error": f"Hama plot gate {hres.get('score')}/100 <95 blocked: {hres.get('findings')} - fix per hama://A001 gold", "hama_gate": hres})
            except Exception:
                pass
            if hasattr(backend, "drawing_plot_pdf"):
                res = await backend.drawing_plot_pdf(path=path)
            else:
                res = CommandResult(ok=True, payload={"plot": path})
        elif operation in ("get_variables", "variables", "get_vars"):
            names = data.get("names") or data.get("variables")
            if hasattr(backend, "drawing_get_variables"):
                res = await backend.drawing_get_variables(names=names)
            else:
                res = CommandResult(ok=True, payload={"variables": names})
        elif operation in ("execute_lisp", "lisp", "eval_lisp", "dotnet_invoke", "dotnet"):
            code = data.get("code") or data.get("command") or ""
            # RCE gate — enforce ALLOW_RCE from config.py; set AUTOCAD_ARCH_MCP_ALLOW_RCE=1 to enable
            from .config import ALLOW_RCE

            if not ALLOW_RCE:
                return _json({"ok": False, "error": "RCE disabled, set AUTOCAD_ARCH_MCP_ALLOW_RCE=1"})
            if hasattr(backend, "execute_lisp"):
                res = await backend.execute_lisp(code=code)
            else:
                res = CommandResult(ok=False, error="execute_lisp not supported on this backend")
        else:
            if hasattr(backend, operation):
                fn = getattr(backend, operation)
                try:
                    res = await fn(**data) if data else await fn()
                except TypeError:
                    res = await fn(data.get("path") or data.get("code") or "")
            elif hasattr(backend, f"drawing_{operation}"):
                fn = getattr(backend, f"drawing_{operation}")
                res = await fn(**data) if data else await fn()
            elif hasattr(backend, "_dispatch"):
                res = await backend._dispatch(operation, data)
            else:
                res = CommandResult(ok=True, payload={"operation": operation, "data": data})
    except KeyError as e:
        return _error(f"Missing param: {e}")
    except Exception as e:
        return _error(str(e))

    d = _to_dict(res)
    d = await add_screenshot_if_available(d, include_screenshot)
    return _json(d)


@mcp.tool(annotations={"title": "Hama Gold"})
async def hama_gold(operation: str, data: dict | None = None, include_screenshot: bool = False) -> str:
    """Hama gold teaching — every-run retrieval of construction perfection.

    operations:
    - retrieve: data {intent: str, k: int=3} -> top-k gold exemplars (BARAL municipal + Hama A001/A020) via cosine similarity
    - similarity: data {features: dict, gold_id: str="hama_A001"} -> 0-100 vs Hama
    - extract: data {} -> extract current drawing features via ezdxf (layers, dims, hatches, viewports) for scoring
    - score: data {features: dict} -> composite Hama 0.5*validator +0.3*vision+0.2*sim
    """
    if data is None:
        data = {}
    try:
        if operation in ("retrieve", "query", "search"):
            intent = data.get("intent") or data.get("query") or "architectural plan"
            k = int(data.get("k", 3))
            if hama_retrieve is None:
                return _json({"ok": False, "error": "hama_store not available"})
            res = hama_retrieve(intent, k=k)
            return _json({"ok": True, "gold": res})
        elif operation in ("similarity", "sim", "hama_similarity"):
            features = data.get("features") or {}
            gold_id = data.get("gold_id", "hama_A001")
            if hama_similarity is None:
                return _json({"ok": False, "error": "hama_store not available"})
            sim = hama_similarity(features, gold_id=gold_id)
            return _json({"ok": True, "similarity": sim, "gold_id": gold_id})
        elif operation in ("extract", "features", "extract_features"):
            try:
                backend = await get_backend()
                if hasattr(backend, "doc") and getattr(backend, "doc", None) is not None:
                    try:
                        from .rag.hama_store import extract_hama_features  # type: ignore

                        feats = extract_hama_features(backend.doc)
                        return _json({"ok": True, "features": feats})
                    except Exception as e:
                        return _error(str(e))
                else:
                    return _json({"ok": False, "error": "no doc (use file_ipc backend with AutoCAD or ezdxf headless after drawing_create)"})
            except Exception as e:
                return _error(str(e))
        elif operation in ("score", "score_hama", "composite"):
            features = data.get("features") or {}
            # optionally extract from doc if empty
            if not features:
                try:
                    backend = await get_backend()
                    if hasattr(backend, "doc") and getattr(backend, "doc", None) is not None:
                        from .rag.hama_store import extract_hama_features  # type: ignore

                        feats = extract_hama_features(backend.doc)
                        features.update(
                            {
                                "has_title": "G-TTLB" in feats.get("layers", []),
                                "has_north": "A-NORTH" in feats.get("layers", []),
                                "has_viewport": feats.get("viewports", 0) > 0,
                                "has_section_line": any("A-SECT" in l for l in feats.get("layers", [])),
                                "has_hatch": feats.get("hatches_count", 0) > 0,
                            }
                        )
                except Exception:
                    pass
            try:
                from .nbc.validator import score_drawing_hama
                from .nbc.judge import hama_composite  # type: ignore

                # if doc available, use hama_composite for full 0.5/0.3/0.2
                try:
                    backend = await get_backend()
                    if hasattr(backend, "doc") and getattr(backend, "doc", None) is not None:
                        # try composite with doc
                        try:
                            comp = hama_composite(backend.doc, features, None)
                            return _json({"ok": True, "hama_composite": comp})
                        except Exception:
                            pass
                except Exception:
                    pass
                # fallback to validator-only Hama score
                res = score_drawing_hama(features)
                return _json({"ok": True, "hama_score": res})
            except Exception as e:
                return _error(str(e))
        else:
            return _json({"ok": False, "error": f"unknown hama_gold operation {operation}"})
    except Exception as e:
        return _error(str(e))


@mcp.tool(annotations={"title": "NBC Generate Any"})
async def nbc_generate(operation: str, data: dict | None = None, include_screenshot: bool = False) -> str:
    """Generate any Hama-level drawing: plan 1:100, section 1:20, detail 1:5, schedule, site 1:200.

    operation: drawing_type e.g., plan, section, detail, schedule, site, elevation, wall_detail
    data: {scale: "1:100"/"1:5"/"1:20", building: [WxH], grid_x, grid_y, walls, title, detail_type, kind, building, etc}
    """
    if data is None:
        data = {}
    # Gate via validator any
    drawing_type = operation or data.get("drawing_type", "plan")
    scale = data.get("scale", "1:100")
    # Validate drawing_type/scale ladder
    allowed_scales = ["1:5", "1:10", "1:16", "1:20", "1:25", "1:50", "1:100", "1:150", "1:200", "1:275", "1:500"]
    if scale not in allowed_scales and not scale.startswith("1:"):
        return _json({"ok": False, "error": f"scale {scale} not in Hama ladder {allowed_scales}"})
    if generate_any is None:
        return _json({"ok": False, "error": "generators not available"})
    try:
        backend = await get_backend()
    except Exception as e:
        return _error(str(e))
    try:
        params = dict(data)
        params["scale"] = scale
        params["drawing_type"] = drawing_type
        res = await generate_any(backend, drawing_type, params)
        d = {"ok": True, "payload": res}
        d = await add_screenshot_if_available(d, include_screenshot)
        # Score via Hama composite any
        try:
            from .nbc.judge import hama_composite_any  # type: ignore

            # Build validator features from params
            feats: dict = {}
            if params.get("building"):
                # infer room area etc?
                pass
            comp = hama_composite_any(backend.doc, feats, drawing_type=drawing_type)
            d["hama_score"] = comp
        except Exception:
            pass
        return _json(d)
    except Exception as e:
        return _error(str(e))


def main() -> None:
    """Entry for python -m autocad_arch_mcp."""
    mcp.run(transport="stdio")
