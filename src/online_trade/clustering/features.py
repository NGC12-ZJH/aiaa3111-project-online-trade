"""Profile-period RFM features: one row per profile customer."""

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


def load_profile_orders(orders_path):
    """Read task A's orders.csv.gz and keep profile-period orders with a customer id."""
    orders = pd.read_csv(orders_path, dtype=str)
    profile = orders[orders["split"].eq("profile") & orders["is_identified_customer"].eq("1")].copy()
    profile["invoice_datetime"] = pd.to_datetime(profile["invoice_datetime"])
    for column in ["gross_purchase_amount", "net_amount", "basket_size"]:
        profile[column] = profile[column].astype(float)
    return profile


def build_rfm(profile_orders, cutoff):
    """Aggregate RFM per customer.

    R = days from the last valid purchase to the cutoff; F = number of distinct valid
    orders; M = sum of gross purchase amount. monetary_net (net of returns) is only used
    for sensitivity checks; profile_baskets is used to check cluster sample sizes.
    """
    valid = profile_orders[profile_orders["is_valid_rfm_order"].eq("1")]
    by_customer = valid.groupby("customer_id")
    rfm = pd.DataFrame({
        "recency": (pd.Timestamp(cutoff) - by_customer["invoice_datetime"].max()).dt.total_seconds() / 86400,
        "frequency": by_customer["basket_id"].nunique(),
        "monetary": by_customer["gross_purchase_amount"].sum(),
        "mean_basket_size": by_customer["basket_size"].mean(),
    })
    # Net amount must include cancellation/return orders, so sum over all profile orders
    rfm["monetary_net"] = profile_orders.groupby("customer_id")["net_amount"].sum().reindex(rfm.index)
    eligible = profile_orders[profile_orders["is_eligible_for_main_comparison"].eq("1")]
    rfm["profile_baskets"] = eligible.groupby("customer_id").size().reindex(rfm.index, fill_value=0)

    # Stop if the customer list differs from task A's profile-customer flag
    expected = set(profile_orders.loc[profile_orders["is_profile_customer"].eq("1"), "customer_id"])
    if set(rfm.index) != expected:
        raise ValueError(f"RFM customers ({len(rfm)}) differ from A's profile customers ({len(expected)})")
    return rfm.sort_index()


def feature_matrix(rfm, monetary="monetary", log_recency=False):
    """Clustering input: standardized [R, log1p(F), log1p(M)].

    F and M are heavily right-skewed, so the log keeps a few large buyers from forming
    their own clusters; R stays in raw days. Standardizing gives the three features equal
    weight. The scaler is fit on profile customers only and never refit.
    """
    recency = np.log1p(rfm["recency"]) if log_recency else rfm["recency"]
    raw = np.column_stack([
        recency,
        np.log1p(rfm["frequency"]),
        np.log1p(rfm[monetary].clip(lower=0)),  # net amount can be negative: clip at 0 before the log
    ])
    return StandardScaler().fit_transform(raw)
