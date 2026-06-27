import sys
import types
import unittest
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))


class _DummySignal:
    def connect(self, *_args, **_kwargs):
        return None


class _DummyQObject:
    pass


class _DummyQtCore:
    QObject = _DummyQObject


sys.modules.setdefault("FreeCAD", types.SimpleNamespace(Console=types.SimpleNamespace(PrintError=lambda *_args, **_kwargs: None)))
sys.modules.setdefault("FreeCADGui", types.SimpleNamespace())
sys.modules.setdefault("compat", types.SimpleNamespace(QtCore=_DummyQtCore))
sys.modules.setdefault("assembly_graph", types.SimpleNamespace(AssemblyGraph=object))
sys.modules.setdefault("knowledge_base", types.SimpleNamespace(KnowledgeBase=object))

from secret_store import protect_secret, unprotect_secret
from orchestrator import _validate_exec_code, translate_error, AIOrchestrator, _safe_import


class SecurityBasicsTests(unittest.TestCase):
    def test_sandbox_rejects_import_statements(self):
        with self.assertRaises(ImportError):
            _validate_exec_code("import os\nprint('nope')")

    def test_translate_error_keeps_generic_attribute_error_path(self):
        diagnosis, strategy = translate_error("AttributeError: unexpected descriptor failure")
        self.assertIn("bad_attr_gen", diagnosis)
        self.assertEqual(strategy, "")

    def test_secret_store_round_trips(self):
        value = "secret-value-123"
        encrypted = protect_secret(value, "api_key")
        self.assertNotEqual(encrypted, value)
        self.assertEqual(unprotect_secret(encrypted, "api_key"), value)

    def test_secret_store_empty_roundtrip(self):
        self.assertEqual(protect_secret("", "api_key"), "")
        self.assertEqual(unprotect_secret("", "api_key"), "")

    def test_secret_store_decrypt_bogus(self):
        self.assertEqual(unprotect_secret("garbage", "api_key"), "")

    def test_secret_overwrite_then_read(self):
        v1 = protect_secret("first_value", "overwrite_test")
        v2 = protect_secret("second_value", "overwrite_test")
        self.assertEqual(unprotect_secret(v2, "overwrite_test"), "second_value")

    def test_secret_multiple_purposes(self):
        token1 = protect_secret("val_a", "purpose_a")
        token2 = protect_secret("val_b", "purpose_b")
        self.assertEqual(unprotect_secret(token1, "purpose_a"), "val_a")
        self.assertEqual(unprotect_secret(token2, "purpose_b"), "val_b")

    def test_secret_cross_purpose_isolation(self):
        token = protect_secret("isolated", "sp_a")
        self.assertNotEqual(unprotect_secret(token, "sp_b"), "isolated")

    def test_secret_unicode_roundtrip(self):
        value = "s\u00e9cret \u2603 \U0001f600"
        token = protect_secret(value, "unicode_test")
        self.assertEqual(unprotect_secret(token, "unicode_test"), value)

    def test_secret_large_value(self):
        value = "x" * 10000
        token = protect_secret(value, "large_test")
        self.assertEqual(unprotect_secret(token, "large_test"), value)

    def test_pre_validate_catches_gui_recompute(self):
        violations = AIOrchestrator.pre_validate("FreeCADGui.activeDocument().recompute()")
        self.assertTrue(any("recompute" in v for v in violations), violations)

    def test_pre_validate_catches_view_default_view(self):
        violations = AIOrchestrator.pre_validate("view.viewDefaultView()")
        self.assertTrue(any("viewDefaultView" in v for v in violations), violations)

    def test_translate_error_maps_gui_recompute(self):
        diagnosis, strategy = translate_error("'Gui.Document' object has no attribute 'recompute'")
        self.assertIn("recompute", diagnosis)
        self.assertIn("FreeCAD.ActiveDocument.recompute", strategy)

    def test_translate_error_maps_view_default(self):
        diagnosis, strategy = translate_error("AttributeError: viewDefaultView")
        self.assertIn("viewDefaultView", diagnosis)
        self.assertIn("SendMsgToActiveView", strategy)

    def test_pre_validate_catches_pad_type_dimension(self):
        code = "body = doc.addObject('PartDesign::Body', 'Body')\npad.Type = 'Dimension'"
        violations = AIOrchestrator.pre_validate(code)
        self.assertTrue(any("Dimension" in v for v in violations), violations)

    def test_translate_error_maps_pad_type_enum(self):
        diagnosis, strategy = translate_error(
            "ValueError: 'Dimension' is not part of the enumeration in WingPad.Type")
        self.assertIn("Length", strategy)

    def test_translate_error_maps_unit_mismatch(self):
        diagnosis, _strategy = translate_error(
            "ArithmeticError: Quantity::operator -(): Unit mismatch in minus operation")
        self.assertIn(".Value", diagnosis)

    def test_translate_error_maps_open_wire(self):
        diagnosis, _strategy = translate_error("WingPad: Wire is not closed.")
        self.assertIn("open_wire", diagnosis)

    def test_translate_error_maps_null_input(self):
        diagnosis, _strategy = translate_error("ValueError: Null input shape")
        self.assertIn("null_input", diagnosis)

    def test_translate_error_maps_body_not_allowed(self):
        diagnosis, _strategy = translate_error("ValueError: Body: object is not allowed")
        self.assertIn("body_not_allowed", diagnosis)
        self.assertIn("newObject", diagnosis)

    def test_translate_error_maps_not_dag(self):
        diagnosis, _strategy = translate_error("Document.cpp(2498): The graph must be a DAG.")
        self.assertIn("not_dag", diagnosis)

    def test_translate_error_maps_bad_attach_plane(self):
        diagnosis, _strategy = translate_error(
            "PickProfile: AttachEngine3D: subshape not found GuitarPickBody.XY_Plane")
        self.assertIn("bad_attach_plane", diagnosis)

    def test_translate_error_maps_bad_arc(self):
        diagnosis, _strategy = translate_error(
            "TypeError: ArcOfCircle constructor expects a circle curve and a parameter range or three points")
        self.assertIn("bad_arc", diagnosis)

    # ── Sandbox edge cases ──────────────────────────────────────

    def test_safe_import_allows_preloaded_module(self):
        from orchestrator.security import _PRELOADED_MODULES
        self.assertIn("math", _PRELOADED_MODULES)
        mod = _safe_import("math")
        self.assertIsNotNone(mod)

    def test_safe_import_rejects_untrusted_module(self):
        with self.assertRaises(ImportError):
            _safe_import("os")

    def test_validate_exec_code_bad_syntax_does_not_raise(self):
        _validate_exec_code("this is not valid python {{{")
        # Must not raise — SyntaxError is silently ignored

    def test_validate_exec_code_rejects_class_access(self):
        with self.assertRaises(ImportError):
            _validate_exec_code("obj.__class__")

    def test_validate_exec_code_rejects_bases_access(self):
        with self.assertRaises(ImportError):
            _validate_exec_code("obj.__bases__")

    def test_validate_exec_code_rejects_subclasses_call(self):
        with self.assertRaises(ImportError):
            _validate_exec_code("obj.__subclasses__()")

    # ── Release pipeline tests ──────────────────────────────────

    def test_python_deps_bootstrap_in_initgui(self):
        """InitGui.py must add .python-deps to sys.path before any other import."""
        initgui_path = MODULE_DIR / "InitGui.py"
        with open(initgui_path) as f:
            src = f.read()
        lines = src.splitlines()
        bootstrap_line = next(
            (i for i, l in enumerate(lines) if ".python-deps" in l), None
        )
        assert bootstrap_line is not None, \
            ".python-deps bootstrap missing from InitGui.py"
        assert bootstrap_line < 15, \
            f".python-deps bootstrap at line {bootstrap_line} — must be in first 15 lines"

    def test_initgui_bootstrap_uses_abspath(self):
        """Bootstrap must use abspath so it works regardless of cwd."""
        initgui_path = MODULE_DIR / "InitGui.py"
        with open(initgui_path) as f:
            src = f.read()
        assert "abspath" in src or "resolve" in src, \
            "Bootstrap must use os.path.abspath or Path.resolve — relative paths break when cwd changes"

    def test_update_deps_script_exists(self):
        assert (MODULE_DIR / "tools" / "update_deps.py").exists(), \
            "tools/update_deps.py missing — needed to regenerate vendored deps before release"

    def test_package_xml_has_python_deps(self):
        """package.xml must declare ezdxf and shapely as pythondeps."""
        pkg_xml = MODULE_DIR / "package.xml"
        with open(pkg_xml) as f:
            content = f.read()
        assert "ezdxf" in content, "ezdxf missing from package.xml pythondeps"
        assert "shapely" in content, "shapely missing from package.xml pythondeps"


if __name__ == "__main__":
    unittest.main()
