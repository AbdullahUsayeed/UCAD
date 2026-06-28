"""
pcb_vision_deps.py
------------------
Check what's available for the PCB vision pipeline (KiCad CLI + API key + model).
Follows the same pattern as local_dxf.py for dependency checking.
"""

import enum
import os
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Known installation paths for kicad-cli.exe on Windows
# ---------------------------------------------------------------------------
_KICAD_CLI_CANDIDATES = [
    r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
    r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe",
    r"C:\Program Files\KiCad\7.0\bin\kicad-cli.exe",
    r"C:\Program Files (x86)\KiCad\9.0\bin\kicad-cli.exe",
    r"C:\Program Files (x86)\KiCad\8.0\bin\kicad-cli.exe",
    r"C:\Program Files (x86)\KiCad\7.0\bin\kicad-cli.exe",
]


# ---------------------------------------------------------------------------
# Models that support vision/image inputs
# ---------------------------------------------------------------------------
VISION_CAPABLE_MODELS = {
    # Anthropic
    "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6",
    "claude-sonnet-4-6", "claude-haiku-4-5",
    # OpenAI
    "gpt-4o", "gpt-4o-mini", "gpt-4-turbo",
    # Google
    "gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash",
    # DeepSeek (vision model specifically)
    "deepseek-chat", "deepseek-vl2",
}


class VisionDeps(enum.Enum):
    OK              = "all_available"
    NO_KICAD_CLI    = "missing_kicad_cli"
    NO_API_KEY      = "missing_api_key"
    NO_BOTH         = "missing_both"
    NO_VISION_MODEL = "model_lacks_vision"


def model_supports_vision(model_name: str) -> bool:
    """Check if the selected model can process images."""
    if not model_name:
        return False
    model_lower = model_name.lower()
    return any(m in model_lower for m in VISION_CAPABLE_MODELS)


def _find_kicad_cli() -> str | None:
    """
    Return the path to kicad-cli.exe, or None if not found.

    Search order:
      1. ``KICAD_CLI`` environment variable (user override)
      2. Hard-coded candidate paths (newest version first)
      3. PATH via ``where kicad-cli`` (works if KiCad bin is on PATH)
    """
    env_path = os.environ.get("KICAD_CLI", "").strip()
    if env_path and Path(env_path).is_file():
        return env_path

    for candidate in _KICAD_CLI_CANDIDATES:
        if Path(candidate).is_file():
            return candidate

    try:
        result = subprocess.run(
            ["where", "kicad-cli"],
            capture_output=True, text=True, timeout=5
        )
        first_line = result.stdout.strip().splitlines()[0]
        if first_line and Path(first_line).is_file():
            return first_line
    except Exception:
        pass

    return None


def get_vision_deps_status(api_key: str = "", model: str = "") -> VisionDeps:
    has_cli = _find_kicad_cli() is not None
    has_key = bool(api_key or os.environ.get("DEEPSEEK_API_KEY", "").strip())
    model_configured = bool(model)
    has_model = model_supports_vision(model) if model_configured else True

    if not has_cli and not has_key:
        return VisionDeps.NO_BOTH
    if not has_cli:
        return VisionDeps.NO_KICAD_CLI
    if not has_key:
        return VisionDeps.NO_API_KEY
    if model_configured and not has_model:
        return VisionDeps.NO_VISION_MODEL
    return VisionDeps.OK


_VISION_DEPS_MESSAGES = {
    VisionDeps.NO_KICAD_CLI: (
        "\u26a0\ufe0f KiCad CLI not found \u2014 vision analysis skipped.<br>"
        "To enable: <b>Download KiCad from <a href='https://www.kicad.org'>kicad.org</a></b> "
        "(kicad-cli.exe ships with it).<br>"
        "Or set the <code>KICAD_CLI</code> environment variable to its path.<br>"
        "<i>Enclosure will still generate \u2014 connector cutouts use heuristics instead.</i>"
    ),
    VisionDeps.NO_API_KEY: (
        "\u26a0\ufe0f DeepSeek API key not set \u2014 vision analysis skipped.<br>"
        "To enable: get a key at <b>platform.deepseek.com</b> and either:<br>"
        "- Set <code>DEEPSEEK_API_KEY</code> environment variable, or<br>"
        "- Enter it in Settings \u2192 Vision API Key<br>"
        "<i>Enclosure will still generate \u2014 connector cutouts use heuristics instead.</i>"
    ),
    VisionDeps.NO_BOTH: (
        "\u26a0\ufe0f Vision analysis unavailable (KiCad CLI + DeepSeek key both missing).<br>"
        "Enclosure will generate using PCB parser data only.<br>"
        "See README for vision setup instructions."
    ),
    VisionDeps.NO_VISION_MODEL: (
        "\u26a0\ufe0f Current model does not support vision \u2014 visual PCB analysis skipped.<br>"
        "To enable: switch to a vision-capable model in Settings:<br>"
        "- <b>Claude</b>: claude-opus-4-8, claude-sonnet-4-6<br>"
        "- <b>OpenAI</b>: gpt-4o, gpt-4o-mini<br>"
        "- <b>Google</b>: gemini-1.5-pro, gemini-2.0-flash<br>"
        "- <b>DeepSeek</b>: deepseek-vl2<br>"
        "<i>Enclosure will still generate \u2014 connector cutouts use heuristics instead.</i>"
    ),
    VisionDeps.OK: "",
}


def get_vision_deps_message(status: VisionDeps) -> str:
    """Return a human-readable HTML message about dependency status."""
    return _VISION_DEPS_MESSAGES.get(status, "Unknown vision dependency status")



