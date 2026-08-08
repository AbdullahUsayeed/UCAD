"""stage_mod.py — Copy the addon's plain open-source source into build/mod_stage/.

Used by the Inno Setup installer (installer/build_installer.bat) to package the
Mod into the installer without obfuscation (project is LGPL open source).

Includes a stripped copy of .python-deps/ so the Mod works standalone inside a
normal FreeCAD (the addon's InitGui.py boots vendored deps from .python-deps).

Usage:
    python tools/stage_mod.py
"""

import os
import shutil
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent
OUT = SOURCE / "build" / "mod_stage"

# Directories that never ship with the addon.
EXCLUDE_DIRS = {
    "build", "dist", "__pycache__", ".git", ".github", ".pytest_cache",
    ".python-deps", "launcher", "installer", "tests", "examples",
    "server", "worker", "tools", "deploy", "Resources",
}
# Individual files that never ship.
EXCLUDE_FILES = {
    "config.json", "install.bat", "install.sh", "Dockerfile",
    "docker-compose.yml", "pytest.ini", ".gitignore", ".coverage",
    "install_log.txt", "install_test.log", "pyarmor.bug.log",
    # server-side / infra files belong in the repo, not the addon Mod
    "server.py", "database.py", "requirements-dev.txt",
}
# File extensions that never ship.
EXCLUDE_EXT = {".pyc", ".cover", ".tmp", ".zip", ".db", ".db-shm", ".db-wal"}


def _copy_stripped_deps(deps_src: Path, out_deps: Path):
    """Copy .python-deps with caches/tests/metadata stripped (runtime-only)."""
    skip_dirs = {"__pycache__", "tests", "test", "testing"}
    skip_suffixes = {".pyc", ".pyo", ".pyi", ".tmp"}
    copied = 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(deps_src):
        dirnames[:] = [
            d for d in dirnames
            if d not in skip_dirs
            and not d.endswith(".dist-info")
            and not d.endswith(".egg-info")
        ]
        for fname in filenames:
            if fname.endswith(tuple(skip_suffixes)):
                continue
            src = Path(dirpath) / fname
            rel = src.relative_to(deps_src)
            dst = out_deps / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
            total += src.stat().st_size
    print(f"  Copied .python-deps/: {copied} files, {total / 1e6:.1f} MB")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    copied = 0
    for item in sorted(SOURCE.rglob("*")):
        rel = item.relative_to(SOURCE)
        parts = rel.parts
        if any(p in EXCLUDE_DIRS for p in parts):
            continue
        if item.is_file() and (item.name in EXCLUDE_FILES or item.suffix in EXCLUDE_EXT):
            continue
        dst = OUT / rel
        if item.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dst)
            copied += 1

    # Vendored runtime deps so the Mod works standalone in FreeCAD
    deps_src = SOURCE / ".python-deps"
    if deps_src.exists():
        _copy_stripped_deps(deps_src, OUT / ".python-deps")

    print(f"Staged {copied} source files into {OUT}")
    print(f"Total size: {sum(f.stat().st_size for f in OUT.rglob('*') if f.is_file()) / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
