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


sys.modules.setdefault("FreeCAD", types.SimpleNamespace(Console=types.SimpleNamespace(PrintError=lambda *_args, **_kwargs: None)))
sys.modules.setdefault("FreeCADGui", types.SimpleNamespace())
sys.modules.setdefault("compat", types.SimpleNamespace(QtCore=_DummyQtCore))
sys.modules.setdefault("assembly_graph", types.SimpleNamespace(AssemblyGraph=object))
sys.modules.setdefault("knowledge_base", types.SimpleNamespace(KnowledgeBase=object))

from orchestrator import AIOrchestrator


class PlanParsingTests(unittest.TestCase):
    def setUp(self):
        self.orch = object.__new__(AIOrchestrator)

    def test_extract_plan_accepts_markdown_step_em_dash(self):
        text = """## Plan

### Step 1 — Analyze the selected sketch footprint
Measure the wire bounds and confirm orientation.

### Step 2 — Pad the base enclosure
Create a Pad with the requested height.
"""
        steps = self.orch.extract_plan(text)
        self.assertEqual(
            steps,
            [
                "Analyze the selected sketch footprint",
                "Pad the base enclosure",
            ],
        )

    def test_extract_plan_single_step_allowed_by_default(self):
        text = """### Step 1 — Generate four snap clips
Use cantilever geometry on the long walls.
"""
        default_steps = self.orch.extract_plan(text)
        single_step = self.orch.extract_plan(text, min_steps=1)
        self.assertEqual(default_steps, ["Generate four snap clips"])
        self.assertEqual(single_step, ["Generate four snap clips"])

    def test_extract_plan_min_steps_two_rejects_single(self):
        text = """### Step 1 — Generate four snap clips
Use cantilever geometry on the long walls.
"""
        self.assertIsNone(self.orch.extract_plan(text, min_steps=2))

    def test_extract_plan_caps_at_max_steps(self):
        text = "1. first step\n2. second step\n3. third step\n4. fourth step\n5. fifth step\n"
        steps = self.orch.extract_plan(text, max_steps=3)
        self.assertEqual(steps, ["first step", "second step", "third step"])

    def test_extract_plan_max_steps_no_truncation_when_fewer(self):
        text = "1. first step\n2. second step\n"
        steps = self.orch.extract_plan(text, max_steps=3)
        self.assertEqual(steps, ["first step", "second step"])


class ExtractCodeBlocksTests(unittest.TestCase):
    def setUp(self):
        self.orch = object.__new__(AIOrchestrator)

    def test_python_fence(self):
        r = "Here:\n```python\nimport FreeCAD\ndoc = FreeCAD.ActiveDocument\n```\n"
        blocks = self.orch.extract_code_blocks(r)
        self.assertEqual(len(blocks), 1)
        self.assertIn("import FreeCAD", blocks[0])

    def test_capital_python_fence(self):
        r = "```Python\nimport FreeCAD\n```"
        blocks = self.orch.extract_code_blocks(r)
        self.assertEqual(len(blocks), 1)
        self.assertIn("import FreeCAD", blocks[0])

    def test_untagged_fence(self):
        r = "```\nimport FreeCAD\ndoc = FreeCAD.ActiveDocument\n```"
        blocks = self.orch.extract_code_blocks(r)
        self.assertEqual(len(blocks), 1)
        self.assertIn("import FreeCAD", blocks[0])

    def test_api_plan_then_code(self):
        r = ("<API_PLAN>\nbox.Length = 10\n</API_PLAN>\n\n"
             "```python\nbox = doc.addObject('Part::Box', 'Box')\n```")
        blocks = self.orch.extract_code_blocks(r)
        self.assertEqual(len(blocks), 1)
        self.assertIn("addObject", blocks[0])
        self.assertNotIn("API_PLAN", blocks[0])

    def test_json_fence_not_treated_as_code(self):
        r = "```json\n{\"a\": 1}\n```"
        self.assertEqual(self.orch.extract_code_blocks(r), [])

    def test_unfenced_heuristic_excludes_api_plan(self):
        r = ("<API_PLAN>\nsome.plan = 1\n</API_PLAN>\n"
             "import FreeCAD\ndoc = FreeCAD.ActiveDocument\n"
             "box = doc.addObject('Part::Box', 'Box')\n")
        blocks = self.orch.extract_code_blocks(r)
        self.assertEqual(len(blocks), 1)
        self.assertIn("addObject", blocks[0])
        self.assertNotIn("some.plan", blocks[0])


if __name__ == "__main__":
    unittest.main()
