"""Trigger regex edge cases for all knowledge modules."""

from orchestrator import (
    should_inject_gear,
    should_inject_triangle,
    should_inject_curvedshapes,
    should_inject_addfc,
    should_inject_airfoil,
)


# ── Gear ────────────────────────────────────────────────────────────────

class TestGearTriggerEdgeCases:
    def test_partial_word_does_not_match(self):
        assert not should_inject_gear("gearbox lubricant guide")

    def test_punctuation_after_still_matches(self):
        assert should_inject_gear("need a gear!")

    def test_mixed_case_still_matches(self):
        assert should_inject_gear("SPUR GEAR DESIGN")

    def test_multi_topic_includes_gear(self):
        assert should_inject_gear("bracket and gear")


# ── Triangle ────────────────────────────────────────────────────────────

class TestTriangleTriggerEdgeCases:
    def test_triangulation_does_not_match(self):
        assert not should_inject_triangle("triangulation algorithm")

    def test_triangular_root_in_other_word_does_not_match(self):
        assert not should_inject_triangle("subtriangular deposit")

    def test_right_triangle_variation_matches(self):
        assert should_inject_triangle("right triangle")

    def test_mixed_case_still_matches(self):
        assert should_inject_triangle("EQUILATERAL triangle")


# ── CurvedShapes ────────────────────────────────────────────────────────

class TestCurvedShapesTriggerEdgeCases:
    def test_loft_a_surface_does_not_match(self):
        assert not should_inject_curvedshapes("loft a surface")

    def test_wing_design_does_not_match(self):
        assert not should_inject_curvedshapes("design a wing")

    def test_boat_hull_matches(self):
        assert should_inject_curvedshapes("boat hull")

    def test_hull_curves_matches(self):
        assert should_inject_curvedshapes("add hull curves between profiles")

    def test_morph_matches(self):
        assert should_inject_curvedshapes("morph between two shapes")

    def test_fuselage_matches(self):
        assert should_inject_curvedshapes("aircraft fuselage design")

    def test_blend_surface_matches(self):
        assert should_inject_curvedshapes("blend surface between edges")

    def test_curved_array_matches(self):
        assert should_inject_curvedshapes("curved array along path")


# ── AddFC ───────────────────────────────────────────────────────────────

class TestAddFCTriggerEdgeCases:
    def test_add_a_face_does_not_match(self):
        assert not should_inject_addfc("add a face to the solid")

    def test_addfc_camelcase_still_matches(self):
        assert should_inject_addfc("use AddFC from the addon manager")

    def test_install_macro_matches(self):
        assert should_inject_addfc("install macro from repository")

    def test_addon_manager_matches(self):
        assert should_inject_addfc("open addon manager")

    def test_macro_runner_matches(self):
        assert should_inject_addfc("macro runner utility")


# ── Airfoil ─────────────────────────────────────────────────────────────

class TestAirfoilTriggerEdgeCases:
    def test_swing_does_not_match_because_word_boundary(self):
        assert not should_inject_airfoil("swing dance party")

    def test_airfoil_core_word_matches(self):
        assert should_inject_airfoil("design an airfoil")

    def test_winglet_matches(self):
        assert should_inject_airfoil("winglet design")
