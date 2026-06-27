"""Exec-level validation of generated template code — syntax, mock execution,
API call correctness, and placeholder completeness.  No FreeCAD required."""

import re
import pytest
from orchestrator.templates import TEMPLATE_SCHEMAS, render_template
from conftest import (assert_valid_python, get_all_call_names,
                       run_in_mock_freecad, extract_template_code)


# ── Individual template classes ──────────────────────────────────────────


class TestGearTemplate:
    def test_syntax(self):
        assert_valid_python(render_template("gear"), "gear")

    def test_calls_part_api_involute(self):
        code = extract_template_code(render_template("gear"))
        names = get_all_call_names(code)
        assert "makePolygon" in names, "Expected Part.makePolygon for involute teeth"
        assert "extrude" in names, "Expected face.extrude to create solid"
        assert "Part.show" in names or "addObject" in names

    def test_override_module(self):
        rendered = render_template("gear", {"module": 2.5})
        inner = extract_template_code(rendered)
        assert "2.5" in inner
        assert_valid_python(inner, "gear-override-inner")

    def test_no_placeholder_remnants(self):
        code = render_template("gear")
        for key in TEMPLATE_SCHEMAS["gear"]:
            assert "{" + key + "}" not in code, (
                f"Unsubstituted placeholder {{{key}}} remains in gear template"
            )


class TestTriangleTemplate:
    def test_syntax(self):
        assert_valid_python(render_template("triangle"), "triangle")

    def test_calls_makewire(self):
        inner = extract_template_code(render_template("triangle"))
        ns = run_in_mock_freecad(inner)
        ns["Draft"].makeWire.assert_called()

    def test_override_base(self):
        rendered = render_template("triangle", {"height": 25.0})
        inner = extract_template_code(rendered)
        assert "25.0" in inner
        assert_valid_python(inner, "triangle-override-inner")

    def test_no_placeholder_remnants(self):
        code = render_template("triangle")
        for key in TEMPLATE_SCHEMAS["triangle"]:
            assert "{" + key + "}" not in code, (
                f"Unsubstituted placeholder {{{key}}} remains in triangle template"
            )


class TestCurvedShapesTemplate:
    def test_syntax(self):
        assert_valid_python(render_template("curvedshapes"), "curvedshapes")

    def test_calls_make_curved_array(self):
        inner = extract_template_code(render_template("curvedshapes"))
        names = get_all_call_names(inner)
        assert "makeCurvedArray" in names

    def test_activates_workbench(self):
        code = render_template("curvedshapes")
        assert "CurvedShapesWorkbench" in code

    def test_override_span(self):
        rendered = render_template("curvedshapes", {"span": 75.0})
        inner = extract_template_code(rendered)
        assert "75.0" in inner
        assert_valid_python(inner, "curvedshapes-override-inner")

    def test_no_placeholder_remnants(self):
        code = render_template("curvedshapes")
        for key in TEMPLATE_SCHEMAS["curvedshapes"]:
            assert "{" + key + "}" not in code, (
                f"Unsubstituted placeholder {{{key}}} remains in curvedshapes template"
            )


# ── Parametrized catch-all ───────────────────────────────────────────────


@pytest.mark.parametrize("name", list(TEMPLATE_SCHEMAS.keys()))
def test_every_template_has_valid_syntax(name):
    code = render_template(name)
    assert_valid_python(code, label=name)


@pytest.mark.parametrize("name", list(TEMPLATE_SCHEMAS.keys()))
def test_every_template_has_no_placeholder_remnants(name):
    code = render_template(name)
    for key in TEMPLATE_SCHEMAS.get(name, {}):
        assert "{" + key + "}" not in code, (
            f"[{name}] Unsubstituted placeholder {{{key}}} remains after render"
        )
