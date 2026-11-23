"""Build reproducible pre-Test shopping baskets and as-of features."""
from collections import defaultdict
from dataclasses import dataclass
import hashlib
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import RobustScaler
from threadpoolctl import threadpool_limits

SNAPSHOT = "2ae672b7ea6edb7f5e1561b6a64823004dea833e"
PROFILE_END = "2010-06-01"
DISCOVERY_END = "2010-12-01"
CUTOFF = "2011-06-01"
SEED = 1122


@dataclass
class Retail:
    orders: pd.DataFrame
    items: dict
    cancellations: pd.DataFrame
    taxonomy: pd.DataFrame
    audit: dict

    def between(self, start, end, customers=None):
        assert start < end <= CUTOFF
        frame = self.orders.loc[self.orders.date.ge(start) & self.orders.date.lt(end)]
        return frame if customers is None else frame.loc[frame.customer_id.isin(customers)]


def pretest_csv(repo, name, usecols, types):
    path = f"{SNAPSHOT}:data/processed/A_data_preparation/{name}.csv.gz"
    frames = []
    with subprocess.Popen(["git", "-C", str(repo), "show", path], stdout=subprocess.PIPE) as git:
        for chunk in pd.read_csv(
            git.stdout, compression="gzip", usecols=usecols, dtype=types, keep_default_na=False,
            chunksize=125000,
        ):
            select = chunk.invoice_datetime.lt(CUTOFF) & chunk.split.isin(["profile", "discovery", "validation"])
            frames.append(chunk.loc[select])
        assert git.wait() == 0
    return pd.concat(frames, ignore_index=True)


def load_retail(repo, cache):
    taxonomy_path = repo / "data/taxonomy/item_taxonomy_v1.csv"
    tax_digest = hashlib.sha256(taxonomy_path.read_bytes()).hexdigest()
    tag = f"retail-v3-{SNAPSHOT[:12]}-{tax_digest[:12]}-{CUTOFF}.pkl"
    if cache and (cache / tag).is_file():
        return Retail(**pd.read_pickle(cache / tag))
    tax = pd.read_csv(taxonomy_path, dtype=str, keep_default_na=False)
    assert tax.stock_code.is_unique
    tx_names = ("invoice_id", "stock_code", "quantity", "invoice_datetime", "unit_price", "customer_id",
                "split", "is_cancelled_invoice", "is_canonical_source_row",
                "is_exact_duplicate_candidate", "is_valid_basket_item")
    tx = pretest_csv(repo, "clean_transactions", tx_names, {
        "invoice_id": str, "stock_code": str, "invoice_datetime": str, "customer_id": str, "split": str,
    })
    out_names = ("basket_id", "customer_id", "invoice_datetime", "invoice_date", "country", "split",
                 "gross_purchase_amount", "is_valid_order")
    orders = pretest_csv(repo, "orders", out_names, {key: str for key in out_names if key not in
                                                    ("gross_purchase_amount", "is_valid_order")})
    orders = orders.loc[orders.is_valid_order.eq(1)].rename(columns={"invoice_date": "date", "basket_id": "id"})
    orders = orders.sort_values(["invoice_datetime", "id"]).reset_index(drop=True)
    assert orders.id.is_unique
    audit = {"snapshot": SNAPSHOT, "taxonomy_sha256": tax_digest, "cutoff_exclusive": CUTOFF}
    audit["pretest_raw_canonical_rows"] = int(tx.is_canonical_source_row.eq(1).sum())
    audit["orders_by_split"] = {k: int(v) for k, v in orders.split.value_counts().items()}
    audit["maximum_date_in_analysis"] = orders.date.max()
    cancelled = tx.loc[
        tx.is_canonical_source_row.eq(1) & tx.is_cancelled_invoice.eq(1) & tx.customer_id.ne(""),
        ["invoice_id", "customer_id", "invoice_datetime"],
    ].drop_duplicates(["invoice_id", "customer_id"])
    cancelled["date"] = cancelled.invoice_datetime.str[:10]
    lines = tx.loc[tx.is_valid_basket_item.eq(1), ["invoice_id", "stock_code", "quantity", "unit_price"]].copy()
    lines = lines.loc[lines.invoice_id.isin(orders.id)]
    assert lines.quantity.gt(0).all() and lines.unit_price.gt(0).all()
    labels = tax.set_index("stock_code")
    lines["category"] = lines.stock_code.map(labels.l2_id).fillna("other")
    lines["season"] = lines.stock_code.map(labels.season).fillna("")
    audit["unmapped_positive_lines"] = int((~lines.stock_code.isin(labels.index)).sum())
    audit["usable_sales_lines"] = len(lines)
    audit["identified_cancellation_invoices"] = len(cancelled)
    items = {}
    for invoice, group in lines.groupby("invoice_id", sort=False):
        items[invoice] = tuple(zip(group.stock_code, group.category, group.quantity.astype(float),
                                   group.unit_price.astype(float), group.season))
    assert set(orders.id) == set(items)
    assert orders.date.max() < CUTOFF and cancelled.date.max() < CUTOFF
    first = orders.loc[orders.customer_id.ne("")].groupby("customer_id").date.min()
    orders["first_day"] = orders.customer_id.map(first).fillna("")
    orders["first_order"] = orders.customer_id.ne("") & ~orders.customer_id.duplicated()
    payload = {"orders": orders, "items": items, "cancellations": cancelled, "taxonomy": tax, "audit": audit}
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
        pd.to_pickle(payload, cache / tag)
    return Retail(**payload)


def features(lines, low_price, high_price):
    qty = np.array([x[2] for x in lines], dtype=float)
    price = np.array([x[3] for x in lines], dtype=float)
    if not qty.size:
        return np.zeros(7)
    by_sku = defaultdict(float)
    for sku, _, q, _, _ in lines:
        by_sku[sku] += q
    return np.array([
        qty.sum(), len(by_sku), max(by_sku.values()) / qty.sum(), np.median(price),
        qty[price <= low_price].sum() / qty.sum(), qty[price > high_price].sum() / qty.sum(),
        max(by_sku.values()),
    ])


def price_bands(retail, orders):
    prices = [line[3] for invoice in orders.id for line in retail.items[invoice]]
    return tuple(np.quantile(prices, [.33, .67]))


def asof_profile(retail, stop, price, lookback=None):
    start = "2009-12-01" if lookback is None else lookback
    history = retail.between(start, stop)
    rows = []
    for order in history.itertuples(index=False):
        if order.customer_id:
            rows.append((order.customer_id, order.date, order.gross_purchase_amount, order.country,
                         *features(retail.items[order.id], *price)))
    df = pd.DataFrame(rows, columns=["id", "date", "amount", "country", "qty", "skus", "concentration",
                                    "price", "low", "high", "max_sku"])
    grouped = df.groupby("id", sort=True)
    shape = grouped[["qty", "skus", "concentration", "price", "low", "high", "max_sku"]].median()
    dates = pd.to_datetime(grouped.date.max())
    shape["recency"] = (pd.Timestamp(stop) - dates).dt.days
    shape["frequency"] = grouped.size()
    shape["monetary"] = grouped.amount.sum()
    shape["nonuk"] = grouped.country.agg(lambda x: (x.ne("") & x.ne("United Kingdom")).mean())
    shape["country_missing"] = grouped.country.agg(lambda x: x.eq("").mean())
    c = retail.cancellations
    cancellation_count = c.loc[c.date.ge(start) & c.date.lt(stop)].groupby("customer_id").size()
    cancellation_count = cancellation_count.reindex(shape.index, fill_value=0)
    shape["cancel_share"] = cancellation_count / (shape["frequency"] + cancellation_count)
    return shape


def log_numeric(values, log_columns):
    result = np.asarray(values, dtype=float).copy()
    result[:, log_columns] = np.log1p(result[:, log_columns])
    return result


class FormCluster:
    def __init__(self, values, log_columns, k=3):
        self.log_columns = log_columns
        logged = log_numeric(values, log_columns)
        self.low, self.high = np.quantile(logged, [.01, .99], axis=0)
        clipped = np.clip(logged, self.low, self.high)
        self.scaler = RobustScaler().fit(clipped)
        with threadpool_limits(limits=1):
            self.model = KMeans(n_clusters=k, n_init=12, random_state=SEED).fit(self.scaler.transform(clipped))
        raw = self.distances(values)
        assigned = raw.argmin(axis=1)
        self.radii = np.array([np.quantile(raw[assigned == i, i], .95) for i in range(k)])
        self.labels = assigned

    def distances(self, values):
        return self.model.transform(self.scaler.transform(np.clip(
            log_numeric(values, self.log_columns), self.low, self.high)))

    def route(self, values):
        distances = self.distances(values)
        labels = distances.argmin(axis=1)
        return labels, distances[np.arange(len(labels)), labels] <= self.radii[labels] + 1e-9


def build_view(retail, orders, price):
    data = orders.reset_index(drop=True).copy()
    baskets, seen, targets, vectors, seasonal = [], [], [], [], []
    for invoice in data.id:
        lines = retail.items[invoice]
        basket = frozenset(line[1] for line in lines if line[1] != "other")
        baskets.append(basket)
        has_season = any(line[4] not in ("", "none", "unknown") for line in lines if line[1] != "other")
        seasonal.append(has_season)
        if len(basket) < 2:
            seen.append(frozenset())
            targets.append("")
            vectors.append(np.zeros(7))
            continue
        labels = sorted(basket)
        digest = hashlib.sha256(f"retail1122-v1|{invoice}".encode()).digest()
        target = labels[int.from_bytes(digest[:8], "big") % len(labels)]
        # Omit all lines belonging to the target before computing any cart feature.
        remainder = [line for line in lines if line[1] != target]
        seen.append(basket - {target})
        targets.append(target)
        vectors.append(features(remainder, *price))
    data["seasonal_order"] = seasonal
    data["has_target"] = [bool(x) for x in targets]
    data["basket"] = baskets
    data["observed"] = seen
    data["target"] = targets
    data["cart"] = list(vectors)
    return data


def group_random(profile, labels, seed):
    # Keep the selected labels' counts exactly within Profile purchase-frequency bins.
    buckets = pd.cut(profile.frequency, bins=[0, 1, 2, 4, 8, 16, 32, np.inf], labels=False)
    rng = np.random.default_rng(seed)
    shuffled = np.array(labels).copy()
    for indices in buckets.groupby(buckets).indices.values():
        shuffled[indices] = rng.permutation(shuffled[indices])
    return dict(zip(profile.index, map(str, shuffled)))


def frequency_groups(profile):
    # Choose cutpoints between observed frequencies, never split equal values.
    counts = profile.frequency.value_counts().sort_index()
    cumulative = counts.cumsum()
    size = len(profile)
    first = (cumulative.iloc[:-2] - size / 3).abs().idxmin()
    last = (cumulative.loc[cumulative.index > first].iloc[:-1] - 2 * size / 3).abs().idxmin()
    return np.digitize(profile.frequency.to_numpy(), [first, last], right=True), [int(first), int(last)]

