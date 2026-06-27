from __future__ import annotations

import hashlib
import json
import os
import socket
import ssl
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

# ── Cloudflare Worker endpoint (set this after deploying) ──────────
# Format: https://<your-worker>.<your-subdomain>.workers.dev
SERVER_URL = "https://ai-companion-licensing.usayeed10.workers.dev"
BUY_URL = SERVER_URL + "/checkout?plan=yearly"
CACHE_TTL_DAYS = 7

# ── key format ─────────────────────────────────────────────────────
KEY_PREFIX = "USYD"
KEY_SEGMENTS = 4     # USYD-XXXX-XXXX-XXXX
KEY_SEGMENT_LEN = 4

def _log(msg: str) -> None:
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog(f"[Licensing] {msg}\n")
    except Exception:
        pass


def generate_key() -> str:
    """Generate a license key in USYD-XXXX-XXXX-XXXX format."""
    import secrets
    segs = [secrets.token_hex(KEY_SEGMENT_LEN // 2).upper() for _ in range(KEY_SEGMENTS - 1)]
    return f"{KEY_PREFIX}-{'-'.join(segs)}"


def key_hash(key: str) -> str:
    """Deterministic hash used as the KV store key on the Worker."""
    return hashlib.sha256(key.strip().upper().encode()).hexdigest()


def get_machine_id() -> str:
    raw = f"{uuid.getnode()}:{socket.gethostname()}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def get_machine_name() -> str:
    return socket.gethostname()


class LicenseManager:
    def __init__(self, config_path: str | None = None):
        self._config_path = config_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "config.json"
        )
        self._cache: dict | None = None

    def _load_config(self) -> dict:
        try:
            with open(self._config_path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_config(self, data: dict) -> None:
        existing = self._load_config()
        existing.update(data)
        tmp = self._config_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(existing, f)
            os.replace(tmp, self._config_path)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise

    def get_license_key(self) -> str | None:
        cfg = self._load_config()
        encrypted = cfg.get("license_key_secure", "")
        if encrypted:
            from secret_store import unprotect_secret
            try:
                return unprotect_secret(encrypted, "license_key") or None
            except Exception:
                return None
        plain = cfg.get("license_key", "")
        return plain if plain else None

    def set_license_key(self, key: str) -> None:
        from secret_store import protect_secret, store_secret, load_json_file
        cfg = self._load_config()
        store_secret(cfg, "license_key", key)
        self._save_config(cfg)

    def _server_url(self, path: str) -> str:
        return f"{SERVER_URL}{path}"

    def validate(self, license_key: str | None = None) -> dict:
        key = license_key or self.get_license_key()
        if not key:
            return {"valid": False, "error": "no_key"}

        machine = get_machine_id()
        name = get_machine_name()
        url = self._server_url(f"/api/validate?key={key}&machine={machine}&name={name}")

        try:
            req = Request(url, method="GET", headers={"Accept": "application/json"})
            with urlopen(req, timeout=10, context=ssl.create_default_context()) as resp:
                result = json.loads(resp.read().decode())
        except URLError as e:
            _log(f"Validation network error: {e}")
            cached = self._read_cache()
            if cached and cached.get("valid"):
                return cached
            return {"valid": False, "error": "network_error", "detail": str(e)}
        except Exception as e:
            _log(f"Validation error: {e}")
            return {"valid": False, "error": "unknown", "detail": str(e)}

        if result.get("valid"):
            self._write_cache(result)
        else:
            self._clear_cache()

        return result

    def check(self) -> dict:
        cached = self._read_cache()
        if cached:
            now = time.time()
            cached_at = cached.get("cached_at", 0)
            if now - cached_at < CACHE_TTL_DAYS * 86400:
                if cached.get("valid"):
                    return cached

        key = self.get_license_key()
        if not key:
            return {"valid": False, "error": "no_key", "trial": True}

        return self.validate(key)

    def deactivate(self) -> dict:
        key = self.get_license_key()
        if not key:
            return {"ok": False, "error": "no_key"}

        machine = get_machine_id()
        url = self._server_url("/api/deactivate")

        try:
            import json as _json
            body = _json.dumps({"key": key, "machine": machine}).encode()
            req = Request(url, data=body, method="POST", headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            })
            with urlopen(req, timeout=10, context=ssl.create_default_context()) as resp:
                result = _json.loads(resp.read().decode())
        except Exception as e:
            _log(f"Deactivation error: {e}")
            return {"ok": False, "error": str(e)}

        if result.get("ok"):
            self._clear_cache()

        return result

    def _read_cache(self) -> dict | None:
        cfg = self._load_config()
        raw = cfg.get("license_cache")
        if isinstance(raw, dict):
            return raw
        return None

    def _write_cache(self, data: dict) -> None:
        cache = {
            "valid": data.get("valid", False),
            "activation_count": data.get("activation_count", 0),
            "max_activations": data.get("max_activations", 3),
            "expires_at": data.get("expires_at", ""),
            "cached_at": time.time(),
        }
        self._save_config({"license_cache": cache})
        self._cache = cache

    def _clear_cache(self) -> None:
        cfg = self._load_config()
        cfg.pop("license_cache", None)
        self._save_config(cfg)
        self._cache = None
