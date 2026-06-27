"""Comprehensive tests for secret_store.py — file I/O, store/read, backends.

Many tests force the fernet backend by monkeypatching capability checks,
so they work on any platform without DPAPI or keyring.
"""

import json
import os
import pytest
import secret_store as ss


# ── Capability checks ────────────────────────────────────────────

class TestCapabilityChecks:
    def test_can_use_dpapi_returns_bool(self):
        assert isinstance(ss._can_use_dpapi(), bool)

    def test_can_use_keyring_returns_bool(self):
        assert isinstance(ss._can_use_keyring(), bool)

    def test_can_use_fernet_returns_bool(self):
        assert isinstance(ss._can_use_fernet(), bool)


# ── Internal helpers ─────────────────────────────────────────────

class TestInternalHelpers:
    def test_machine_secret_returns_bytes(self):
        result = ss._machine_secret()
        assert isinstance(result, bytes)
        assert len(result) == 32

    def test_machine_secret_is_deterministic(self):
        assert ss._machine_secret() == ss._machine_secret()

    def test_secrets_file_path_returns_absolute(self):
        path = ss._secrets_file_path()
        assert isinstance(path, str)
        assert path.endswith(".secrets_encrypted")
        assert os.path.isabs(path)

    def test_log_error_does_not_crash(self):
        ss._log_error("test message")
        assert True  # no exception raised

    def test_fernet_key_returns_bytes(self):
        key = ss._fernet_key()
        assert isinstance(key, bytes)
        assert len(key) > 0


# ── Load / save / atomic write ───────────────────────────────────

class TestFileIO:
    def test_load_json_file_happy_path(self, tmp_path):
        fp = tmp_path / "config.json"
        fp.write_text('{"a": 1, "b": 2}', encoding="utf-8")
        assert ss.load_json_file(str(fp)) == {"a": 1, "b": 2}

    def test_load_json_file_not_found(self):
        assert ss.load_json_file("nope/nonexistent.json") == {}

    def test_load_json_file_invalid_json(self, tmp_path):
        fp = tmp_path / "bad.json"
        fp.write_text("not json", encoding="utf-8")
        result = ss.load_json_file(str(fp))
        assert result == {}

    def test_load_json_file_non_dict_returns_empty(self, tmp_path):
        fp = tmp_path / "list.json"
        fp.write_text("[1, 2, 3]", encoding="utf-8")
        assert ss.load_json_file(str(fp)) == {}

    def test_atomic_write_json_round_trip(self, tmp_path):
        fp = tmp_path / "out.json"
        data = {"x": 42, "y": "hello"}
        ss.atomic_write_json(str(fp), data)
        assert json.loads(fp.read_text(encoding="utf-8")) == data


# ── Fernet backend round-trip ────────────────────────────────────

class TestFernetBackend:
    @pytest.fixture(autouse=True)
    def _force_fernet(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ss, "_can_use_dpapi", lambda: False)
        monkeypatch.setattr(ss, "_can_use_keyring", lambda: False)
        monkeypatch.setattr(ss, "_can_use_fernet", lambda: True)
        monkeypatch.setattr(ss, "_secrets_file_path",
                            lambda: str(tmp_path / ".secrets_test"))
        yield

    def test_protect_unprotect_round_trip(self):
        token = ss.protect_secret("my_api_key_value", "api_key")
        assert token != "my_api_key_value"
        assert token.startswith("__fernet__:")
        assert ss.unprotect_secret(token, "api_key") == "my_api_key_value"

    def test_protect_unprotect_unicode(self):
        value = "s\u00e9cret \u2603 \U0001f600"
        token = ss.protect_secret(value, "unicode_key")
        assert ss.unprotect_secret(token, "unicode_key") == value

    def test_protect_unprotect_large_value(self):
        value = "x" * 10000
        token = ss.protect_secret(value, "large_key")
        assert ss.unprotect_secret(token, "large_key") == value

    def test_protect_empty_value(self):
        assert ss.protect_secret("", "whatever") == ""

    def test_unprotect_empty_value(self):
        assert ss.unprotect_secret("", "whatever") == ""

    def test_unprotect_bogus_token(self):
        assert ss.unprotect_secret("garbage", "test") == ""

    def test_unprotect_wrong_purpose(self):
        token = ss.protect_secret("secret_for_a", "purpose_a")
        result = ss.unprotect_secret(token, "purpose_b")
        # wrong purpose should not return the secret
        assert result != "secret_for_a"

    def test_fernet_store_persists_on_disk(self, tmp_path):
        secrets_file = tmp_path / ".secrets_test"
        assert not secrets_file.exists()
        ss.protect_secret("stored_value", "persist_key")
        assert secrets_file.exists()
        raw = json.loads(secrets_file.read_text(encoding="utf-8"))
        assert "persist_key" in raw


# ── store_secret / read_secret / has_legacy_plaintext ────────────

class TestStoreRead:
    @pytest.fixture(autouse=True)
    def _force_fernet(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ss, "_can_use_dpapi", lambda: False)
        monkeypatch.setattr(ss, "_can_use_keyring", lambda: False)
        monkeypatch.setattr(ss, "_can_use_fernet", lambda: True)
        monkeypatch.setattr(ss, "_secrets_file_path",
                            lambda: str(tmp_path / ".secrets_test"))
        yield

    def test_store_then_read_returns_value(self):
        cfg = {}
        ss.store_secret(cfg, "api_key", "sk-abc123")
        assert ss.read_secret(cfg, "api_key") == "sk-abc123"

    def test_store_empty_removes_key(self):
        cfg = {"api_key_secure": "__fernet__:dummy"}
        ss.store_secret(cfg, "api_key", "")
        assert ss.read_secret(cfg, "api_key") == ""

    def test_read_missing_key_returns_empty(self):
        assert ss.read_secret({}, "nonexistent") == ""

    def test_store_overwrites_previous(self):
        cfg = {}
        ss.store_secret(cfg, "api_key", "first_value")
        assert ss.read_secret(cfg, "api_key") == "first_value"
        ss.store_secret(cfg, "api_key", "second_value")
        assert ss.read_secret(cfg, "api_key") == "second_value"

    def test_read_fallback_to_legacy_plaintext(self):
        cfg = {"api_key": "legacy_plain_key"}
        assert ss.read_secret(cfg, "api_key") == "legacy_plain_key"

    def test_has_legacy_plaintext_true(self):
        cfg = {"api_key": "exposed"}
        assert ss.has_legacy_plaintext(cfg) is True

    def test_has_legacy_plaintext_false(self):
        cfg = {"api_key_secure": "__fernet__:encrypted"}
        assert ss.has_legacy_plaintext(cfg) is False

    def test_has_legacy_plaintext_empty_string_false(self):
        cfg = {"api_key": ""}
        assert ss.has_legacy_plaintext(cfg) is False
