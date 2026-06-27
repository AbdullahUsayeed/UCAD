"""DXF preprocessor — validates, cleans, and returns structured 2D profile data.
Uses ezdxf for parsing and Shapely for geometry validation/cleaning.

Current contract: DXF -> closed manufacturable profiles.
Open entities (ARC, LINE, open SPLINE, open POLYLINE, etc.) are intentionally
ignored because they cannot be extruded without inference.

Future extension point — auto-close open geometry:
    process_dxf(path, allow_open=False, auto_close="off")

    auto_close="safe":
      Level 1 — endpoint snapping (coincident endpoints within tolerance)
      Level 2 — chain assembly (connect endpoint-adjacent entities)
      Level 3 — near-closed loop completion (gap < 5% of perimeter)

    auto_close="aggressive": (Levels 1-3 + below)
      Level 4 — tangent-continuous path merging
      Level 5 — feature reconstruction (midlines, bend lines, centerlines)

    Implement via: _close_open_path(entities, mode, tolerance) -> List[Polygon]"""

from typing import List, Dict, Any, Optional, Tuple, Set
import math
import os
from collections import defaultdict, Counter

import ezdxf
from ezdxf.addons import geo
from shapely.geometry import Polygon
from shapely import make_valid, simplify, coverage_union_all


# ── Unit conversion (all factors to mm) ──────────────────────────
_UNIT_TABLE: Dict[int, Tuple[str, float]] = {
    0:  ("unknown", 1.0),
    1:  ("inches", 25.4),
    2:  ("feet", 304.8),
    3:  ("miles", 1609344.0),
    4:  ("millimeters", 1.0),
    5:  ("centimeters", 10.0),
    6:  ("meters", 1000.0),
    7:  ("kilometers", 1_000_000.0),
    8:  ("microinches", 2.54e-5),
    9:  ("mils", 0.0254),
    10: ("yards", 914.4),
    11: ("angstroms", 1e-7),
    12: ("nanometers", 1e-6),
    13: ("microns", 0.001),
    14: ("decimeters", 100.0),
    15: ("decameters", 10_000.0),
    16: ("hectometers", 100_000.0),
    17: ("gigameters", 1e12),
}


def _guess_units(extents_max: float) -> tuple:
    """Guess units from the largest coordinate value.
    Returns (unit_name, scale_to_mm)."""
    if extents_max > 5000:
        return ("inches_assumed", 25.4)
    elif extents_max > 500:
        return ("mm_uncertain", 1.0)
    else:
        return ("mm", 1.0)


def process_dxf(filepath: str, tolerance: Optional[float] = None,
                layers: Optional[List[str]] = None,
                merge_multipolygons: bool = True,
                auto_close: str = "off") -> Dict[str, Any]:
    """Load a DXF file, extract 2D profiles, clean, and return structured JSON.

    Args:
        filepath: Path to the DXF file.
        tolerance: Simplification tolerance in mm. If None, auto-scaled
                   to 0.1% of the bounding box diagonal.
        layers: Only process entities on these layers (None = all).
        merge_multipolygons: If True, merge touching/overlapping sub-geometries
                             of a MultiPolygon into a single profile.
                             If False, each sub-geometry becomes its own profile.
        auto_close: How to handle open (non-closed) entities:
                    "off" — skip open entities (default).
                    "safe" — auto-close individual entities whose start/end
                             endpoints are within tolerance.
                    "aggressive" — safe mode + chain assembly connecting
                                   endpoint-adjacent entities into closed loops.

    Returns:
        Dict with keys: status, profiles, warnings, metadata.
    """
    warn_counts: Counter = Counter()
    doc, recovery_warnings = _read_dxf(filepath, warn_counts)
    if doc is None:
        return {"status": "error", "error": "Cannot read DXF file",
                "profiles": [], "warnings": ["Cannot read DXF file"], "metadata": {}}

    msp = doc.modelspace()
    layer_filter: Optional[Set[str]] = set(layers) if layers else None

    # Collect all coords early for unit guessing
    all_xs, all_ys = [], []

    # ── Step 1: Extract geometry from all supported entity types ───
    raw_entries: List[Tuple[Polygon, str]] = []
    open_entities: List[Tuple[Any, List[tuple], str]] = []  # (entity, coords, layer)

    for entity in msp.query("LWPOLYLINE POLYLINE CIRCLE ARC ELLIPSE SPLINE"):
        try:
            layer = entity.dxf.layer
            if layer_filter and layer not in layer_filter:
                continue

            if entity.dxftype() == "CIRCLE":
                geom = _circle_to_polygon(entity)
                if geom is not None:
                    raw_entries.append((geom, layer))
                continue

            if entity.dxftype() == "ARC":
                geom = _arc_to_polygon(entity)
                if geom is not None:
                    raw_entries.append((geom, layer))
                elif auto_close != "off":
                    closed_geom = _arc_to_polygon(entity, force_close=True)
                    if closed_geom is not None:
                        raw_entries.append((closed_geom, layer))
                        warn_counts["ARC auto-closed as full circle"] += 1
                    else:
                        warn_counts["ARC skipped (non-closed)"] += 1
                else:
                    warn_counts["ARC skipped (non-closed)"] += 1
                continue

            closed = _is_closed(entity)

            coords = _entity_coords_path(entity)
            if coords is None:
                coords = _entity_coords_direct(entity)

            if not coords or len(coords) < 3:
                continue

            # Track extents for unit guessing
            for x, y in coords:
                all_xs.append(x)
                all_ys.append(y)

            if closed and coords[0] != coords[-1]:
                coords.append(coords[0])

            if not closed:
                if auto_close != "off":
                    open_entities.append((entity, coords, layer))
                else:
                    warn_counts[f"{entity.dxftype()} skipped (non-closed)"] += 1
                continue

            try:
                poly = Polygon(coords)
                if poly.is_empty or (poly.is_valid and poly.area < 1e-8):
                    continue
                raw_entries.append((poly, layer))
            except Exception as e:
                warn_counts[f"Bad polygon on layer '{layer}': {e}"] += 1
                continue

        except Exception as e:
            ent_layer = getattr(entity, 'dxf', None)
            ent_layer = getattr(ent_layer, 'layer', '?') if ent_layer else '?'
            warn_counts[f"Error processing entity on layer '{ent_layer}': {e}"] += 1

    # ── Unit handling (guess after we have coordinate extents) ──
    extents_max = 0.0
    if all_xs and all_ys:
        extents_max = max(abs(max(all_xs)), abs(min(all_xs)),
                          abs(max(all_ys)), abs(min(all_ys)))
    insunits = doc.header.get("$INSUNITS", 0)
    if insunits == 0:
        unit_name, mm_factor = _guess_units(extents_max)
        warn_counts[f"DXF units undefined, guessed '{unit_name}'"] += 1
    else:
        unit_name, mm_factor = _UNIT_TABLE.get(insunits, ("unknown", 1.0))
        if mm_factor != 1.0:
            warn_counts[f"Converting from {unit_name} to mm (x{mm_factor})"] += 1

    # ── Auto-close open entities ──────────────────────────────────
    if auto_close != "off" and open_entities:
        closed_indices: Set[int] = set()
        for i, (entity, coords, layer) in enumerate(open_entities):
            closed_coords = _try_close_entity(entity, coords, layer, tolerance, warn_counts)
            if closed_coords is not None:
                closed_indices.add(i)
                try:
                    poly = Polygon(closed_coords)
                    if not poly.is_empty and poly.area >= 1e-8:
                        raw_entries.append((poly, layer))
                except Exception as e:
                    warn_counts[f"Polygon from auto-closed entity failed: {e}"] += 1

        # Chain assembly (aggressive mode only)
        if auto_close == "aggressive":
            remaining = [(coords, layer)
                         for i, (e, coords, layer) in enumerate(open_entities)
                         if i not in closed_indices]
            if remaining:
                chained = _chain_open_entities(remaining, tolerance, mm_factor, warn_counts)
                for coords, layer in chained:
                    if len(coords) < 3:
                        continue
                    try:
                        poly = Polygon(coords)
                        if not poly.is_empty and poly.area >= 1e-8:
                            raw_entries.append((poly, layer))
                            warn_counts["Chained open entities into closed profile"] += 1
                    except Exception as ex:
                        warn_counts[f"Chained polygon creation failed: {ex}"] += 1

    # HATCH boundaries
    for entity in msp.query("HATCH"):
        try:
            layer = entity.dxf.layer
            if layer_filter and layer not in layer_filter:
                continue
            try:
                for polygon in geo.from_hatch_boundary_path(entity):
                    if polygon and not polygon.is_empty and polygon.area > 1e-8:
                        raw_entries.append((polygon, layer))
            except Exception:
                warn_counts["HATCH boundary parse error"] += 1
        except Exception as e:
            ent_layer = getattr(entity, 'dxf', None)
            ent_layer = getattr(ent_layer, 'layer', '?') if ent_layer else '?'
            warn_counts[f"HATCH entity error on layer '{ent_layer}': {e}"] += 1

    if not raw_entries:
        warn_counts["No valid closed polygonal geometry found in DXF"] += 1

    # ── Step 2: Validate and clean each profile ────────────────────
    cleaned_profiles = []
    seen_layers: Set[str] = set()

    # Compute global bbox to scale tolerance
    xs_all, ys_all = [], []
    for geom, _layer in raw_entries:
        try:
            bounds = geom.bounds
            xs_all.extend([bounds[0], bounds[2]])
            ys_all.extend([bounds[1], bounds[3]])
        except Exception:
            pass

    if xs_all:
        bbox_diag = math.sqrt(
            (max(xs_all) - min(xs_all)) ** 2 +
            (max(ys_all) - min(ys_all)) ** 2)
    else:
        bbox_diag = 0.0

    if tolerance is None:
        tolerance = max(bbox_diag * 0.001, 0.001)

    for geom, layer in raw_entries:
        if mm_factor != 1.0:
            geom = _scale_polygon(geom, mm_factor)
        for pw in _process_one_geometry(geom, tolerance, merge_multipolygons):
            pw["layer"] = layer
            pw["profile_type"] = _classify_profile(layer, pw)
            cleaned_profiles.append(pw)
            seen_layers.add(layer)

    # ── Step 2b: Fallback outline classification ───────────────────
    cleaned_profiles = _apply_outline_fallback(cleaned_profiles)

    # ── Step 3: Detect overlaps between profiles ───────────────────
    if len(cleaned_profiles) > 1:
        overlap_warnings = _detect_overlaps(cleaned_profiles)
        for w in overlap_warnings:
            warn_counts[w] += 1

    # ── Step 4: Global bounding box ────────────────────────────────
    xs, ys = [], []
    for p in cleaned_profiles:
        xs.extend(c[0] for c in p["coordinates"])
        ys.extend(c[1] for c in p["coordinates"])
    bbox = [min(xs), min(ys), max(xs), max(ys)] if xs else [0.0, 0.0, 0.0, 0.0]

    # Promote per-profile warnings to global counter
    for p in cleaned_profiles:
        pw = p.pop("_warnings", None)
        if pw:
            for w in pw:
                warn_counts[f"[layer '{p['layer']}'] {w}"] += 1

    # ── Convert warning counter to deduplicated list ───────────────
    warnings_list: List[str] = []
    for msg, count in warn_counts.most_common():
        if count > 1:
            warnings_list.append(f"{msg} (x{count})")
        else:
            warnings_list.append(msg)

    # ── Normalize all coordinates to origin ─────────────────────────
    result = {
        "status": "ok",
        "profiles": cleaned_profiles,
        "warnings": warnings_list,
        "units": unit_name,
        "unit_scale": mm_factor,
        "metadata": {
            "units": unit_name,
            "mm_factor": mm_factor,
            "layers": sorted(seen_layers),
            "profile_count": len(cleaned_profiles),
            "bbox": bbox,
        }
    }
    result = _normalize_to_origin(result)

    return result


# ── Geometry helpers ─────────────────────────────────────────────


def _normalize_to_origin(result: Dict[str, Any]) -> Dict[str, Any]:
    """Translate all profile coordinates so bounding box center sits at (0,0)."""
    profiles: List[Dict[str, Any]] = result.get("profiles", [])
    if not profiles:
        return result

    xs: List[float] = []
    ys: List[float] = []
    for p in profiles:
        coords = p.get("coordinates", [])
        if coords:
            for c in coords:
                xs.append(c[0])
                ys.append(c[1])
    if not xs or not ys:
        return result

    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0

    for p in profiles:
        coords = p.get("coordinates", [])
        if coords:
            p["coordinates"] = [(x - cx, y - cy) for x, y in coords]
        holes = p.get("holes", [])
        if holes:
            p["holes"] = [[(x - cx, y - cy) for x, y in h] for h in holes]
        bbox = p.get("bbox")
        if bbox and len(bbox) == 4:
            p["bbox"] = [round(bbox[0] - cx, 3), round(bbox[1] - cy, 3),
                         round(bbox[2] - cx, 3), round(bbox[3] - cy, 3)]

    meta = result.get("metadata", {})
    old_bbox = meta.get("bbox")
    if old_bbox and len(old_bbox) == 4:
        meta["bbox"] = [round(old_bbox[0] - cx, 3), round(old_bbox[1] - cy, 3),
                        round(old_bbox[2] - cx, 3), round(old_bbox[3] - cy, 3)]
    meta["origin_offset"] = [round(cx, 3), round(cy, 3)]
    meta["normalized"] = True

    return result


def _scale_polygon(geom, factor: float) -> Polygon:
    """Scale a polygon uniformly, preserving holes."""
    if factor == 1.0:
        return geom
    if hasattr(geom, 'geom_type') and geom.geom_type == 'MultiPolygon':
        scaled = [_scale_polygon(g, factor) for g in geom.geoms]
        return coverage_union_all([g for g in scaled if not g.is_empty])

    ext = [(x * factor, y * factor) for x, y in geom.exterior.coords]
    holes = [[(x * factor, y * factor) for x, y in ring.coords]
             for ring in geom.interiors]
    try:
        return Polygon(ext, holes)
    except Exception:
        return geom.buffer(0)


def _classify_profile(layer: str, profile: Dict) -> str:
    """Classify a profile by its layer name and geometric properties.

    Uses regex matching for flexible layer name recognition.
    Returns one of: outline, hole, cutout, slot, drill, bend_line, engrave, keep_out, unknown.
    """
    import re
    lu = layer.strip().upper()

    # Exact matches first
    if lu in ("OUTLINE", "BOARD", "BODY", "PROFILE", "PROFILE_OUTER"):
        return "outline"
    if lu in ("CUTOUT", "CUT_OUT", "POCKET", "CAVITY"):
        return "cutout"
    if lu in ("HOLE", "DRILL", "DRILLS", "THRU"):
        return "drill"
    if lu in ("SLOT", "SLOTS"):
        return "slot"
    if lu in ("BEND", "FOLD", "BEND_LINE"):
        return "bend_line"
    if lu in ("ENGRAVE", "TEXT", "MARK", "ETCH"):
        return "engrave"
    if lu in ("KEEP_OUT", "KEEPOUT", "RESTRICT", "RESTRICTED", "KEEPOUT_ZONE"):
        return "keep_out"

    # Regex-based matching for common patterns
    if re.search(r'\b(OUTLINE|OUTER|PROFILE)\b', lu):
        return "outline"
    if re.search(r'\b(CUTOUT?|POCKET|CAVITY|THRU)\b', lu):
        return "cutout"
    if re.search(r'\b(HOLE|DRILL|THRU)\b', lu):
        return "drill"
    if re.search(r'\bSLOT\b', lu):
        return "slot"
    if re.search(r'\b(BEND|FOLD|BEND_LINE)\b', lu):
        return "bend_line"
    if re.search(r'\b(ENGRAVE|TEXT|MARK|ETCH)\b', lu):
        return "engrave"
    if re.search(r'\b(KEEP.?OUT|RESTRICT)\b', lu):
        return "keep_out"

    # Heuristic: small profile on a layer with "hole" or "cut" in name
    if "HOLE" in lu or "DRILL" in lu:
        return "drill"
    if "CUT" in lu:
        return "cutout"
    if "SLOT" in lu:
        return "slot"
    return "unknown"


def _apply_outline_fallback(profiles):
    """When no profile has OUTLINE classification, tag the largest closed profile."""
    if any(p.get("profile_type") == "outline" for p in profiles):
        return profiles
    closed = [p for p in profiles if p.get("type") == "Polygon"]
    if not closed:
        return profiles
    largest = max(closed, key=lambda p: p.get("area", 0))
    largest["profile_type"] = "outline"
    largest["classification_source"] = "largest_area_heuristic"
    return profiles


# ── DXF I/O ──────────────────────────────────────────────────────

def _read_dxf(filepath: str, warn_counts: Counter) -> Tuple[Any, bool]:
    """Read DXF with recovery. Returns (doc, had_recovery_warnings)."""
    if not os.path.exists(filepath):
        warn_counts["File not found"] += 1
        return None, False
    try:
        doc = ezdxf.readfile(filepath)
        return doc, False
    except ezdxf.DXFStructureError as e:
        warn_counts[f"File has structural errors, attempting recovery: {e}"] += 1
        try:
            doc, audit_info = ezdxf.recover.readfile(filepath)
            if audit_info and audit_info.errors:
                for err in audit_info.errors[:5]:
                    warn_counts[f"DXF recovery error: {err}"] += 1
            return doc, True
        except Exception as e2:
            warn_counts[f"Recovery failed: {e2}"] += 1
            return None, False
    except IOError as e:
        warn_counts[f"Cannot read file: {e}"] += 1
        return None, False


# ── Entity extraction ────────────────────────────────────────────

def _entity_coords_path(entity) -> Optional[List[tuple]]:
    """Extract coordinates using ezdxf.make_path (handles bulge/arc segments)."""
    try:
        from ezdxf import path as ezpath
        main = ezpath.make_path(entity)
        if main is None or len(main) < 2:
            return None
        flat = list(main.flattening(0.1))
        return [(float(v.x), float(v.y)) for v in flat]
    except Exception:
        return None


def _entity_coords_direct(entity) -> Optional[List[tuple]]:
    """Fallback: extract vertices directly from entity."""
    try:
        if entity.dxftype() == "LWPOLYLINE":
            return [(float(p[0]), float(p[1])) for p in entity.vertices()]
        elif entity.dxftype() == "POLYLINE":
            return [(float(v.dxf.location.x), float(v.dxf.location.y))
                    for v in entity.vertices]
        elif entity.dxftype() == "SPLINE":
            bspline = entity.construction_tool()
            pts = [bspline.point(t / 63) for t in range(64)]
            return [(float(p.x), float(p.y)) for p in pts]
        elif entity.dxftype() == "ELLIPSE":
            return _ellipse_to_coords(entity)
    except Exception:
        return None
    return None


def _ellipse_to_coords(entity, n: int = 64) -> Optional[List[tuple]]:
    """Convert a DXF ELLIPSE to a polygon approximation.

    Samples n points between start_param and end_param.
    """
    try:
        cx, cy, _cz = entity.dxf.center
        mx, my, _mz = entity.dxf.major_axis
        ratio = entity.dxf.ratio
        start = entity.dxf.start_param
        end = entity.dxf.end_param
        a = math.sqrt(mx*mx + my*my)
        if a < 1e-12:
            return None
        b = a * ratio
        angle = math.atan2(my, mx)
        pts = []
        param_range = end - start
        for i in range(n):
            theta = start + param_range * i / (n - 1) if n > 1 else start
            ex = a * math.cos(theta) * math.cos(angle) - b * math.sin(theta) * math.sin(angle)
            ey = a * math.cos(theta) * math.sin(angle) + b * math.sin(theta) * math.cos(angle)
            pts.append((cx + ex, cy + ey))
        return pts
    except Exception:
        return None


def _is_closed(entity) -> bool:
    try:
        if entity.dxftype() == "LWPOLYLINE":
            return bool(entity.closed)
        if entity.dxftype() == "POLYLINE":
            return entity.is_closed
        if entity.dxftype() == "SPLINE":
            return bool(entity.dxf.flags & 1)
        if entity.dxftype() == "ELLIPSE":
            start = entity.dxf.start_param
            end = entity.dxf.end_param
            return abs(end - start - 2 * math.pi) < 1e-6
    except Exception:
        return False
    return False


def _circle_to_polygon(entity) -> Optional[Polygon]:
    """Convert a DXF CIRCLE to a 64-segment Shapely Polygon."""
    try:
        cx, cy = entity.dxf.center.x, entity.dxf.center.y
        r = float(entity.dxf.radius)
        if r <= 0:
            return None
        n = 64
        pts = [(cx + r * math.cos(2 * math.pi * i / n),
                cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
        return Polygon(pts)
    except Exception:
        return None


def _arc_to_polygon(entity, force_close: bool = False) -> Optional[Polygon]:
    """Convert a closed ARC (full circle) to a polygon.
    Non-closed arcs are converted and treated as open geometry.
    When force_close=True, also converts partial arcs to polygons."""
    try:
        cx, cy = entity.dxf.center.x, entity.dxf.center.y
        r = float(entity.dxf.radius)
        if r <= 0:
            return None
        start_deg = entity.dxf.start_angle
        end_deg = entity.dxf.end_angle
        sweep = (end_deg - start_deg) % 360.0
        is_full = abs(sweep - 360.0) < 1e-6 or abs(sweep) < 1e-6
        if is_full:
            n = 64
            pts = [(cx + r * math.cos(2 * math.pi * i / n),
                    cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
            return Polygon(pts)
        if force_close:
            # Convert partial arc to a pie-shaped polygon
            start_rad = math.radians(start_deg)
            end_rad = math.radians(end_deg)
            n = max(16, int(abs(sweep) / 5))
            pts = [(cx, cy)]
            for i in range(n + 1):
                theta = start_rad + (end_rad - start_rad) * i / n
                pts.append((cx + r * math.cos(theta), cy + r * math.sin(theta)))
            pts.append((cx, cy))
            return Polygon(pts)
        return None
    except Exception:
        return None


def _try_close_entity(entity, coords: List[tuple], layer: str,
                      tolerance: Optional[float],
                      warn_counts: Counter) -> Optional[List[tuple]]:
    """Try to close an open entity by connecting its endpoints.

    Closes if the start-end gap is within tolerance or within 5% of perimeter.
    Returns closed coordinates (with start point appended) or None.
    """
    if not coords or len(coords) < 2:
        return None

    start = coords[0]
    end = coords[-1]

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    gap = math.sqrt(dx*dx + dy*dy)

    perimeter = sum(
        math.sqrt((coords[k+1][0]-coords[k][0])**2 +
                  (coords[k+1][1]-coords[k][1])**2)
        for k in range(len(coords)-1)
    )

    perim_based = perimeter * 0.05
    tol_based = (tolerance or 0.1) * 5
    threshold = max(perim_based, tol_based, 0.01)

    if gap <= threshold:
        closed = coords + [coords[0]]
        warn_counts[f"Auto-closed {entity.dxftype()} (gap={gap:.3f})"] += 1
        return closed

    return None


def _sample_entity(entity, samples=20):
    """Sample an entity into a polyline, handling SPLINE and other types."""
    try:
        if entity.dxftype() == "SPLINE":
            bspline = entity.construction_tool()
            return [(float(bspline.point(t / (samples - 1)).x),
                     float(bspline.point(t / (samples - 1)).y))
                    for t in range(samples)]
        coords = _entity_coords_path(entity)
        if coords is None:
            coords = _entity_coords_direct(entity)
        if coords and len(coords) >= 2:
            stride = max(1, len(coords) // samples)
            return [coords[i] for i in range(0, len(coords), stride)]
        return coords or []
    except Exception:
        return []


def _dist(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def _chain_open_entities(entries, tolerance, mm_factor, warn_counts):
    """Chain open entities into closed profiles by endpoint matching.

    Uses a second-pass approach with wider gap tolerance and spline sampling.
    Returns list of (closed_coords, layer) tuples.
    """
    # First pass: try the existing greedy chain algorithm
    existing_chains = _chain_entities_greedy(entries, tolerance, warn_counts)

    # Second pass: spline chaining with wider gap tolerance
    result = list(existing_chains)

    # Group coords by layer for second pass
    segments = {}
    for i, (coords, layer) in enumerate(entries):
        pts = coords or []
        if len(pts) >= 2:
            segments.setdefault(layer, []).append({
                "start": pts[0], "end": pts[-1], "pts": pts, "idx": i
            })

    # Group by layer and try chaining
    chained = []
    for layer, segs in segments.items():
        used_segs = set()
        for si, seg in enumerate(segs):
            if si in used_segs:
                continue
            chain = list(seg["pts"])
            used_segs.add(si)
            changed = True
            while changed:
                changed = False
                tail = chain[-1]
                perimeter = sum(_dist(chain[j], chain[j + 1]) for j in range(len(chain) - 1))
                tol = max(1.0, perimeter * 0.05)
                for sj, other in enumerate(segs):
                    if sj in used_segs:
                        continue
                    if _dist(tail, other["start"]) < tol:
                        chain.extend(other["pts"][1:])
                        used_segs.add(sj)
                        changed = True
                        break
                    elif _dist(tail, other["end"]) < tol:
                        chain.extend(reversed(other["pts"][:-1]))
                        used_segs.add(sj)
                        changed = True
                        break
            # Check if chain closes
            gap = _dist(chain[0], chain[-1])
            perimeter = sum(_dist(chain[j], chain[j + 1]) for j in range(len(chain) - 1))
            tol = max(1.0, perimeter * 0.05)
            if gap <= tol:
                # Close the chain
                if gap < 0.05:
                    chain[-1] = chain[0]
                else:
                    chain.append(chain[0])
                chained.append((chain, layer))
                warn_counts["SPLINE chain closed into profile"] += 1

    result.extend(chained)
    return result


def _chain_entities_greedy(entries, tolerance, warn_counts):
    """Greedy endpoint-matching chain (original algorithm)."""
    from collections import defaultdict
    by_layer = defaultdict(list)
    for coords, layer in entries:
        if coords and len(coords) >= 2:
            by_layer[layer].append(list(coords))

    result = []
    for layer, pool in by_layer.items():
        chain_threshold = max((tolerance or 0.1) * 2, 0.1)
        changed = True
        while changed:
            changed = False
            used = set()
            for i in range(len(pool)):
                if i in used:
                    continue
                chain = pool[i]
                if len(chain) < 2:
                    used.add(i)
                    continue
                chain_start = chain[0]
                chain_end = chain[-1]
                best_j = -1
                best_mode = 0
                best_dist = chain_threshold + 1
                for j, seg in enumerate(pool):
                    if i == j or j in used or len(seg) < 2:
                        continue
                    seg_start = seg[0]
                    seg_end = seg[-1]
                    d_end_to_start = _dist(chain_end, seg_start)
                    d_end_to_end = _dist(chain_end, seg_end)
                    d_start_to_start = _dist(chain_start, seg_start)
                    d_start_to_end = _dist(chain_start, seg_end)
                    candidates = [
                        (d_end_to_start, 0, False),
                        (d_end_to_end, 0, True),
                        (d_start_to_start, 1, True),
                        (d_start_to_end, 1, False),
                    ]
                    for dist, _, _ in candidates:
                        if dist < best_dist:
                            best_dist = dist
                            best_j = j
                            if dist == d_end_to_start:
                                best_mode = 0
                            elif dist == d_end_to_end:
                                best_mode = 1
                            elif dist == d_start_to_start:
                                best_mode = 2
                            elif dist == d_start_to_end:
                                best_mode = 3
                if best_j >= 0 and best_dist <= chain_threshold:
                    seg = pool[best_j]
                    seg_rev = list(reversed(seg))
                    if best_mode == 0:
                        chain = chain + seg[1:]
                    elif best_mode == 1:
                        chain = chain + seg_rev[1:]
                    elif best_mode == 2:
                        chain = seg_rev + chain[1:]
                    elif best_mode == 3:
                        chain = seg + chain[1:]
                    pool[i] = chain
                    used.add(best_j)
                    changed = True
            pool = [p for idx, p in enumerate(pool) if idx not in used]
            if not changed:
                break
        for coords in pool:
            if len(coords) >= 3:
                result.append((coords, layer))
    return result


# ── Geometry processing ──────────────────────────────────────────

_AREA_CHANGE_THRESHOLD = 0.10  # 10%


def _process_one_geometry(geom: Polygon, tolerance: float,
                          merge_multipolygons: bool = True) -> List[Dict[str, Any]]:
    """Validate, repair, simplify a Shapely geometry.

    Returns a list of profile dicts (may be empty if geometry is degenerate).
    When the input is a MultiPolygon:
      - merge_multipolygons=True  → merge touching sub-geometries into one profile
      - merge_multipolygons=False → emit one profile per sub-geometry
    """
    profile_warnings: List[str] = []
    was_multi = hasattr(geom, 'geom_type') and geom.geom_type == 'MultiPolygon'
    orig_area = geom.area if hasattr(geom, 'area') else 0.0

    if not geom.is_valid:
        geom = make_valid(geom)
        if geom.is_empty:
            return []
        if hasattr(geom, 'geom_type') and geom.geom_type not in ('Polygon', 'MultiPolygon'):
            return []
        area_after = geom.area if hasattr(geom, 'area') else orig_area
        if orig_area > 0 and area_after > 0:
            change = abs(area_after - orig_area) / orig_area
            if change > _AREA_CHANGE_THRESHOLD:
                profile_warnings.append(
                    f"self-intersection repair changed area by {change:.1%}")
            else:
                profile_warnings.append("self-intersection repaired")
        else:
            profile_warnings.append("self-intersection repaired")

    # MultiPolygon handling — split into sub-geometries
    if hasattr(geom, 'geom_type') and geom.geom_type == 'MultiPolygon':
        polygons = [g for g in geom.geoms if not g.is_empty]
        if not polygons:
            return []
        for i, sub in enumerate(polygons):
            if not sub.is_valid:
                polygons[i] = sub.buffer(0)
        if len(polygons) == 1:
            results = _process_profile(polygons[0], tolerance, profile_warnings)
            return [results] if results else []
        if merge_multipolygons:
            merged = coverage_union_all(polygons)
            if merged.is_empty:
                return []
            if was_multi and not profile_warnings:
                profile_warnings.append("multi-part geometry merged")
            results = _process_profile(merged, tolerance, profile_warnings)
            return [results] if results else []
        else:
            # Emit one profile per sub-geometry
            out = []
            for sub in polygons:
                sub_results = _process_profile(sub, tolerance, list(profile_warnings))
                if sub_results:
                    out.append(sub_results)
            if not was_multi and not profile_warnings:
                profile_warnings.append("multi-part geometry split into islands")
            return out

    # Single Polygon case
    results = _process_profile(geom, tolerance, profile_warnings)
    return [results] if results else []


def _process_profile(geom, tolerance: float,
                     profile_warnings: List[str]) -> Optional[Dict[str, Any]]:
    """Simplify and serialize a single polygon (not MultiPolygon)."""
    pre_simplify_area = geom.area if hasattr(geom, 'area') else 0.0
    simplified = _simplify_polygon(geom, tolerance)
    if simplified is None:
        return None
    if pre_simplify_area > 0 and simplified.area > 0:
        change = abs(simplified.area - pre_simplify_area) / pre_simplify_area
        if change > _AREA_CHANGE_THRESHOLD:
            profile_warnings.append(
                f"simplification changed area by {change:.1%}")
    geom = simplified

    result = _geom_to_dict(geom, profile_warnings)
    if result is None:
        profile_warnings.append("profile skipped: fewer than 3 unique points after dedup")
        return None
    result["_warnings"] = profile_warnings
    return result


def _simplify_polygon(geom: Polygon, tolerance: float) -> Optional[Polygon]:
    try:
        if geom.is_empty:
            return None
        simplified = simplify(geom, tolerance=tolerance, preserve_topology=True)
        if simplified.is_empty:
            return None
        if hasattr(simplified, 'geom_type') and simplified.geom_type == 'MultiPolygon':
            areas = [(g.area, g) for g in list(simplified.geoms) if not g.is_empty]
            if not areas:
                return None
            simplified = max(areas, key=lambda x: x[0])[1]
        return simplified
    except Exception:
        return geom if not geom.is_empty else None


def _dedup_consecutive(points: list, tolerance: float = 1e-9) -> list:
    """Remove consecutive duplicate points where distance < tolerance.

    Also removes the closing duplicate if the last point equals the first
    (auto-close artifacts).
    """
    if not points:
        return points

    result = [points[0]]
    for pt in points[1:]:
        dx = pt[0] - result[-1][0]
        dy = pt[1] - result[-1][1]
        if (dx * dx + dy * dy) ** 0.5 >= tolerance:
            result.append(pt)

    if len(result) > 1:
        dx = result[-1][0] - result[0][0]
        dy = result[-1][1] - result[0][1]
        if (dx * dx + dy * dy) ** 0.5 < tolerance:
            result = result[:-1]

    return result


def _geom_to_dict(geom, extra_warnings: List[str]) -> Optional[Dict[str, Any]]:
    """Convert a Shapely geometry to a serializable dict.

    Returns None if the geometry has fewer than 3 unique consecutive points
    after deduplication.
    """
    if hasattr(geom, 'geom_type') and geom.geom_type == 'MultiPolygon':
        parts = sorted(list(geom.geoms), key=lambda g: g.area, reverse=True)
        result = _geom_to_dict(parts[0], extra_warnings)
        if result is None:
            return None
        return result
    try:
        exterior = list(geom.exterior.coords)
        holes = [list(ring.coords) for ring in geom.interiors]
    except Exception:
        return {"type": "Polygon", "coordinates": [], "holes": [],
                "area": 0, "bbox": [0, 0, 0, 0], "profile_type": "unknown"}
    exterior = _dedup_consecutive(exterior)
    if len(exterior) < 3:
        return None
    holes = [_dedup_consecutive(h) for h in holes if len(h) >= 3]
    min_x, min_y, max_x, max_y = geom.bounds
    return {
        "type": "Polygon",
        "coordinates": exterior,
        "holes": holes,
        "area": round(geom.area, 3),
        "bbox": [round(min_x, 3), round(min_y, 3),
                 round(max_x, 3), round(max_y, 3)],
    }


# ── Overlap detection ────────────────────────────────────────────

def _detect_overlaps(profiles: List[Dict[str, Any]]) -> List[str]:
    """Detect overlapping, nested, or duplicate profiles using STRtree.

    Uses Jaccard similarity for more robust detection.
    Distinguishes:
    - Nested/contained (one inside another — expected for cutouts)
    - True partial overlap (likely an error)
    - Duplicate / near-duplicate

    Complexity: O(n log n) vs naive O(n^2) for large sets.
    """
    from shapely.strtree import STRtree

    warnings: List[str] = []
    geoms: List[Optional[Polygon]] = []
    for p in profiles:
        try:
            g = Polygon(p["coordinates"], p["holes"])
            geoms.append(g)
        except Exception:
            geoms.append(None)

    # Build list of (original_index, polygon) for valid geometries
    valid_pairs = [(i, g) for i, g in enumerate(geoms) if g is not None and g.is_valid]
    if len(valid_pairs) < 2:
        return warnings

    valid_geoms = [g for _, g in valid_pairs]
    valid_orig_idx = [i for i, _ in valid_pairs]
    tree = STRtree(valid_geoms)

    for orig_i, ga in valid_pairs:
        for jj in tree.query(ga):
            j = valid_orig_idx[jj]
            if j <= orig_i:
                continue
            gb = geoms[j]

            try:
                if ga.equals(gb):
                    warnings.append(
                        f"Duplicate: layer '{profiles[orig_i]['layer']}' == '{profiles[j]['layer']}'")
                    continue
                # Check containment (after equals — A.contains(A) is True in Shapely)
                if ga.contains(gb) or gb.contains(ga):
                    continue
                inter = ga.intersection(gb)
                if inter.is_empty:
                    # Check for near-coincident edges using size-relative tolerance
                    ga_bounds = ga.bounds
                    gb_bounds = gb.bounds
                    min_dim = min(
                        ga_bounds[2] - ga_bounds[0],
                        ga_bounds[3] - ga_bounds[1],
                        gb_bounds[2] - gb_bounds[0],
                        gb_bounds[3] - gb_bounds[1],
                    )
                    eps = max(min_dim * 1e-5, 0.001)
                    buf_a = ga.buffer(eps)
                    buf_b = gb.buffer(eps)
                    if not buf_a.intersection(buf_b).is_empty:
                        warnings.append(
                            f"Near-miss: layer '{profiles[orig_i]['layer']}' and "
                            f"'{profiles[j]['layer']}' are close but don't overlap")
                    continue
                union = ga.union(gb)
                if union.is_empty:
                    continue
                jaccard = inter.area / union.area
                overlap_ratio = inter.area / min(ga.area, gb.area)

                if jaccard > 0.8:
                    warnings.append(
                        f"Near-duplicate: layer '{profiles[orig_i]['layer']}' ~ "
                        f"'{profiles[j]['layer']}' (Jaccard={jaccard:.0%})")
                elif overlap_ratio > 0.01:
                    warnings.append(
                        f"Partial overlap: layer '{profiles[orig_i]['layer']}' and "
                        f"'{profiles[j]['layer']}' overlap by {inter.area:.1f} sq-units "
                        f"(ratio={overlap_ratio:.1%})")
            except Exception:
                warnings.append(
                    f"Overlap detection failed between layer '{profiles[orig_i]['layer']}' "
                    f"and '{profiles[j]['layer']}'")
    return warnings
