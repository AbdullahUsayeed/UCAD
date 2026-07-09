"""Component update system — checks each component independently.

Update strategy:
  - Launcher: downloads new launcher.exe, swaps on next launch
  - Plugin: downloads new Mod files into Runtime/AICompanion/
  - Runtime: downloads updated FreeCAD portable

Each component has its own version tracked in version.py.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from .paths import BASE, LAUNCHER, MOD, UPDATES
from .version import (
    LAUNCHER_VERSION, PLUGIN_VERSION, RUNTIME_VERSION,
    ALL_COMPONENTS, version_summary,
)

GITHUB_API = "https://api.github.com/repos/AbdullahUsayeed/UCAD/releases/latest"


def check_for_updates() -> dict[str, Optional[str]]:
    """Check GitHub for newer versions of each component.
    
    Returns dict of component_name -> download_url or None if up-to-date.
    """
    result = {}
    try:
        import requests
        resp = requests.get(GITHUB_API, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        # Parse release assets to find per-component updates
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            download_url = asset.get("browser_download_url", "")

            if name.startswith("launcher-"):
                version = name.replace("launcher-", "").replace(".exe", "")
                if _compare_versions(version, LAUNCHER_VERSION.version) > 0:
                    result["launcher"] = download_url

            elif name.startswith("plugin-"):
                version = name.replace("plugin-", "").replace(".zip", "")
                if _compare_versions(version, PLUGIN_VERSION.version) > 0:
                    result["plugin"] = download_url

            elif name.startswith("freecad-"):
                version = name.replace("freecad-", "").replace(".7z", "")
                if _compare_versions(version, RUNTIME_VERSION.version) > 0:
                    result["runtime"] = download_url
    except Exception:
        pass

    return result


def _compare_versions(v1: str, v2: str) -> int:
    """Compare two semver strings. Returns -1/0/1."""
    try:
        parts1 = [int(x) for x in v1.split(".")]
        parts2 = [int(x) for x in v2.split(".")]
        for a, b in zip(parts1, parts2):
            if a < b: return -1
            if a > b: return 1
        return len(parts1) - len(parts2)
    except (ValueError, IndexError):
        return 0


def update_launcher(download_url: str) -> bool:
    """Download new launcher.exe, stage for swap on next launch."""
    try:
        import requests
        resp = requests.get(download_url, stream=True, timeout=30)
        resp.raise_for_status()

        UPDATES.mkdir(parents=True, exist_ok=True)
        update_exe = UPDATES / "UCAD Launcher.new.exe"

        with open(update_exe, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        return True
    except Exception as e:
        print(f"Update failed: {e}")
        return False


def apply_pending_update():
    """Apply staged launcher update on startup."""
    pending = UPDATES / "UCAD Launcher.new.exe"
    if not pending.exists():
        return False

    current = LAUNCHER / "UCAD Launcher.exe"
    backup = LAUNCHER / "UCAD Launcher.bak.exe"

    try:
        # Backup current
        if current.exists():
            shutil.copy2(current, backup)

        # Swap
        shutil.move(str(pending), str(current))
        pending.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def get_current_version() -> str:
    """Return the current version string for display."""
    return f"Launcher v{LAUNCHER_VERSION.version}, Plugin v{PLUGIN_VERSION.version}"
