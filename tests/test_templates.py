"""Tests for parameterized design templates and quick-code dispatch."""
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


class _MockKB:
    def build(self, *a, **k):
        return "mock knowledge base"
    def set_version(self, *a, **k):
        pass


sys.modules.setdefault("FreeCAD", types.SimpleNamespace(
    Console=types.SimpleNamespace(PrintError=lambda *a, **k: None),
    Version=lambda: ["0", "21"],
    ActiveDocument=None,
    Vector=lambda *a: None,
))
sys.modules.setdefault("FreeCADGui", types.SimpleNamespace(
    execCommand=lambda *a: None,
    SendMsgToActiveView=lambda *a: None,
    addonManager=lambda: None,
    activateWorkbench=lambda *a: None,
))
sys.modules.setdefault("compat", types.SimpleNamespace(QtCore=_DummyQtCore))
sys.modules.setdefault("assembly_graph", types.SimpleNamespace(AssemblyGraph=object))
sys.modules.setdefault("knowledge_base", types.SimpleNamespace(KnowledgeBase=_MockKB))

from orchestrator import (render_template, TEMPLATE_SCHEMAS)


class QuickCodeTests(unittest.TestCase):
    """Verify quick-code templates resolve and render without error."""

    def test_triangle_in_quickcode_list(self):
        result = render_template("triangle")
        self.assertTrue(len(result) > 0)
        self.assertIn("Draft.makeWire", result)

    def test_curvedshapes_in_quickcode_list(self):
        result = render_template("curvedshapes")
        self.assertTrue(len(result) > 0)
        self.assertIn("makeCurvedArray", result)

    def test_render_triangle_default(self):
        result = render_template("triangle")
        self.assertIn("height = 50", result)

    def test_render_curvedshapes_default(self):
        result = render_template("curvedshapes")
        self.assertIn("span = 50.0", result)
        self.assertIn("chord = 100.0", result)
        self.assertIn("count = 20", result)

    def test_render_triangle_override(self):
        result = render_template("triangle", {"height": 80})
        self.assertIn("height = 80", result)
        self.assertNotIn("{height}", result, "placeholder must be fully substituted")

    def test_render_curvedshapes_schema_keys(self):
        keys = TEMPLATE_SCHEMAS["curvedshapes"]
        self.assertIn("span", keys)
        self.assertIn("chord", keys)
        self.assertIn("count", keys)

    def test_all_templates_render_without_keyerror(self):
        """Every template must render without KeyError using default schema values."""
        for name in TEMPLATE_SCHEMAS:
            result = render_template(name)
            self.assertGreater(len(result), 0,
                               f"template '{name}' produced empty output")

    def test_addfc_in_quickcode_list(self):
        result = render_template("addfc")
        self.assertTrue(len(result) > 0)
        self.assertIn("addFC.FCMacro", result)

    def test_render_addfc_default(self):
        result = render_template("addfc")
        self.assertIn("getUserMacroDir", result)
        self.assertIn("github.com/triplus/Add", result)

    def test_addfc_schema_keys(self):
        keys = TEMPLATE_SCHEMAS["addfc"]
        self.assertIsInstance(keys, dict)


if __name__ == "__main__":
    unittest.main()
