"""Evidence for each candidate clustering and the pre-registered selection rule."""

import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score, silhouette_score

from .methods import METHODS, fit_predict


def bootstrap_ari(method, X, k, reference, seed, repeats, **method_args):
    """Stability: re-cluster bootstrap samples and compare with the full-data labels
    on the sampled customers only, using the adjusted Rand index (ARI).

    ARI = 1 means identical groupings; ARI near 0 means no better than chance.
    Returns (mean, standard deviation).
    """
    rng = np.random.default_rng(seed)
    scores = []
    for _ in range(repeats):
        index = rng.choice(len(X), size=len(X), replace=True)
        labels = fit_predict(method, X[index], k, seed=int(rng.integers(2**31)), **method_args)
        first = pd.Series(labels).groupby(index).first()  # count a customer drawn several times only once
        scores.append(adjusted_rand_score(reference[first.index], first.to_numpy()))
    return float(np.mean(scores)), float(np.std(scores))


def describe_candidate(method, k, X, labels, rfm, stability):
    """One row of the comparison table for a (method, k) candidate."""
    sizes = np.bincount(labels, minlength=k)
    baskets = rfm["profile_baskets"].groupby(labels).sum()
    return {
        "method": method,
        "k": k,
        "n_groups": int(len(np.unique(labels))),
        # Separation in [-1, 1]: high when customers sit close to their own cluster and far
        # from the nearest other one; computed in the same feature space for every method
        "silhouette": round(float(silhouette_score(X, labels)), 4),
        "bootstrap_ari_mean": round(stability[0], 4),
        "bootstrap_ari_std": round(stability[1], 4),
        "min_cluster_share": round(float(sizes.min() / len(labels)), 4),
        "min_cluster_profile_baskets": int(baskets.min()),
        "cluster_sizes": "/".join(map(str, sizes)),
    }


def select_candidate(table, rule):
    """Apply the configured rule: filter, take the best silhouette, and break near-ties
    by smaller k and then by method order."""
    table = table.copy()
    table["eligible"] = (
        table["n_groups"].eq(table["k"])
        & table["min_cluster_share"].ge(rule["min_cluster_share"])
        & table["bootstrap_ari_mean"].ge(rule["min_bootstrap_ari"])
    )
    pool = table[table["eligible"]]
    if pool.empty:
        raise ValueError("No candidate passes the selection rule; revisit the rule as a team")
    near_best = pool[pool["silhouette"] >= pool["silhouette"].max() - rule["silhouette_tie_tolerance"]]
    rank = near_best.assign(method_rank=near_best["method"].map(METHODS.index))
    chosen = rank.sort_values(["k", "method_rank"]).index[0]
    table["selected"] = table.index == chosen
    return table, table.loc[chosen]
