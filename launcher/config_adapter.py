"""Config adapter — bridges the launcher's centralized config into the Mod.

The Mod reads config from two places:
1. If UCAD_HOME env var is set: reads from <UCAD_HOME>/Config/config.json + Secrets/secret.bin
2. Otherwise: reads from the legacy Mod-relative config.json (backward compat)
"""
import json
import os
from pathlib import Path
from typing import Any, Optional


def get_ucad_base() -> Optional[Path]:
    """Return UCAD base directory if launched by the launcher."""
    home = os.environ.get("UCAD_HOME")
    if home:
        return Path(home).resolve()
    return None


def load_launcher_config() -> dict[str, Any]:
    """Load config from launcher's centralized location."""
    base = get_ucad_base()
    if not base:
        return {}

    config_file = base / "Config" / "config.json"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def load_launcher_secrets() -> dict[str, str]:
    """Load secrets from launcher's encrypted secret store."""
    base = get_ucad_base()
    if not base:
        return {}

    secret_file = base / "Secrets" / "secret.bin"
    if not secret_file.exists():
        return {}

    try:
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        import base64, hashlib, socket, uuid

        def _machine_key() -> bytes:
            raw = f"{uuid.getnode()}:{socket.gethostname()}".encode()
            return hashlib.sha256(raw).digest()

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32,
            salt=b"UCAD_Secret_v2", iterations=200_000,
        )
        fernet = Fernet(base64.urlsafe_b64encode(kdf.derive(_machine_key())))
        raw = fernet.decrypt(secret_file.read_bytes())
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def get_api_key() -> Optional[str]:
    """Get API key from launcher config (preferred) or legacy config."""
    secrets = load_launcher_secrets()
    if secrets.get("api_key"):
        return secrets["api_key"]

    # Fallback: legacy Mod-relative config.json
    try:
        mod_dir = os.path.dirname(os.path.abspath(__file__))
        legacy = os.path.join(mod_dir, "config.json")
        if os.path.exists(legacy):
            from secret_store import read_secret, load_json_file
            cfg = load_json_file(legacy)
            return read_secret(cfg, "api_key")
    except Exception:
        pass
    return None


def merge_configs(mod_config: dict[str, Any]) -> dict[str, Any]:
    """Merge launcher config into Mod config. Launcher values take priority."""
    launcher_cfg = load_launcher_config()
    if not launcher_cfg:
        return mod_config

    merged = dict(mod_config)
    # Launcher config overrides Mod config for these keys
    override_keys = [
        "provider", "model", "url", "provider_label", "model_label",
        "mode", "theme", "chat_font_size", "code_font_size",
        "temperature", "max_tokens", "max_history_length",
        "retries_per_step", "auto_replan", "sandbox_mode",
        "max_defer_attempts", "ollama_url", "ollama_model", "proxy_url",
    ]
    for key in override_keys:
        if key in launcher_cfg:
            merged[key] = launcher_cfg[key]

    # Inject API key from secrets
    api_key = get_api_key()
    if api_key:
        merged["api_key"] = api_key

    return merged
