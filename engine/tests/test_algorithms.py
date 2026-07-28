import math
import unittest

from litemap_engine.algorithms import blur_score, confidence, fit_grid_phase, is_hard_cut, ray_carve


class AlgorithmTests(unittest.TestCase):
    def test_blur_score_detects_edges(self):
        flat = [[0.5] * 5 for _ in range(5)]
        edge = [[0, 0, 1, 1, 1] for _ in range(5)]
        self.assertEqual(blur_score(flat), 0)
        self.assertGreater(blur_score(edge), 0)

    def test_cut_detection_uses_normalized_histograms(self):
        self.assertFalse(is_hard_cut([10, 20, 10], [20, 40, 20]))
        self.assertTrue(is_hard_cut([100, 0, 0], [0, 0, 100]))

    def test_grid_phase(self):
        phase, certainty = fit_grid_phase([0.21, 1.19, 2.22, 4.20], 1.0)
        self.assertAlmostEqual(phase, 0.205, places=2)
        self.assertGreater(certainty, 0.99)

    def test_confidence_penalizes_single_view_and_disagreement(self):
        many = confidence(0.95, 0.9, 5)
        single = confidence(0.95, 0.9, 1)
        self.assertGreater(many, single)
        self.assertLess(confidence(0.95, 0.9, 5, 0.7), many)

    def test_ray_carving_excludes_surface_cell(self):
        cells = ray_carve((0.1, 0.1, 0.1), (3.2, 0.1, 0.1))
        self.assertIn((0, 0, 0), cells)
        self.assertIn((2, 0, 0), cells)
        self.assertNotIn((3, 0, 0), cells)


if __name__ == "__main__":
    unittest.main()
