"""Cross-platform secret storage for AI Companion.

Windows  → CryptProtectData (DPAPI)
Linux    → keyring (libsecret) → fallback: encrypted file via cryptography.fernet
macOS    → keyring (macOS Keychain) → fallback: encrypted file via cryptography.fernet
"""

import base64
import hashlib
import json
import os
import socket
import sys
import tempfile
import uuid

HAS_KEYRING = False
try:
    import keyring
    import keyring.errors
    HAS_KEYRING = True
except ImportError:
    pass

HAS_CRYPTOGRAPHY = False
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTOGRAPHY = True
except ImportError:
    pass


SECRET_KEYS = ("api_key",)
_ENTROPY_PREFIX = "AICompanion"
_SERVICE_NAME = "freecad-ai-companion"


def _log_error(message):
    try:
        import FreeCAD
        FreeCAD.Console.PrintError(f"[AICompanion] {message}\n")
    except Exception:
        print(f"[AICompanion] {message}")


def _machine_secret():
    raw = f"{uuid.getnode()}:{socket.gethostname()}".encode()
    return hashlib.sha256(raw).digest()


def _fernet_key():
    if not HAS_CRYPTOGRAPHY:
        raise RuntimeError("cryptography package required for encrypted-file fallback")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"AICompanion_v1", iterations=200_000)
    return base64.urlsafe_b64encode(kdf.derive(_machine_secret()))


def _secrets_file_path():
    return os.path.join(os.path.dirname(__file__), ".secrets_encrypted")


# ── Windows DPAPI ────────────────────────────────────────────

def _can_use_dpapi():
    return sys.platform == "win32" and hasattr(sys, "getwindowsversion")


def _protect_windows(value, purpose):
    import ctypes
    from ctypes import wintypes
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    class _DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    def _make_blob(data):
        if not data:
            return _DataBlob(0, None), None
        buf = (ctypes.c_byte * len(data)).from_buffer_copy(data)
        return _DataBlob(len(data), buf), buf

    def _blob_to_bytes(blob):
        if not blob.cbData or not blob.pbData:
            return b""
        return ctypes.string_at(blob.pbData, blob.cbData)

    data_blob, data_buf = _make_blob(value.encode("utf-8"))
    entropy = f"{_ENTROPY_PREFIX}:{purpose}".encode("utf-8")
    entropy_blob, entropy_buf = _make_blob(entropy)
    out_blob = _DataBlob()

    if not crypt32.CryptProtectData(
        ctypes.byref(data_blob), "AICompanion",
        ctypes.byref(entropy_blob), None, None, 0x01,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()
    try:
        return base64.b64encode(_blob_to_bytes(out_blob)).decode("ascii")
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _unprotect_windows(value, purpose):
    import ctypes
    from ctypes import wintypes
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    class _DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    def _make_blob(data):
        if not data:
            return _DataBlob(0, None), None
        buf = (ctypes.c_byte * len(data)).from_buffer_copy(data)
        return _DataBlob(len(data), buf), buf

    def _blob_to_bytes(blob):
        if not blob.cbData or not blob.pbData:
            return b""
        return ctypes.string_at(blob.pbData, blob.cbData)

    encrypted = base64.b64decode(value.encode("ascii"))
    data_blob, data_buf = _make_blob(encrypted)
    entropy = f"{_ENTROPY_PREFIX}:{purpose}".encode("utf-8")
    entropy_blob, entropy_buf = _make_blob(entropy)
    out_blob = _DataBlob()

    if not crypt32.CryptUnprotectData(
        ctypes.byref(data_blob), None,
        ctypes.byref(entropy_blob), None, None, 0,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()
    try:
        return _blob_to_bytes(out_blob).decode("utf-8")
    finally:
        kernel32.LocalFree(out_blob.pbData)


# ── Keyring ──────────────────────────────────────────────────

def _can_use_keyring():
    return HAS_KEYRING


def _protect_keyring(value, purpose):
    username = os.environ.get("USER", os.environ.get("USERNAME", "default"))
    keyring.set_password(_SERVICE_NAME, f"{purpose}:{username}", value)
    return f"__keyring__:{purpose}:{username}"


def _unprotect_keyring(stored, purpose):
    prefix = f"__keyring__:{purpose}:"
    if not stored.startswith(prefix):
        return None
    username = stored[len(prefix):]
    return keyring.get_password(_SERVICE_NAME, f"{purpose}:{username}")


# ── Encrypted file (Fernet) ──────────────────────────────────

def _can_use_fernet():
    return HAS_CRYPTOGRAPHY


def _load_fernet_store():
    path = _secrets_file_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_fernet_store(store):
    path = _secrets_file_path()
    directory = os.path.dirname(path) or os.getcwd()
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="secrets_", suffix=".tmp", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(store, handle)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _protect_fernet(value, purpose):
    key = _fernet_key()
    cipher = Fernet(key)
    token = cipher.encrypt(value.encode("utf-8"))
    store = _load_fernet_store()
    store[purpose] = token.decode("ascii")
    _save_fernet_store(store)
    return f"__fernet__:{purpose}"


def _unprotect_fernet(stored, purpose):
    if stored != f"__fernet__:{purpose}":
        return None
    store = _load_fernet_store()
    token = store.get(purpose)
    if not token:
        return None
    key = _fernet_key()
    cipher = Fernet(key)
    return cipher.decrypt(token.encode("ascii")).decode("utf-8")


# ── Public API ───────────────────────────────────────────────

def protect_secret(value, purpose):
    if not value:
        return ""
    if _can_use_dpapi():
        return _protect_windows(value, purpose)
    if _can_use_keyring():
        return _protect_keyring(value, purpose)
    if _can_use_fernet():
        return _protect_fernet(value, purpose)
    raise RuntimeError(
        "No secure storage backend available. "
        "Install the 'keyring' package (pip install keyring) "
        "or 'cryptography' (pip install cryptography) "
        "to persist secrets securely on this platform."
    )


def unprotect_secret(value, purpose):
    if not value:
        return ""
    if _can_use_dpapi():
        try:
            return _unprotect_windows(value, purpose)
        except Exception as ex:
            _log_error(f"DPAPI decryption failed for '{purpose}': {ex}")
            return ""
    if value.startswith("__keyring__:"):
        if _can_use_keyring():
            return _unprotect_keyring(value, purpose) or ""
        raise RuntimeError("keyring package required to decrypt secrets stored with keyring backend")
    if value.startswith("__fernet__:"):
        if _can_use_fernet():
            return _unprotect_fernet(value, purpose) or ""
        raise RuntimeError("cryptography package required to decrypt secrets stored with fernet backend")
    return ""


def load_json_file(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as ex:
        _log_error(f"Invalid config JSON at {path}: {ex}")
        return {}


def store_secret(config, key, value):
    config.pop(key, None)
    secure_key = f"{key}_secure"
    if value:
        config[secure_key] = protect_secret(value, key)
    else:
        config.pop(secure_key, None)


def read_secret(config, key):
    secure_key = f"{key}_secure"
    encrypted = config.get(secure_key, "")
    if isinstance(encrypted, str) and encrypted:
        try:
            return unprotect_secret(encrypted, key)
        except Exception as ex:
            _log_error(f"Failed to decrypt {key}: {ex}")
    legacy = config.get(key, "")
    return legacy if isinstance(legacy, str) else ""


def has_legacy_plaintext(config):
    return any(isinstance(config.get(key), str) and config.get(key) for key in SECRET_KEYS)


def atomic_write_json(path, data):
    directory = os.path.dirname(path) or os.getcwd()
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="config_", suffix=".tmp", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
