"""Shared test fixtures and FreeCAD stubs for AICompanion tests.

This file MUST be first in the test discovery order (pytest loads conftest.py
before any test modules). The FreeCAD module stubs are placed at module level
so they are in sys.modules before any test file imports from orchestrator.
"""

import sys
from unittest.mock import MagicMock

# ── FreeCAD module stubs (must be set BEFORE any orchestrator import) ─────
_FREECAD_MODULES = [
    "FreeCAD", "FreeCADGui", "Part", "Draft", "Sketcher",
    "PartDesign", "CurvedShapes", "freecad",
    "freecad.gears", "freecad.gears.commands",
]
for _mod in _FREECAD_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# compat shim — provides QtCore.QObject used by AIOrchestrator base class
if "compat" not in sys.modules:
    import types
    _qt_core = types.SimpleNamespace()
    _qt_core.QObject = type("QObject", (), {})
    sys.modules["compat"] = types.SimpleNamespace(QtCore=_qt_core)


# ── AST + exec helpers for template validation ────────────────────────────

import ast
import re


def extract_template_code(rendered: str) -> str:
    """Strip the ``\"\"\"```python```` fence wrapper that every template wraps output in.

    Returns the raw executable Python inside.  If no wrapper is detected
    the string is returned unchanged (allowing reuse with non-wrapped code).
    """
    m = re.search(r'^"""```python\n(.*?)\n```"""', rendered, re.DOTALL)
    return m.group(1) if m else rendered


def assert_valid_python(code: str, label: str = ""):
    """Raise AssertionError with the offending line if code has a syntax error."""
    try:
        ast.parse(code)
    except SyntaxError as e:
        snippet = code.splitlines()[max(0, e.lineno - 1)] if e.lineno else ""
        raise AssertionError(
            f"[{label}] SyntaxError on line {e.lineno}: {e.msg}\n  >>> {snippet}"
        )


def get_all_call_names(code: str) -> list:
    """Return every function/method name that is called in the code."""
    tree = ast.parse(code)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                names.append(node.func.attr)
            elif isinstance(node.func, ast.Name):
                names.append(node.func.id)
    return names


def run_in_mock_freecad(code: str) -> dict:
    """
    Execute generated FreeCAD Python in an isolated namespace where every
    FreeCAD symbol is a MagicMock. Returns the namespace so tests can
    assert on mock call counts and arguments.
    Raises AssertionError on SyntaxError before exec is attempted.
    """
    assert_valid_python(code, label="run_in_mock_freecad")
    ns = {
        "FreeCAD": MagicMock(),
        "FreeCADGui": MagicMock(),
        "App": MagicMock(),
        "Gui": MagicMock(),
        "Part": MagicMock(),
        "Draft": MagicMock(),
        "Sketcher": MagicMock(),
        "PartDesign": MagicMock(),
        "CurvedShapes": MagicMock(),
        "__builtins__": __builtins__,
    }
    try:
        exec(compile(code, "<generated>", "exec"), ns)
    except Exception as e:
        raise AssertionError(f"Generated code raised {type(e).__name__}: {e}")
    return ns


# ── pytest fixtures ────────────────────────────────────────────────────────

import pytest


@pytest.fixture(autouse=True)
def mock_anthropic():
    """Prevent any real API calls during integration tests.

    This fixture is autouse so every test automatically has a mock
    Anthropic/LLM client.  The pipeline() helper uses it to simulate
    the AI returning template code.
    """
    return MagicMock()
