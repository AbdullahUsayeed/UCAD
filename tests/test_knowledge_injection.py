import sys
import types
import unittest
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))


class _DummyQObject:
    pass


class _DummyQtCore:
    QObject = _DummyQObject


# Other test files may set FreeCAD without Version via setdefault.
# Ensure our mock has all keys AIOrchestrator needs.
_fc = sys.modules.setdefault("FreeCAD", types.SimpleNamespace())
_fc.Console = getattr(_fc, "Console", types.SimpleNamespace(PrintError=lambda *_a, **_k: None))
if not hasattr(_fc, "Version"):
    _fc.Version = lambda: ["0", "21"]
if not hasattr(_fc, "ActiveDocument"):
    _fc.ActiveDocument = None
if not hasattr(_fc, "Vector"):
    _fc.Vector = lambda *a: None

sys.modules.setdefault("FreeCADGui", types.SimpleNamespace(
    execCommand=lambda *a: None,
    SendMsgToActiveView=lambda *a: None,
    addonManager=lambda: None,
))
sys.modules.setdefault("compat", types.SimpleNamespace(QtCore=_DummyQtCore))
sys.modules.setdefault("assembly_graph", types.SimpleNamespace(AssemblyGraph=object))
sys.modules.setdefault("knowledge_base", types.SimpleNamespace(KnowledgeBase=object))

# Replace KnowledgeBase mock with one that supports .build() and .set_version()
# so AIOrchestrator can be instantiated for injection end-to-end tests.
class _MockKB:
    def build(self, *a, **k):
        return "mock knowledge base"
    def set_version(self, *a, **k):
        pass

sys.modules["knowledge_base"] = types.SimpleNamespace(KnowledgeBase=_MockKB)

from orchestrator import (AIRFOIL_KNOWLEDGE, should_inject_airfoil,
                          GEAR_KNOWLEDGE, should_inject_gear,
                          TRIANGLE_KNOWLEDGE, should_inject_triangle,
                          CURVEDSHAPES_KNOWLEDGE, CURVEDSHAPES_WING_BRIDGE,
                          should_inject_curvedshapes,
                          ADDFC_KNOWLEDGE, should_inject_addfc,
                          AIOrchestrator)


class AirfoilInjectionTests(unittest.TestCase):
    def test_triggers_on_airfoil_requests(self):
        for t in ("generate a NACA 2412 wing",
                  "make an airfoil with chord 150mm",
                  "design a winglet",
                  "extrude an aerofoil over a 300mm wingspan"):
            self.assertTrue(should_inject_airfoil(t), t)

    def test_does_not_trigger_on_unrelated_requests(self):
        for t in ("make a box 10x10x10", "cylinder radius 5",
                  "a sphere", "generate a rectangle and a cylinder", ""):
            self.assertFalse(should_inject_airfoil(t), t)

    def test_knowledge_contains_closed_wire_guidance(self):
        self.assertIn("isClosed", AIRFOIL_KNOWLEDGE)
        self.assertIn("trailing edge", AIRFOIL_KNOWLEDGE.lower())

    def test_knowledge_prefers_part_face_extrude(self):
        self.assertIn("Part.Face", AIRFOIL_KNOWLEDGE)
        self.assertIn("extrude", AIRFOIL_KNOWLEDGE)
        self.assertIn("naca4", AIRFOIL_KNOWLEDGE)

    def test_knowledge_uses_draft_make_bspline_closed(self):
        self.assertIn("make_bspline", AIRFOIL_KNOWLEDGE)
        self.assertIn("closed=True", AIRFOIL_KNOWLEDGE)

    def test_knowledge_has_no_import_statements(self):
        # Imports are disabled in the sandbox; the recipe must not teach them.
        for line in AIRFOIL_KNOWLEDGE.splitlines():
            s = line.strip()
            self.assertFalse(
                s.startswith("import ") or s.startswith("from "),
                f"recipe contains an import statement: {line!r}",
            )


class GearInjectionTests(unittest.TestCase):
    def test_triggers_on_gear_requests(self):
        for t in ("make a spur gear with 30 teeth",
                  "generate an involute gear module 2",
                  "create a worm gear",
                  "I need a gear pair that meshes",
                  "design a cycloid gear",
                  "make a pinion"):
            self.assertTrue(should_inject_gear(t), t)

    def test_does_not_trigger_on_unrelated_requests(self):
        for t in ("make a box 10x10x10", "generate a NACA airfoil",
                  "extrude a cylinder", "create a fillet on this edge", ""):
            self.assertFalse(should_inject_gear(t), t)

    def test_knowledge_contains_gear_guidance(self):
        self.assertIn("def make_gear", GEAR_KNOWLEDGE)
        self.assertIn("involute_point", GEAR_KNOWLEDGE)
        self.assertIn("num_teeth", GEAR_KNOWLEDGE)

    def test_knowledge_has_fallback_path(self):
        self.assertIn("def make_gear", GEAR_KNOWLEDGE)
        self.assertIn("involute_point", GEAR_KNOWLEDGE)


class TriangleInjectionTests(unittest.TestCase):
    def test_triggers_on_triangle_requests(self):
        for t in ("make a triangle with angle 60 and height 50",
                  "create an isosceles triangle",
                  "generate a right triangle",
                  "triangle with base 100 and angle 45",
                  "vertex angle 90 degree triangle"):
            self.assertTrue(should_inject_triangle(t), t)

    def test_does_not_trigger_on_unrelated_requests(self):
        for t in ("make a box 10x10x10", "generate a NACA airfoil",
                  "extrude a cylinder", "create a gear with 20 teeth", ""):
            self.assertFalse(should_inject_triangle(t), t)

    def test_knowledge_contains_draft_makewire(self):
        self.assertIn("Draft.makeWire", TRIANGLE_KNOWLEDGE)
        self.assertIn("triangle_ah", TRIANGLE_KNOWLEDGE)

    def test_knowledge_has_formulas(self):
        self.assertIn("base = ", TRIANGLE_KNOWLEDGE)
        self.assertIn("hypo = ", TRIANGLE_KNOWLEDGE)


class CurvedShapesInjectionTests(unittest.TestCase):
    def test_triggers_on_curved_shapes_requests(self):
        for t in ("blend a circle into a square profile",
                  "create a fuselage with tapered cross-section",
                  "make a curved array of a profile",
                  "use hull curves to scale a shape",
                  "build a boat hull using curved shapes",
                  "add a notch connector between two parts",
                  "cross-section cut of a solid"):
            self.assertTrue(should_inject_curvedshapes(t), t)

    def test_does_not_trigger_on_unrelated_requests(self):
        for t in ("make a box 10x10x10", "generate a NACA airfoil",
                  "extrude a cylinder", "create a gear with 20 teeth",
                  "make a right triangle", ""):
            self.assertFalse(should_inject_curvedshapes(t), t)

    def test_knowledge_contains_makecurvedarray(self):
        self.assertIn("makeCurvedArray", CURVEDSHAPES_KNOWLEDGE)
        self.assertIn("makeCurvedSegment", CURVEDSHAPES_KNOWLEDGE)
        self.assertIn("makeCurvedPathArray", CURVEDSHAPES_KNOWLEDGE)

    def test_knowledge_has_items_guidance(self):
        self.assertIn("10-20 for preview", CURVEDSHAPES_KNOWLEDGE)
        self.assertIn("40-80 for final", CURVEDSHAPES_KNOWLEDGE)

    def test_knowledge_has_hullcurve_constraint(self):
        self.assertIn("MUST lie in", CURVEDSHAPES_KNOWLEDGE)
        self.assertIn("standard plane", CURVEDSHAPES_KNOWLEDGE)

    def test_knowledge_has_correct_fallback(self):
        self.assertIn("Part.makeLoft", CURVEDSHAPES_KNOWLEDGE)
        self.assertEqual(CURVEDSHAPES_KNOWLEDGE.count("Part.makeLoft"), 1,
                         "Only one fallback mention — avoid contradictory guidance")

    def test_wing_bridge_links_airfoil_to_curvedshapes(self):
        self.assertIn("makeCurvedArray", CURVEDSHAPES_WING_BRIDGE)
        self.assertIn("airfoil", CURVEDSHAPES_WING_BRIDGE)
        self.assertIn("Base=", CURVEDSHAPES_WING_BRIDGE)


# --- addFC ---


class AddFCInjectionTests(unittest.TestCase):
    def test_addfc_triggers_on_addfc(self):
        for t in ("how do I use addFC",
                  "run the addFC manager",
                  "addFC macro runner"):
            self.assertTrue(should_inject_addfc(t), t)

    def test_addfc_triggers_on_install_addon(self):
        for t in ("install addon in FreeCAD",
                  "install macro in FreeCAD",
                  "addon manager for workbenches",
                  "macro runner for batch install"):
            self.assertTrue(should_inject_addfc(t), t)

    def test_addfc_does_not_trigger_on_unrelated(self):
        for t in ("make a gear with 20 teeth",
                  "generate a NACA airfoil",
                  "create a curved array",
                  "extrude a cylinder", ""):
            self.assertFalse(should_inject_addfc(t), t)

    def test_addfc_knowledge_injected_in_prompt(self):
        # Use object.__new__ to bypass __init__ (same pattern as other test files)
        orch = object.__new__(AIOrchestrator)
        orch._last_user_input = "install addon for freecad"
        orch.kb = _MockKB()
        orch.failures = types.SimpleNamespace(as_prompt_section=lambda: "")
        orch._dxf_context = None
        result = orch.build_system_prompt()
        self.assertIn("addFC", result)
        self.assertIn("FreeCADGui.execCommand", result)
        self.assertIn("has no `.install()` or `.run()` method", result,
                      "injected knowledge should warn against hallucinated API")

    def test_addfc_knowledge_contains_programmatic_usage(self):
        self.assertIn("FreeCADGui.execCommand", ADDFC_KNOWLEDGE)
        self.assertIn("addFC", ADDFC_KNOWLEDGE)

    def test_triangle_knowledge_contains_rule_zero(self):
        """RULE #0 must be first — before any other content."""
        first_500 = TRIANGLE_KNOWLEDGE[:500]
        self.assertIn("RULE #0", first_500,
                       "RULE #0 must appear in the first 500 chars of TRIANGLE_KNOWLEDGE")
        self.assertIn("DO NOT EXTRUDE", first_500.upper(),
                       "Extrusion warning must appear at the top of TRIANGLE_KNOWLEDGE")

    def test_no_make_extrusion_correction_present(self):
        """API correction for Part.makeExtrusion must exist."""
        ids = [c.get("id") for c in AIOrchestrator.API_CORRECTIONS if isinstance(c, dict)]
        self.assertIn("no_make_extrusion", ids,
                       "no_make_extrusion correction missing from API_CORRECTIONS")


if __name__ == "__main__":
    unittest.main()
