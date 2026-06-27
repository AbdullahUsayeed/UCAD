"""Integration tests: full pipeline from user prompt → system prompt → executable code.

No real API calls, no FreeCAD required — every LLM interaction is mocked.
"""

import types
import pytest
from conftest import (run_in_mock_freecad, extract_template_code,
                       assert_valid_python, get_all_call_names)


# ── helpers ──────────────────────────────────────────────────────────────


class _MockKB:
    def build(self, *a, **k):
        return "mock knowledge base"
    def set_version(self, *a, **k):
        pass


def _make_orch(prompt: str):
    """Minimal AIOrchestrator instance, ready for build_system_prompt()."""
    from orchestrator import AIOrchestrator
    orch = object.__new__(AIOrchestrator)
    orch._last_user_input = prompt
    orch.kb = _MockKB()
    orch.failures = types.SimpleNamespace(as_prompt_section=lambda: "")
    orch._dxf_context = None
    return orch


def pipeline(prompt: str, mock_client=None) -> dict:
    """Simulate the full orchestrator pipeline with a mocked API.

    Returns {"system_prompt": str, "code": str, "ns": dict} so each test
    can assert at whichever layer it cares about.
    """
    system_prompt = _make_orch(prompt).build_system_prompt()

    from orchestrator.templates import render_template
    from orchestrator.gear_knowledge import should_inject_gear
    from orchestrator.triangle_knowledge import should_inject_triangle
    from orchestrator.curvedshapes_knowledge import should_inject_curvedshapes
    from orchestrator.airfoil_knowledge import should_inject_airfoil

    if should_inject_gear(prompt):
        code = render_template("gear")
    elif should_inject_triangle(prompt):
        code = render_template("triangle")
    elif should_inject_curvedshapes(prompt):
        code = render_template("curvedshapes")
    elif should_inject_airfoil(prompt):
        code = "import FreeCAD\nApp.newDocument('Wing')"
    else:
        code = "import FreeCAD\nApp.newDocument('Test')"

    inner = extract_template_code(code) if "\"\"\"" in code else code
    ns = run_in_mock_freecad(inner)
    return {"system_prompt": system_prompt, "code": code, "ns": ns}


# ── topic-level integration tests ────────────────────────────────────────


class TestGearIntegration:

    def test_system_prompt_contains_gear_knowledge(self, mock_anthropic):
        result = pipeline("make a gear with module 1.5")
        assert "def make_gear" in result["system_prompt"]

    def test_system_prompt_contains_involute_fallback(self, mock_anthropic):
        result = pipeline("make a gear with module 1.5")
        assert "involute" in result["system_prompt"]

    def test_generated_code_is_executable(self, mock_anthropic):
        result = pipeline("make a gear with module 1.5")
        assert result["ns"] is not None

    def test_api_corrections_present(self, mock_anthropic):
        result = pipeline("make a gear with module 1.5")
        assert "freecad.gears" in result["system_prompt"]


class TestTriangleIntegration:

    def test_system_prompt_contains_triangle_knowledge(self, mock_anthropic):
        result = pipeline("draw a triangle")
        assert "Draft.makeWire" in result["system_prompt"]

    def test_generated_code_calls_makewire(self, mock_anthropic):
        result = pipeline("draw a triangle")
        ns = result["ns"]
        ns["Draft"].makeWire.assert_called()


class TestCurvedShapesIntegration:

    def test_system_prompt_contains_curvedshapes_knowledge(self, mock_anthropic):
        result = pipeline("make a curved surface blend")
        assert "makeCurvedArray" in result["system_prompt"]

    def test_generated_code_activates_workbench(self, mock_anthropic):
        result = pipeline("curved surface blend")
        assert "CurvedShapesWorkbench" in result["code"]


class TestAddFCIntegration:

    def test_system_prompt_contains_addfc_knowledge(self, mock_anthropic):
        result = pipeline("how do I install an addon with addFC")
        assert "addFC is a third-party" in result["system_prompt"]

    def test_addfc_does_not_inject_on_unrelated(self, mock_anthropic):
        result = pipeline("make a box")
        assert "addFC is a third-party" not in result["system_prompt"]


class TestExclusionLogic:

    def test_gear_excludes_curvedshapes(self, mock_anthropic):
        result = pipeline("make a gear")
        sp = result["system_prompt"]
        assert "def make_gear" in sp
        assert "CurvedShapes.makeCurvedArray" not in sp

    def test_wing_prompt_injects_bridge_not_full_curvedshapes(self, mock_anthropic):
        result = pipeline("design a wing airfoil with hull curves")
        sp = result["system_prompt"]
        assert "You have both airfoil" in sp
        assert "CurvedShapes" in sp


# ── parametrized regression guard ────────────────────────────────────────


REGRESSION_CASES = [
    ("make a gear",                         "def make_gear",                  True),
    ("make a gear",                         "CurvedShapes.makeCurvedArray", False),
    ("draw a triangle",                     "Draft.makeWire",                 True),
    ("blend two surfaces",                  "makeCurvedArray",                True),
    ("design a wing with hull curves",      "You have both airfoil",          True),
    ("install addFC addon",                 "addFC is a third-party",         True),
    ("make a simple box",                   "def make_gear",                 False),
]


@pytest.mark.parametrize("prompt,phrase,should_contain", REGRESSION_CASES)
def test_prompt_injection_regression(prompt, phrase, should_contain, mock_anthropic):
    sp = _make_orch(prompt).build_system_prompt()
    if should_contain:
        assert phrase in sp, f"Expected {phrase!r} in system prompt for {prompt!r}"
    else:
        assert phrase not in sp, f"Did NOT expect {phrase!r} in system prompt for {prompt!r}"


def test_response_mode_header_is_first_content(mock_anthropic):
    orch = _make_orch("draw a triangle")
    orch.model = "claude-sonnet-4-6"
    orch.max_tokens = 4096
    sp = orch.build_system_prompt()
    assert sp.strip().startswith("You are an expert, autonomous FreeCAD AI Developer"), \
        "Response mode header must be the very first content in system prompt"


def test_response_mode_header_precedes_api_corrections(mock_anthropic):
    orch = _make_orch("draw a triangle")
    orch.model = "claude-sonnet-4-6"
    orch.max_tokens = 4096
    sp = orch.build_system_prompt()
    header_pos = sp.find("RESPONSE FORMAT RULES")
    corrections_pos = sp.find("COMMON FREECAD API MISTAKES")
    assert header_pos < corrections_pos, \
        "RESPONSE FORMAT RULES must appear before API corrections"


class TestDxfNormalizationIntegration:
    """DXF coordinate normalization reaches the AI context injection point."""

    def _make_orch(self, profiles_data, mock_anthropic):
        from orchestrator.core import AIOrchestrator
        from dxf_processor import _normalize_to_origin
        result = {
            "status": "ok",
            "profiles": profiles_data,
            "metadata": {
                "bbox": [-2607, 567, -2569, 605],
                "profile_count": len(profiles_data),
                "units": "mm",
            },
            "warnings": [],
        }
        out = _normalize_to_origin(result)
        orch = object.__new__(AIOrchestrator)
        orch._dxf_context = out
        orch._last_user_input = "extrude the outline 5mm"
        orch.kb = _MockKB()
        orch.failures = types.SimpleNamespace(as_prompt_section=lambda: "")
        return orch

    def test_dxf_coordinate_rule_in_system_prompt(self, mock_anthropic):
        orch = self._make_orch([{
            "coordinates": [(-2607, 567), (-2569, 567), (-2569, 605), (-2607, 605)],
            "holes": [], "bbox": [-2607, 567, -2569, 605],
        }], mock_anthropic)
        sp = orch.build_system_prompt()
        assert "DXF COORDINATE RULE" in sp
        assert "pre-normalized" in sp

    def test_no_large_coords_in_formatted_output(self, mock_anthropic):
        orch = self._make_orch([{
            "coordinates": [(-2607, 567), (-2569, 567), (-2569, 605), (-2607, 605)],
            "holes": [], "bbox": [-2607, 567, -2569, 605],
        }], mock_anthropic)
        formatted = orch._format_dxf_data()
        import re
        large = re.findall(r"\b\d{4,}\b", formatted)
        assert not large, f"Large coordinates leaked: {large[:5]}"

    def test_normalized_coords_in_formatted_output(self, mock_anthropic):
        orch = self._make_orch([{
            "coordinates": [(-2607, 567), (-2569, 567), (-2569, 605), (-2607, 605)],
            "holes": [], "bbox": [-2607, 567, -2569, 605],
        }], mock_anthropic)
        formatted = orch._format_dxf_data()
        import re
        coords_in_text = re.findall(r"\((-?\d+\.?\d*),(-?\d+\.?\d*)\)", formatted)
        for x_str, y_str in coords_in_text:
            x, y = float(x_str), float(y_str)
            assert abs(x) < 100, f"Coordinate x={x} too large (should be normalized near 0)"
            assert abs(y) < 100, f"Coordinate y={y} too large (should be normalized near 0)"


def test_ask_mode_role_label_guides_not_executes():
    """Ask mode prompt must instruct guidance, not autonomous code execution."""
    import inspect
    import re
    from orchestrator import core as core_module
    src = inspect.getsource(core_module)
    # There is exactly one "ask" key in role_label — confirm it's the new one
    matches = re.findall(r'"ask":\s*"([^"]+)"', src)
    assert len(matches) >= 1
    ask_prompt = matches[-1]
    assert "Guide the user" in ask_prompt
    assert "step by step" in ask_prompt
    assert "autonomous" not in ask_prompt.lower()
    assert "numbered plan" not in ask_prompt.lower()


def test_addfc_fallback_dispatch(mock_anthropic):
    """get_fallback_code must dispatch 'addfc' to the addFC template."""
    from orchestrator.core import AIOrchestrator
    orch = object.__new__(AIOrchestrator)
    orch._last_user_input = ""
    orch.kb = _MockKB()
    orch.failures = types.SimpleNamespace(as_prompt_section=lambda: "")
    orch._dxf_context = None
    code = orch.get_fallback_code("install an addon manager addfc")
    assert code is not None
    assert len(code) > 0
    assert "addFC.FCMacro" in code



