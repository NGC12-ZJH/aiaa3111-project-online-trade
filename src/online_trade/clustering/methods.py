"""Four clustering methods on the same standardized RFM matrix X (columns: R, log F, log M)."""

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.mixture import GaussianMixture

METHODS = ("kmeans", "gmm", "ward", "rfm_score")


def fit_predict(method, X, k, seed, n_init=10, score_bins=5):
    """Return one cluster id (0..k-1) per customer."""
    if method == "kmeans":
        # Assign customers to the nearest centre, move centres to cluster means, repeat;
        # keep the best of n_init random starts
        labels = KMeans(n_clusters=k, n_init=n_init, random_state=seed).fit_predict(X)
    elif method == "gmm":
        # Model customers as k elliptical Gaussian components; take the most likely one
        model = GaussianMixture(n_components=k, covariance_type="full", n_init=n_init, random_state=seed)
        labels = model.fit(X).predict(X)
    elif method == "ward":
        # Merge bottom-up, each time joining the pair that least increases within-cluster
        # variance; deterministic, so the seed is unused
        labels = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(X)
    elif method == "rfm_score":
        labels = rfm_score_labels(X, k, score_bins)
    else:
        raise ValueError(f"Unknown method: {method}")
    return order_by_value(X, labels)


def rfm_score_labels(X, k, bins=5):
    """Business-rule baseline: score R (more recent is better), F and M from 1 to bins
    by percentile rank, sum the scores, and cut the total into k quantile tiers.

    Ties share the average rank, so customers with equal F (e.g. a single order) get the
    same score instead of being split arbitrarily. Heavy ties in the total can yield fewer
    than k tiers; such candidates are recorded and excluded during evaluation.
    """
    directed = pd.DataFrame({"r": -X[:, 0], "f": X[:, 1], "m": X[:, 2]})
    total = np.ceil(directed.rank(pct=True, method="average") * bins).sum(axis=1)
    return pd.qcut(total, k, labels=False, duplicates="drop").to_numpy()


def order_by_value(X, labels):
    """Renumber clusters from lowest to highest value (cluster mean of -R + log F + log M).

    Cluster ids then mean the same thing across methods and runs:
    0 is the lowest-value cluster and k-1 the highest.
    """
    value = pd.Series(-X[:, 0] + X[:, 1] + X[:, 2])
    order = value.groupby(labels).mean().sort_values().index
    mapping = {old: new for new, old in enumerate(order)}
    return np.array([mapping[label] for label in labels])
