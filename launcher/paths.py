r"""Centralized path management for the UCAD Assistant application.

All directory/file paths are derived from UCAD_BASE which defaults to
%LOCALAPPDATA%\UCAD Assistant and can be overridden via UCAD_HOME.
"""
import os
from pathlib import Path


def _ucad_base() -> Path:
    override = os.environ.get("UCAD_HOME")
    if override:
        return Path(override).resolve()
    return Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "UCAD Assistant"


# ── Root ───────────────────────────────────────────────────
BASE = _ucad_base()

# ── Launcher (self) ────────────────────────────────────────
LAUNCHER = BASE / "Launcher"

# ── Runtime (FreeCAD + Mod) ────────────────────────────────
RUNTIME   = BASE / "Runtime"
FREECAD   = RUNTIME / "FreeCAD"       # portable FreeCAD installation
MOD       = RUNTIME / "AICompanion"   # the Mod, loaded via -M flag

# ── Config / Secrets ───────────────────────────────────────
CONFIG   = BASE / "Config"
SECRETS  = BASE / "Secrets"
LOGS     = BASE / "Logs"
CACHE    = BASE / "Cache"
UPDATES  = BASE / "Updates"
RUNTIME_DATA = BASE / "RuntimeData"

# ── Specific files ─────────────────────────────────────────
CONFIG_FILE     = CONFIG / "config.json"
SECRETS_FILE    = SECRETS / "secret.bin"
USER_CFG        = RUNTIME_DATA / "user.cfg"
STARTUP_SCRIPT  = RUNTIME_DATA / "startup.py"

# ── Log files ──────────────────────────────────────────────
LAUNCHER_LOG = LOGS / "launcher.log"
LITELLM_LOG  = LOGS / "litellm.log"


def ensure_dirs():
    """Create all required directories if they don't exist."""
    for d in [LAUNCHER, RUNTIME, CONFIG, SECRETS, LOGS, CACHE, UPDATES,
              RUNTIME_DATA, FREECAD, MOD]:
        d.mkdir(parents=True, exist_ok=True)
