"""四种分群方法，输入都是同一个标准化 RFM 矩阵 X（列顺序：R, logF, logM）。"""

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.mixture import GaussianMixture

METHODS = ("kmeans", "gmm", "ward", "rfm_score")


def fit_predict(method, X, k, seed, n_init=10, score_bins=5):
    """返回每名顾客的群号（0..k-1）。"""
    if method == "kmeans":
        # 反复把顾客分给最近的中心、再更新中心；n_init 次随机起点取最优
        labels = KMeans(n_clusters=k, n_init=n_init, random_state=seed).fit_predict(X)
    elif method == "gmm":
        # 假设顾客来自 k 个椭圆形高斯分布，取概率最大的那个
        model = GaussianMixture(n_components=k, covariance_type="full", n_init=n_init, random_state=seed)
        labels = model.fit(X).predict(X)
    elif method == "ward":
        # 自底向上合并，每次合并使群内平方和增加最少的两群；结果不依赖随机种子
        labels = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(X)
    elif method == "rfm_score":
        labels = rfm_score_labels(X, k, score_bins)
    else:
        raise ValueError(f"Unknown method: {method}")
    return order_by_value(X, labels)


def rfm_score_labels(X, k, bins=5):
    """业务分档基线：R（越近越好）、F、M 各按百分位打 1..bins 分，总分再按分位数切成 k 档。

    并列取平均名次，因此 F 相同的顾客（如只买过 1 单）得分相同，不会被任意拆开；
    总分并列过多时可能少于 k 档，评价时会被记录并排除。
    """
    directed = pd.DataFrame({"r": -X[:, 0], "f": X[:, 1], "m": X[:, 2]})
    total = np.ceil(directed.rank(pct=True, method="average") * bins).sum(axis=1)
    return pd.qcut(total, k, labels=False, duplicates="drop").to_numpy()


def order_by_value(X, labels):
    """把群号按“价值”从低到高重排（价值 = -R + logF + logM 的群均值）。

    这样不同方法、不同次运行的群号含义一致：0 号最低价值，k-1 号最高价值。
    """
    value = pd.Series(-X[:, 0] + X[:, 1] + X[:, 2])
    order = value.groupby(labels).mean().sort_values().index
    mapping = {old: new for new, old in enumerate(order)}
    return np.array([mapping[label] for label in labels])
