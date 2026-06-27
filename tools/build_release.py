"""Build a PyArmor-obfuscated release of the AICompanion FreeCAD addon.

Usage:
    & "C:\\Program Files\\FreeCAD 1.1\\bin\\python.exe" tools/build_release.py

Requires:
    - PyArmor installed: & "C:\Program Files\FreeCAD 1.1\bin\python.exe" -m pip install pyarmor
    - FreeCAD's Python 3.11 (PyArmor runtime must match FreeCAD's Python version)

Notes:
    Free tier may fail on extra-large files (>32KB code objects per function).
    Those files are shipped plain. For full protection, upgrade to Basic:
    https://jondy.github.io/paypal/index.html  ($52 one-time)
    After purchasing: pyarmor reg <license-file> && re-run this script.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent
RELEASE = SOURCE.parent / "AICompanion_Release"
PYARMOR = None

PLAIN_FILES = [
    "InitGui.py",
    "package.xml",
    "config.json",
    "secret_store.py",
    "compat.py",
]

PLAIN_DIRS = [
    "Resources",
    "examples",
    "tests",
]

IP_MODULES = [
    "orchestrator/",
    "AICompanionGui.py",
    "sidebar_widget.py",
    "chat_panel.py",
    "settings_dialog.py",
    "code_history_widget.py",
    "dxf_mode.py",
    "local_dxf.py",
    "enclosure_builder.py",
    "enclosure_template.py",
    "enclosure_templates.py",
    "enclosure_templates_v2.py",
    "pcb_parser.py",
    "pcb_mode.py",
    "sandbox_runner.py",
    "knowledge_base.py",
    "geometry_contract.py",
    "sketch_compiler.py",
    "companion_app.py",
    "companion_context.py",
    "context_injector.py",
    "drawing_generator.py",
    "assembly_graph.py",
    "failure_collector.py",
    "task_step.py",
    "hammond_enclosures.py",
    "ai_setup_dialog.py",
]


def _find_pyarmor():
    candidates = [
        Path(os.environ.get("APPDATA", "")) / "Python" / "Python311" / "Scripts" / "pyarmor.exe",
        Path(sys.prefix) / "Scripts" / "pyarmor.exe",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return shutil.which("pyarmor")


def _obfuscate_item(path: Path, out_dir: Path) -> bool:
    rel = path.relative_to(SOURCE)
    print(f"  Obfuscating {rel} ...", end=" ")
    sys.stdout.flush()
    result = subprocess.run(
        [PYARMOR, "gen", "--output", str(out_dir), str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode == 0:
        print("OK")
        return True
    for line in result.stderr.splitlines():
        if "ERROR" in line or "Error" in line:
            print(f"FAILED ({line.strip()})")
            return False
    print("FAILED")
    return False


def _copy_obfuscated(src: Path, obf_dir: Path, out: Path):
    """Copy obfuscated file to correct location.
    
    PyArmor strips directory paths — it outputs {tmp}/errors.py
    even for orchestrator/errors.py. We place it back correctly.
    """
    rel = src.relative_to(SOURCE)
    dst = out / rel
    dst.parent.mkdir(parents=True, exist_ok=True)

    obf_src = obf_dir / src.name
    if obf_src.exists() and obf_src.is_file():
        shutil.copy2(obf_src, dst)
        return

    # Fallback: try obf_dir / rel for cases where PyArmor preserves the path
    obf_src2 = obf_dir / rel
    if obf_src2.exists():
        shutil.copy2(obf_src2, dst)


def _copy_plain(src: Path, out: Path):
    rel = src.relative_to(SOURCE)
    dst = out / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def _copy_runtime(obf_dir: Path):
    runtime_dirs = list(obf_dir.glob("pyarmor_runtime_*"))
    for rd in runtime_dirs:
        dst = RELEASE / rd.name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(rd, dst)
        print(f"  Copied runtime: {rd.name}/")


def main():
    global PYARMOR
    PYARMOR = _find_pyarmor()
    if not PYARMOR:
        print("ERROR: PyArmor not found. Install with:")
        print('  & "C:\\Program Files\\FreeCAD 1.1\\bin\\python.exe" -m pip install pyarmor')
        sys.exit(1)

    py_ver = subprocess.run([PYARMOR, "--version"], capture_output=True, text=True, timeout=10)
    print(py_ver.stdout.strip())

    if RELEASE.exists():
        shutil.rmtree(RELEASE)
    RELEASE.mkdir(parents=True)

    obf_ok = []
    obf_fail = []

    with tempfile.TemporaryDirectory(prefix="pyarmor_build_") as tmp:
        obf_dir = Path(tmp)

        for mod in IP_MODULES:
            src = SOURCE / mod
            if not src.exists():
                continue

            if src.is_dir():
                dir_ok = []
                dir_fail = []
                for py_file in sorted(src.rglob("*.py")):
                    if _obfuscate_item(py_file, obf_dir):
                        _copy_obfuscated(py_file, obf_dir, RELEASE)
                        dir_ok.append(str(py_file.relative_to(SOURCE)))
                    else:
                        _copy_plain(py_file, RELEASE)
                        dir_fail.append(str(py_file.relative_to(SOURCE)))
                obf_ok.extend(dir_ok)
                obf_fail.extend(dir_fail)
            else:
                if _obfuscate_item(src, obf_dir):
                    _copy_obfuscated(src, obf_dir, RELEASE)
                    obf_ok.append(mod)
                else:
                    _copy_plain(src, RELEASE)
                    obf_fail.append(mod)

        _copy_runtime(obf_dir)

    _copy_plain_files()
    _copy_python_deps()

    print(f"\n{'='*50}")
    print(f"Obfuscated OK:   {len(obf_ok)} modules")
    for m in obf_ok:
        print(f"   [OK] {m}")
    if obf_fail:
        print(f"\nShipped plain:   {len(obf_fail)} modules (too large for PyArmor free tier)")
        for m in obf_fail:
            print(f"  [PLAIN] {m}")
        print("\nTo obfuscate these, buy PyArmor Basic:")
        print("  https://jondy.github.io/paypal/index.html")

    print(f"\nRelease directory: {RELEASE}")
    print(f"Total files: {len(list(RELEASE.rglob('*')))}")
    print("\nTo deploy:")
    print(f'  xcopy "{RELEASE}" "%APPDATA%\\FreeCAD\\v1-1\\Mod\\AICompanion\\" /E /I /Y')


def _copy_plain_files():
    for fname in PLAIN_FILES:
        src = SOURCE / fname
        if src.exists():
            shutil.copy2(src, RELEASE / fname)

    for dname in PLAIN_DIRS:
        src = SOURCE / dname
        if src.exists():
            dst = RELEASE / dname
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)


def _copy_python_deps():
    """Copy .python-deps/ into release, excluding test/dev artifacts."""
    deps_src = SOURCE / ".python-deps"
    deps_dst = RELEASE / ".python-deps"

    if not deps_src.exists():
        print("WARNING: .python-deps/ not found — run tools/update_deps.py first")
        return

    EXCLUDE_PATTERNS = {
        "__pycache__", "*.dist-info", "*.pyi",
        "test", "tests", "testing",
        "*.egg-info",
    }

    def should_exclude(path: Path) -> bool:
        for pat in EXCLUDE_PATTERNS:
            if path.match(pat):
                return True
        return False

    if deps_dst.exists():
        shutil.rmtree(deps_dst)
    deps_dst.mkdir(parents=True)

    total_size = 0
    file_count = 0
    for item in sorted(deps_src.rglob("*")):
        if should_exclude(item):
            continue
        rel = item.relative_to(deps_src)
        dst = deps_dst / rel
        if item.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dst)
            total_size += item.stat().st_size
            file_count += 1

    print(f"Copied .python-deps/: {file_count} files, {total_size/1e6:.1f} MB")


if __name__ == "__main__":
    main()
