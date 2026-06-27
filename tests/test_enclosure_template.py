import os
import sys
import inspect
import re
from pathlib import Path
from unittest.mock import MagicMock

MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import pytest
from enclosure_template import (
    EnclosureGeometry, EnclosureConfig, BoardData, MountingHole, DocumentBuilder,
    board_dict_to_boarddata, params_to_enclosure_config, LID_SCREW_SIZES,
)


def make_board(width=80, height=60):
    return BoardData(
        width=width,
        height=height,
        mounting_holes=[
            MountingHole(x=5,  y=5,  diameter=3.2),
            MountingHole(x=75, y=5,  diameter=3.2),
            MountingHole(x=5,  y=55, diameter=3.2),
            MountingHole(x=75, y=55, diameter=3.2),
        ],
        components=[],
    )


PARAMS = EnclosureConfig(
    wall_thickness=2.0,
    floor_thickness=2.0,
    margin=1.0,
    enable_vents=False,
    enable_connectors=False,
    enable_pcb_ref=False,
    enable_label_recess=False,
)


class TestEnclosureGeometry:

    def test_instantiates_with_valid_board(self):
        geo = EnclosureGeometry(make_board(), PARAMS)
        assert geo is not None

    def test_shell_dimensions_include_margin(self):
        board = make_board(width=80, height=60)
        geo = EnclosureGeometry(board, PARAMS)
        margin = PARAMS.margin
        wall = PARAMS.wall_thickness
        expected_outer_x = 80 + 2 * margin + 2 * wall
        assert abs(geo.outer_x - expected_outer_x) < 0.1, \
            f"Outer X wrong: {geo.outer_x} vs {expected_outer_x}"

    def test_boss_count_matches_corners(self):
        geo = EnclosureGeometry(make_board(), PARAMS)
        assert len(geo.boss_locs) == 4

    def test_standoff_count_matches_mounting_holes(self):
        geo = EnclosureGeometry(make_board(), PARAMS)
        assert len(geo.standoff_locs) == 4

    def test_inner_z_accounts_for_standoff_pcb_headroom(self):
        geo = EnclosureGeometry(make_board(), PARAMS)
        expected = PARAMS.pcb_standoff_height + 1.6 + 0.0 + PARAMS.headroom
        assert abs(geo.inner_z - expected) < 0.1

    def test_shapecolor_values_are_float_tuples(self):
        """No hex strings or integer RGB in EnclosureGeometry source."""
        src = inspect.getsource(EnclosureGeometry)
        hex_colors = re.findall(r"ShapeColor\s*=\s*['\"]#[0-9a-fA-F]+['\"]", src)
        assert not hex_colors, f"Hex color strings found: {hex_colors}"
        int_colors = re.findall(r"ShapeColor\s*=\s*\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)", src)
        assert not int_colors, f"Integer RGB tuples found (use floats): {int_colors}"

    def test_board_dict_to_boarddata_converts_dimensions(self):
        board_dict = {
            "dimensions": {"width": 100.0, "height": 50.0, "x_min": 0, "y_min": 0, "x_max": 100, "y_max": 50},
            "mounting_holes": [],
            "components": [],
            "edge_connectors": [],
        }
        bd = board_dict_to_boarddata(board_dict)
        assert abs(bd.width - 100.0) < 0.1
        assert abs(bd.height - 50.0) < 0.1

    def test_no_standoffs_outside_cavity(self):
        board = make_board(width=80, height=60)
        geo = EnclosureGeometry(board, PARAMS)
        wt = PARAMS.wall_thickness
        for sx, sy in geo.standoff_locs:
            assert wt < sx < geo.outer_x - wt, f"Standoff x={sx} outside cavity"
            assert wt < sy < geo.outer_y - wt, f"Standoff y={sy} outside cavity"


from contextlib import contextmanager

@contextmanager
def _patch_geo_methods(geo_cls, dummy):
    """Temporarily replace Geo static methods with stubs returning dummy."""
    import unittest.mock as um
    originals = {}
    for name in ("box", "cyl", "fuse", "cut", "chamfer_top", "valid"):
        originals[name] = getattr(geo_cls, name)
        setattr(geo_cls, name, um.MagicMock(return_value=dummy))
    geo_cls.validate_boolean_result = um.MagicMock(return_value=True)
    yield
    for name, orig in originals.items():
        setattr(geo_cls, name, orig)


class TestScrewSizeMapping:
    """LID_SCREW_SIZES dict must cover all standard sizes and EnclosureConfig must derive correct lid holes."""

    def test_screw_sizes_contain_all_standards(self):
        for size in ("M2", "M2.5", "M3", "M3.5", "M4", "M5", "M6"):
            assert size in LID_SCREW_SIZES, f"Missing screw size {size}"

    def test_m3_defaults_unchanged(self):
        cfg = EnclosureConfig()
        assert cfg.lid_insert_od == 4.2
        assert cfg.lid_screw_clearance_d == 3.2
        assert cfg.lid_cbore_d == 6.0

    def test_m2_mapping(self):
        cfg = EnclosureConfig(screw_size="M2")
        assert cfg.lid_screw_clearance_d == 2.2, "M2 clearance should be 2.2mm"
        assert cfg.lid_cbore_d == 4.5, "M2 cbore should be 4.5mm"

    def test_m4_mapping(self):
        cfg = EnclosureConfig(screw_size="M4")
        assert cfg.lid_screw_clearance_d == 4.3, "M4 clearance should be 4.3mm"
        assert cfg.lid_cbore_d == 8.0, "M4 cbore should be 8.0mm"

    def test_params_to_enclosure_config_passes_screw_size(self):
        cfg = params_to_enclosure_config({"screw_size": "M2"})
        assert cfg.lid_screw_clearance_d == 2.2
        assert cfg.lid_cbore_d == 4.5
        assert cfg.screw_size == "M2"

    def test_invalid_screw_size_falls_back_to_m3(self):
        cfg = params_to_enclosure_config({"screw_size": "M99"})
        assert cfg.lid_screw_clearance_d == 3.2, "Invalid size should fall back to M3"
        assert cfg.screw_size == "M3"

    def test_all_screw_sizes_have_unique_values(self):
        seen = {}
        for size, vals in LID_SCREW_SIZES.items():
            clr = vals[2]
            assert clr not in seen, f"{size} and {seen[clr]} share clearance {clr}"
            seen[clr] = size


class TestDocumentBuilder:

    def _dummy_shape(self):
        s = MagicMock()
        s.isNull.return_value = False
        s.Volume = 100.0
        return s

    def test_build_returns_shell_and_lid_separately(self):
        from enclosure_template import Geo as _Geo
        doc = MagicMock()
        doc.addObject.side_effect = lambda t, n: MagicMock()
        with _patch_geo_methods(_Geo, self._dummy_shape()):
            builder = DocumentBuilder(doc)
            result = builder.build_enclosure(doc, make_board(), PARAMS)
        assert "shell" in result
        assert "lid" in result

    def test_build_returns_export_compound(self):
        from enclosure_template import Geo as _Geo
        doc = MagicMock()
        doc.addObject.side_effect = lambda t, n: MagicMock()
        with _patch_geo_methods(_Geo, self._dummy_shape()):
            builder = DocumentBuilder(doc)
            result = builder.build_enclosure(doc, make_board(), PARAMS)
        assert "compound" in result

    def test_model_tree_has_named_objects(self):
        from enclosure_template import Geo as _Geo
        doc = MagicMock()
        added_names = []

        def track_add(type_str, name):
            added_names.append(name)
            return MagicMock()

        doc.addObject.side_effect = track_add
        with _patch_geo_methods(_Geo, self._dummy_shape()):
            builder = DocumentBuilder(doc)
            builder.build_enclosure(doc, make_board(), PARAMS)
        assert "Shell_Final" in added_names, "Shell_Final not added to document"
        assert "Lid_Final" in added_names, "Lid_Final not added to document"
        assert "Shell" in added_names, "Shell container missing"
        assert "Lid" in added_names, "Lid container missing"


def test_no_part_show_correction_present():
    """API correction for Part.show() must exist."""
    from orchestrator.core import AIOrchestrator
    ids = [c.get("id") for c in AIOrchestrator.API_CORRECTIONS if isinstance(c, dict)]
    assert "no_part_show" in ids


# ── Collision resolution tests ──────────────────────────────────────────────

def _board_with_connectors():
    """Board with two edge connectors that may overlap corner bosses."""
    from enclosure_template import Component
    return BoardData(
        width=80, height=60,
        mounting_holes=[
            MountingHole(x=5, y=5, diameter=3.2),
            MountingHole(x=75, y=5, diameter=3.2),
            MountingHole(x=5, y=55, diameter=3.2),
            MountingHole(x=75, y=55, diameter=3.2),
        ],
        components=[
            Component(ref="J1", x=78, y=10, height=5, width=9, depth=5,
                      connector=True, connector_type="USB_C", wall="E"),
            Component(ref="J2", x=40, y=58, height=6, width=14, depth=6,
                      connector=True, connector_type="HDMI", wall="N"),
            Component(ref="R1", x=30, y=30, height=2, width=3, depth=3,
                      connector=False),
        ],
    )


class TestCollisionResolution:

    def test_connector_boss_overlap_creates_slot_adjustment(self):
        """Connector near corner boss should produce a non-zero slot reduction."""
        board = _board_with_connectors()
        cfg = EnclosureConfig(wall_thickness=2, floor_thickness=2, margin=1,
                              enable_vents=False, enable_connectors=True,
                              enable_pcb_ref=False, enable_label_recess=False)
        geo = EnclosureGeometry(board, cfg)
        # J1 at (78, 10) is near the East-wall boss at the SE corner —
        # should trigger an adjustment
        assert "J1" in geo._slot_adjustments, \
            f"Expected J1 adjustment, got {geo._slot_adjustments}"
        assert geo._slot_adjustments["J1"] > 0

    def test_connector_boss_overlap_at_minimum_distance(self):
        """A connector placed far from bosses should produce no adjustment."""
        from enclosure_template import Component
        board = BoardData(
            width=80, height=60,
            mounting_holes=[
                MountingHole(x=5, y=5, diameter=3.2),
                MountingHole(x=75, y=5, diameter=3.2),
            ],
            components=[
                Component(ref="J1", x=40, y=30, height=5, width=9, depth=5,
                          connector=True, connector_type="USB_C", wall="E"),
            ],
        )
        cfg = EnclosureConfig(wall_thickness=2, floor_thickness=2, margin=1,
                              enable_vents=False, enable_connectors=True,
                              enable_pcb_ref=False, enable_label_recess=False)
        geo = EnclosureGeometry(board, cfg)
        # Centered connector should not overlap any corner boss
        assert geo._slot_adjustments == {}, \
            f"Expected no adjustments, got {geo._slot_adjustments}"

    def test_slot_adjustment_guardrail_never_below_connector_width(self):
        """Even extreme overlap should not shrink slot below the connector itself."""
        from enclosure_template import Component
        # Place connector extremely close to a boss
        board = BoardData(
            width=30, height=30,
            mounting_holes=[MountingHole(x=5, y=5, diameter=3.2)],
            components=[
                Component(ref="J1", x=22, y=5, height=5, width=16, depth=6,
                          connector=True, connector_type="RJ45", wall="E"),
            ],
        )
        cfg = EnclosureConfig(wall_thickness=2, floor_thickness=2, margin=1,
                              enable_vents=False, enable_connectors=True,
                              enable_pcb_ref=False, enable_label_recess=False)
        geo = EnclosureGeometry(board, cfg)
        if "J1" in geo._slot_adjustments:
            # The slot after reduction must still be >= nominal connector width
            # RJ45 CONNECTOR_TYPES entry = 16.0 wide
            nominal = 16.0
            min_acceptable = nominal + cfg.connector_clearance
            pw = 16.0 + 2 * cfg.connector_clearance
            reduced = pw - 2 * geo._slot_adjustments["J1"]
            assert reduced >= min_acceptable, \
                f"Slot width {reduced:.1f} below minimum {min_acceptable:.1f}"

    def test_connector_standoff_overlap_absorbs_standoff(self):
        """Connector overlapping a standoff should add it to _overlap_standoffs."""
        from enclosure_template import Component
        board = BoardData(
            width=30, height=30,
            mounting_holes=[MountingHole(x=22, y=5, diameter=3.2)],  # near East edge, SE corner
            components=[
                Component(ref="J1", x=24, y=6, height=5, width=10, depth=5,
                          connector=True, connector_type="USB_C", wall="E"),
            ],
        )
        cfg = EnclosureConfig(wall_thickness=2, floor_thickness=2, margin=1,
                              enable_vents=False, enable_connectors=True,
                              enable_pcb_ref=False, enable_label_recess=False)
        geo = EnclosureGeometry(board, cfg)
        standoff_at_conflict = any(
            i in geo._overlap_standoffs
            for i, (sx, sy) in enumerate(geo.standoff_locs)
            if abs(sx - 24) < 3 and abs(sy - 6) < 3
        )
        assert geo._overlap_standoffs, \
            f"Expected at least one standoff absorbed, got {geo._overlap_standoffs}"

    def test_no_connectors_no_resolution_needed(self):
        """Board with no connectors should produce no slot_adjustments or overlap_standoffs from connectors."""
        # Place mounting hole at center to avoid boss↔standoff collision (separate concern)
        board = BoardData(
            width=80, height=60,
            mounting_holes=[MountingHole(x=40, y=30, diameter=3.2)],
            components=[],
        )
        cfg = EnclosureConfig(wall_thickness=2, floor_thickness=2, margin=1,
                              enable_vents=False, enable_connectors=False,
                              enable_pcb_ref=False, enable_label_recess=False)
        geo = EnclosureGeometry(board, cfg)
        assert geo._slot_adjustments == {}


# ── Face detection and wall fallback tests ─────────────────────────────────

class TestFaceDetection:

    def test_parser_sets_face_for_edge_connectors(self):
        """The PCB parser should set 'face' for components detected as near_edge."""
        import pcb_parser
        import tempfile
        # Minimal KiCad PCB with one USB-C near the East edge
        kicad_content = """
(kicad_pcb (version 20231024)
  (gr_line (start 0 0) (end 100 0) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 100 0) (end 100 60) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 100 60) (end 0 60) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 0 60) (end 0 0) (layer "Edge.Cuts") (width 0.1))
  (footprint "USB_C_Receptacle" (layer "F.Cu")
    (at 95 30 0)
    (fp_text reference "J1" (at 0 0) (layer "F.SilkS"))
    (pad "1" smd rect (at 90 28) (size 2 3))
    (pad "2" smd rect (at 90 32) (size 2 3))
  )
)
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".kicad_pcb",
                                          delete=False, encoding="utf-8") as f:
            f.write(kicad_content)
            path = f.name
        try:
            data = pcb_parser.parse(path)
            for c in data["components"]:
                if c.get("near_edge") and c.get("connector"):
                    assert "face" in c, \
                        f"Edge connector {c['ref']} missing 'face': {c}"
                    assert c["face"] in ("N", "S", "E", "W"), \
                        f"Invalid face '{c['face']}' for {c['ref']}"
                    # USB-C at x=95 on board 0..100 → nearest edge is East (E)
                    assert c["face"] == "E", \
                        f"Expected face=E for East-edge connector, got {c['face']}"
        finally:
            os.unlink(path)

    def test_boarddata_wall_uses_face_before_rotation(self):
        """board_dict_to_boarddata should prefer 'face' over rotation inference."""
        board_dict = {
            "dimensions": {"width": 100, "height": 60, "x_min": 0, "y_min": 0, "x_max": 100, "y_max": 60},
            "mounting_holes": [],
            "edge_connectors": [
                {"ref": "J1", "name": "USB_C_Receptacle", "x": 95, "y": 30, "height": 3.5},
            ],
            "components": [
                {"ref": "J1", "name": "USB_C_Receptacle", "x": 95, "y": 30,
                 "height": 3.5, "width": 9, "length": 5,
                 "near_edge": True, "rotation": 90, "face": "W"},
            ],
        }
        bd = board_dict_to_boarddata(board_dict)
        assert len(bd.components) == 1
        # face=W should take priority over rotation=90 → "N"
        assert bd.components[0].wall == "W", \
            f"Expected wall=W from face, got wall={bd.components[0].wall}"

    def test_boarddata_rotation_fallback_when_no_face(self):
        """Without 'face', rotation should be used for wall inference."""
        board_dict = {
            "dimensions": {"width": 100, "height": 60, "x_min": 0, "y_min": 0, "x_max": 100, "y_max": 60},
            "mounting_holes": [],
            "edge_connectors": [
                {"ref": "J1", "name": "USB_C_Receptacle", "x": 95, "y": 30, "height": 3.5},
            ],
            "components": [
                {"ref": "J1", "name": "USB_C_Receptacle", "x": 95, "y": 30,
                 "height": 3.5, "width": 9, "length": 5,
                 "near_edge": True, "rotation": 90},
                # no "face" key — should fall back to rotation
            ],
        }
        bd = board_dict_to_boarddata(board_dict)
        assert bd.components[0].wall == "N", \
            f"Expected wall=N from rotation=90, got wall={bd.components[0].wall}"

    def test_nearest_wall_fallback_when_no_face_or_rotation(self):
        """Without 'face' or rotation, nearest-wall heuristic should apply."""
        board_dict = {
            "dimensions": {"width": 100, "height": 60, "x_min": 0, "y_min": 0, "x_max": 100, "y_max": 60},
            "mounting_holes": [],
            "edge_connectors": [],
            "components": [
                {"ref": "J1", "name": "USB_C_Receptacle", "x": 95, "y": 30,
                 "height": 3.5, "width": 9, "length": 5,
                 "near_edge": True, "rotation": 0},
            ],
        }
        bd = board_dict_to_boarddata(board_dict)
        # rotation=0 normally maps to E, but we need to test that face and rotation both missing
        # still works — so let's also test what happens without the rotation key
        board_dict["components"][0].pop("rotation", None)
        bd = board_dict_to_boarddata(board_dict)
        assert bd.components[0].wall is None, \
            f"Expected wall=None (deferred to make_connector_slot), got {bd.components[0].wall}"


# ── Input validation tests ─────────────────────────────────────────────────

class TestInputValidation:

    def test_validate_bad_dimensions(self):
        """Negative or zero dimensions should not crash geometry, but produce logged warning."""
        from enclosure_template import _validate_enclosure_inputs
        board = BoardData(width=-1, height=0, mounting_holes=[], components=[])
        cfg = EnclosureConfig()
        errors = _validate_enclosure_inputs(board, cfg)
        assert any("dimensions invalid" in e for e in errors), f"Missing dimensions error: {errors}"

    def test_validate_standoff_height_too_low(self):
        """Standoff height < 2mm should warn about potential clearance issues."""
        from enclosure_template import _validate_enclosure_inputs
        board = BoardData(width=80, height=60, mounting_holes=[], components=[])
        cfg = EnclosureConfig(pcb_standoff_height=1.0)
        errors = _validate_enclosure_inputs(board, cfg)
        assert any("standoff" in e.lower() for e in errors)

    def test_validate_screw_size(self):
        """Unknown screw size should produce a warning but not crash."""
        from enclosure_template import _validate_enclosure_inputs
        board = BoardData(width=80, height=60, mounting_holes=[], components=[])
        cfg = EnclosureConfig(screw_size="M99")
        errors = _validate_enclosure_inputs(board, cfg)
        assert any("M99" in e for e in errors), f"Expected M99 warning, got {errors}"


# ── Build pipeline integration tests ───────────────────────────────────────

class TestBuildPipeline:

    def _dummy_shape(self):
        s = MagicMock()
        s.isNull.return_value = False
        s.Volume = 100.0
        return s

    def test_build_with_connectors_and_vents(self):
        """Full build with connectors, vents, and snaps should not crash."""
        from enclosure_template import Geo as _Geo, Component
        board = BoardData(
            width=60, height=40,
            mounting_holes=[
                MountingHole(x=5, y=5, diameter=3.2),
                MountingHole(x=55, y=5, diameter=3.2),
                MountingHole(x=5, y=35, diameter=3.2),
                MountingHole(x=55, y=35, diameter=3.2),
            ],
            components=[
                Component(ref="J1", x=58, y=20, height=5, width=9, depth=5,
                          connector=True, connector_type="USB_C", wall="E"),
            ],
        )
        cfg = EnclosureConfig(
            wall_thickness=2, floor_thickness=2, margin=1,
            enable_vents=True, enable_snaps=True,
            enable_connectors=True, enable_lip=True,
            enable_label_recess=True, enable_pcb_ref=False,
        )
        doc = MagicMock()
        doc.addObject.side_effect = lambda t, n: MagicMock()
        with _patch_geo_methods(_Geo, self._dummy_shape()):
            builder = DocumentBuilder(doc)
            result = builder.build_enclosure(doc, board, cfg)
        assert "shell" in result
        assert "lid" in result

    def test_build_with_no_mounting_holes(self):
        """Board with no mounting holes should still produce valid enclosure."""
        from enclosure_template import Geo as _Geo
        board = BoardData(width=40, height=30, mounting_holes=[], components=[])
        cfg = EnclosureConfig(
            wall_thickness=2, floor_thickness=2, margin=1,
            enable_vents=False, enable_connectors=False,
            enable_pcb_ref=False, enable_label_recess=False,
        )
        doc = MagicMock()
        doc.addObject.side_effect = lambda t, n: MagicMock()
        with _patch_geo_methods(_Geo, self._dummy_shape()):
            builder = DocumentBuilder(doc)
            result = builder.build_enclosure(doc, board, cfg)
        assert "shell" in result
        assert "lid" in result

    def test_build_rejects_missing_document(self):
        """build_enclosure should raise clear error when doc is None."""
        from enclosure_template import DocumentBuilder
        builder = DocumentBuilder(None)
        board = make_board()
        cfg = PARAMS
        with pytest.raises((TypeError, ValueError, RuntimeError, AttributeError)):
            builder.build_enclosure(None, board, cfg)
