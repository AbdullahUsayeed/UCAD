import os
import sys
from pathlib import Path
from unittest.mock import patch

MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import pytest
from pcb_vision_deps import (
    get_vision_deps_status,
    get_vision_deps_message,
    model_supports_vision,
    VisionDeps,
)


class TestPCBVisionDeps:

    def test_no_cli_no_key_returns_no_both(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("pcb_vision_deps._find_kicad_cli", return_value=None):
                result = get_vision_deps_status(api_key="")
                assert result == VisionDeps.NO_BOTH

    def test_has_key_no_cli_returns_no_kicad(self):
        with patch("pcb_vision_deps._find_kicad_cli", return_value=None):
            result = get_vision_deps_status(api_key="sk-test-123")
            assert result == VisionDeps.NO_KICAD_CLI

    def test_both_available_returns_ok(self):
        with patch("pcb_vision_deps._find_kicad_cli", return_value=r"C:\kicad-cli.exe"):
            result = get_vision_deps_status(api_key="sk-test-123")
            assert result == VisionDeps.OK

    def test_non_vision_model_returns_no_vision_model(self):
        with patch("pcb_vision_deps._find_kicad_cli", return_value=r"C:\kicad-cli.exe"):
            result = get_vision_deps_status(api_key="sk-test", model="deepseek-r1")
            assert result == VisionDeps.NO_VISION_MODEL

    def test_vision_model_with_all_deps_returns_ok(self):
        with patch("pcb_vision_deps._find_kicad_cli", return_value=r"C:\kicad-cli.exe"):
            result = get_vision_deps_status(api_key="sk-test", model="claude-opus-4-8")
            assert result == VisionDeps.OK

    def test_model_supports_vision_recognises_known_models(self):
        assert model_supports_vision("gpt-4o") is True
        assert model_supports_vision("gpt-4o-mini") is True
        assert model_supports_vision("claude-sonnet-4-6") is True
        assert model_supports_vision("gemini-1.5-pro") is True
        assert model_supports_vision("deepseek-vl2") is True
        assert model_supports_vision("deepseek-chat") is True

    def test_model_supports_vision_rejects_non_vision_models(self):
        assert model_supports_vision("deepseek-r1") is False
        assert model_supports_vision("llama3") is False
        assert model_supports_vision("") is False

    def test_get_vision_deps_message_returns_string_for_each_status(self):
        for status in VisionDeps:
            msg = get_vision_deps_message(status)
            if status == VisionDeps.OK:
                assert msg == ""
            else:
                assert isinstance(msg, str)
                assert len(msg) > 10

    def test_api_key_from_env_var_works(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-env-key"}, clear=True):
            with patch("pcb_vision_deps._find_kicad_cli", return_value=r"C:\kicad-cli.exe"):
                result = get_vision_deps_status(api_key="")
                assert result == VisionDeps.OK
