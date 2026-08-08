"""Build the UCAD Launcher executables using PyInstaller.

Usage:
    python launcher/build_launcher.py             # GUI + CLI
    python launcher/build_launcher.py --cli-only   # CLI only
    python launcher/build_launcher.py --gui-only   # GUI only

Requires PyInstaller:
    python -m pip install pyinstaller
"""
import os
import shutil
import subprocess
import sys
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "build" / "launcher"
DIST_DIR = ROOT / "dist"


def _run_pyinstaller(name, script, hidden_imports=None, console=True, icon=None):
    """Run PyInstaller and return success bool."""
    build_dir = BUILD_DIR / name
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name", name,
        "--onedir",
    ]

    if not console:
        cmd.append("--windowed")

    if icon and icon.exists():
        cmd.extend(["--icon", str(icon)])

    for hi in (hidden_imports or []):
        cmd.extend(["--hidden-import", hi])

    cmd.append(str(script))

    print(f"Building {name}...")
    result = subprocess.run(cmd, cwd=build_dir)
    if result.returncode != 0:
        print(f"  FAILED: {name}")
        return False

    # Copy output to dist
    built = build_dir / "dist" / name
    if built.exists():
        dest = DIST_DIR / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(built, dest)
        print(f"  Built: {dest}")
        return True
    print(f"  Output not found: {built}")
    return False


def build_cli():
    launcher_dir = ROOT / "launcher"
    cli_script = launcher_dir / "cli.py"
    icon = ROOT / "Resources" / "icons" / "ai_companion.ico"

    return _run_pyinstaller(
        "UCAD CLI",
        cli_script,
        hidden_imports=[
            "launcher.paths",
            "launcher.config_manager",
            "launcher.runtime_manager",
            "launcher.version",
            "launcher.diagnostics",
            # lazily imported inside runtime_manager.download_freecad()
            "py7zr",
        ],
        console=True,
        icon=icon,
    )


def build_gui():
    launcher_dir = ROOT / "launcher"
    gui_script = launcher_dir / "main_window.py"
    icon = ROOT / "Resources" / "icons" / "ai_companion.ico"

    return _run_pyinstaller(
        "UCAD Launcher",
        gui_script,
        hidden_imports=[
            "launcher.paths",
            "launcher.config_manager",
            "launcher.runtime_manager",
            "launcher.version",
            "launcher.diagnostics",
            # lazily imported inside runtime_manager.download_freecad()
            "py7zr",
        ],
        console=False,
        icon=icon,
    )


def main():
    parser = argparse.ArgumentParser(description="Build UCAD Launcher executables")
    parser.add_argument("--cli-only", action="store_true", help="Build CLI only")
    parser.add_argument("--gui-only", action="store_true", help="Build GUI only")
    args = parser.parse_args()

    # Ensure output dirs
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    ok = True

    if args.gui_only:
        ok = build_gui()
    elif args.cli_only:
        ok = build_cli()
    else:
        ok = build_cli()
        if ok:
            ok = build_gui()

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
