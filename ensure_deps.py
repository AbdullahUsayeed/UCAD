"""ensure_deps.py — verify and (optionally) install vendored dependencies.

Fallback for FreeCAD 1.1 Addon Manager, which does not run post_install.py
automatically. The workbench calls ensure_deps() at init; if any critical
package is missing from .python-deps/, the user is offered a one-click pip
install into the addon's vendored directory.
"""

import os
import subprocess
import sys
import threading
from pathlib import Path

ADDON_DIR = Path(__file__).resolve().parent
DEPS_DIR = ADDON_DIR / ".python-deps"
REQ_FILE = ADDON_DIR / "requirements.txt"

CRITICAL = ("litellm", "ezdxf", "shapely")

# Guards against double-prompting if both post_install and init-time checks run.
_prompt_lock = threading.Lock()
_prompt_shown = False


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog(f"[AICompanion] {msg}\n")
    except ImportError:
        print(msg)


def missing_packages() -> list:
    """Return names of CRITICAL packages that cannot be imported.

    Looks in the standard process path, which InitGui.py already augments with
    the vendored .python-deps/ directory before this module is imported.
    """
    missing = []
    for pkg in CRITICAL:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    return missing


def _find_python():
    """Find the Python interpreter bundled with FreeCAD."""
    candidates = [
        r"C:\Program Files\FreeCAD 1.1\bin\python.exe",
        r"C:\Program Files\FreeCAD 1.0\bin\python.exe",
        r"C:\Program Files\FreeCAD 0.21\bin\python.exe",
        "/snap/freecad/current/usr/bin/python3",
        "/app/bin/python3",
        "/usr/lib/freecad/bin/python3",
        "/Applications/FreeCAD.app/Contents/Resources/bin/python3",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return sys.executable


def _run_pip(python_exe):
    """pip install requirements.txt into .python-deps. Returns (ok, output)."""
    cmd = [
        python_exe, "-m", "pip", "install",
        "--target", str(DEPS_DIR),
        "--upgrade",
        "-r", str(REQ_FILE),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except Exception as e:
        return False, str(e)
    ok = result.returncode == 0
    return ok, (result.stdout + result.stderr).strip()


def install_deps(verbose=True) -> tuple:
    """Install CRITICAL deps into .python-deps. Returns (ok, output)."""
    python_exe = _find_python()
    _log(f"Installing dependencies with {python_exe} ...")
    if not REQ_FILE.exists():
        _log("requirements.txt not found — skipping pip install")
        return False, "requirements.txt not found"
    ok, output = _run_pip(python_exe)
    if verbose or not ok:
        _log(output or ("dependencies installed" if ok else "pip install failed"))
    return ok, output


def _ask_user(missing: list) -> bool:
    """Prompt to install missing deps. Returns True if the user agreed."""
    try:
        from compat import QtWidgets
    except Exception:
        return False
    mw = None
    try:
        import FreeCADGui
        mw = FreeCADGui.getMainWindow()
    except Exception:
        pass
    box = QtWidgets.QMessageBox(mw)
    box.setIcon(QtWidgets.QMessageBox.Question)
    box.setWindowTitle("UCAD Assistant — Missing Dependencies")
    box.setText(
        "Required packages are not installed:\n\n"
        + ", ".join(missing)
        + "\n\nInstall them now? (pip install into the addon's "
        ".python-deps folder)"
    )
    install_btn = box.addButton("Install", QtWidgets.QMessageBox.AcceptRole)
    box.addButton("Skip", QtWidgets.QMessageBox.RejectRole)
    box.setDefaultButton(install_btn)
    box.exec_()
    return box.clickedButton() is install_btn


def ensure_deps(auto_install=True) -> bool:
    """Ensure critical deps are importable.

    Returns True if all CRITICAL packages are available (including after a
    successful install). When deps are missing, prompts the user once per
    process. If auto_install is False, never invokes pip.
    """
    global _prompt_shown
    missing = missing_packages()
    if not missing:
        return True

    with _prompt_lock:
        if _prompt_shown:
            return False
        _prompt_shown = True

    want = False
    if auto_install:
        try:
            want = _ask_user(missing)
        except Exception as e:
            _log(f"Dependency prompt failed: {e}")
    if not want:
        _log("Skipped dependency install; missing: " + ", ".join(missing))
        return False

    ok, output = install_deps()
    if not ok:
        return False

    # Refresh sys.path so the freshly installed packages are importable.
    deps = str(DEPS_DIR)
    if deps not in sys.path:
        sys.path.insert(0, deps)
    return not missing_packages()
