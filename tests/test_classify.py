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


sys.modules.setdefault("FreeCAD", types.SimpleNamespace(Console=types.SimpleNamespace(PrintError=lambda *_a, **_k: None)))
sys.modules.setdefault("FreeCADGui", types.SimpleNamespace())
sys.modules.setdefault("compat", types.SimpleNamespace(QtCore=_DummyQtCore))
sys.modules.setdefault("assembly_graph", types.SimpleNamespace(AssemblyGraph=object))
sys.modules.setdefault("knowledge_base", types.SimpleNamespace(KnowledgeBase=object))

from orchestrator import AIOrchestrator


class ClassifyRequestTests(unittest.TestCase):
    def setUp(self):
        self.orch = object.__new__(AIOrchestrator)

    def _label(self, text):
        return self.orch.classify_request(text)[0]

    def test_single_primitive_is_simple(self):
        for t in ("generate a rectangle", "make a box 10x5x3",
                  "cylinder radius 4", "a sphere", "draw a cube"):
            self.assertEqual(self._label(t), "simple", t)

    def test_single_primitive_is_confident(self):
        self.assertTrue(self.orch.classify_request("generate a rectangle")[1])

    def test_quantity_stays_simple(self):
        self.assertEqual(self._label("five boxes"), "simple")

    def test_relational_is_medium(self):
        for t in ("a box on top of another box", "cylinder aligned with the hole",
                  "a box with a hole through it"):
            self.assertEqual(self._label(t), "medium", t)

    def test_constraints_are_complex(self):
        for t in ("a parametric bracket", "sketch a constrained rectangle",
                  "fillet the edges", "an assembly of two parts",
                  "revolve the profile"):
            self.assertEqual(self._label(t), "complex", t)

    def test_distinct_primitives_are_medium(self):
        self.assertEqual(self._label("a box and a cylinder"), "medium")

    def test_empty_is_ambiguous(self):
        label, confident = self.orch.classify_request("")
        self.assertFalse(confident)

    def test_unknown_is_ambiguous_medium(self):
        label, confident = self.orch.classify_request("do the thing from before")
        self.assertEqual(label, "medium")
        self.assertFalse(confident)


if __name__ == "__main__":
    unittest.main()
