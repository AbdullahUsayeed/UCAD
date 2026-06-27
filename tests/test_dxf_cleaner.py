import os
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]

if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

try:
    import ezdxf
    from dxf_processor import process_dxf, _normalize_to_origin, _dedup_consecutive
except Exception:
    ezdxf = None
    process_dxf = None
    _normalize_to_origin = None
    _dedup_consecutive = None


@unittest.skipUnless(ezdxf is not None and process_dxf is not None, "DXF dependencies not installed")
class DxfCleanerTests(unittest.TestCase):
    def _build_dxf(self, add_entities):
        fd, path = tempfile.mkstemp(suffix=".dxf")
        os.close(fd)
        doc = ezdxf.new("R2010")
        try:
            doc.units = 4  # millimeters
        except Exception:
            pass
        msp = doc.modelspace()
        add_entities(msp)
        doc.saveas(path)
        return path

    def test_process_dxf_returns_closed_profiles(self):
        def _entities(msp):
            msp.add_lwpolyline([(0, 0), (40, 0), (40, 20), (0, 20)], close=True, dxfattribs={"layer": "OUTLINE"})
            msp.add_circle((10, 10), 2, dxfattribs={"layer": "HOLE"})

        path = self._build_dxf(_entities)
        try:
            result = process_dxf(path)
        finally:
            os.unlink(path)

        self.assertEqual(result.get("status"), "ok")
        self.assertGreaterEqual(len(result.get("profiles", [])), 2)
        self.assertIn("OUTLINE", result.get("metadata", {}).get("layers", []))

    def test_open_geometry_is_skipped_with_warning(self):
        def _entities(msp):
            msp.add_lwpolyline([(0, 0), (30, 0), (30, 10), (0, 10)], close=True, dxfattribs={"layer": "OUTLINE"})
            msp.add_arc((0, 0), radius=5, start_angle=0, end_angle=90, dxfattribs={"layer": "AUX"})

        path = self._build_dxf(_entities)
        try:
            result = process_dxf(path)
        finally:
            os.unlink(path)

        self.assertEqual(result.get("status"), "ok")
        warnings = "\n".join(result.get("warnings", []))
        self.assertIn("ARC skipped (non-closed)", warnings)


    def test_process_dxf_output_includes_normalization_keys(self):
        def _entities(msp):
            msp.add_lwpolyline([(100, 200), (300, 200), (300, 400), (100, 400)],
                               close=True, dxfattribs={"layer": "OUTLINE"})
        path = self._build_dxf(_entities)
        try:
            result = process_dxf(path)
        finally:
            os.unlink(path)
        meta = result.get("metadata", {})
        self.assertTrue(meta.get("normalized"))
        self.assertIn("origin_offset", meta)
        self.assertEqual(len(meta["origin_offset"]), 2)

    def test_normalized_profiles_have_centered_bbox(self):
        def _entities(msp):
            msp.add_lwpolyline([(0, 0), (500, 0), (500, 500), (0, 500)],
                               close=True, dxfattribs={"layer": "OUTLINE"})
        path = self._build_dxf(_entities)
        try:
            result = process_dxf(path)
        finally:
            os.unlink(path)
        meta = result.get("metadata", {})
        pts = result["profiles"][0]["coordinates"]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        self.assertAlmostEqual(cx, 0.0, places=9)
        self.assertAlmostEqual(cy, 0.0, places=9)


@unittest.skipUnless(_normalize_to_origin is not None, "_normalize_to_origin not available")
class NormalizeToOriginTests(unittest.TestCase):
    def test_centers_large_coordinates_at_origin(self):
        result = {
            "status": "ok",
            "profiles": [
                {"coordinates": [(100, 200), (300, 200), (300, 400), (100, 400)],
                 "holes": [], "bbox": [100, 200, 300, 400]},
            ],
            "metadata": {"bbox": [100, 200, 300, 400]},
        }
        out = _normalize_to_origin(result)
        meta = out["metadata"]
        self.assertEqual(meta["origin_offset"], [200.0, 300.0])
        self.assertTrue(meta["normalized"])
        self.assertEqual(meta["bbox"], [-100.0, -100.0, 100.0, 100.0])
        coords = out["profiles"][0]["coordinates"]
        self.assertEqual(coords, [(-100, -100), (100, -100), (100, 100), (-100, 100)])
        p_bbox = out["profiles"][0]["bbox"]
        self.assertEqual(p_bbox, [-100.0, -100.0, 100.0, 100.0])

    def test_already_centered_sets_origin_offset(self):
        result = {
            "profiles": [
                {"coordinates": [(-50, -50), (50, -50), (50, 50), (-50, 50)],
                 "holes": [], "bbox": [-50, -50, 50, 50]},
            ],
            "metadata": {"bbox": [-50, -50, 50, 50]},
        }
        out = _normalize_to_origin(result)
        self.assertEqual(out["profiles"][0]["coordinates"],
                         [(-50, -50), (50, -50), (50, 50), (-50, 50)])
        self.assertEqual(out["metadata"]["origin_offset"], [0.0, 0.0])
        self.assertTrue(out["metadata"]["normalized"])

    def test_translates_holes(self):
        result = {
            "profiles": [
                {"coordinates": [(0, 0), (100, 0), (100, 100), (0, 100)],
                 "holes": [[(30, 30), (50, 30), (50, 50), (30, 50)]],
                 "bbox": [0, 0, 100, 100]},
            ],
            "metadata": {"bbox": [0, 0, 100, 100]},
        }
        out = _normalize_to_origin(result)
        self.assertEqual(out["profiles"][0]["holes"],
                         [[(-20, -20), (0, -20), (0, 0), (-20, 0)]])

    def test_empty_profiles_returns_unchanged(self):
        result = {"status": "ok", "profiles": [], "metadata": {"bbox": [0, 0, 0, 0]}}
        out = _normalize_to_origin(result)
        self.assertNotIn("origin_offset", out.get("metadata", {}))
        self.assertNotIn("normalized", out.get("metadata", {}))

    def test_multiple_profiles_use_same_offset(self):
        result = {
            "profiles": [
                {"coordinates": [(0, 0), (200, 0), (200, 200), (0, 200)],
                 "holes": [], "bbox": [0, 0, 200, 200]},
                {"coordinates": [(50, 50), (150, 0), (200, 150)],
                 "holes": [], "bbox": [50, 0, 200, 150]},
            ],
            "metadata": {"bbox": [0, 0, 200, 200]},
        }
        out = _normalize_to_origin(result)
        meta = out["metadata"]
        self.assertEqual(meta["origin_offset"], [100.0, 100.0])
        self.assertEqual(out["profiles"][0]["coordinates"][0], (-100, -100))
        self.assertEqual(out["profiles"][1]["coordinates"][0], (-50, -50))


@unittest.skipUnless(_dedup_consecutive is not None, "_dedup_consecutive not available")
class TestDedupConsecutive(unittest.TestCase):

    def test_removes_exact_duplicates(self):
        pts = [[0,0], [0,0], [1,0], [1,0], [1,1]]
        result = _dedup_consecutive(pts)
        self.assertEqual(result, [[0,0], [1,0], [1,1]])

    def test_removes_closing_duplicate(self):
        pts = [[0,0], [1,0], [1,1], [0,0]]
        result = _dedup_consecutive(pts)
        self.assertEqual(result, [[0,0], [1,0], [1,1]])

    def test_keeps_near_but_not_equal_points(self):
        pts = [[0,0], [0.001, 0], [1,0]]
        result = _dedup_consecutive(pts)
        self.assertEqual(len(result), 3)

    def test_empty_list_returns_empty(self):
        self.assertEqual(_dedup_consecutive([]), [])

    def test_single_point_returns_single(self):
        self.assertEqual(_dedup_consecutive([[1,2]]), [[1,2]])

    def test_all_duplicates_returns_one(self):
        pts = [[5,5], [5,5], [5,5]]
        result = _dedup_consecutive(pts)
        self.assertEqual(result, [[5,5]])

    @unittest.skipUnless(ezdxf is not None and process_dxf is not None, "DXF dependencies not installed")
    def test_profile_with_degenerate_vertices_skipped(self):
        """A profile reduced to < 3 points after dedup must not appear in output."""
        import os
        fixture = os.path.join(os.path.dirname(__file__), "fixtures", "N-145.dxf")
        if not os.path.exists(fixture):
            self.skipTest("N-145.dxf not available")
        result = process_dxf(fixture)
        for profile in result.get("profiles", []):
            pts = profile.get("coordinates", [])
            self.assertGreaterEqual(len(pts), 3,
                f"Profile with {len(pts)} points survived dedup — should have been filtered")


if __name__ == "__main__":
    unittest.main()
