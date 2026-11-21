import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from online_trade.extra_eval import engine  # noqa: E402
from online_trade.extra_eval.e5 import by_adjust  # noqa: E402


def toy_pool():
    """Categories 0,1,2; combos: singles, {0,1}, {0,2}, {1,2}, {0,1,2}; rules point at their combo row."""
    combos = [(0,), (1,), (2,), (0, 1), (0, 2), (1, 2), (0, 1, 2)]
    row = {c: i for i, c in enumerate(combos)}
    # directed rules: 0->1, 1->0 (same combo), 01->2 (triple), 0->2
    r_joint = np.array([row[(0, 1)], row[(0, 1)], row[(0, 1, 2)], row[(0, 2)]])
    return SimpleNamespace(combos=combos, row=row, r_joint=r_joint)


class ExtraEvalTests(unittest.TestCase):
    def test_test_period_is_locked_without_freeze(self):
        if engine.FREEZE.exists():
            self.skipTest("protocol already frozen")
        with self.assertRaises(PermissionError):
            engine.load_period("test")

    def test_combo_walk_skips_reverse_and_superset(self):
        pool = toy_pool()
        rows, rules, pos = engine.combo_walk(pool, np.array([0, 1, 2, 3]), limit=5)
        self.assertEqual(rows, [pool.row[(0, 1)], pool.row[(0, 2)]])  # 1->0 reverse and 01->2 superset skipped
        self.assertEqual(rules, [0, 3])
        self.assertEqual(pos, 4)

    def test_largest_remainder_quota_sums_to_budget(self):
        self.assertEqual(engine.allocate({"0": 801, "1": 2173, "2": 4547}, 100), {"0": 11, "1": 29, "2": 60})

    def test_benjamini_yekutieli(self):
        h = 1 + 1 / 2 + 1 / 3
        np.testing.assert_allclose(by_adjust([0.01, 0.02, 0.03]), [0.03 * h] * 3)
        np.testing.assert_allclose(by_adjust([0.5, 0.001]), [min(1, 0.5 * 1.5), 0.001 * 2 * 1.5])


if __name__ == "__main__":
    unittest.main()
