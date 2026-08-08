"""stage_mod.py — Copy the addon's plain open-source source into build/mod_stage/.

Used by the Inno Setup installer (installer/build_installer.bat) to package the
Mod into the installer without obfuscation (project is LGPL open source).

Usage:
    python tools/stage_mod.py
"""

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
    "docker-compose.yml", "pytest.ini",
}
# File extensions that never ship.
EXCLUDE_EXT = {".pyc", ".cover", ".tmp", ".zip", ".db", ".db-shm", ".db-wal"}


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

    print(f"Staged {copied} files into {OUT}")
    print(f"Total size: {sum(f.stat().st_size for f in OUT.rglob('*') if f.is_file()) / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
