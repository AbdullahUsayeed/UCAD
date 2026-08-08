# InitGui.py - FreeCAD AI Companion Workbench V4
import sys as _sys, os as _os, FreeCAD, FreeCADGui
try: __file__
except NameError: __file__ = _os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "AICompanion", "InitGui.py")
_ADDON_DIR = _os.path.dirname(_os.path.abspath(__file__))

_deps_dir = _os.path.join(_ADDON_DIR, ".python-deps")
if _os.path.isdir(_deps_dir) and _deps_dir not in _sys.path:
    _sys.path.insert(0, _deps_dir)
del _deps_dir
__version__ = "1.1.0"

if _os.environ.get("UCAD_LAUNCHED"):
    FreeCAD.Console.PrintLog("[UCAD] Launched by UCAD Launcher\n")

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

import warnings

_IGNORE_CATS = (FutureWarning, DeprecationWarning, ImportWarning, UserWarning)
for _cat in _IGNORE_CATS:
    warnings.filterwarnings("ignore", category=_cat)

_SUPPRESS_PATTERNS = [
    "constraintdesign", "kicadstepup", "kicad", "stepup",
    "no module named", "failed to load", "deprecated",
]

def _make_filter(orig_fn):
    _patterns = _SUPPRESS_PATTERNS
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

try:
    FreeCADGui.addCommand('AI_Companion_Command', AICompanionCommand())
except Exception as e:
    FreeCAD.Console.PrintError(f"AICompanion: failed to register command: {e}\n")

class AICompanionWorkbench(FreeCADGui.Workbench):
    WorkbenchId = "UCADAssistant"
    MenuText = "UCAD Assistant"
    ToolTip = "Usayeed AI CAD Agent v1.1.0"
    
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

try:
    FreeCADGui.addWorkbench(AICompanionWorkbench())
except Exception as e:
    FreeCAD.Console.PrintError(f"AICompanion: failed to register workbench: {e}\n")

def _ask_telemetry_consent():
    """Show a simple consent dialog. Returns True if the user agreed."""
    try:
        from compat import QtWidgets, QtCore
        mw = FreeCADGui.getMainWindow()
        parent = mw if mw else None
        box = QtWidgets.QMessageBox(parent)
        box.setWindowTitle("UCAD Assistant — Usage Statistics")
        box.setIcon(QtWidgets.QMessageBox.Question)
        box.setText(
            "Help improve UCAD Assistant.\n\n"
            "May UCAD Assistant collect anonymous usage statistics "
            "(CAD commands and AI-generated scripts) and send them to "
            "our server to train better models?"
        )
        box.setInformativeText(
            "No document data or personal information is collected. "
            "You can change this anytime in Settings."
        )
        accept = box.addButton("I Agree", QtWidgets.QMessageBox.AcceptRole)
        box.addButton("No Thanks", QtWidgets.QMessageBox.RejectRole)
        box.setDefaultButton(accept)
        box.exec_()
        return box.clickedButton() is accept
    except Exception:
        return False


def _maybe_start_telemetry():
    """Start the collector only if the user has agreed to telemetry."""
    from telemetry import TelemetryCollector, has_consent, record_consent
    consent = has_consent()
    if consent is None:
        consent = _ask_telemetry_consent()
        record_consent(consent)
        FreeCAD.Console.PrintLog(
            "[AICompanion:Telemetry] Consent "
            + ("accepted" if consent else "declined") + "\n"
        )
    if not consent:
        return
    try:
        tc = TelemetryCollector()
        FreeCADGui._telemetry = tc
        tc.install_do_command_hook()
        tc.install_run_command_hook()
        tc.install_report_view_hook()
        tc._hook_python_console()
    except Exception:
        pass


try:
    import threading
    threading.Timer(2.0, _maybe_start_telemetry).start()
except Exception:
    pass
