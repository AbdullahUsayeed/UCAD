# InitGui.py - FreeCAD AI Companion Workbench V4
import sys as _sys, os as _os, FreeCAD, FreeCADGui
try: __file__
except NameError: __file__ = _os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "AICompanion", "InitGui.py")
_ADDON_DIR = _os.path.dirname(_os.path.abspath(__file__))

# Bootstrap vendored dependencies — must be first
_deps_dir = _os.path.join(_ADDON_DIR, ".python-deps")
if _os.path.isdir(_deps_dir) and _deps_dir not in _sys.path:
    _sys.path.insert(0, _deps_dir)
del _deps_dir
__version__ = "1.0.0"

# ── Verify critical dependencies are available ────────────
_MISSING_DEPS = []
for _pkg in ("litellm", "ezdxf", "shapely"):
    try:
        __import__(_pkg)
    except ImportError:
        _MISSING_DEPS.append(_pkg)
if _MISSING_DEPS:
    _msg = (
        f"Missing critical dependencies: {', '.join(_MISSING_DEPS)}.\n"
        "Run this in your terminal to install:\n"
    )
    if _os.name == "nt":
        _msg += (
            '  "C:\\Program Files\\FreeCAD 1.1\\bin\\python.exe" -m pip install -r "'
            + _os.path.join(_ADDON_DIR, "requirements.txt") + '"\n'
        )
    else:
        _msg += "  pip install -r " + _os.path.join(_ADDON_DIR, "requirements.txt") + "\n"
    _msg += "Or run: python tools/update_deps.py"
    FreeCAD.Console.PrintError(f"[AICompanion] {_msg}\n")
    del _msg
del _MISSING_DEPS, _pkg

# ── Startup noise suppression ────────────────────────────
# External addons (ConstraintDesign, KiCadStepUp, etc.) may emit Python
# warnings or FreeCAD console noise during import.  We filter known
# patterns so the Report View stays usable for the user.
import warnings

# 1. Python-level filter — suppresses DeprecationWarning, FutureWarning, etc.
#    from all modules during the import phase.
_IGNORE_CATS = (FutureWarning, DeprecationWarning, ImportWarning, UserWarning)
for _cat in _IGNORE_CATS:
    warnings.filterwarnings("ignore", category=_cat)

# 2. FreeCAD console filter — suppresses PrintWarning/PrintLog lines whose
#    text matches known noisy externals.
_SUPPRESS_PATTERNS = [
    "constraintdesign", "kicadstepup", "kicad", "stepup",
    "no module named", "failed to load", "deprecated",
]

def _make_filter(orig_fn):
    _patterns = _SUPPRESS_PATTERNS  # capture at definition time (avoids runtime global lookup issues)
    def wrapper(msg, *a, **kw):
        ml = msg.lower() if isinstance(msg, str) else ""
        if any(p in ml for p in _patterns):
            return
        return orig_fn(msg, *a, **kw)
    return wrapper

_ORIG_WARN = getattr(FreeCAD.Console, "PrintWarning", None)
_ORIG_LOG = getattr(FreeCAD.Console, "PrintLog", None)
try:
    if callable(_ORIG_WARN):
        FreeCAD.Console.PrintWarning = _make_filter(_ORIG_WARN)
    if callable(_ORIG_LOG):
        FreeCAD.Console.PrintLog = _make_filter(_ORIG_LOG)
except Exception:
    pass

# 3. Restore original functions after 15 s so user-generated warnings are not lost.
import threading
def _restore(orig_warn=_ORIG_WARN, orig_log=_ORIG_LOG, ignore_cats=_IGNORE_CATS,
             _warnings=warnings, _FreeCAD_Console=FreeCAD.Console):
    try:
        if callable(orig_warn):
            _FreeCAD_Console.PrintWarning = orig_warn
        if callable(orig_log):
            _FreeCAD_Console.PrintLog = orig_log
    except Exception:
        pass
    for _cat in ignore_cats:
        _warnings.filterwarnings("default", category=_cat)
_timer = threading.Timer(15.0, _restore)
_timer.daemon = True
_timer.start()

def _make_icon():
    from compat import QtCore, QtGui
    pm = QtGui.QPixmap(32, 32)
    pm.fill(QtCore.Qt.transparent)
    if pm.isNull():
        pm = QtGui.QPixmap(32, 32)
        pm.fill(QtCore.Qt.gray)
        return pm
    try:
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setBrush(QtGui.QColor("#0e639c"))
        p.setPen(QtCore.Qt.NoPen)
        p.drawRoundedRect(5, 3, 22, 26, 5, 5)
        p.setBrush(QtGui.QColor("#6af7b8"))
        p.drawPolygon([QtCore.QPoint(16, 9), QtCore.QPoint(23, 18), QtCore.QPoint(9, 18)])
        p.setBrush(QtGui.QColor("#f7c96a"))
        p.drawEllipse(20, 11, 4, 4)
        p.end()
    except Exception:
        pm.fill(QtCore.Qt.gray)
    return pm

class AICompanionCommand:
    def GetResources(self):
        try:
            pixmap = _make_icon()
        except Exception:
            # Never block command registration due to icon rendering/import issues.
            pixmap = ""
        return {
            'Pixmap': pixmap,
            'MenuText': 'Open AI Copilot',
            'ToolTip': 'Open AI design assistant (Ctrl+Shift+A)',
            'Accel': 'Ctrl+Shift+A'
        }
    
    def Activated(self):
        try:
            from AICompanionGui import show_sidebar
            show_sidebar()
        except Exception as e:
            import traceback
            FreeCAD.Console.PrintError(f"AICompanion: {e}\n{traceback.format_exc()}\n")

# Register command
try:
    FreeCADGui.addCommand('AI_Companion_Command', AICompanionCommand())
except Exception as e:
    FreeCAD.Console.PrintError(f"AICompanion: failed to register command: {e}\n")

class AICompanionWorkbench(FreeCADGui.Workbench):
    MenuText = "UCAD Assistant"
    ToolTip = "Usayeed AI CAD Agent v1.0.0: Sketches, Booleans, Templates, Multi-Docs"
    
    def Initialize(self):
        import traceback
        try:
            if 'AI_Companion_Command' not in FreeCADGui.listCommands():
                FreeCADGui.addCommand('AI_Companion_Command', AICompanionCommand())
        except Exception:
            FreeCAD.Console.PrintError(f"AICompanion Initialize: {traceback.format_exc()}\n")
        self.appendToolbar("AI Tools", ["AI_Companion_Command"])
        self.appendMenu("AI Copilot", ["AI_Companion_Command"])
    
    def Activated(self):
        try:
            from AICompanionGui import show_sidebar
            show_sidebar()
        except Exception as e:
            import traceback
            FreeCAD.Console.PrintError(f"AICompanion Workbench.Activated failed: {e}\n{traceback.format_exc()}\n")

    def GetClassName(self):
        return "Gui::PythonWorkbench"

# Register workbench
try:
    FreeCADGui.addWorkbench(AICompanionWorkbench())
except Exception as e:
    FreeCAD.Console.PrintError(f"AICompanion: failed to register workbench: {e}\n")
