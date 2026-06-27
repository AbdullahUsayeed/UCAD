# enclosure_template_v2.py
# -*- coding: utf-8 -*-
"""
Parametric PCB Enclosure Generator  ·  v2.1
=============================================
Produces a clean single-solid Shell and Lid as Part::Features.

  Shell_Final  — deep tray with standoffs, bosses, vent slots,
                 connector cutouts, optional cable anchors and snap arms
  Lid_Final    — cover with tongue, counterbores, optional label recess
  PCB_Board    — dark FR4 green PCB outline (reference only)
  Components   — light grey / black component blocks (reference only)
  MountingHole rings — gold/yellow mounting hole indicators (reference only)

FEATURES
--------
  • Dataclass-driven, typed config — no more magic-number dicts
  • Connector type registry — USB-A/C, HDMI, barrel jack, RJ45, DB9, custom
  • Ventilation slot auto-generation (safe-zone clipped, density-aware)
  • Recessed label area on lid top face
  • Snap-fit cantilever arms as screw alternative
  • Cable-tie anchor posts with horizontal routing slots
  • Collision detection: boss↔standoff, connector↔boss, connector↔standoff,
    connector↔vent, cutout↔boss
  • Per-feature enable/disable flags
  • Per-boolean logging — failed fuses/cuts identified by feature name
  • Wall selection by footprint rotation (not just nearest-edge heuristic)
  • Custom cutout bounds validation with console logging
  • Auto BOM summary printed to FreeCAD console

REQUIREMENTS
-----------
  FreeCAD 0.20 +  (uses Part workbench only, no FreeCADGui dependency)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Set

import FreeCAD
import Part

# ──────────────────────────────────────────────────────────────────────────────
#  CONNECTOR TYPE REGISTRY
#  Add your own entries; width/height are the *panel hole* dimensions in mm.
# ──────────────────────────────────────────────────────────────────────────────

CONNECTOR_TYPES: Dict[str, Tuple[float, float]] = {
    "USB_A":       ( 8.5,  5.0),
    "USB_C":       ( 9.0,  3.5),
    "USB_MINI":    ( 7.5,  3.0),
    "MICRO_USB":   ( 8.0,  2.5),
    "HDMI":        (15.5,  6.5),
    "MINI_HDMI":   (11.5,  5.5),
    "BARREL_2_5":  ( 8.0,  8.0),   # circular — use width==height
    "BARREL_5_5":  (10.0, 10.0),
    "RJ45":        (16.0, 13.5),
    "DB9":         (25.0, 11.0),
    "DB15":        (33.4, 11.0),
    "SMA":         ( 8.0,  8.0),
    "CUSTOM":      ( 0.0,  0.0),   # fill in component dict directly
}

# ──────────────────────────────────────────────────────────────────────────────
#  STANDARD ENCLOSURE COLOURS  (RGB float tuples, values 0.0-1.0)
# ──────────────────────────────────────────────────────────────────────────────

COLOR_SHELL       = (0.85, 0.85, 0.85)  # light grey
COLOR_LID         = (0.75, 0.75, 0.80)  # slightly blue-grey
COLOR_PCB         = (0.00, 0.60, 0.00)  # green (translucent)
COLOR_COMPONENT   = (0.20, 0.20, 0.20)  # dark grey
COLOR_CONNECTOR   = (0.05, 0.05, 0.05)  # near black
COLOR_BOSS        = (0.85, 0.85, 0.85)  # same as shell
COLOR_HOLE_RING   = (0.83, 0.68, 0.21)  # gold
COLOR_STANDOFF    = (0.30, 0.50, 0.80)  # blue
COLOR_SNAP        = (0.65, 0.55, 0.10)  # bronze

# ──────────────────────────────────────────────────────────────────────────────
#  DATA STRUCTURES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class MountingHole:
    x: float
    y: float
    diameter: float = 2.5


@dataclass
class Component:
    ref: str
    x: float
    y: float
    height: float = 3.0
    width: float = 3.0         # footprint width (X)
    depth: float = 3.0         # footprint depth (Y)
    connector: bool = False
    connector_type: str = "CUSTOM"   # key in CONNECTOR_TYPES
    wall: Optional[str] = None       # force wall: "N"/"S"/"E"/"W" or None=auto
    rotation: float = 0.0            # footprint rotation in degrees (0=East, 90=North, etc.)


@dataclass
class BoardData:
    width: float
    height: float                          # PCB Y dimension
    mounting_holes: List[MountingHole] = field(default_factory=list)
    components:     List[Component]    = field(default_factory=list)


# Standard lid screw parameters indexed by screw size.
# (insert_od, insert_depth, screw_clearance_d, cbore_d, cbore_depth, boss_wall)
LID_SCREW_SIZES = {
    "M2":   (3.2, 3.0, 2.2, 4.5, 1.5, 1.2),
    "M2.5": (3.8, 3.5, 2.7, 5.0, 1.8, 1.4),
    "M3":   (4.2, 4.5, 3.2, 6.0, 2.0, 1.8),
    "M3.5": (4.8, 5.0, 3.7, 7.0, 2.2, 2.0),
    "M4":   (5.5, 5.5, 4.3, 8.0, 2.5, 2.2),
    "M5":   (6.8, 6.5, 5.3, 10.0, 3.0, 2.8),
    "M6":   (8.0, 7.5, 6.4, 12.0, 3.5, 3.2),
}


@dataclass
class EnclosureConfig:
    # ── Shell ────────────────────────────────────────────────────────────────
    wall_thickness:   float = 3.0
    floor_thickness:  float = 3.0
    lid_thickness:    float = 3.0
    corner_chamfer:   float = 1.5
    margin:           float = 6.0       # PCB-to-wall clearance

    # ── Heights ──────────────────────────────────────────────────────────────
    pcb_standoff_height: float = 5.0
    headroom:            float = 10.0   # above tallest component

    # ── Lid screws ──────────────────────────────────────────────────────────
    screw_size:             str   = "M3"
    lid_insert_od:          float = 4.2
    lid_insert_depth:       float = 4.5
    lid_screw_clearance_d:  float = 3.2
    lid_cbore_d:            float = 6.0
    lid_cbore_depth:        float = 2.0
    boss_wall:              float = 1.8

    # ── PCB standoffs ────────────────────────────────────────────────────────
    pcb_pilot_d:      float = 2.2
    pcb_pilot_depth:  float = 4.0
    standoff_wall:    float = 1.5

    # ── Lip ─────────────────────────────────────────────────────────────────
    lip_width:      float = 1.2
    lip_depth:      float = 1.8
    lip_clearance:  float = 0.15

    def __post_init__(self):
        sizes = LID_SCREW_SIZES.get(self.screw_size)
        if sizes and self.screw_size != "M3":
            (self.lid_insert_od,
             self.lid_insert_depth,
             self.lid_screw_clearance_d,
             self.lid_cbore_d,
             self.lid_cbore_depth,
             self.boss_wall) = sizes

    # ── Connector slots ──────────────────────────────────────────────────────
    connector_clearance:   float = 0.3
    connector_z_clearance: float = 0.3

    # ── Ventilation ──────────────────────────────────────────────────────────
    enable_vents:       bool  = True
    vent_slot_width:    float = 1.5    # individual slot width
    vent_slot_gap:      float = 2.0    # spacing between slots
    vent_slot_length:   float = 12.0   # slot length along wall
    vent_wall:          str   = "N"    # which wall: N/S/E/W
    vent_z_offset:      float = 3.0    # from floor to bottom of vent array

    # ── Label recess on lid ──────────────────────────────────────────────────
    enable_label_recess: bool  = True
    label_recess_depth:  float = 0.6
    label_margin:        float = 6.0    # from lid edge to recess edge

    # ── Snap-fit arms (replaces screws when enable_snaps=True) ──────────────
    enable_snaps:       bool  = False
    snap_arm_width:     float = 4.0
    snap_arm_length:    float = 8.0
    snap_arm_thickness: float = 1.2
    snap_hook_height:   float = 1.2

    # ── Cable-tie anchor posts ───────────────────────────────────────────────
    enable_cable_anchors: bool  = False
    cable_anchor_locs:    List[Tuple[float, float]] = field(default_factory=list)
    cable_anchor_r:       float = 1.5
    cable_anchor_h:       float = 5.0
    cable_slot_w:         float = 2.5   # slot cut through anchor for cable

    # ── Custom cutouts (AI-suggested holes) ─────────────────────────────────
    custom_cutouts: List[dict] = field(default_factory=list)  # [{type,wall,x_mm,y_mm,width_mm,height_mm?,label?}]

    # ── Per-feature on/off ───────────────────────────────────────────────────
    enable_chamfer:    bool = True
    enable_lip:        bool = True
    enable_connectors: bool = True
    enable_pcb_ref:    bool = True


# ──────────────────────────────────────────────────────────────────────────────
#  PCB TO ENCLOSURE ADAPTER  — converts parsed KiCad dicts to dataclass objects
# ──────────────────────────────────────────────────────────────────────────────

CONNECTOR_KEYWORDS = ["USB", "HDMI", "RJ45", "Audio", "Terminal", "Connector",
                       "Ethernet", "DSUB", "SIM", "SD", "microSD", "Header",
                       "PinHeader", "Socket", "Barrel_Jack", "DC",
                       "Button", "SW_", "Switch"]


def _detect_connector_type(name: str) -> str:
    name_u = name.upper().replace("-", "_")
    for key in CONNECTOR_TYPES:
        if key == "CUSTOM":
            continue
        if key in name_u:
            return key
    # Broader checks
    if "USB" in name_u and "A" in name_u:
        return "USB_A"
    if "USB" in name_u and "C" in name_u:
        return "USB_C"
    if "USB" in name_u:
        return "USB_C"
    if "HDMI" in name_u:
        return "HDMI"
    if "RJ45" in name_u or "ETHERNET" in name_u:
        return "RJ45"
    if "BARREL" in name_u or "DC" in name_u or "POWER" in name_u:
        return "BARREL_5_5"
    if "DB9" in name_u or "DSUB" in name_u:
        return "DB9"
    if "SMA" in name_u:
        return "SMA"
    return "CUSTOM"


def _is_connector_footprint(name: str) -> bool:
    name_l = name.lower()
    return any(kw.lower() in name_l for kw in CONNECTOR_KEYWORDS)


def board_dict_to_boarddata(board_dict: dict):
    """Convert a parsed PCB dict (from pcb_parser) to a BoardData dataclass."""
    dims = board_dict["dimensions"]
    x0 = dims.get("x_min", 0)
    y0 = dims.get("y_min", 0)
    holes = [
        MountingHole(round(h["x"] - x0, 4), round(h["y"] - y0, 4), h.get("diameter", 2.5))
        for h in board_dict.get("mounting_holes", [])
    ]
    edge_connector_refs = {
        c.get("ref", "") for c in board_dict.get("edge_connectors", [])
        if c.get("ref")
    }

    components = []
    for c in board_dict.get("components", []):
        ref = c.get("ref", "?")
        is_conn = ref in edge_connector_refs or _is_connector_footprint(c.get("name", ""))
        conn_type = _detect_connector_type(c.get("name", "")) if is_conn else "CUSTOM"
        wall = None
        if is_conn:
            wall = c.get("face")  # explicit face from parser (nearest-edge, most reliable)
        if not wall and is_conn and "rotation" in c:
            # Fallback: infer from rotation  (0°→E, 90°→N, 180°→W, 270°→S)
            rot_norm = float(c["rotation"]) % 360
            wall_map = {0: "E", 90: "N", 180: "W", 270: "S"}
            wall = wall_map.get(round(rot_norm / 90) * 90)
        rotation = float(c.get("rotation", 0))
        comp = Component(
            ref=ref,
            x=c["x"] - x0, y=c["y"] - y0,
            height=c.get("height", 3.0),
            width=c.get("width", 3.0) or 3.0,
            depth=c.get("length", 3.0) or 3.0,
            connector=is_conn,
            connector_type=conn_type,
            wall=wall,
            rotation=rotation,
        )
        components.append(comp)

    return BoardData(
        width=round(dims["width"], 4),
        height=round(dims["height"], 4),
        mounting_holes=holes,
        components=components,
    )


def _clamp(value, lo, hi, name):
    """Clamp a float to [lo, hi] and warn if out of range."""
    v = float(value)
    if v < lo or v > hi:
        FreeCAD.Console.PrintWarning(
            f"  [params] {name}={v:.2f} clamped to [{lo:.2f}, {hi:.2f}]\n"
        )
    return max(lo, min(hi, v))


def params_to_enclosure_config(params: dict):
    """Convert a flat params dict (from AI or UI) to an EnclosureConfig.

    All float dimensions are clamped to physically valid ranges to prevent
    the AI from emitting negative or absurdly large values.
    """
    custom_cutouts = params.get("custom_cutouts", [])
    if isinstance(custom_cutouts, list):
        validated = []
        for cc in custom_cutouts:
            if not isinstance(cc, dict):
                continue
            cc_type = cc.get("type", "round")
            if cc_type not in ("round", "slot", "rectangle", "cable"):
                cc_type = "round"
            validated.append({
                "type": cc_type,
                "wall": cc.get("wall", "front"),
                "x_mm": float(cc.get("x_mm", 0)),
                "y_mm": float(cc.get("y_mm", 0)),
                "width_mm": float(cc.get("width_mm", 5)),
                "height_mm": float(cc.get("height_mm", cc.get("width_mm", 5))),
                "label": str(cc.get("label", "")),
            })
    else:
        validated = []

    screw_size = params.get("screw_size", "M3")
    if screw_size not in LID_SCREW_SIZES:
        screw_size = "M3"

    return EnclosureConfig(
        wall_thickness=_clamp(params.get("wall_thickness", params.get("wall_t", 3.0)), 0.5, 50.0, "wall_thickness"),
        floor_thickness=_clamp(params.get("floor_thickness", params.get("floor_t", 3.0)), 0.5, 25.0, "floor_thickness"),
        lid_thickness=_clamp(params.get("lid_thickness", params.get("lid_t", 3.0)), 0.5, 25.0, "lid_thickness"),
        margin=_clamp(params.get("margin", 6.0), 0.0, 50.0, "margin"),
        screw_size=screw_size,
        pcb_standoff_height=_clamp(params.get("pcb_standoff_height", 5.0), 0.0, 50.0, "pcb_standoff_height"),
        headroom=_clamp(params.get("headroom_mm", params.get("headroom", 10.0)), 0.0, 200.0, "headroom"),
        connector_clearance=_clamp(params.get("clearance", params.get("connector_clearance", 0.3)), 0.0, 10.0, "connector_clearance"),
        connector_z_clearance=_clamp(params.get("connector_z_clearance", 0.3), 0.0, 10.0, "connector_z_clearance"),
        enable_vents=bool(params.get("ventilation", params.get("enable_vents", True))),
        enable_snaps=bool(params.get("enable_snaps", params.get("snap_fit_count", 0) > 1)),
        enable_connectors=True,
        enable_lip=True,
        enable_pcb_ref=bool(params.get("enable_pcb_ref", params.get("show_pcb", True))),
        enable_label_recess=bool(params.get("enable_label_recess", True)),
        vent_slot_width=_clamp(params.get("vent_slot_width", 1.5), 0.5, 25.0, "vent_slot_width"),
        custom_cutouts=validated,
    )


def build_from_parsed(board_dict: dict, params: dict = None):
    """Build enclosure from parsed PCB data dict + optional params.
    
    This is the primary integration point — converts pcb_parser output
    to the dataclass types and runs the full enclosure generator.
    
    Args:
        board_dict: dict from pcb_parser.parse()
        params: optional dict with enclosure parameter overrides
        
    Returns:
        (success: bool, message: str)
    """
    try:
        if params is None:
            params = {}
        board = board_dict_to_boarddata(board_dict)
        cfg = params_to_enclosure_config(params)
        build_enclosure(board, cfg)
        return True, "Enclosure generated successfully."
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"Enclosure build failed: {type(e).__name__}: {e}"

# ──────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

PCB_THICKNESS = 1.6
TOL = 0.02   # anti-coincident-face epsilon


# ──────────────────────────────────────────────────────────────────────────────
#  LOW-LEVEL GEOMETRY HELPERS
# ──────────────────────────────────────────────────────────────────────────────

class Geo:
    """Thin wrappers around Part primitives with error handling."""

    @staticmethod
    def box(sx: float, sy: float, sz: float,
            x: float = 0.0, y: float = 0.0, z: float = 0.0
            ) -> Optional[Part.Shape]:
        if sx <= 0 or sy <= 0 or sz <= 0:
            FreeCAD.Console.PrintWarning(f"  [geo] Skipping degenerate box {sx}×{sy}×{sz}\n")
            return None
        try:
            return Part.makeBox(sx, sy, sz, FreeCAD.Vector(x, y, z))
        except Exception as e:
            FreeCAD.Console.PrintError(f"  [geo] box failed: {e}\n")
            return None

    @staticmethod
    def cyl(r: float, h: float,
            x: float, y: float, z: float) -> Optional[Part.Shape]:
        if r <= 0 or h <= 0:
            FreeCAD.Console.PrintWarning(f"  [geo] Skipping degenerate cylinder r={r} h={h}\n")
            return None
        try:
            return Part.makeCylinder(r, h, FreeCAD.Vector(x, y, z))
        except Exception as e:
            FreeCAD.Console.PrintError(f"  [geo] cylinder failed: {e}\n")
            return None

    @staticmethod
    def fuse(a: Optional[Part.Shape],
             b: Optional[Part.Shape]) -> Optional[Part.Shape]:
        if a is None: return b
        if b is None: return a
        try:
            result = a.fuse(b)
            if result.isNull():
                FreeCAD.Console.PrintWarning("  [geo] fuse returned null, keeping base\n")
                return a
            return result
        except Exception as e:
            FreeCAD.Console.PrintError(f"  [geo] fuse FAILED: {e}\n")
            return a

    @staticmethod
    def cut(base: Optional[Part.Shape],
            tool: Optional[Part.Shape]) -> Optional[Part.Shape]:
        if base is None or tool is None:
            return base
        try:
            result = base.cut(tool)
            if result.isNull():
                FreeCAD.Console.PrintWarning("  [geo] cut returned null, keeping base\n")
                return base
            return result
        except Exception as e:
            FreeCAD.Console.PrintError(f"  [geo] cut FAILED: {e}\n")
            return base

    @staticmethod
    def validate_boolean_result(original: Optional[Part.Shape],
                                result: Optional[Part.Shape],
                                label: str) -> bool:
        """Post-operation check: compare result against original for silent volume loss."""
        if result is None or result.isNull():
            FreeCAD.Console.PrintError(f"  [geo] BOOLEAN FAILURE — {label} produced null shape\n")
            return False
        if original is not None and not original.isNull():
            try:
                eps = 0.001
                if result.Volume + eps < original.Volume:
                    ratio = result.Volume / original.Volume if original.Volume > 0 else 0
                    if ratio < 0.1:
                        FreeCAD.Console.PrintError(
                            f"  [geo] BOOLEAN FAILURE — {label} destroyed shape: "
                            f"volume dropped from {original.Volume:.0f} to {result.Volume:.0f} "
                            f"({ratio*100:.0f}% remaining). Keeping original.\n"
                        )
                        return False
            except Exception:
                pass
        return True

    @staticmethod
    def chamfer_top(shape: Optional[Part.Shape],
                    size: float) -> Optional[Part.Shape]:
        """Chamfer the top-face perimeter edges of a shape."""
        if shape is None or size <= 0:
            return shape
        try:
            bb = shape.BoundBox
            top_z = bb.ZMax
            edges = [
                e for e in shape.Edges
                if (abs(e.Vertexes[0].Point.z - top_z) < 0.1 and
                    abs(e.Vertexes[1].Point.z - top_z) < 0.1 and
                    e.Length > size * 2)
            ]
            if edges:
                return shape.makeChamfer(size, edges)
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"  [geo] chamfer failed: {e}\n")
        return shape

    @staticmethod
    def valid(shape: Optional[Part.Shape], label: str = "") -> bool:
        if shape is None or shape.isNull():
            FreeCAD.Console.PrintWarning(f"  [geo] Invalid shape: {label}\n")
            return False
        return True


# ── Input validation ────────────────────────────────────────────────────────

def _validate_enclosure_inputs(board: BoardData, config: EnclosureConfig) -> List[str]:
    """Validate BoardData and EnclosureConfig before geometry computation.
    Returns a list of warning/error messages. Caller decides whether to proceed.
    """
    errors = []
    if board.width <= 0 or board.height <= 0:
        errors.append(f"Board dimensions invalid: {board.width:.1f} x {board.height:.1f} mm")
    if config.wall_thickness < 1.0:
        errors.append(f"Wall thickness {config.wall_thickness:.1f}mm is very thin (< 1.0mm)")
    if config.floor_thickness < 1.0:
        errors.append(f"Floor thickness {config.floor_thickness:.1f}mm is very thin (< 1.0mm)")
    if config.pcb_standoff_height < 2.0:
        errors.append(f"PCB standoff height {config.pcb_standoff_height:.1f}mm is low — may cause clearance issues")
    if config.margin < 0.5:
        errors.append(f"PCB margin {config.margin:.1f}mm is very tight (< 0.5mm)")
    if config.screw_size not in LID_SCREW_SIZES:
        errors.append(f"Screw size '{config.screw_size}' not in standard sizes {list(LID_SCREW_SIZES)} — will fall back to M3")
    if not board.components and config.enable_connectors:
        errors.append("enable_connectors=True but board has no components — no cutouts will be generated")
    if not board.mounting_holes:
        errors.append("No mounting holes found — enclosure will have no PCB standoffs")
    if config.enable_vents and config.vent_wall.upper() not in ("N", "S", "E", "W"):
        errors.append(f"Invalid vent_wall '{config.vent_wall}' — must be N/S/E/W")
    if config.enable_snaps and not config.enable_lip:
        errors.append("enable_snaps=True without enable_lip — snap arms require the lip groove for clearance")
    for cc in config.custom_cutouts:
        wall = cc.get("wall", "").lower()
        if wall not in ("front", "back", "left", "right", "top"):
            errors.append(f"Custom cutout wall '{wall}' not recognized — use front/back/left/right/top")
    for ci, cc in enumerate(config.custom_cutouts):
        x = cc.get("x_mm", 0)
        y = cc.get("y_mm", 0)
        w = cc.get("width_mm", 0)
        if isinstance(x, str) or isinstance(y, str) or isinstance(w, str):
            errors.append(f"Custom cutout #{ci} has string value (x={x}, y={y}, w={w}) — expected numbers")
    for i, sh in enumerate(board.mounting_holes):
        ox = config.wall_thickness + config.margin
        oy = config.wall_thickness + config.margin
        inner_x = board.width + 2 * config.margin
        inner_y = board.height + 2 * config.margin
        sx, sy = sh.x, sh.y
        if not (0 <= sx <= board.width and 0 <= sy <= board.height):
            errors.append(f"Mounting hole #{i} at ({sx:.1f}, {sy:.1f}) is outside PCB bounds "
                          f"(0, 0) – ({board.width:.1f}, {board.height:.1f})")
    for i, comp in enumerate(board.components):
        if not (0 <= comp.x <= board.width and 0 <= comp.y <= board.height):
            errors.append(f"Component {comp.ref} at ({comp.x:.1f}, {comp.y:.1f}) is outside PCB bounds "
                          f"(0, 0) – ({board.width:.1f}, {board.height:.1f})")
    return errors


# ──────────────────────────────────────────────────────────────────────────────
#  ENCLOSURE GEOMETRY ENGINE
# ──────────────────────────────────────────────────────────────────────────────

class EnclosureGeometry:
    """Computes all derived dimensions and builds Part shapes."""

    def __init__(self, board: BoardData, cfg: EnclosureConfig):
        self.b   = board
        self.cfg = cfg
        # Validate inputs before proceeding
        validation_errors = _validate_enclosure_inputs(board, cfg)
        if validation_errors:
            FreeCAD.Console.PrintWarning(
                "  ── Input Validation ──\n" +
                "\n".join(f"    ⚠ {e}" for e in validation_errors) +
                "\n  ─────────────────────\n"
            )
        self._derive()
        self._overlap_standoffs: Set[int] = set()
        self._slot_adjustments: Dict[str, float] = {}   # comp.ref → mm to reduce slot width per side
        collision_ok = self._validate_collisions()
        self._resolve_collisions()
        self._print_summary()

    # ── Derived dimensions ────────────────────────────────────────────────────

    def _derive(self):
        b   = self.b
        cfg = self.cfg
        wt  = cfg.wall_thickness
        ft  = cfg.floor_thickness
        m   = cfg.margin

        self.inner_x = b.width  + 2 * m
        self.inner_y = b.height + 2 * m
        max_h = max((c.height for c in b.components), default=0.0)
        self.inner_z = cfg.pcb_standoff_height + PCB_THICKNESS + max_h + cfg.headroom

        self.outer_x = self.inner_x + 2 * wt
        self.outer_y = self.inner_y + 2 * wt
        self.base_h  = ft + self.inner_z

        self.pcb_ox = wt + m
        self.pcb_oy = wt + m
        self.pcb_z  = ft + cfg.pcb_standoff_height

        self.boss_r     = cfg.lid_insert_od / 2.0 + cfg.boss_wall
        self.standoff_r = cfg.pcb_pilot_d   / 2.0 + cfg.standoff_wall

        br = self.boss_r
        wt = cfg.wall_thickness
        self.boss_locs = [
            (wt + br,                 wt + br                ),
            (self.outer_x - wt - br,  wt + br                ),
            (wt + br,                 self.outer_y - wt - br ),
            (self.outer_x - wt - br,  self.outer_y - wt - br),
        ]
        self.standoff_locs = [
            (h.x + self.pcb_ox, h.y + self.pcb_oy)
            for h in b.mounting_holes
        ]

        # Safe-zone x/y between bosses (for vent/connector placement)
        xs = sorted(bx for bx, _ in self.boss_locs)
        ys = sorted(by for _, by in self.boss_locs)
        self.safe_x = (xs[1] + self.boss_r + 1.0, xs[2] - self.boss_r - 1.0)
        self.safe_y = (ys[1] + self.boss_r + 1.0, ys[2] - self.boss_r - 1.0)

    # ── Collision checks ─────────────────────────────────────────────────────

    def _validate_collisions(self):
        wt = self.cfg.wall_thickness
        ok = True
        all_cols = (
            [(bx, by, self.boss_r,     "Boss",     idx) for idx, (bx, by) in enumerate(self.boss_locs)] +
            [(sx, sy, self.standoff_r, "Standoff", idx) for idx, (sx, sy) in enumerate(self.standoff_locs)]
        )
        n = len(all_cols)
        for i in range(n):
            xi, yi, ri, li, idi = all_cols[i]
            if not (wt < xi < self.outer_x - wt and wt < yi < self.outer_y - wt):
                FreeCAD.Console.PrintWarning(f"  ⚠ {li} {idi} ({xi:.2f},{yi:.2f}) outside cavity!\n")
                ok = False
            for j in range(i + 1, n):
                xj, yj, rj, lj, idj = all_cols[j]
                dist = math.hypot(xi - xj, yi - yj)
                min_d = ri + rj + 0.5
                if dist < min_d:
                    FreeCAD.Console.PrintWarning(
                        f"  ⚠ {li} {idi} and {lj} {idj} overlap by {min_d - dist:.2f} mm!\n"
                    )
                    ok = False
                    if li == "Standoff" and lj == "Boss":
                        self._overlap_standoffs.add(idi)
                    elif li == "Boss" and lj == "Standoff":
                        self._overlap_standoffs.add(idj)

        # connector ↔ boss/standoff collisions
        ft = self.cfg.floor_thickness
        sh = self.cfg.pcb_standoff_height
        for comp in self.b.components:
            if not comp.connector:
                continue
            cx = comp.x + self.pcb_ox
            cy = comp.y + self.pcb_oy
            cr = max(comp.width, comp.depth) / 2 + 1.0
            for idx, (bx, by) in enumerate(self.boss_locs):
                cd = math.hypot(cx - bx, cy - by)
                if cd < cr + self.boss_r:
                    FreeCAD.Console.PrintWarning(
                        f"  ⚠ Connector {comp.ref} overlaps Boss {idx} "
                        f"by {cr + self.boss_r - cd:.2f} mm\n"
                    )
                    ok = False
            for idx, (sx, sy) in enumerate(self.standoff_locs):
                cd = math.hypot(cx - sx, cy - sy)
                if cd < cr + self.standoff_r:
                    FreeCAD.Console.PrintWarning(
                        f"  ⚠ Connector {comp.ref} overlaps Standoff {idx} "
                        f"by {cr + self.standoff_r - cd:.2f} mm\n"
                    )
                    ok = False

        # vent slot ↔ connector collision (vent wall must not cross a connector)
        if self.cfg.enable_vents:
            vw = self.cfg.vent_wall.upper()
            for comp in self.b.components:
                if not comp.connector:
                    continue
                wall = comp.wall or "?"
                if wall == vw or wall == {"N": "S", "S": "N", "E": "W", "W": "E"}.get(vw):
                    FreeCAD.Console.PrintWarning(
                        f"  ⚠ Vent wall {vw} may conflict with connector {comp.ref} (on {wall}) — "
                        f"vent slot may be partially occluded\n"
                    )

        # custom cutout ↔ boss collisions
        for ci, cc in enumerate(self.cfg.custom_cutouts):
            wall = cc.get("wall", "").lower()
            if wall == "top":
                continue
            cc_x = float(cc.get("x_mm", 0))
            cc_y = float(cc.get("y_mm", 0))
            cc_w = float(cc.get("width_mm", 5))
            cc_h = float(cc.get("height_mm", cc_w))
            # Approximate centre of cutout in enclosure coordinates
            if wall in ("front", "back"):
                cut_cx = cc_x
                cut_cy = self.outer_y / 2.0
            else:
                cut_cx = self.outer_x / 2.0
                cut_cy = cc_x
            cr = max(cc_w, cc_h) / 2 + 1.0
            for idx, (bx, by) in enumerate(self.boss_locs):
                cd = math.hypot(cut_cx - bx, cut_cy - by)
                if cd < cr + self.boss_r:
                    FreeCAD.Console.PrintWarning(
                        f"  ⚠ Custom cutout #{ci} (wall={wall}) overlaps Boss {idx} "
                        f"by {cr + self.boss_r - cd:.2f} mm\n"
                    )
                    ok = False

        if ok:
            FreeCAD.Console.PrintMessage("  ✓ Collision check passed — all features clear.\n")
        if self._overlap_standoffs:
            FreeCAD.Console.PrintWarning(
                f"  → {len(self._overlap_standoffs)} standoff(s) overlap a lid boss — "
                f"will be absorbed into the boss column.\n"
            )

    # ── Collision resolution (automatic fixes) ─────────────────────────────

    def _resolve_collisions(self):
        """Try to automatically fix detected collisions.
        
        Populates:
          self._overlap_standoffs  — standoff indices to skip
          self._slot_adjustments   — comp.ref → mm to reduce slot width (per side)
        Prints resolution actions to console.
        """
        resolutions = []
        ft = self.cfg.floor_thickness
        sh = self.cfg.pcb_standoff_height

        # 1. Connector ↔ boss: reduce slot width proportionally
        for comp in self.b.components:
            if not comp.connector:
                continue
            cx = comp.x + self.pcb_ox
            cy = comp.y + self.pcb_oy
            cr = max(comp.width, comp.depth) / 2.0 + 1.0
            # Compute nominal slot width for this connector (before any clearance)
            if comp.connector_type in CONNECTOR_TYPES and comp.connector_type != "CUSTOM":
                nominal_w = CONNECTOR_TYPES[comp.connector_type][0]
            else:
                nominal_w = comp.width
            min_acceptable = nominal_w + self.cfg.connector_clearance  # never below connector + minimum slack
            overlap_max = 0.0
            for idx, (bx, by) in enumerate(self.boss_locs):
                cd = math.hypot(cx - bx, cy - by)
                overlap = cr + self.boss_r - cd
                if overlap > 0:
                    overlap_max = max(overlap_max, overlap)
                    reduction = min(overlap + 0.2, 2.0)  # cap at 2mm per side
                    # Guard: never shrink slot below minimum acceptable width
                    current_pw = comp.width + 2 * self.cfg.connector_clearance
                    new_pw = max(current_pw - 2 * reduction, min_acceptable)
                    actual_reduction = (current_pw - new_pw) / 2.0
                    if actual_reduction > 0:
                        self._slot_adjustments[comp.ref] = max(
                            self._slot_adjustments.get(comp.ref, 0), actual_reduction
                        )
                        resolutions.append(
                            f"    Connector {comp.ref} overlaps Boss {idx} by "
                            f"{overlap:.1f}mm — reduced slot width by {actual_reduction:.1f}mm per side "
                            f"(min {min_acceptable:.1f}mm)\n"
                        )
                    else:
                        resolutions.append(
                            f"    Connector {comp.ref} overlaps Boss {idx} by "
                            f"{overlap:.1f}mm — cannot reduce further (slot at minimum {min_acceptable:.1f}mm)\n"
                        )

        # 2. Connector ↔ standoff: absorb the standoff
        for comp in self.b.components:
            if not comp.connector:
                continue
            cx = comp.x + self.pcb_ox
            cy = comp.y + self.pcb_oy
            cr = max(comp.width, comp.depth) / 2.0 + 1.0
            for idx, (sx, sy) in enumerate(self.standoff_locs):
                cd = math.hypot(cx - sx, cy - sy)
                overlap = cr + self.standoff_r - cd
                if overlap > 0 and idx not in self._overlap_standoffs:
                    self._overlap_standoffs.add(idx)
                    resolutions.append(
                        f"    Connector {comp.ref} overlaps Standoff {idx} "
                        f"by {overlap:.1f}mm — standoff absorbed\n"
                    )

        if resolutions:
            FreeCAD.Console.PrintMessage(
                "  ── Collision Resolutions ──\n" + "".join(resolutions) +
                "  ───────────────────────────\n"
            )
        else:
            FreeCAD.Console.PrintMessage("  ✓ No collisions to resolve.\n")

    def _print_summary(self):
        cfg = self.cfg
        FreeCAD.Console.PrintMessage(
            "\n" + "═"*60 + "\n"
            f"  Outer envelope : {self.outer_x:.2f} × {self.outer_y:.2f} × {self.base_h:.2f} mm\n"
            f"  Inner cavity   : {self.inner_x:.2f} × {self.inner_y:.2f} × {self.inner_z:.2f} mm\n"
            f"  PCB origin     : ({self.pcb_ox:.2f}, {self.pcb_oy:.2f}, {self.pcb_z:.2f})\n"
            f"  Boss radius    : {self.boss_r:.2f} mm   Standoff radius: {self.standoff_r:.2f} mm\n"
            f"  Vents          : {'ON' if cfg.enable_vents else 'OFF'}   "
            f"Label recess: {'ON' if cfg.enable_label_recess else 'OFF'}   "
            f"Snaps: {'ON' if cfg.enable_snaps else 'OFF'}\n"
            + "═"*60 + "\n"
        )

    # ── Shell ────────────────────────────────────────────────────────────────

    def shell(self) -> Optional[Part.Shape]:
        cfg = self.cfg
        wt  = cfg.wall_thickness
        ft  = cfg.floor_thickness
        outer = Geo.box(self.outer_x, self.outer_y, self.base_h)
        if cfg.enable_chamfer:
            outer = Geo.chamfer_top(outer, cfg.corner_chamfer)
        cavity = Geo.box(
            self.inner_x + TOL, self.inner_y + TOL, self.inner_z + TOL,
            wt - TOL/2, wt - TOL/2, ft - TOL/2
        )
        result = Geo.cut(outer, cavity)
        if not Geo.valid(result, "shell"):
            FreeCAD.Console.PrintError("  [enclosure] SHELL FAILED — enclosure will be empty\n")
        return result

    # ── Columns ──────────────────────────────────────────────────────────────

    def add_columns(self, base: Optional[Part.Shape]) -> Optional[Part.Shape]:
        cfg = self.cfg
        ft  = cfg.floor_thickness
        col_h = self.inner_z - cfg.lip_depth - 0.3

        for bx, by in self.boss_locs:
            base = Geo.fuse(base, Geo.cyl(self.boss_r, col_h, bx, by, ft))
            try:
                import FreeCADGui
                FreeCADGui.updateGui()
            except Exception:
                pass

        sh = cfg.pcb_standoff_height
        for idx, (sx, sy) in enumerate(self.standoff_locs):
            if idx in self._overlap_standoffs:
                continue
            base = Geo.fuse(base, Geo.cyl(self.standoff_r, sh, sx, sy, ft))
            try:
                import FreeCADGui
                FreeCADGui.updateGui()
            except Exception:
                pass

        return base

    def mounting_standoffs(self) -> Optional[Part.Shape]:
        cfg = self.cfg
        ft  = cfg.floor_thickness
        sh  = cfg.pcb_standoff_height
        result = None
        for sx, sy in self.standoff_locs:
            result = Geo.fuse(result, Geo.cyl(self.standoff_r, sh, sx, sy, ft))
        return result

    def mounting_bosses(self) -> Optional[Part.Shape]:
        cfg = self.cfg
        ft  = cfg.floor_thickness
        col_h = self.inner_z - cfg.lip_depth - 0.3
        result = None
        for bx, by in self.boss_locs:
            result = Geo.fuse(result, Geo.cyl(self.boss_r, col_h, bx, by, ft))
        return result

    # ── Lip groove ───────────────────────────────────────────────────────────

    def cut_lip_groove(self, base: Optional[Part.Shape]) -> Optional[Part.Shape]:
        if not self.cfg.enable_lip:
            return base
        cfg = self.cfg
        wt  = cfg.wall_thickness
        lw  = min(cfg.lip_width, (wt - 0.4) / 2.0)
        ld  = cfg.lip_depth
        gz  = self.base_h - ld + TOL

        go = Geo.box(
            self.outer_x - 2*lw + TOL, self.outer_y - 2*lw + TOL, ld + TOL*2,
            lw - TOL/2, lw - TOL/2, gz - TOL
        )
        gi = Geo.box(
            self.inner_x + 2*lw - TOL, self.inner_y + 2*lw - TOL, ld + TOL*2,
            wt - lw - TOL/2, wt - lw - TOL/2, gz - TOL
        )
        base = Geo.cut(base, go)
        base = Geo.cut(base, gi)
        return base

    # ── Drill columns ────────────────────────────────────────────────────────

    def drill_columns(self, base: Optional[Part.Shape]) -> Optional[Part.Shape]:
        cfg = self.cfg
        ft  = cfg.floor_thickness

        insert_r  = cfg.lid_insert_od / 2.0
        insert_d  = cfg.lid_insert_depth
        clr_r     = cfg.lid_screw_clearance_d / 2.0
        col_h     = self.inner_z - cfg.lip_depth - 0.3
        top       = self.base_h

        for bx, by in self.boss_locs:
            base = Geo.cut(base, Geo.cyl(insert_r, insert_d + TOL, bx, by, top - insert_d))
            base = Geo.cut(base, Geo.cyl(clr_r, col_h + TOL, bx, by, ft - TOL))
            try:
                import FreeCADGui
                FreeCADGui.updateGui()
            except Exception:
                pass

        pilot_r = cfg.pcb_pilot_d / 2.0
        pilot_d = min(cfg.pcb_pilot_depth, cfg.pcb_standoff_height - 0.8)
        top_so  = ft + cfg.pcb_standoff_height

        for idx, (sx, sy) in enumerate(self.standoff_locs):
            if idx in self._overlap_standoffs:
                continue
            base = Geo.cut(base, Geo.cyl(pilot_r, pilot_d + TOL, sx, sy, top_so - pilot_d))
            try:
                import FreeCADGui
                FreeCADGui.updateGui()
            except Exception:
                pass

        return base

    # ── Connector slots ──────────────────────────────────────────────────────

    def cut_connectors(self, base: Optional[Part.Shape]) -> Optional[Part.Shape]:
        if not self.cfg.enable_connectors:
            return base
        cfg = self.cfg
        wt  = cfg.wall_thickness
        ft  = cfg.floor_thickness
        sh  = cfg.pcb_standoff_height
        cc  = cfg.connector_clearance
        zcc = cfg.connector_z_clearance

        failures = []
        for comp in self.b.components:
            if not comp.connector:
                continue

            # Resolve hole dimensions from type registry
            if comp.connector_type in CONNECTOR_TYPES and comp.connector_type != "CUSTOM":
                pw, ph = CONNECTOR_TYPES[comp.connector_type]
                pw += 2 * cc
                ph += 2 * zcc
            else:
                pw = comp.width  + 2 * cc
                ph = comp.height + 2 * zcc

            cx = comp.x + self.pcb_ox
            cy = comp.y + self.pcb_oy
            z_bot = max(ft + sh + PCB_THICKNESS - ph / 2 - zcc, ft + 0.5)

            # Determine wall
            if comp.wall:
                wall = comp.wall.upper()
            else:
                dist = {"E": self.outer_x - cx, "W": cx,
                        "N": self.outer_y - cy, "S": cy}
                wall = min(dist, key=dist.get)

            sxl, sxh = self.safe_x
            syl, syh = self.safe_y
            slot = None

            if wall in ("E", "W"):
                y1 = max(cy - pw/2, syl)
                y2 = min(cy + pw/2, syh)
                x0 = self.outer_x - wt - TOL/2 if wall == "E" else -TOL/2
                if y2 > y1:
                    slot = Geo.box(wt + TOL, y2 - y1, ph, x0, y1, z_bot)
            else:  # N / S
                x1 = max(cx - pw/2, sxl)
                x2 = min(cx + pw/2, sxh)
                y0 = self.outer_y - wt - TOL/2 if wall == "N" else -TOL/2
                if x2 > x1:
                    slot = Geo.box(x2 - x1, wt + TOL, ph, x1, y0, z_bot)

            if slot:
                old_base = base
                base = Geo.cut(base, slot)
                if not Geo.validate_boolean_result(old_base, base, f"connector {comp.ref}"):
                    failures.append(comp.ref)
                else:
                    FreeCAD.Console.PrintMessage(f"    Slot cut for {comp.ref} ({comp.connector_type}) on wall {wall}\n")
                try:
                    import FreeCADGui
                    FreeCADGui.updateGui()
                except Exception:
                    pass
            else:
                FreeCAD.Console.PrintWarning(f"    Slot SKIPPED for {comp.ref} — clipped to zero by safe zone\n")

        if failures:
            FreeCAD.Console.PrintWarning(
                f"    {len(failures)} connector cutout(s) failed: {', '.join(failures)}\n"
            )

        return base

    # ── Ventilation slots ────────────────────────────────────────────────────

    def cut_vents(self, base: Optional[Part.Shape]) -> Optional[Part.Shape]:
        """Cut a row of vent slots on one wall, clipped to safe zone."""
        if not self.cfg.enable_vents:
            return base
        cfg  = self.cfg
        wt   = cfg.wall_thickness
        ft   = cfg.floor_thickness
        wall = cfg.vent_wall.upper()
        sw   = cfg.vent_slot_width
        sg   = cfg.vent_slot_gap
        sl   = cfg.vent_slot_length
        step = sw + sg

        # Clamp slot length so it doesn't punch through the lip groove or top face
        max_sl = self.base_h - ft - cfg.vent_z_offset - cfg.lip_depth - 1.0
        sl = min(sl, max_sl)

        if wall in ("N", "S"):
            lo, hi = self.safe_x
            slot_count = max(1, int((hi - lo + sg) / step))
            total_w = slot_count * step - sg
            start = lo + (hi - lo - total_w) / 2

            for i in range(slot_count):
                x0 = start + i * step
                y0 = self.outer_y - wt - TOL/2 if wall == "N" else -TOL/2
                z0 = ft + cfg.vent_z_offset
                slot = Geo.box(sw, wt + TOL, sl, x0, y0, z0)
                base = Geo.cut(base, slot)
                try:
                    import FreeCADGui
                    FreeCADGui.updateGui()
                except Exception:
                    pass
        else:  # E / W
            lo, hi = self.safe_y
            slot_count = max(1, int((hi - lo + sg) / step))
            total_w = slot_count * step - sg
            start = lo + (hi - lo - total_w) / 2

            for i in range(slot_count):
                y0 = start + i * step
                x0 = self.outer_x - wt - TOL/2 if wall == "E" else -TOL/2
                z0 = ft + cfg.vent_z_offset
                slot = Geo.box(wt + TOL, sw, sl, x0, y0, z0)
                base = Geo.cut(base, slot)
                try:
                    import FreeCADGui
                    FreeCADGui.updateGui()
                except Exception:
                    pass

        FreeCAD.Console.PrintMessage(f"    {slot_count} vent slots cut on wall {wall}\n")
        return base

    # ── Cable-tie anchor posts ───────────────────────────────────────────────

    def add_cable_anchors(self, base: Optional[Part.Shape]) -> Optional[Part.Shape]:
        if not self.cfg.enable_cable_anchors:
            return base
        cfg  = self.cfg
        ft   = cfg.floor_thickness
        ar   = cfg.cable_anchor_r
        ah   = cfg.cable_anchor_h
        sw   = cfg.cable_slot_w / 2.0

        for ax, ay in cfg.cable_anchor_locs:
            post = Geo.cyl(ar, ah, ax, ay, ft)
            base = Geo.fuse(base, post)
            # Cut horizontal slot through post for cable routing
            slot = Geo.box(ar * 2 + TOL, sw, ah * 0.5, ax - ar - TOL/2, ay - sw/2, ft + ah * 0.5)
            base = Geo.cut(base, slot)

        return base

    # ── Lid ──────────────────────────────────────────────────────────────────

    def lid(self) -> Optional[Part.Shape]:
        cfg    = self.cfg
        wt     = cfg.wall_thickness
        lt     = cfg.lid_thickness
        lw     = min(cfg.lip_width, (wt - 0.4) / 2.0)
        ld     = cfg.lip_depth
        tol    = cfg.lip_clearance
        lid_z  = self.base_h - TOL

        # Main plate
        shape = Geo.box(self.outer_x, self.outer_y, lt, 0, 0, lid_z)
        if cfg.enable_chamfer:
            shape = Geo.chamfer_top(shape, cfg.corner_chamfer)

        # Screw counterbores + clearance
        screw_r = cfg.lid_screw_clearance_d / 2.0
        cb_r    = cfg.lid_cbore_d / 2.0
        cb_h    = cfg.lid_cbore_depth
        for bx, by in self.boss_locs:
            shape = Geo.cut(shape, Geo.cyl(screw_r, lt + TOL, bx, by, lid_z - TOL))
            shape = Geo.cut(shape, Geo.cyl(cb_r, cb_h, bx, by, lid_z + lt - cb_h))

        # Interlocking tongue
        if cfg.enable_lip:
            to_in = tol
            t_outer = Geo.box(
                self.outer_x - 2*to_in, self.outer_y - 2*to_in, ld,
                to_in, to_in, lid_z - ld
            )
            ti_in = wt - lw + tol
            t_inner = Geo.box(
                self.outer_x - 2*ti_in, self.outer_y - 2*ti_in, ld + 2,
                ti_in, ti_in, lid_z - ld - 1
            )
            tongue = Geo.cut(t_outer, t_inner)
            for bx, by in self.boss_locs:
                tongue = Geo.cut(tongue, Geo.cyl(self.boss_r + tol + 0.4, ld + 3, bx, by, lid_z - ld - 1.5))
            shape = Geo.fuse(shape, tongue)

        # Label recess on top face
        if cfg.enable_label_recess:
            lm  = cfg.label_margin
            rd  = cfg.label_recess_depth
            top = lid_z + lt - rd
            recess = Geo.box(
                self.outer_x - 2*lm, self.outer_y - 2*lm, rd + TOL,
                lm, lm, top
            )
            shape = Geo.cut(shape, recess)
            FreeCAD.Console.PrintMessage("    Label recess added to lid\n")

        return shape

    # ── Snap-fit arms (optional) ─────────────────────────────────────────────

    def snap_arms(self) -> Optional[Part.Shape]:
        """
        Cantilever snap arms for lid retention.
        Placed on the inside face of the N/S walls, midspan.
        """
        if not self.cfg.enable_snaps:
            return None
        cfg = self.cfg
        wt  = cfg.wall_thickness
        ft  = cfg.floor_thickness
        aw  = cfg.snap_arm_width
        al  = cfg.snap_arm_length
        at  = cfg.snap_arm_thickness
        hk  = cfg.snap_hook_height
        z0  = ft + self.inner_z / 2

        arms = None
        mid_x = self.outer_x / 2

        for y_pos, dir_y in [
            (wt,               1),   # South wall, pointing inward (+Y)
            (self.outer_y - wt, -1), # North wall, pointing inward (-Y)
        ]:
            arm = Geo.box(aw, al, at, mid_x - aw/2, y_pos, z0)
            # Hook at free end
            hook_y = y_pos + dir_y * al
            hook = Geo.box(aw, at, hk, mid_x - aw/2, hook_y, z0)
            arm = Geo.fuse(arm, hook)
            arms = Geo.fuse(arms, arm)

        return arms

    # ── PCB reference ────────────────────────────────────────────────────────

    def pcb_board(self) -> Optional[Part.Shape]:
        if not self.cfg.enable_pcb_ref:
            return None
        return Geo.box(self.b.width, self.b.height, PCB_THICKNESS,
                       self.pcb_ox, self.pcb_oy, self.pcb_z)

    def pcb_mounting_holes(self) -> Optional[Part.Shape]:
        if not self.cfg.enable_pcb_ref:
            return None
        z = self.pcb_z
        h = PCB_THICKNESS
        result = None
        for mh in self.b.mounting_holes:
            cx = mh.x + self.pcb_ox
            cy = mh.y + self.pcb_oy
            ring_outer = Geo.cyl(mh.diameter / 2 + 0.3, h, cx, cy, z)
            ring_inner = Geo.cyl(mh.diameter / 2, h + 0.1, cx, cy, z)
            ring = Geo.cut(ring_outer, ring_inner)
            result = Geo.fuse(result, ring)
        return result

    # ── Individual shape factories (for the named-object build pipeline) ──

    def make_outer_box(self) -> Optional[Part.Shape]:
        cfg = self.cfg
        outer = Geo.box(self.outer_x, self.outer_y, self.base_h)
        if outer and cfg.enable_chamfer:
            outer = Geo.chamfer_top(outer, cfg.corner_chamfer)
        return outer

    def make_cavity(self) -> Optional[Part.Shape]:
        cfg = self.cfg
        return Geo.box(
            self.inner_x + TOL, self.inner_y + TOL, self.inner_z + TOL,
            cfg.wall_thickness - TOL/2, cfg.wall_thickness - TOL/2,
            cfg.floor_thickness - TOL/2
        )

    def make_boss(self, bx: float, by: float) -> Optional[Part.Shape]:
        cfg = self.cfg
        col_h = self.inner_z - cfg.lip_depth - 0.3
        OV = 0.05
        return Geo.cyl(self.boss_r, col_h + OV, bx, by, cfg.floor_thickness - OV)

    def make_standoff(self, sx: float, sy: float) -> Optional[Part.Shape]:
        cfg = self.cfg
        OV = 0.05
        return Geo.cyl(self.standoff_r, cfg.pcb_standoff_height + OV, sx, sy, cfg.floor_thickness - OV)

    def make_insert_hole(self, bx: float, by: float) -> Optional[Part.Shape]:
        cfg = self.cfg
        return Geo.cyl(cfg.lid_insert_od / 2.0, cfg.lid_insert_depth + TOL, bx, by, self.base_h - cfg.lid_insert_depth)

    def make_screw_hole(self, bx: float, by: float) -> Optional[Part.Shape]:
        cfg = self.cfg
        col_h = self.inner_z - cfg.lip_depth - 0.3
        return Geo.cyl(cfg.lid_screw_clearance_d / 2.0, col_h + TOL, bx, by, cfg.floor_thickness - TOL)

    def make_pilot_hole(self, sx: float, sy: float) -> Optional[Part.Shape]:
        cfg = self.cfg
        pilot_r = cfg.pcb_pilot_d / 2.0
        pilot_d = min(cfg.pcb_pilot_depth, cfg.pcb_standoff_height - 0.8)
        top_so = cfg.floor_thickness + cfg.pcb_standoff_height
        OV = 0.05
        return Geo.cyl(pilot_r, pilot_d + OV, sx, sy, top_so - pilot_d)

    def make_lip_groove_outer(self) -> Optional[Part.Shape]:
        if not self.cfg.enable_lip:
            return None
        cfg = self.cfg
        lw = min(cfg.lip_width, (cfg.wall_thickness - 0.4) / 2.0)
        ld = cfg.lip_depth
        gz = self.base_h - ld + TOL
        return Geo.box(
            self.outer_x - 2*lw + TOL, self.outer_y - 2*lw + TOL, ld + TOL*2,
            lw - TOL/2, lw - TOL/2, gz - TOL
        )

    def make_lip_groove_inner(self) -> Optional[Part.Shape]:
        if not self.cfg.enable_lip:
            return None
        cfg = self.cfg
        lw = min(cfg.lip_width, (cfg.wall_thickness - 0.4) / 2.0)
        ld = cfg.lip_depth
        gz = self.base_h - ld + TOL
        return Geo.box(
            self.inner_x + 2*lw - TOL, self.inner_y + 2*lw - TOL, ld + TOL*2,
            cfg.wall_thickness - lw - TOL/2, cfg.wall_thickness - lw - TOL/2, gz - TOL
        )

    def make_connector_slot(self, comp) -> Optional[Part.Shape]:
        if not self.cfg.enable_connectors:
            return None
        cfg = self.cfg
        cc = cfg.connector_clearance
        zcc = cfg.connector_z_clearance
        if comp.connector_type in CONNECTOR_TYPES and comp.connector_type != "CUSTOM":
            pw, ph = CONNECTOR_TYPES[comp.connector_type]
            pw += 2 * cc
            ph += 2 * zcc
        else:
            pw = comp.width + 2 * cc
            ph = comp.height + 2 * zcc
        # Apply auto-collision-reduction (both sides)
        reduction = self._slot_adjustments.get(comp.ref, 0)
        pw = max(pw - 2 * reduction, comp.width)  # never less than connector itself
        cx = comp.x + self.pcb_ox
        cy = comp.y + self.pcb_oy
        z_bot = max(cfg.floor_thickness + cfg.pcb_standoff_height + PCB_THICKNESS - ph / 2 - zcc, cfg.floor_thickness + 0.5)
        if comp.wall:
            wall = comp.wall.upper()
        else:
            dist = {"E": self.outer_x - cx, "W": cx, "N": self.outer_y - cy, "S": cy}
            wall = min(dist, key=dist.get)
        sxl, sxh = self.safe_x
        syl, syh = self.safe_y
        wt = cfg.wall_thickness
        if wall in ("E", "W"):
            y1 = max(cy - pw/2, syl)
            y2 = min(cy + pw/2, syh)
            x0 = self.outer_x - wt - TOL/2 if wall == "E" else -TOL/2
            if y2 > y1:
                return Geo.box(wt + TOL, y2 - y1, ph, x0, y1, z_bot)
        else:
            x1 = max(cx - pw/2, sxl)
            x2 = min(cx + pw/2, sxh)
            y0 = self.outer_y - wt - TOL/2 if wall == "N" else -TOL/2
            if x2 > x1:
                return Geo.box(x2 - x1, wt + TOL, ph, x1, y0, z_bot)
        return None

    def make_custom_cutout(self, cc: dict) -> Optional[Part.Shape]:
        """Generate a custom cutout shape on a specific wall.
        
        cc keys: type (round/slot/rectangle/cable), wall (front/back/left/right/top),
                 x_mm, y_mm, width_mm, height_mm, label
        Clamps cutout to wall bounds and logs when values are corrected.
        """
        cfg = self.cfg
        cc_type = cc.get("type", "round")
        wall = cc.get("wall", "front").lower()
        cx = float(cc.get("x_mm", 0))
        cy = float(cc.get("y_mm", 0))
        w = float(cc.get("width_mm", 5))
        h = float(cc.get("height_mm", w))
        wt = cfg.wall_thickness
        ox, oy = self.outer_x, self.outer_y
        ez = cfg.floor_thickness + cfg.pcb_standoff_height + PCB_THICKNESS  # PCB top z
        z_max = self.base_h - cfg.lip_depth - 1.0  # max z to avoid lip groove
        label = cc.get("label", f"cutout_{wall}")

        def _log_clamp(name, orig, clamped, bound_name, lo, hi):
            if abs(orig - clamped) > 0.01:
                FreeCAD.Console.PrintWarning(
                    f"  ⚠ Cutout '{label}' {name} clamped from {orig:.1f} to {clamped:.1f} "
                    f"({bound_name} bounds [{lo:.1f}, {hi:.1f}])\n"
                )

        # Wall mapping: front/back = Y walls, left/right = X walls, top = lid
        if wall == "front":
            x0 = max(cx - w/2, 0.5); _log_clamp("x_start", cx - w/2, x0, "wall X", 0.5, ox - 0.5)
            x1 = min(cx + w/2, ox - 0.5); _log_clamp("x_end", cx + w/2, x1, "wall X", 0.5, ox - 0.5)
            y0 = -TOL
            z0 = max(cy - h/2, cfg.floor_thickness + 0.5); _log_clamp("z_bot", cy - h/2, z0, "floor Z", cfg.floor_thickness + 0.5, z_max)
            z1 = min(cy + h/2, z_max); _log_clamp("z_top", cy + h/2, z1, "ceil Z", cfg.floor_thickness + 0.5, z_max)
            if x1 <= x0 or z1 <= z0:
                FreeCAD.Console.PrintWarning(f"  ⚠ Cutout '{label}' rejected — zero area on front wall\n")
                return None
            return Geo.box(x1 - x0, wt + TOL, z1 - z0, x0, y0, z0)

        elif wall == "back":
            x0 = max(cx - w/2, 0.5); _log_clamp("x_start", cx - w/2, x0, "wall X", 0.5, ox - 0.5)
            x1 = min(cx + w/2, ox - 0.5); _log_clamp("x_end", cx + w/2, x1, "wall X", 0.5, ox - 0.5)
            y0 = oy - wt - TOL
            z0 = max(cy - h/2, cfg.floor_thickness + 0.5); _log_clamp("z_bot", cy - h/2, z0, "floor Z", cfg.floor_thickness + 0.5, z_max)
            z1 = min(cy + h/2, z_max); _log_clamp("z_top", cy + h/2, z1, "ceil Z", cfg.floor_thickness + 0.5, z_max)
            if x1 <= x0 or z1 <= z0:
                FreeCAD.Console.PrintWarning(f"  ⚠ Cutout '{label}' rejected — zero area on back wall\n")
                return None
            return Geo.box(x1 - x0, wt + TOL, z1 - z0, x0, y0, z0)

        elif wall == "left":
            x0 = -TOL
            y0 = max(cx - w/2, 0.5); _log_clamp("y_start", cx - w/2, y0, "wall Y", 0.5, oy - 0.5)
            y1 = min(cx + w/2, oy - 0.5); _log_clamp("y_end", cx + w/2, y1, "wall Y", 0.5, oy - 0.5)
            z0 = max(cy - h/2, cfg.floor_thickness + 0.5); _log_clamp("z_bot", cy - h/2, z0, "floor Z", cfg.floor_thickness + 0.5, z_max)
            z1 = min(cy + h/2, z_max); _log_clamp("z_top", cy + h/2, z1, "ceil Z", cfg.floor_thickness + 0.5, z_max)
            if y1 <= y0 or z1 <= z0:
                FreeCAD.Console.PrintWarning(f"  ⚠ Cutout '{label}' rejected — zero area on left wall\n")
                return None
            return Geo.box(wt + TOL, y1 - y0, z1 - z0, x0, y0, z0)

        elif wall == "right":
            x0 = ox - wt - TOL
            y0 = max(cx - w/2, 0.5); _log_clamp("y_start", cx - w/2, y0, "wall Y", 0.5, oy - 0.5)
            y1 = min(cx + w/2, oy - 0.5); _log_clamp("y_end", cx + w/2, y1, "wall Y", 0.5, oy - 0.5)
            z0 = max(cy - h/2, cfg.floor_thickness + 0.5); _log_clamp("z_bot", cy - h/2, z0, "floor Z", cfg.floor_thickness + 0.5, z_max)
            z1 = min(cy + h/2, z_max); _log_clamp("z_top", cy + h/2, z1, "ceil Z", cfg.floor_thickness + 0.5, z_max)
            if y1 <= y0 or z1 <= z0:
                FreeCAD.Console.PrintWarning(f"  ⚠ Cutout '{label}' rejected — zero area on right wall\n")
                return None
            return Geo.box(wt + TOL, y1 - y0, z1 - z0, x0, y0, z0)

        elif wall == "top":
            lz = self.base_h - TOL
            x0 = max(cx - w/2, 0.5); _log_clamp("x_start", cx - w/2, x0, "lid X", 0.5, ox - 0.5)
            x1 = min(cx + w/2, ox - 0.5); _log_clamp("x_end", cx + w/2, x1, "lid X", 0.5, ox - 0.5)
            y0 = max(cy - h/2, 0.5); _log_clamp("y_start", cy - h/2, y0, "lid Y", 0.5, oy - 0.5)
            y1 = min(cy + h/2, oy - 0.5); _log_clamp("y_end", cy + h/2, y1, "lid Y", 0.5, oy - 0.5)
            if x1 <= x0 or y1 <= y0:
                FreeCAD.Console.PrintWarning(f"  ⚠ Cutout '{label}' rejected — zero area on top wall\n")
                return None
            return Geo.box(x1 - x0, y1 - y0, cfg.lid_thickness + TOL, x0, y0, lz - TOL)

        FreeCAD.Console.PrintWarning(f"  ⚠ Cutout '{label}' has unknown wall '{wall}' — skipped\n")
        return None

    def make_lid_plate(self) -> Optional[Part.Shape]:
        cfg = self.cfg
        lid_z = self.base_h - TOL
        shape = Geo.box(self.outer_x, self.outer_y, cfg.lid_thickness, 0, 0, lid_z)
        if shape and cfg.enable_chamfer:
            shape = Geo.chamfer_top(shape, cfg.corner_chamfer)
        return shape

    def make_lid_tongue(self) -> Optional[Part.Shape]:
        if not self.cfg.enable_lip:
            return None
        cfg = self.cfg
        lw = min(cfg.lip_width, (cfg.wall_thickness - 0.4) / 2.0)
        ld = cfg.lip_depth
        tol = cfg.lip_clearance
        lid_z = self.base_h - TOL
        t_outer = Geo.box(self.outer_x - 2*tol, self.outer_y - 2*tol, ld, tol, tol, lid_z - ld)
        ti_in = cfg.wall_thickness - lw + tol
        t_inner = Geo.box(self.outer_x - 2*ti_in, self.outer_y - 2*ti_in, ld + 2, ti_in, ti_in, lid_z - ld - 1)
        tongue = Geo.cut(t_outer, t_inner)
        for bx, by in self.boss_locs:
            tongue = Geo.cut(tongue, Geo.cyl(self.boss_r + tol + 0.4, ld + 3, bx, by, lid_z - ld - 1.5))
        return tongue

    def make_counterbore(self, bx: float, by: float) -> Optional[Part.Shape]:
        cfg = self.cfg
        lid_z = self.base_h - TOL
        lt = cfg.lid_thickness
        screw_r = cfg.lid_screw_clearance_d / 2.0
        cb_r = cfg.lid_cbore_d / 2.0
        cb_h = cfg.lid_cbore_depth
        screw = Geo.cyl(screw_r, lt + TOL, bx, by, lid_z - TOL)
        cb = Geo.cyl(cb_r, cb_h, bx, by, lid_z + lt - cb_h)
        return Geo.fuse(screw, cb)

    def make_label_recess(self) -> Optional[Part.Shape]:
        if not self.cfg.enable_label_recess:
            return None
        cfg = self.cfg
        lid_z = self.base_h - TOL
        lt = cfg.lid_thickness
        top = lid_z + lt - cfg.label_recess_depth
        return Geo.box(self.outer_x - 2*cfg.label_margin, self.outer_y - 2*cfg.label_margin, cfg.label_recess_depth + TOL, cfg.label_margin, cfg.label_margin, top)

    def make_pcb_reference(self) -> Optional[Part.Shape]:
        if not self.cfg.enable_pcb_ref:
            return None
        return Geo.box(self.b.width, self.b.height, PCB_THICKNESS, self.pcb_ox, self.pcb_oy, self.pcb_z)

    def make_component_block(self, comp) -> Optional[Part.Shape]:
        cz = self.pcb_z + PCB_THICKNESS
        cw = comp.width if comp.width else 3.0
        cd = comp.depth if comp.depth else 3.0
        return Geo.box(cw, cd, comp.height, comp.x + self.pcb_ox - cw/2, comp.y + self.pcb_oy - cd/2, cz)


# ──────────────────────────────────────────────────────────────────────────────
#  DOCUMENT BUILDER
# ──────────────────────────────────────────────────────────────────────────────

class DocumentBuilder:
    """Adds Part shapes to the FreeCAD document with colours and placement."""

    def __init__(self, doc):
        self.doc = doc

    @staticmethod
    def _set_color(obj, color_tuple, transparency=0):
        """Safely set color — no-op if running headless (no GUI)."""
        try:
            if hasattr(obj, 'ViewObject') and obj.ViewObject is not None:
                obj.ViewObject.ShapeColor = color_tuple
                obj.ViewObject.DisplayMode = "Flat Lines"
                if transparency:
                    obj.ViewObject.Transparency = transparency
        except Exception:
            pass  # headless FreeCAD — skip silently

    def add(self, shape: Optional[Part.Shape], name: str,
            color: Tuple[float, float, float],
            transparency: int = 0,
            z_offset: float = 0.0) -> bool:
        if shape is None or not Geo.valid(shape, name):
            FreeCAD.Console.PrintWarning(f"  Skipped adding {name} (null shape)\n")
            return False
        obj = self.doc.addObject("Part::Feature", name)
        obj.Shape = shape
        self._set_color(obj, color, transparency)
        if z_offset:
            obj.Placement.Base = FreeCAD.Vector(0, 0, z_offset)
        FreeCAD.Console.PrintMessage(f"  + {name} added\n")
        return True

    # ── App::Part container helpers ─────────────────────────────────────────

    @staticmethod
    def _make_part_container(doc, name: str, label: str = ""):
        """Create an App::Part container with a human-readable label."""
        part = doc.addObject("App::Part", name)
        part.Label = label or name
        return part

    @staticmethod
    def _add_to_container(container, obj):
        """Add a FreeCAD object to an App::Part container."""
        if hasattr(container, 'addObject'):
            container.addObject(obj)

    # ── High-level enclosure builder ───────────────────────────────────────

    @staticmethod
    def _build_single_solid(positives: List[Optional[Part.Shape]],
                            negatives: List[Optional[Part.Shape]]) -> Optional[Part.Shape]:
        """Fuse all positive shapes, then cut all negatives in Python.
        Returns a single clean Part.Shape (no document objects created).
        Logs each boolean op with index so failed cuts can be traced."""
        current = None
        for idx, p in enumerate(positives):
            if p is None:
                continue
            old = current
            current = Geo.fuse(current, p)
            if not Geo.validate_boolean_result(old, current, f"fuse positive #{idx}"):
                FreeCAD.Console.PrintWarning(f"  [build] Fuse #{idx} failed — positive skipped\n")
                current = old
            try:
                import FreeCADGui
                FreeCADGui.updateGui()
            except Exception:
                pass
        for idx, n in enumerate(negatives):
            if n is None:
                continue
            old = current
            current = Geo.cut(current, n)
            if not Geo.validate_boolean_result(old, current, f"cut negative #{idx}"):
                FreeCAD.Console.PrintWarning(f"  [build] Cut #{idx} failed — negative skipped\n")
                current = old
            try:
                import FreeCADGui
                FreeCADGui.updateGui()
            except Exception:
                pass
        return current

    def build_enclosure(self, doc, board: BoardData, config: EnclosureConfig) -> dict:
        """Build enclosure with clean single-solid base and lid.
        Returns dict of {shell, lid, compound, root} with Part::Feature objects."""
        FreeCAD.Console.PrintMessage("  [dbg] build_enclosure ENTERED\n")
        geo = EnclosureGeometry(board, config)
        db = self

        FreeCAD.Console.PrintMessage("\n" + "═"*60 + "\n")
        FreeCAD.Console.PrintMessage("  Enclosure Generator\n")
        FreeCAD.Console.PrintMessage("═"*60 + "\n")
        connector_count = len([c for c in board.components if c.connector])
        FreeCAD.Console.PrintMessage(
            f"  Board: {board.width:.1f} x {board.height:.1f} mm  "
            f"Mounting holes: {len(board.mounting_holes)}  "
            f"Components: {len(board.components)}  "
            f"Connectors: {connector_count}\n"
        )
        FreeCAD.Console.PrintMessage(
            f"  Features: vents={'ON' if config.enable_vents else 'OFF'}  "
            f"snaps={'ON' if config.enable_snaps else 'OFF'}  "
            f"lip={'ON' if config.enable_lip else 'OFF'}  "
            f"cable anchors={'ON' if config.enable_cable_anchors else 'OFF'}\n"
        )

        # ── Organisers ──────────────────────────────────────────────────────
        root     = db._make_part_container(doc, "PCB_Enclosure", "PCB Enclosure")
        shell_ct = db._make_part_container(doc, "Shell", "Shell")
        lid_ct   = db._make_part_container(doc, "Lid", "Lid")
        ref_ct   = db._make_part_container(doc, "Reference", "Reference (hidden)")
        db._add_to_container(root, shell_ct)
        db._add_to_container(root, lid_ct)
        db._add_to_container(root, ref_ct)

        # ── Shell — build solid in Python, add final result only ────────────
        FreeCAD.Console.PrintMessage("  Building shell...\n")
        shell_positives: List[Optional[Part.Shape]] = [
            geo.make_outer_box(),
        ]
        for bx, by in geo.boss_locs:
            shell_positives.append(geo.make_boss(bx, by))
        for i, (sx, sy) in enumerate(geo.standoff_locs):
            if i not in geo._overlap_standoffs:
                shell_positives.append(geo.make_standoff(sx, sy))
        n_absorbed = len(geo._overlap_standoffs)
        if n_absorbed:
            FreeCAD.Console.PrintMessage(f"    {n_absorbed} standoff(s) absorbed into bosses (collision resolution)\n")
        if config.enable_snaps:
            snap = geo.snap_arms()
            if snap:
                shell_positives.append(snap)
                FreeCAD.Console.PrintMessage("  + Snap-fit arms added to shell\n")

        shell_negatives: List[Optional[Part.Shape]] = [
            geo.make_cavity(),
        ]
        if config.enable_lip:
            shell_negatives.append(geo.make_lip_groove_outer())
            shell_negatives.append(geo.make_lip_groove_inner())
        for bx, by in geo.boss_locs:
            shell_negatives.append(geo.make_insert_hole(bx, by))
            shell_negatives.append(geo.make_screw_hole(bx, by))
        for i, (sx, sy) in enumerate(geo.standoff_locs):
            if i not in geo._overlap_standoffs:
                shell_negatives.append(geo.make_pilot_hole(sx, sy))
        if config.enable_connectors:
            for comp in board.components:
                if comp.connector:
                    shell_negatives.append(geo.make_connector_slot(comp))
        for cc in config.custom_cutouts:
            if cc.get("wall", "").lower() != "top":
                shell_negatives.append(geo.make_custom_cutout(cc))

        n_pos = sum(1 for p in shell_positives if p is not None)
        n_neg = sum(1 for n in shell_negatives if n is not None)
        FreeCAD.Console.PrintMessage(f"    Positives: {n_pos}, Negatives: {n_neg}\n")

        shell_shape = db._build_single_solid(shell_positives, shell_negatives)

        # Vents and cable anchors — use legacy base-modification helpers
        if shell_shape:
            shell_shape = geo.cut_vents(shell_shape)
            shell_shape = geo.add_cable_anchors(shell_shape)

        shell_obj = None
        if shell_shape and Geo.valid(shell_shape, "Shell_Final"):
            shell_obj = doc.addObject("Part::Feature", "Shell_Final")
            shell_obj.Label = "Shell_Final"
            shell_obj.Shape = shell_shape
            db._add_to_container(shell_ct, shell_obj)
            db._set_color(shell_obj, COLOR_SHELL, transparency=80)
            FreeCAD.Console.PrintMessage("  + Shell_Final added (single solid)\n")

        # ── Lid — build solid in Python, add final result only ──────────────
        FreeCAD.Console.PrintMessage("  Building lid...\n")
        lid_positives: List[Optional[Part.Shape]] = [
            geo.make_lid_plate(),
        ]
        tongue = geo.make_lid_tongue()
        if tongue:
            lid_positives.append(tongue)

        lid_negatives: List[Optional[Part.Shape]] = []
        for bx, by in geo.boss_locs:
            lid_negatives.append(geo.make_counterbore(bx, by))
        label_recess = geo.make_label_recess()
        if label_recess:
            lid_negatives.append(label_recess)
        for cc in config.custom_cutouts:
            if cc.get("wall", "").lower() == "top":
                lid_negatives.append(geo.make_custom_cutout(cc))

        ln_pos = sum(1 for p in lid_positives if p is not None)
        ln_neg = sum(1 for n in lid_negatives if n is not None)
        FreeCAD.Console.PrintMessage(f"    Positives: {ln_pos}, Negatives: {ln_neg}\n")

        lid_shape = db._build_single_solid(lid_positives, lid_negatives)
        lid_obj = None
        if lid_shape and Geo.valid(lid_shape, "Lid_Final"):
            lid_obj = doc.addObject("Part::Feature", "Lid_Final")
            lid_obj.Label = "Lid_Final"
            lid_obj.Shape = lid_shape
            db._add_to_container(lid_ct, lid_obj)
            db._set_color(lid_obj, COLOR_LID)
            lid_obj.Placement.Base = FreeCAD.Vector(0, 0, geo.base_h + 25.0)
            FreeCAD.Console.PrintMessage("  + Lid_Final added (single solid, offset above base)\n")

        # ── PCB reference shapes ───────────────────────────────────────────
        if config.enable_pcb_ref:
            pcb_shape = geo.make_pcb_reference()
            if pcb_shape:
                pcb_obj = doc.addObject("Part::Feature", "PCB_Board")
                pcb_obj.Label = "PCB_Board"
                pcb_obj.Shape = pcb_shape
                db._add_to_container(ref_ct, pcb_obj)
                db._set_color(pcb_obj, COLOR_PCB, transparency=30)
            for comp in board.components:
                label = f"Connector_{comp.ref}" if comp.connector else f"Component_{comp.ref}"
                cb = geo.make_component_block(comp)
                if cb:
                    obj = doc.addObject("Part::Feature", label)
                    obj.Label = label
                    obj.Shape = cb
                    db._add_to_container(ref_ct, obj)
                    db._set_color(obj, COLOR_CONNECTOR if comp.connector else COLOR_COMPONENT)
            for i, mh in enumerate(board.mounting_holes):
                cx = mh.x + geo.pcb_ox
                cy = mh.y + geo.pcb_oy
                ring_outer = Geo.cyl(mh.diameter / 2 + 0.3, PCB_THICKNESS, cx, cy, geo.pcb_z)
                ring_inner = Geo.cyl(mh.diameter / 2, PCB_THICKNESS + 0.1, cx, cy, geo.pcb_z)
                ring = Geo.cut(ring_outer, ring_inner)
                if ring:
                    obj = doc.addObject("Part::Feature", f"MountingHole_{i+1}")
                    obj.Label = f"MountingHole_{i+1}"
                    obj.Shape = ring
                    db._add_to_container(ref_ct, obj)
                    db._set_color(obj, COLOR_HOLE_RING)
            ref_ct.Visibility = True

        # ── Export compound ────────────────────────────────────────────────
        compound = doc.addObject("Part::Compound", "Export_Compound")
        compound.Label = "Export (Shell + Lid)"
        compound.Links = [shell_obj, lid_obj]
        db._add_to_container(root, compound)

        doc.recompute()
        try:
            FreeCAD.Gui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

        # ── BOM summary ────────────────────────────────────────────────────
        connectors = [c for c in board.components if c.connector]
        FreeCAD.Console.PrintMessage(
            "\n" + "═"*60 + "\n"
            "  BILL OF MATERIALS SUMMARY\n"
            f"  Enclosure outer: {geo.outer_x:.2f} × {geo.outer_y:.2f} × {geo.base_h:.2f} mm\n"
            f"  {config.screw_size} heat-set inserts × {len(geo.boss_locs)}\n"
            f"  PCB standoff screws × {len(geo.standoff_locs)}\n"
            f"  Connector cutouts   × {len(connectors)} "
            f"({', '.join(c.connector_type for c in connectors)})\n"
            f"  Vent slots          : {'Yes (generated)' if config.enable_vents else 'No'}\n"
            f"  Lid label recess    : {'Yes' if config.enable_label_recess else 'No'}\n"
            f"  Snap-fit lid arms   : {'Yes (generated)' if config.enable_snaps else 'No'}\n"
            f"  Cable anchor posts  : {'Yes (generated)' if config.enable_cable_anchors else 'No'}\n"
            + "═"*60 + "\n"
        )
        FreeCAD.Console.PrintMessage("  ✓ Build complete.\n\n")

        return {
            "shell": shell_obj,
            "lid": lid_obj,
            "compound": compound,
            "root": root,
        }


# ──────────────────────────────────────────────────────────────────────────────
#  LEGACY MAIN ASSEMBLY FUNCTION
#  Kept for backward compatibility; delegates to DocumentBuilder.build_enclosure
# ──────────────────────────────────────────────────────────────────────────────

def build_enclosure(board: BoardData, cfg: EnclosureConfig):
    doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument("Enclosure_v2")
    # Clean up previous enclosure objects so they don't accumulate
    enclosure_labels = [
        obj.Label for obj in doc.Objects
        if any(kw in obj.Label for kw in
               ("Enclosure", "Shell", "Lid", "PCB", "Snap", "Export"))
    ]
    for label in enclosure_labels:
        try:
            objs = doc.getObjectsByLabel(label)
            if objs:
                doc.removeObject(objs[0].Name)
        except Exception:
            pass
    db = DocumentBuilder(doc)
    return db.build_enclosure(doc, board, cfg)


# ──────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Self-test with sample data
    sample_dict = {
        "dimensions": {"x_min": 10.0, "x_max": 90.0, "y_min": 5.0, "y_max": 65.0, "width": 80.0, "height": 60.0},
        "mounting_holes": [
            {"x": 13.0, "y": 8.0, "diameter": 3.2},
            {"x": 87.0, "y": 8.0, "diameter": 3.2},
            {"x": 13.0, "y": 62.0, "diameter": 3.2},
            {"x": 87.0, "y": 62.0, "diameter": 3.2},
        ],
        "components": [
            {"ref": "U1", "name": "QFP-44", "x": 50.0, "y": 35.0, "height": 12.0, "width": 12.0, "length": 12.0, "near_edge": False},
            {"ref": "J1", "name": "USB_C_Receptacle", "x": 87.5, "y": 35.0, "height": 3.5, "width": 9.0, "length": 5.0, "near_edge": True, "connector_width": 9.0},
        ],
        "edge_connectors": [
            {"ref": "J1", "name": "USB_C_Receptacle", "x": 87.5, "y": 35.0, "height": 3.5},
        ],
    }
    success, msg = build_from_parsed(sample_dict, {"wall_thickness": 3.0, "margin": 6.0})
    print(f"Result: {success} — {msg}")