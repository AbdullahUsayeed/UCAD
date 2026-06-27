"""Mutation guard — verifies the trigger test suite catches real regressions.

Each test temporarily monkeypatches a should_inject_* function to always
return False, then asserts that the integration system_prompt no longer
contains the expected knowledge phrase. If the phrase still appears,
the knowledge module is being injected by a path not under test.
"""

import types
import pytest
from unittest.mock import patch


_MOCK_KB = types.SimpleNamespace(
    build=lambda *a, **k: "mock knowledge base",
    set_version=lambda *a, **k: None,
)


def _make_orch(prompt: str):
    from orchestrator import AIOrchestrator
    orch = object.__new__(AIOrchestrator)
    orch._last_user_input = prompt
    orch.kb = _MOCK_KB
    orch.failures = types.SimpleNamespace(as_prompt_section=lambda: "")
    orch._dxf_context = None
    return orch


# Unique phrases from each knowledge module — must NOT appear in any
# always-on API_CORRECTIONS entry, so they are strict indicators of
# scoped-injection success.
GEAR_PHRASE = "def make_gear"
TRIANGLE_PHRASE = "triangle_ah"
CURVEDSHAPES_PHRASE = "HULL WIRES MUST LIE"
ADDFC_PHRASE = "batch installation"


class TestMutationGuard:

    def test_killing_gear_injection_removes_gear_knowledge(self):
        with patch("orchestrator.core.should_inject_gear", return_value=False):
            sp = _make_orch("make a gear with module 2").build_system_prompt()
        assert GEAR_PHRASE not in sp, (
            f"{GEAR_PHRASE!r} still appeared even with should_inject_gear killed — "
            "GEAR_KNOWLEDGE is leaking in via an untested path"
        )

    def test_killing_triangle_injection_removes_triangle_knowledge(self):
        with patch("orchestrator.core.should_inject_triangle", return_value=False):
            sp = _make_orch("draw a triangle 30mm base").build_system_prompt()
        assert TRIANGLE_PHRASE not in sp, (
            f"{TRIANGLE_PHRASE!r} still appeared with should_inject_triangle killed"
        )

    def test_killing_curvedshapes_injection_removes_curvedshapes_knowledge(self):
        with patch("orchestrator.core.should_inject_curvedshapes", return_value=False):
            sp = _make_orch("blend two hull curves together").build_system_prompt()
        assert CURVEDSHAPES_PHRASE not in sp, (
            f"{CURVEDSHAPES_PHRASE!r} still appeared with should_inject_curvedshapes killed"
        )

    def test_killing_addfc_injection_removes_addfc_knowledge(self):
        with patch("orchestrator.core.should_inject_addfc", return_value=False):
            sp = _make_orch("install an addon with addFC").build_system_prompt()
        assert ADDFC_PHRASE not in sp, (
            f"{ADDFC_PHRASE!r} still appeared with should_inject_addfc killed"
        )

    def test_always_on_api_corrections_survive_killed_injection(self):
        """API_CORRECTIONS must always appear regardless of injection flags."""
        with patch("orchestrator.core.should_inject_gear", return_value=False):
            sp = _make_orch("make a gear").build_system_prompt()
        # "freecad.gears" appears in the `mistake` field of the always-on
        # fcgear_not_installed API correction entry — it MUST survive.
        assert "freecad.gears" in sp, (
            "Always-on API_CORRECTIONS disappeared when gear injection was killed"
        )
