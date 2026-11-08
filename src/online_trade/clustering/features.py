"""Profile 期 RFM 特征：每名 Profile 顾客一行。"""

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


def load_profile_orders(orders_path):
    """读取 A 的 orders.csv.gz，只保留 Profile 期、有顾客编号的订单。"""
    orders = pd.read_csv(orders_path, dtype=str)
    profile = orders[orders["split"].eq("profile") & orders["is_identified_customer"].eq("1")].copy()
    profile["invoice_datetime"] = pd.to_datetime(profile["invoice_datetime"])
    for column in ["gross_purchase_amount", "net_amount", "basket_size"]:
        profile[column] = profile[column].astype(float)
    return profile


def build_rfm(profile_orders, cutoff):
    """按顾客汇总 RFM。

    R = 截止日 - 最后一次有效购买（天）；F = 不同有效订单数；M = 毛购买金额之和。
    monetary_net（含退款订单的净额）只用于敏感性检查；profile_baskets 用于检查群体样本量。
    """
    valid = profile_orders[profile_orders["is_valid_rfm_order"].eq("1")]
    by_customer = valid.groupby("customer_id")
    rfm = pd.DataFrame({
        "recency": (pd.Timestamp(cutoff) - by_customer["invoice_datetime"].max()).dt.total_seconds() / 86400,
        "frequency": by_customer["basket_id"].nunique(),
        "monetary": by_customer["gross_purchase_amount"].sum(),
        "mean_basket_size": by_customer["basket_size"].mean(),
    })
    # 净额要包含取消/退货订单，所以在全部 Profile 订单上汇总
    rfm["monetary_net"] = profile_orders.groupby("customer_id")["net_amount"].sum().reindex(rfm.index)
    eligible = profile_orders[profile_orders["is_eligible_for_main_comparison"].eq("1")]
    rfm["profile_baskets"] = eligible.groupby("customer_id").size().reindex(rfm.index, fill_value=0)

    # 与 A 的 Profile 顾客定义核对，人数或名单不一致就停止
    expected = set(profile_orders.loc[profile_orders["is_profile_customer"].eq("1"), "customer_id"])
    if set(rfm.index) != expected:
        raise ValueError(f"RFM customers ({len(rfm)}) differ from A's profile customers ({len(expected)})")
    return rfm.sort_index()


def feature_matrix(rfm, monetary="monetary", log_recency=False):
    """聚类输入：[R, log1p(F), log1p(M)] 标准化。

    F、M 极度右偏，取对数防止少数大客户单独成群；标准化让三项量纲一致。
    标准化只用这批 Profile 顾客拟合，之后不再重算。
    """
    recency = np.log1p(rfm["recency"]) if log_recency else rfm["recency"]
    raw = np.column_stack([
        recency,
        np.log1p(rfm["frequency"]),
        np.log1p(rfm[monetary].clip(lower=0)),  # 净额可能为负，截到 0 再取对数
    ])
    return StandardScaler().fit_transform(raw)
