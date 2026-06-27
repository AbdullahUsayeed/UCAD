"""Tests for render_template resilience against edge cases."""

import pytest
from orchestrator import render_template, TEMPLATES


def test_unknown_template_name_raises_keyerror():
    with pytest.raises(KeyError, match="not_a_real_template"):
        render_template("not_a_real_template")


def test_override_with_unknown_key_is_ignored():
    code = render_template("triangle", {"angle": 60, "nonexistent_key": 999})
    assert "angle = 60" in code
    assert "{nonexistent_key}" not in code


def test_override_with_none_value_does_not_crash():
    code = render_template("triangle", {"angle": None})
    assert "None" in code or isinstance(code, str)


def test_override_with_empty_dict_equals_default():
    explicit = render_template("gear", {})
    implicit = render_template("gear")
    assert explicit == implicit


def test_override_with_non_dict_raises_typeerror():
    with pytest.raises(TypeError, match="overrides must be a dict"):
        render_template("gear", "not_a_dict")


def test_override_with_partial_overrides_are_accepted():
    code = render_template("pipe", {"outer_radius": 100})
    assert "ro = 100" in code
    assert "t = 10" in code
    assert "h = 200" in code


def test_all_templates_render_with_all_keys():
    """Every schema key can be individually overridden without syntax remnant."""
    from orchestrator import TEMPLATE_SCHEMAS

    for name, schema in TEMPLATE_SCHEMAS.items():
        if not schema:
            continue
        for key in schema:
            code = render_template(name, {key: schema[key]})
            assert "{" + key + "}" not in code, f"remnant {{{key}}} in {name}"
