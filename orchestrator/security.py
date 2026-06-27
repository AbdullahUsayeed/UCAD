"""Sandbox security: restricted builtins, import validation, escape detection."""
import ast, re, builtins


_PRELOADED_MODULES = {"FreeCAD", "FreeCADGui", "Part", "PartGui", "PartDesign",
                      "PartDesignGui", "Sketcher", "SketcherGui", "Mesh", "Draft",
                      "Import", "Export", "SheetMetal", "Fasteners", "Assembly",
                      "TechDraw", "math"}


def _safe_import(name, *args, **kwargs):
    if name in _PRELOADED_MODULES:
        return __import__(name, *args, **kwargs)
    raise ImportError(
        f"Module '{name}' is not available in the AI sandbox. "
        f"Use only: {', '.join(sorted(_PRELOADED_MODULES))}"
    )


SAFE_BUILTINS = {
    "True": True, "False": False, "None": None,
    "int": int, "float": float, "str": str, "bool": bool,
    "list": list, "dict": dict, "tuple": tuple, "set": set,
    "len": len, "range": range, "print": print,
    "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
    "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
    "sorted": sorted, "reversed": reversed, "any": any, "all": all,
    "isinstance": isinstance, "hasattr": hasattr, "getattr": getattr,
    "setattr": setattr, "type": type, "super": super,
    "iter": iter, "next": next, "slice": slice,
    "Exception": Exception, "ValueError": ValueError,
    "TypeError": TypeError, "AttributeError": AttributeError,
    "KeyError": KeyError, "IndexError": IndexError,
    "StopIteration": StopIteration, "NotImplementedError": NotImplementedError,
    "__import__": _safe_import,
    "__build_class__": builtins.__build_class__,
}

_SANDBOX_ESCAPE_PATTERNS = [
    (r"__class__", "Access to __class__ is blocked (sandbox escape vector)"),
    (r"__bases__", "Access to __bases__ is blocked (sandbox escape vector)"),
    (r"__subclasses__\s*\(", "Access to __subclasses__() is blocked (sandbox escape vector)"),
    (r"__globals__", "Access to __globals__ is blocked (sandbox escape vector)"),
    (r"__builtins__", "Access to __builtins__ is blocked"),
    (r"getattr\([^,)]+,\s*['\"]__", "Access to dunder attributes via getattr is blocked"),
]


def _validate_exec_code(code):
    """Reject sandboxed code that tries to import new modules or escape the sandbox."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ImportError(
                "Import statements are disabled in the AI sandbox. "
                "Use the preloaded FreeCAD, Part, Sketcher, Mesh, Draft, Import, Export, "
                "SheetMetal, Fasteners, Assembly, TechDraw, math, App, Gui, doc, and find bindings. "
                "For enclosures: build_from_parsed, EnclosureBuilder, BoardData, EnclosureConfig "
                "are already in scope — no import needed."
            )
    for pattern, msg in _SANDBOX_ESCAPE_PATTERNS:
        if re.search(pattern, code):
            raise ImportError(f"Sandbox security: {msg}")
