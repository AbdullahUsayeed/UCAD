#!/usr/bin/env python3
"""
Regenerate .python-deps/ for the current platform.
Run this before every release from the repo root:
    python tools/update_deps.py

Requires: pip, FreeCAD's Python (or any Python 3.11 win_amd64 for Windows builds)
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

REPO_ROOT   = Path(__file__).resolve().parents[1]
DEPS_DIR    = REPO_ROOT / ".python-deps"
REQ_FILE    = REPO_ROOT / "requirements.txt"
FREECAD_PY  = os.environ.get(
    "FREECAD_PYTHON",
    r"C:\Program Files\FreeCAD 1.1\bin\python.exe"
)


def run(cmd, **kwargs):
    print(f"$ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, check=True, **kwargs)
    return result


def clean_unnecessary(deps_dir: Path):
    """Remove .dist-info, __pycache__, *.pyi to minimize size."""
    removed = 0
    for pattern in ["*.dist-info", "__pycache__", "*.pyi"]:
        for path in deps_dir.rglob(pattern):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed += 1
    print(f"Cleaned {removed} unnecessary files/dirs")


def verify_imports(python_exe: str, deps_dir: Path):
    """Verify critical packages are importable using target Python."""
    packages = ["litellm", "ezdxf", "shapely"]
    failed = []
    for pkg in packages:
        result = subprocess.run(
            [python_exe, "-c",
             f"import sys; sys.path.insert(0, r'{deps_dir}'); import {pkg}; print('{pkg} OK')"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            failed.append(f"{pkg}: {result.stderr.strip()}")
        else:
            print(result.stdout.strip())
    if failed:
        print("\nFAILED imports:")
        for f in failed:
            print(f"  {f}")
        sys.exit(1)
    else:
        print("\nAll critical imports verified.")


def main():
    python_exe = FREECAD_PY if os.path.exists(FREECAD_PY) else sys.executable
    print(f"Using Python: {python_exe}")
    print(f"Target dir:   {DEPS_DIR}")
    print(f"Requirements: {REQ_FILE}")

    if not REQ_FILE.exists():
        print(f"ERROR: {REQ_FILE} not found")
        sys.exit(1)

    run([python_exe, "-m", "pip", "install",
         "--target", str(DEPS_DIR),
         "--upgrade",
         "-r", str(REQ_FILE)])

    clean_unnecessary(DEPS_DIR)
    verify_imports(python_exe, DEPS_DIR)

    total_size = sum(f.stat().st_size for f in DEPS_DIR.rglob('*') if f.is_file())
    print(f"\nDone. Size: {total_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
