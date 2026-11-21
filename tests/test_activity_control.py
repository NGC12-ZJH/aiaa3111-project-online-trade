import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from online_trade.clustering.activity_control import matched_permutations, stratify  # noqa: E402
from online_trade.taxonomy.category_controls import allocate  # noqa: E402


def test_stratify_inclusive_upper_bounds():
    got = stratify(np.array([1, 2, 3, 4, 5, 9, 10, 40]), [1, 2, 4, 9, None], ["1", "2", "3-4", "5-9", "10+"])
    assert list(got) == ["1", "2", "3-4", "3-4", "5-9", "5-9", "10+", "10+"]


def test_shuffle_keeps_label_counts_inside_each_stratum():
    labels = pd.Series(list("000111222") * 10)
    strata = pd.Series(list("aab") * 30)
    real = pd.crosstab(strata, labels)
    for row in matched_permutations(labels, strata, range(5)):
        assert (pd.crosstab(strata, row).to_numpy() == real.to_numpy()).all()


def test_largest_remainder_allocation_matches_budget():
    assert allocate({"0": 801, "1": 2173, "2": 4547}, 20) == {"0": 2, "1": 6, "2": 12}
    assert allocate({"0": 801, "1": 2173, "2": 4547}, 100) == {"0": 11, "1": 29, "2": 60}
