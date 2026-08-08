"""Command-line interface for UCAD Assistant.

Provides the same functionality as the GUI launcher (detect, validate,
configure, launch) but from the terminal. Useful for:
  - Testing the launcher without a GUI
  - Server/headless environments
  - Debugging

Usage:
  python -m launcher.cli detect         # Find FreeCAD
  python -m launcher.cli validate       # Check system health
  python -m launcher.cli diagnose       # Full diagnostics
  python -m launcher.cli config         # Show current config
  python -m launcher.cli launch         # Launch FreeCAD with UCAD
  python -m launcher.cli setup          # Interactive setup wizard
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Ensure launcher package is importable (critical for PyInstaller frozen builds)
_LAUNCHER_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_LAUNCHER_DIR)
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

import launcher.paths as paths
from launcher.config_manager import load_config, save_config, get_secret, set_secret, load_secrets  # noqa: E402
from launcher.runtime_manager import RuntimeManager  # noqa: E402
from launcher.version import version_summary  # noqa: E402


def cmd_detect(args):
    rm = RuntimeManager()
    exe = rm.find_freecad()
    if exe:
        print(f"FreeCAD: {exe}")
        print(f"Version: {rm.version_str}")
        return 0
    print("FreeCAD: NOT FOUND")
    return 1


def cmd_validate(args):
    rm = RuntimeManager()
    rm.find_freecad()
    issues = rm.validate()
    if issues:
        print("Issues found:")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("All checks passed.")
    return 0


def cmd_diagnose(args):
    try:
        from launcher.diagnostics import run_diagnostics  # noqa: E402
    except ImportError:
        print("Diagnostics module not available (try: pip install requests)")
        return 1

    print("Running diagnostics...")
    report = run_diagnostics()
    print(report.to_text())
    return 0 if report.all_pass else 1


def cmd_config(args):
    cfg = load_config()
    secrets = load_secrets()

    print("--- UCAD Configuration ---")
    print(json.dumps(cfg, indent=2))

    has_key = bool(secrets.get("api_key"))
    print(f"\nAPI Key: {'SET' if has_key else 'NOT SET'}")
    return 0


def cmd_launch(args):
    rm = RuntimeManager()
    exe = rm.find_freecad()
    if not exe:
        print("FreeCAD not found. Use 'detect' to search or 'download' to install.")
        return 1

    print(f"FreeCAD: {exe} (v{rm.version_str})")

    issues = rm.validate()
    if issues:
        print("Warnings:")
        for i in issues:
            print(f"  - {i}")
        if not args.force:
            print("Use --force to launch anyway.")
            return 1

    proc = rm.launch()
    if proc:
        print(f"FreeCAD launched (PID: {proc.pid})")
        proc.wait()
        return 0
    print("Launch failed.")
    return 1


def cmd_download(args):
    rm = RuntimeManager()

    def on_progress(frac):
        bar = "=" * int(frac * 40) + " " * (40 - int(frac * 40))
        sys.stdout.write(f"\r[{bar}] {int(frac * 100)}%")
        sys.stdout.flush()

    print(f"Downloading FreeCAD to {paths.FREECAD}...")
    exe = rm.download_freecad(on_progress=on_progress)
    print()
    if exe:
        print(f"Done: {exe}")
        return 0
    print("Download failed.")
    return 1


def cmd_setup(args):
    """Interactive setup wizard."""
    print("\n=== UCAD Assistant Setup ===\n")
    paths.ensure_dirs()

    cfg = load_config()

    # Provider
    print("Supported providers: anthropic, deepseek, openai, google, ollama")
    provider = input(f"AI Provider [{cfg.get('provider', 'deepseek')}]: ").strip()
    if not provider:
        provider = cfg.get("provider", "deepseek")

    # API Key
    if provider != "ollama":
        existing = get_secret("api_key") or ""
        hint = existing[:8] + "..." if existing else ""
        key = input(f"API Key [{hint}]: ").strip()
        if key:
            set_secret("api_key", key)
        elif not existing:
            print("Warning: No API key provided!")
    else:
        url = input(f"Ollama URL [{cfg.get('ollama_url', 'http://localhost:11434')}]: ").strip()
        if url:
            cfg["ollama_url"] = url

    # Save
    cfg["provider"] = provider
    save_config(cfg)

    print("\nConfig saved to:", paths.CONFIG_FILE)
    print("Secrets saved to:", paths.SECRETS_FILE)

    # Detect FreeCAD
    rm = RuntimeManager()
    exe = rm.find_freecad()
    if exe:
        print(f"\nFreeCAD detected: {exe} (v{rm.version_str})")
    else:
        dl = input("\nFreeCAD not found. Download it? [Y/n]: ").strip().lower()
        if dl != "n":
            cmd_download(args)

    print("\nSetup complete! Run 'launch' to start UCAD Assistant.\n")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="UCAD Assistant - AI-powered CAD design for FreeCAD",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    def add_sub(name, help_text):
        p = sub.add_parser(name, help=help_text)
        if name == "launch":
            p.add_argument("--force", "-f", action="store_true",
                          help="Skip validation warnings")
        return p

    add_sub("detect", "Detect FreeCAD installation")
    add_sub("validate", "Validate system readiness")
    add_sub("diagnose", "Run full diagnostics")
    add_sub("config", "Show current configuration")
    add_sub("launch", "Launch FreeCAD with UCAD")
    add_sub("download", "Download FreeCAD portable")
    add_sub("setup", "Interactive setup wizard")
    add_sub("version", "Show version info")

    args = parser.parse_args()

    commands = {
        "detect": cmd_detect,
        "validate": cmd_validate,
        "diagnose": cmd_diagnose,
        "config": cmd_config,
        "launch": cmd_launch,
        "download": cmd_download,
        "setup": cmd_setup,
        "version": lambda _: print(version_summary()) or 0,
    }

    paths.ensure_dirs()

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
