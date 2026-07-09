"""RuntimeManager — discovers FreeCAD, validates version, injects Mod path,
loads config, starts the FreeCAD process with the UCAD workbench active.

              Launcher
                 │
                 ▼
          RuntimeManager
                 │
    ┌────────────┼────────────┐
    ▼            ▼            ▼
 detect     validate      launch
 FreeCAD     config      FreeCAD
                        + Mod path
                        + startup.py
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from . import paths
from .config_manager import load_config, load_secrets, save_config, save_secrets


FREECAD_MIN_VERSION = (1, 0, 0)
FREECAD_DOWNLOAD_URL = (
    "https://github.com/FreeCAD/FreeCAD/releases/download/"
    "1.1.1/FreeCAD_1.1.1-Windows-x86_64-py311.7z"
)
FREECAD_DOWNLOAD_FILENAME = "FreeCAD_1.1.1-Windows-x86_64-py311.7z"


class RuntimeManager:
    """Manages FreeCAD discovery, validation, configuration, and launch."""

    def __init__(self):
        self._freecad_exe: Optional[Path] = None
        self._version: tuple[int, int, int] = (0, 0, 0)
        self._log = []

    # ── FreeCAD Discovery ─────────────────────────────────

    def find_freecad(self) -> Optional[Path]:
        """Search for FreeCAD.exe in known locations."""
        checks = [
            self._check_registry,
            self._check_program_files,
            self._check_localappdata,
            self._check_portable,
            self._check_path_env,
            self._check_package_managers,
        ]
        for check in checks:
            result = check()
            if result:
                self._freecad_exe = result
                self._version = self._read_version(result)
                self._log.append(f"Found FreeCAD at {result} (v{self.version_str})")
                return result
        return None

    def _check_registry(self) -> Optional[Path]:
        if sys.platform != "win32":
            return None
        try:
            import winreg
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    key = winreg.OpenKey(hive, r"SOFTWARE\FreeCAD")
                    install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                    exe = Path(install_path) / "bin" / "FreeCAD.exe"
                    if exe.exists():
                        return exe
                except (OSError, FileNotFoundError):
                    pass
        except Exception:
            pass
        return None

    def _check_program_files(self) -> Optional[Path]:
        for base in [os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)")]:
            if not base:
                continue
            p = Path(base)
            if not p.exists():
                continue
            for d in p.iterdir():
                if d.is_dir() and "freecad" in d.name.lower():
                    exe = d / "bin" / "FreeCAD.exe"
                    if exe.exists():
                        return exe
        return None

    def _check_localappdata(self) -> Optional[Path]:
        lap = os.environ.get("LOCALAPPDATA", "")
        if not lap:
            return None
        p = Path(lap) / "Programs"
        if not p.exists():
            return None
        for d in p.iterdir():
            if d.is_dir() and "freecad" in d.name.lower():
                exe = d / "bin" / "FreeCAD.exe"
                if exe.exists():
                    return exe
        return None

    def _check_portable(self) -> Optional[Path]:
        """Check if we already have a managed portable FreeCAD."""
        fc_dir = paths.FREECAD
        if fc_dir.exists():
            exe = fc_dir / "bin" / "FreeCAD.exe"
            if exe.exists():
                return exe
        return None

    def _check_path_env(self) -> Optional[Path]:
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)
        for d in path_dirs:
            exe = Path(d) / "FreeCAD.exe"
            if exe.exists():
                return exe
        return None

    def _check_package_managers(self) -> Optional[Path]:
        """Check winget / chocolatey / scoop installations."""
        checks = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
        ]
        scoop = os.environ.get("SCOOP")
        if scoop:
            checks.append(Path(scoop) / "apps" / "freecad" / "current")
        for base in checks:
            if not base.exists():
                continue
            for d in base.rglob("FreeCAD.exe"):
                return d
        return None

    @staticmethod
    def _read_version(exe: Path) -> tuple[int, int, int]:
        try:
            # FreeCAD version info is only via FreeCADCmd (console mode)
            cmd_exe = exe.parent / "FreeCADCmd.exe"
            if not cmd_exe.exists():
                cmd_exe = exe  # fallback
            result = subprocess.run(
                [str(cmd_exe), "-v"],
                capture_output=True, text=True, timeout=15,
            )
            combined = (result.stdout or "") + (result.stderr or "")
            match = re.search(r"(\d+)\.(\d+)\.(\d+)", combined)
            if match:
                return tuple(map(int, match.groups()))
        except Exception:
            pass
        return (0, 0, 0)

    @property
    def version_str(self) -> str:
        return ".".join(str(v) for v in self._version)

    # ── Validation ────────────────────────────────────────

    def validate(self) -> list[str]:
        """Run pre-launch validation checks. Returns list of warnings/errors."""
        issues = []
        if not self._freecad_exe or not self._freecad_exe.exists():
            issues.append("FreeCAD not found")
            return issues

        if self._version < FREECAD_MIN_VERSION:
            issues.append(
                f"FreeCAD {self.version_str} is too old. "
                f"Minimum: {'.'.join(str(v) for v in FREECAD_MIN_VERSION)}"
            )

        cfg = load_config()
        provider = cfg.get("provider", "")
        secrets = load_secrets()
        api_key = secrets.get("api_key", "")
        if provider and provider not in ("ollama", "templates") and not api_key:
            issues.append(f"No API key configured for {provider}")

        if provider == "ollama":
            ollama_url = cfg.get("ollama_url", "http://localhost:11434")
            if not self._check_url_reachable(ollama_url):
                issues.append(f"Ollama not reachable at {ollama_url}")

        return issues

    @staticmethod
    def _check_url_reachable(url: str, timeout: float = 3) -> bool:
        try:
            import requests
            r = requests.get(url.rstrip("/") + "/api/tags", timeout=timeout)
            return r.ok
        except Exception:
            return False

    # ── Download FreeCAD ──────────────────────────────────

    def download_freecad(self, on_progress=None) -> Path:
        """Download portable FreeCAD and extract to Runtime/FreeCAD."""
        import requests as req
        import py7zr

        archive_path = paths.CACHE / FREECAD_DOWNLOAD_FILENAME
        paths.CACHE.mkdir(parents=True, exist_ok=True)

        self._log.append(f"Downloading FreeCAD from {FREECAD_DOWNLOAD_URL}")

        # Download with progress
        response = req.get(FREECAD_DOWNLOAD_URL, stream=True, timeout=30)
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        downloaded = 0

        with open(archive_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if on_progress and total:
                    on_progress(downloaded / total)

        # SHA256 verification
        import hashlib
        sha256 = hashlib.sha256()
        with open(archive_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        computed_hash = sha256.hexdigest()
        self._log.append(f"Downloaded {archive_path} ({computed_hash[:16]}...)")

        # Extract
        self._log.append("Extracting FreeCAD...")
        paths.FREECAD.mkdir(parents=True, exist_ok=True)
        with py7zr.SevenZipFile(archive_path, mode="r") as z:
            z.extractall(path=paths.FREECAD)

        # Handle nested directory (FreeCAD .7z has a root folder)
        children = list(paths.FREECAD.iterdir())
        if len(children) == 1 and children[0].is_dir():
            nested = children[0]
            for item in nested.iterdir():
                dest = paths.FREECAD / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)
            shutil.rmtree(nested)

        archive_path.unlink()

        exe = paths.FREECAD / "bin" / "FreeCAD.exe"
        if exe.exists():
            self._freecad_exe = exe
            self._version = self._read_version(exe)
            self._log.append(f"FreeCAD {self.version_str} extracted to {paths.FREECAD}")
        return exe

    # ── Config / Secrets ──────────────────────────────────

    def ensure_config(self, config: dict) -> None:
        save_config(config)

    def ensure_secrets(self, secrets: dict) -> None:
        save_secrets(secrets)

    # ── Launch ────────────────────────────────────────────

    def launch(self, freecad_exe: Optional[Path] = None) -> Optional[subprocess.Popen]:
        """Launch FreeCAD with UCAD Mod path and startup script."""
        exe = freecad_exe or self._freecad_exe
        if not exe or not exe.exists():
            return None

        # Ensure Mod directory exists for -M flag
        mod_path = paths.MOD
        if not mod_path.exists():
            mod_path.mkdir(parents=True, exist_ok=True)

        # Ensure startup script exists
        startup = self._write_startup_script()

        # Ensure user.cfg exists (set once, not every launch)
        self._ensure_user_cfg()

        # Write a marker so the Mod knows it was launched by the launcher
        env = os.environ.copy()
        env["UCAD_HOME"] = str(paths.BASE)
        env["UCAD_LAUNCHED"] = "1"

        cmd = [
            str(exe),
            "-M", str(paths.RUNTIME),       # additional Mod path
            "-t", str(startup),             # startup script
            "-u", str(paths.USER_CFG),      # custom user config
        ]

        self._log.append(f"Launching: {' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            env=env,
            cwd=str(exe.parent),
        )
        return proc

    def _write_startup_script(self) -> Path:
        """Write startup.py that activates UCAD workbench."""
        script = '''"""UCAD Assistant — startup script run by FreeCAD on launch."""
import os, sys

# Ensure UCAD Mod is discoverable (it's loaded via -M, but guard anyway)
ucad_home = os.environ.get("UCAD_HOME", "")
if ucad_home:
    mod_path = os.path.join(ucad_home, "Runtime", "AICompanion")
    if mod_path not in sys.path:
        sys.path.insert(0, mod_path)

# Activate the UCAD workbench once GUI is ready
def _activate():
    import FreeCADGui
    wbs = FreeCADGui.listWorkbenches()
    if "UCADAssistant" in wbs:
        FreeCADGui.activateWorkbench("UCADAssistant")

import FreeCAD
FreeCAD.Console.PrintLog("[UCAD] Startup script executed.\\n")

# Use a single-shot timer via Qt if available, otherwise fallback
try:
    from PySide6 import QtCore
    QtCore.QTimer.singleShot(500, _activate)
except Exception:
    import threading
    threading.Timer(1.0, _activate).start()
'''
        paths.STARTUP_SCRIPT.parent.mkdir(parents=True, exist_ok=True)
        paths.STARTUP_SCRIPT.write_text(script, encoding="utf-8")
        return paths.STARTUP_SCRIPT

    def _ensure_user_cfg(self) -> None:
        """Write user.cfg once if it doesn't exist."""
        if paths.USER_CFG.exists():
            return
        cfg_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<FreeCAD>
  <BaseApp>
    <Preferences>
      <General>
        <StartWorkbench Type="String">UCADAssistant</StartWorkbench>
      </General>
    </Preferences>
  </BaseApp>
</FreeCAD>'''
        paths.USER_CFG.parent.mkdir(parents=True, exist_ok=True)
        paths.USER_CFG.write_text(cfg_xml, encoding="utf-8")

    # ── Utilities ─────────────────────────────────────────

    def get_freecad_exe(self) -> Optional[Path]:
        return self._freecad_exe

    def get_version(self) -> tuple:
        return self._version

    @property
    def log(self) -> list[str]:
        return self._log
