"""Unified configuration manager.

One config.json (non-secret) + one secret.bin (encrypted).
Both launcher and Mod read from the same files — no sync needed.
"""
import json
import os
from typing import Any, Optional
from .paths import CONFIG_FILE, SECRETS_FILE


# ── Defaults ───────────────────────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    "provider": "deepseek",
    "model": "deepseek/deepseek-chat",
    "url": "",
    "provider_label": "DeepSeek",
    "model_label": "[DeepSeek] DeepSeek Chat",
    "mode": "build",
    "theme": "dark",
    "chat_font_size": 13,
    "code_font_size": 12,
    "temperature": 0.49,
    "max_tokens": 16384,
    "max_history_length": 50,
    "retries_per_step": 5,
    "auto_replan": False,
    "sandbox_mode": True,
    "max_defer_attempts": 15,
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3",
    "proxy_url": "",
    "version": 1,
}

CONFIG_VERSION = 1


# ── Config IO ──────────────────────────────────────────────

def load_config() -> dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                merged = dict(DEFAULT_CONFIG)
                merged.update(data)
                return merged
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict[str, Any]) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    merged["version"] = CONFIG_VERSION
    # Strip secrets before writing config
    merged.pop("api_key", None)
    atomic_write(CONFIG_FILE, merged)


def atomic_write(path, data: dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


# ── Secrets ────────────────────────────────────────────────

SECRET_KEYS = {"api_key"}


def load_secrets() -> dict[str, str]:
    """Load encrypted secrets from secret.bin."""
    if not SECRETS_FILE.exists():
        return {}
    try:
        raw = _decrypt(SECRETS_FILE.read_bytes())
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def save_secrets(secrets: dict[str, str]) -> None:
    """Encrypt and write secrets to secret.bin."""
    SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({k: v for k, v in secrets.items() if v}).encode()
    SECRETS_FILE.write_bytes(_encrypt(payload))


def get_secret(key: str) -> Optional[str]:
    return load_secrets().get(key)


def set_secret(key: str, value: str) -> None:
    secrets = load_secrets()
    secrets[key] = value
    save_secrets(secrets)


def delete_secret(key: str) -> None:
    secrets = load_secrets()
    secrets.pop(key, None)
    save_secrets(secrets)


# ── Encryption ─────────────────────────────────────────────

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    import base64, hashlib, socket, uuid

    def _machine_key() -> bytes:
        raw = f"{uuid.getnode()}:{socket.gethostname()}".encode()
        return hashlib.sha256(raw).digest()

    def _fernet() -> "Fernet":
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"UCAD_Secret_v2",
            iterations=200_000,
        )
        return Fernet(base64.urlsafe_b64encode(kdf.derive(_machine_key())))

    def _encrypt(data: bytes) -> bytes:
        return _fernet().encrypt(data)

    def _decrypt(data: bytes) -> bytes:
        return _fernet().decrypt(data)

except ImportError:
    # Fallback: simple XOR obfuscation (NOT cryptographically secure)
    def _machine_key() -> bytes:
        import hashlib, socket, uuid
        raw = f"{uuid.getnode()}:{socket.gethostname()}".encode()
        return hashlib.sha256(raw).digest()

    def _encrypt(data: bytes) -> bytes:
        key = _machine_key()
        return bytes([b ^ key[i % len(key)] for i, b in enumerate(data)])

    def _decrypt(data: bytes) -> bytes:
        key = _machine_key()
        return bytes([b ^ key[i % len(key)] for i, b in enumerate(data)])
