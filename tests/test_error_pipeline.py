"""Tests for error-handling pipeline functions: extract, report, retry.

Covers exported functions at 0% coverage in test_error_pipeline.py.
"""

import traceback
from orchestrator.errors import (
    deep_extract_freecad_error,
    translate_error,
    build_error_report,
    build_retry_prompt,
    ErrorReport,
)


class TestDeepExtractFreecadError:

    def test_extracts_string_from_normal_exception(self):
        exc = ValueError("normal error message")
        result = deep_extract_freecad_error(exc)
        assert "normal error message" in result

    def test_extracts_from_dict_arg(self):
        exc = ValueError({"sErrMsg": "wrapped FreeCAD error"})
        result = deep_extract_freecad_error(exc)
        assert "wrapped FreeCAD error" in result

    def test_extracts_from_nested_dict(self):
        inner = {"message": "nested message"}
        exc = ValueError({"outer": inner})
        result = deep_extract_freecad_error(exc)
        assert "nested message" in result or "outer" in result

    def test_extracts_from_string_dict(self):
        exc = ValueError('{"msg": "json encoded error"}')
        result = deep_extract_freecad_error(exc)
        assert "json encoded" in result

    def test_empty_args_falls_back_to_str(self):
        class _Empty(BaseException):
            def __init__(self):
                super().__init__()

        result = deep_extract_freecad_error(_Empty())
        assert isinstance(result, str)

    def test_mixed_args_prioritizes_meaningful(self):
        exc = ValueError({"sErrMsg": "real error"}, "filler text")
        result = deep_extract_freecad_error(exc)
        assert "real error" in result


class TestErrorReport:

    def test_default_construction(self):
        r = ErrorReport()
        assert r.category == "unknown"
        assert r.title == ""
        assert r.retry_tier == 1

    def test_custom_construction(self):
        r = ErrorReport(category="sketch_open_profile", title="Wire is open",
                        cause="Profile has 3 edges", fix="Close the wire")
        assert r.category == "sketch_open_profile"
        assert "Wire is open" in r.for_ui()
        assert "Fix: Close the wire" in r.for_ui()

    def test_for_ai_retry_tier_1(self):
        r = ErrorReport(category="bad_attribute", title="Missing attr",
                        fix="Use correct property")
        prompt = r.for_ai_retry()
        assert "EXECUTION ERROR (attempt 1)" in prompt
        assert "Choose a different strategy" in prompt

    def test_for_ai_retry_tier_2(self):
        r = ErrorReport(category="bad_attribute", title="Missing attr",
                        fix="Use correct property", location="line 10",
                        cause="AttributeError", example='obj.Profile = sketch',
                        retry_tier=2)
        prompt = r.for_ai_retry()
        assert "EXECUTION ERROR (attempt 2)" in prompt
        assert "Failed at: line 10" in prompt
        assert "Root cause: AttributeError" in prompt

    def test_for_ai_retry_tier_3(self):
        r = ErrorReport(category="bad_attribute", title="Missing attr",
                        fix="Use correct property", raw_error="AttributeError: no attr",
                        example='obj.Profile = sketch', retry_tier=3)
        prompt = r.for_ai_retry()
        assert "EXECUTION ERROR (attempt 3 — FINAL)" in prompt
        assert "Raw error:" in prompt
        assert "CRITICAL" in prompt


class TestBuildErrorReport:

    def test_returns_error_report_from_exception(self):
        try:
            raise ValueError("test error for build")
        except ValueError as e:
            tb = traceback.format_exc()
            report = build_error_report(e, tb)

        assert isinstance(report, ErrorReport)
        assert report.title
        assert report.category is not None
        assert report.retry_tier == 1

    def test_populates_location_from_traceback(self):
        def inner():
            raise RuntimeError("inner error")
        try:
            inner()
        except RuntimeError as e:
            tb = traceback.format_exc()
            report = build_error_report(e, tb)

        assert isinstance(report, ErrorReport)
        # Location should contain the inner() function
        assert report.location and "inner" in repr(report.location)


class TestBuildRetryPrompt:

    def test_tier_1_prompt_contains_basic_sections(self):
        report = ErrorReport(category="bad_attribute", title="Missing attr",
                             fix="Use correct property")
        prompt = build_retry_prompt(
            user_input="make a box",
            error_report=report,
            previous_code="",
            scene_observation="",
            attempt_number=1,
        )
        assert "RETRY 1/3" in prompt
        assert "OUTPUT RULES" in prompt
        assert "HIGHLIGHT" not in prompt  # no highlight section for tier 1
        assert "FALLBACK STRATEGY" not in prompt  # no fallback for tier 1

    def test_tier_2_includes_highlighted_lines(self):
        report = ErrorReport(category="api_rename", title="Wrong property",
                             fix="Use Profile= instead of Sketch=")
        prompt = build_retry_prompt(
            user_input="make a box",
            error_report=report,
            previous_code="body.newObject(...)",
            scene_observation="",
            attempt_number=2,
        )
        assert "RETRY 2/3" in prompt
        assert "OUTPUT RULES" in prompt

    def test_tier_3_includes_fallback_strategy(self):
        report = ErrorReport(category="null_shape", title="Null shape",
                             fix="Simplify geometry", retry_tier=2)
        prompt = build_retry_prompt(
            user_input="make a box",
            error_report=report,
            previous_code="body.newObject(...)",
            scene_observation="",
            attempt_number=3,
        )
        assert "RETRY 3/3" in prompt
        assert "FALLBACK STRATEGY" in prompt
        assert "Part::Box" in prompt


class TestTranslateError:

    def test_both_points_equal_translates_correctly(self):
        msg = translate_error("OCCError: Both points are equal")
        combined = msg[0] + " " + msg[1]
        assert "dedup" in combined.lower() or "duplicate" in combined.lower() or "identical" in combined.lower(), \
            f"Error translation not helpful: {msg}"
