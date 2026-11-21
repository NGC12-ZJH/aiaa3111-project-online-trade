"""Activity-matched random control groups.

The existing random control (pipeline.py, step 6) shuffles the real labels over all customers, so each
random group has the same head count as the real cluster but a very different activity mix: C2 holds
62% of profile baskets and 60% of Discovery baskets. Here the real labels are shuffled only inside
activity strata, so every stratum keeps exactly the real label counts and every random group has (about)
the real activity mix. A real-vs-random gap that survives this control is not explained by activity alone.
"""

import numpy as np
import pandas as pd


def stratify(values, upper_bounds, labels):
    """Map counts to stratum labels; upper bounds are inclusive and None means no upper bound."""
    edges = [-np.inf] + [np.inf if u is None else u for u in upper_bounds]
    return pd.cut(values, edges, labels=labels, right=True).astype(str)


def matched_permutations(labels, strata, seeds):
    """One row per (seed, customer): real labels shuffled within each stratum."""
    labels = pd.Series(labels).reset_index(drop=True)
    strata = pd.Series(strata).reset_index(drop=True)
    positions = [np.flatnonzero(strata.eq(s).to_numpy()) for s in sorted(strata.unique())]
    out = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        shuffled = labels.to_numpy().copy()
        for pos in positions:
            shuffled[pos] = rng.permutation(shuffled[pos])
        out.append(shuffled)
    return np.vstack(out)


def build_controls(clusters, discovery_baskets_per_customer, config):
    """Return {control_name: DataFrame(customer_id, random_group_id, seed, stratum)} for every configured control."""
    seeds = range(config["seed"], config["seed"] + config["repeats"])
    activity = {
        "number of profile-period orders": clusters["frequency"].to_numpy(),
        "number of eligible Discovery baskets":
            clusters["customer_id"].map(discovery_baskets_per_customer).fillna(0).to_numpy(),
    }
    controls = {}
    for name, spec in config["controls"].items():
        strata = stratify(activity[spec["activity"]], spec["strata_upper_bounds"], spec["strata_labels"])
        groups = matched_permutations(clusters["cluster_id"], strata, seeds)
        frame = pd.concat(pd.DataFrame({"customer_id": clusters["customer_id"].to_numpy(), "random_group_id": row,
                                        "seed": seed, "stratum": strata})
                          for seed, row in zip(seeds, groups))
        # Same head count per group and per stratum as the real clusters, for every seed.
        real = pd.crosstab(strata, clusters["cluster_id"].to_numpy())
        for seed, z in frame.groupby("seed"):
            got = pd.crosstab(z.stratum.to_numpy(), z.random_group_id.to_numpy())
            got = got.reindex(index=real.index, columns=real.columns, fill_value=0)
            assert (got.to_numpy() == real.to_numpy()).all(), (name, seed)
        controls[name] = frame
    return controls
