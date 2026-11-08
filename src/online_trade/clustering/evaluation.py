"""候选分群的四项证据与预先约定的选择规则。"""

import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score, silhouette_score

from .methods import METHODS, fit_predict


def bootstrap_ari(method, X, k, reference, seed, repeats, **method_args):
    """稳定性：有放回抽样后重新分群，只在被抽中的顾客上与全量结果比较 ARI。

    ARI = 1 表示两次分组完全一致，约 0 表示与随机分组无异。返回 (均值, 标准差)。
    """
    rng = np.random.default_rng(seed)
    scores = []
    for _ in range(repeats):
        index = rng.choice(len(X), size=len(X), replace=True)
        labels = fit_predict(method, X[index], k, seed=int(rng.integers(2**31)), **method_args)
        first = pd.Series(labels).groupby(index).first()  # 同一顾客被抽中多次只算一次
        scores.append(adjusted_rand_score(reference[first.index], first.to_numpy()))
    return float(np.mean(scores)), float(np.std(scores))


def describe_candidate(method, k, X, labels, rfm, stability):
    """一个候选（方法 × K）的比较表行。"""
    sizes = np.bincount(labels, minlength=k)
    baskets = rfm["profile_baskets"].groupby(labels).sum()
    return {
        "method": method,
        "k": k,
        "n_groups": int(len(np.unique(labels))),
        # 分离度：同群近、异群远则高，范围 -1..1；所有方法在同一空间计算
        "silhouette": round(float(silhouette_score(X, labels)), 4),
        "bootstrap_ari_mean": round(stability[0], 4),
        "bootstrap_ari_std": round(stability[1], 4),
        "min_cluster_share": round(float(sizes.min() / len(labels)), 4),
        "min_cluster_profile_baskets": int(baskets.min()),
        "cluster_sizes": "/".join(map(str, sizes)),
    }


def select_candidate(table, rule):
    """按配置中的规则选择：先淘汰，再比轮廓系数，分数接近时取更小的 K、再按方法顺序。"""
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
