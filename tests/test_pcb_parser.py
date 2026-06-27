import os
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import pytest
from pcb_parser import parse, validate_board_data

FIXTURE = str(MODULE_DIR / "tests" / "fixtures" / "test_board.kicad_pcb")


class TestPCBParser:

    def test_parses_without_error(self):
        result = parse(FIXTURE)
        assert result is not None

    def test_board_dimensions(self):
        result = parse(FIXTURE)
        dims = result["dimensions"]
        assert abs(dims["width"] - 80.0) < 0.5, f"Width wrong: {dims['width']}"
        assert abs(dims["height"] - 60.0) < 0.5, f"Height wrong: {dims['height']}"

    def test_mounting_holes_detected(self):
        result = parse(FIXTURE)
        holes = result["mounting_holes"]
        assert len(holes) == 4, f"Expected 4 mounting holes, got {len(holes)}"

    def test_mounting_hole_diameter(self):
        result = parse(FIXTURE)
        for hole in result["mounting_holes"]:
            assert abs(hole["diameter"] - 3.2) < 0.1, \
                f"Wrong diameter: {hole['diameter']}"

    def test_no_edge_connectors_on_plain_board(self):
        result = parse(FIXTURE)
        assert result["edge_connectors"] == []

    def test_missing_file_raises(self):
        with pytest.raises((FileNotFoundError, Exception)):
            parse(str(MODULE_DIR / "nonexistent.kicad_pcb"))

    def test_bounding_box_present(self):
        result = parse(FIXTURE)
        dims = result["dimensions"]
        assert "x_min" in dims and "x_max" in dims
        assert "y_min" in dims and "y_max" in dims

    def test_validate_board_data_soft_warnings_on_minimal_board(self):
        result = parse(FIXTURE)
        valid, warnings = validate_board_data(result)
        assert not valid
        assert any("x_min is 0" in w for w in warnings), f"expected x_min=0 warning, got {warnings}"
        assert any("y_min is 0" in w for w in warnings), f"expected y_min=0 warning, got {warnings}"

    def test_validate_board_data_reports_missing_dimensions(self):
        data = {
            "dimensions": {},
            "mounting_holes": [],
            "components": [],
            "edge_connectors": [],
        }
        valid, warnings = validate_board_data(data)
        assert not valid
        assert any("width" in w for w in warnings)
