"""Future work B pre-check, exactly as registered in configs/future_B/precheck.json.

check1: does bulk (pack-multiple) buying exist and vary between customers?
check2: are purchase-form features redundant with B's frozen RFM clusters?
check3: do purchase-form features predict the Discovery category profile beyond scale + RFM?

Reads Profile lines and Profile/Discovery baskets from A's frozen snapshot only. No Validation
or Test rows are read. Stops at the first check that fails its registered rule.
"""

import io
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, spearmanr
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.metrics import adjusted_rand_score
from sklearn.model_selection import KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from online_trade.clustering.features import feature_matrix
from online_trade.taxonomy.category_controls import category_matrix

REPO = Path(__file__).resolve().parents[3]
SNAPSHOT = "2ae672b7ea6edb7f5e1561b6a64823004dea833e"
CONFIG = REPO / "configs/future_B/precheck.json"
OUT = REPO / "results/tables/future_B/precheck"
FORM = ["qty_per_line", "pack_share", "unit_price", "business_hours"]


# ---------------------------------------------------------------- inputs
def _snapshot_csv(path, **kw):
    raw = subprocess.check_output(["git", "show", f"{SNAPSHOT}:{path}"], cwd=REPO)
    return pd.read_csv(io.BytesIO(raw), compression="gzip" if path.endswith(".gz") else None,
                       dtype=str, keep_default_na=False, **kw)


def load_population():
    c = _snapshot_csv("data/processed/B_customer_clustering/customer_clusters.csv")
    c = c.set_index("customer_id")
    for col in ["recency", "frequency", "monetary"]:
        c[col] = c[col].astype(float)
    c["cluster_id"] = c["cluster_id"].astype(int)
    assert len(c) == 2684 and c.cluster_id.value_counts().sort_index().tolist() == [700, 1263, 721]
    return c


def load_profile_lines(population):
    t = _snapshot_csv("data/processed/A_data_preparation/clean_transactions.csv.gz",
                      usecols=["invoice_id", "stock_code", "quantity", "invoice_datetime",
                               "unit_price", "customer_id", "split", "is_valid_basket_item"])
    t = t[t.split.eq("profile") & t.is_valid_basket_item.eq("1") & t.customer_id.isin(population.index)].copy()
    assert set(t.split) == {"profile"}
    t["quantity"] = t.quantity.astype(int)
    t["unit_price"] = t.unit_price.astype(float)
    t["invoice_datetime"] = pd.to_datetime(t.invoice_datetime)
    assert t.invoice_datetime.max() < pd.Timestamp("2010-06-01")
    return t.reset_index(drop=True)


def load_baskets(split):
    b = _snapshot_csv("data/processed/A_data_preparation/baskets.csv.gz")
    b = b[b.split.eq(split) & b.is_eligible_for_main_comparison.eq("1")].reset_index(drop=True)
    assert set(b.split) == {split} and split in ("profile", "discovery")
    return b


# ---------------------------------------------------------------- check 1
def pack_sizes(lines):
    counts = lines.groupby(["stock_code", "quantity"]).size().rename("n").reset_index()
    n_lines = counts.groupby("stock_code").n.sum()
    counts = counts[counts.stock_code.isin(n_lines[n_lines >= 20].index)]
    counts = counts.sort_values(["stock_code", "n", "quantity"], ascending=[True, False, True])
    return counts.drop_duplicates("stock_code").set_index("stock_code").quantity.rename("pack")


def check1(lines, cfg):
    pack = pack_sizes(lines)
    lines["pack"] = lines.stock_code.map(pack)
    denom = lines[lines.pack.notna()].copy()
    denom["is_pack"] = (denom.pack >= 2) & (denom.quantity >= denom.pack) & (denom.quantity % denom.pack == 0)
    lines["is_pack"] = denom.is_pack.reindex(lines.index)  # NaN outside the denominator
    lines["is_generic_pack"] = (lines.quantity >= 6) & (lines.quantity % 6 == 0)

    per_cust = denom.groupby("customer_id").is_pack.agg(["mean", "size"])
    eligible = per_cust[per_cust["size"] >= 5]["mean"]
    q1, q3 = eligible.quantile([0.25, 0.75])

    baskets = lines.groupby("invoice_id").agg(customer_id=("customer_id", "first"),
                                              dt=("invoice_datetime", "first"),
                                              n_items=("stock_code", "nunique"))
    baskets["business"] = (baskets.dt.dt.weekday < 5) & baskets.dt.dt.hour.between(9, 16)

    lines["month"] = lines.invoice_datetime.dt.to_period("M")
    rhos = []
    for _, g in lines.groupby(["stock_code", "month"]):
        if len(g) >= 10 and g.quantity.nunique() > 1 and g.unit_price.nunique() > 1:
            rhos.append(spearmanr(g.quantity, g.unit_price).statistic)
    rhos = np.array(rhos)

    top_q = lines.quantity.value_counts().head(20)
    bins = pd.cut(baskets.n_items, [0, 1, 5, 10, 20, 50, np.inf], labels=["1", "2-5", "6-10", "11-20", "21-50", "51+"])
    res = {
        "n_lines": int(len(lines)), "n_baskets": int(len(baskets)), "n_customers": int(lines.customer_id.nunique()),
        "items_with_pack": int(len(pack)), "denominator_lines": int(len(denom)),
        "denominator_share_of_lines": float(len(denom) / len(lines)),
        "pack_size_distribution": {str(k): int(v) for k, v in pack.value_counts().head(15).items()},
        "pack_line_share": float(denom.is_pack.mean()),
        "generic_pack_line_share": float(lines.is_generic_pack.mean()),
        "customers_with_5_lines": int(len(eligible)),
        "customer_pack_share_quantiles": {str(q): float(eligible.quantile(q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
        "share_customers_pack_ge_half": float((eligible >= 0.5).mean()),
        "customer_pack_share_iqr": float(q3 - q1),
        "basket_items_quantiles": {str(q): float(baskets.n_items.quantile(q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
        "basket_items_bins": {str(k): float(v) for k, v in bins.value_counts(normalize=True).sort_index().items()},
        "business_hours_order_share": float(baskets.business.mean()),
        "tier_pricing": {"item_months": int(len(rhos)), "median_rho": float(np.median(rhos)),
                         "share_rho_negative": float((rhos < 0).mean())},
        "top_quantities": [{"quantity": int(k), "lines": int(v), "share": float(v / len(lines))} for k, v in top_q.items()],
    }
    rule = cfg["check1_bulk_buying_exists"]["pass_rule"]
    res["P1_1"] = res["pack_line_share"] >= 0.30
    res["P1_2"] = 0.20 <= res["share_customers_pack_ge_half"] <= 0.80
    res["P1_3"] = res["customer_pack_share_iqr"] >= 0.20
    res["pass"] = bool(res["P1_1"] and res["P1_2"] and res["P1_3"])
    res["use_relative_price"] = res["tier_pricing"]["median_rho"] <= -0.30
    res["rule_text"] = rule
    return res, lines, baskets, per_cust


# ---------------------------------------------------------------- customer form features
def customer_features(lines, baskets, per_cust, population, relative_price):
    price = lines.unit_price
    if relative_price:
        price = price / lines.groupby(["stock_code", "month"]).unit_price.transform("median")
    lines = lines.assign(price=price)
    by = lines.groupby("customer_id")
    f = pd.DataFrame({
        "n_baskets": np.log1p(baskets.groupby("customer_id").size()),
        "basket_size": np.log1p(baskets.groupby("customer_id").n_items.mean()),
        "qty_per_line": np.log1p(by.quantity.median()),
        "unit_price": by.price.median(),
        "business_hours": baskets.groupby("customer_id").business.mean(),
    }).reindex(population.index)
    assert f.notna().all().all(), "every population customer must have Profile lines"
    cap = f.unit_price.quantile(0.95)
    f["unit_price"] = f.unit_price.clip(upper=cap) / cap
    ok = per_cust[per_cust["size"] >= 5]["mean"]
    f["pack_share"] = ok.reindex(f.index)
    f["has_5_lines"] = f.pack_share.notna()
    f["pack_share"] = f.pack_share.fillna(ok.median())
    return f


# ---------------------------------------------------------------- check 2
def purity(a, b):
    """Sokol & Holy (2021) eq. 13: share of objects in the majority b-cluster of their a-cluster."""
    return float(pd.crosstab(a, b).max(axis=1).sum() / len(a))


def check2(features, population):
    rfm_x = feature_matrix(population)
    r2 = {}
    for col in ["basket_size", "qty_per_line", "pack_share", "unit_price", "business_hours"]:
        y = features[col].to_numpy()
        r2[col] = float(LinearRegression().fit(rfm_x, y).score(rfm_x, y))
    sub = features[features.has_5_lines]
    form_type = np.where(sub.pack_share >= 0.5, "bulk", "scattered")
    cluster = population.loc[sub.index, "cluster_id"].to_numpy()
    tab = pd.crosstab(pd.Series(form_type, name="form_type"), pd.Series(cluster, name="cluster"))
    chi2 = chi2_contingency(tab)[0]
    cramer = float(np.sqrt(chi2 / (tab.values.sum() * (min(tab.shape) - 1))))
    bulk_in_c2 = float(tab.loc["bulk", 2] / tab.loc["bulk"].sum()) if "bulk" in tab.index else float("nan")
    scat_in_c01 = float(tab.loc["scattered", [0, 1]].sum() / tab.loc["scattered"].sum())
    means = features.join(population.cluster_id).groupby("cluster_id")[
        ["basket_size", "qty_per_line", "pack_share", "unit_price", "business_hours"]].mean()
    res = {
        "n_customers_crosstab": int(len(sub)),
        "crosstab_counts": {k: {str(c): int(v) for c, v in row.items()} for k, row in tab.iterrows()},
        "crosstab_row_shares": {k: {str(c): float(v) for c, v in row.items()}
                                for k, row in tab.div(tab.sum(axis=1), axis=0).iterrows()},
        "ARI": float(adjusted_rand_score(form_type, cluster)),
        "cramers_v": cramer,
        "purity_form_given_cluster": purity(cluster, form_type),
        "purity_cluster_given_form": purity(form_type, cluster),
        "bulk_share_in_C2": bulk_in_c2,
        "scattered_share_in_C0_C1": scat_in_c01,
        "R2_on_RFM": r2,
        "feature_means_by_cluster_logscale": {str(k): {c: float(v) for c, v in row.items()} for k, row in means.iterrows()},
    }
    res["S2_a"] = bool(bulk_in_c2 >= 0.80 and scat_in_c01 >= 0.80)
    res["S2_b"] = bool(all(r2[c] >= 0.60 for c in ["basket_size", "qty_per_line", "pack_share"]))
    res["stop"] = bool(res["S2_a"] or res["S2_b"])
    return res


# ---------------------------------------------------------------- check 3
def category_profile(split, taxonomy, population):
    b = load_baskets(split)
    b = b[b.customer_id.isin(population.index)].reset_index(drop=True)
    x, cols = category_matrix(b, taxonomy)
    prof = pd.DataFrame(x.astype(float), columns=cols).groupby(b.customer_id.to_numpy()).mean()
    n = b.groupby("customer_id").size()
    return prof, n


def bray_curtis_rows(p, a):
    den = (p + a).sum(axis=1)
    return np.where(den > 0, np.abs(p - a).sum(axis=1) / np.where(den > 0, den, 1), 0.0)


def cv_bc(model_fn, x, y, folds):
    pred = np.zeros_like(y)
    for tr, te in folds:
        m = model_fn().fit(x[tr], y[tr])
        pred[te] = m.predict(x[te])
    return bray_curtis_rows(np.clip(pred, 0, 1), y)


def check3(features, population, taxonomy, log=print):
    target, n_disc = category_profile("discovery", taxonomy, population)
    ids = n_disc[n_disc >= 3].index.intersection(population.index)
    y = target.loc[ids].to_numpy()
    ceiling, _ = category_profile("profile", taxonomy, population)
    ceiling = ceiling.reindex(population.index, fill_value=0.0).loc[ids].to_numpy()
    rfm = pd.DataFrame(feature_matrix(population), index=population.index).loc[ids].to_numpy()
    f = features.loc[ids]
    g1 = f[["n_baskets", "basket_size"]].to_numpy()
    form = f[FORM].to_numpy()
    groups = {"G1": g1, "G2": np.hstack([g1, rfm]), "G3": np.hstack([g1, rfm, form]),
              "G4": np.hstack([g1, rfm, form, ceiling])}
    folds = list(KFold(5, shuffle=True, random_state=20261122).split(y))
    models = {
        "ridge": lambda: make_pipeline(StandardScaler(), RidgeCV(alphas=[0.1, 1, 10, 100, 1000], cv=5,
                                                                 scoring="neg_mean_squared_error")),
        "random_forest": lambda: RandomForestRegressor(n_estimators=200, min_samples_leaf=5, max_features=0.5,
                                                       random_state=0, n_jobs=-1),
    }
    bins = pd.qcut(f.basket_size.rank(method="first"), 5, labels=False).to_numpy()
    res = {"n_customers": int(len(ids)), "n_categories": int(y.shape[1]), "models": {}}
    for name, fn in models.items():
        bc = {g: cv_bc(fn, x, y, folds) for g, x in groups.items()}
        mean = {g: float(v.mean()) for g, v in bc.items()}
        gap = (mean["G2"] - mean["G3"]) / (mean["G2"] - mean["G4"])
        rng = np.random.default_rng(20261121)
        diff = bc["G2"] - bc["G3"]
        boot = np.array([diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(2000)])
        n_perm = 200 if name == "ridge" else 100
        perm = []
        for s in range(n_perm):
            r = np.random.default_rng(s)
            idx = np.arange(len(ids))
            for b in range(5):
                m = np.where(bins == b)[0]
                idx[m] = r.permutation(m)
            bc3 = cv_bc(fn, np.hstack([g1, rfm, form[idx]]), y, folds).mean()
            perm.append((mean["G2"] - bc3) / (mean["G2"] - mean["G4"]))
            if (s + 1) % 25 == 0:
                log(f"  {name}: permutation {s + 1}/{n_perm}")
        perm = np.array(perm)
        q95 = float(np.quantile(perm, 0.95))
        res["models"][name] = {
            "mean_BC": mean, "gap_closed": float(gap),
            "BC_G2_minus_G3": {"mean": float(diff.mean()), "ci95": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))]},
            "permutation": {"n": n_perm, "median": float(np.median(perm)), "q95": q95,
                            "empirical_p": float((1 + (perm >= gap).sum()) / (1 + n_perm))},
            "pass": bool(gap >= 0.10 and gap > q95),
        }
        log(f"  {name}: BC {mean} gap_closed {gap:.4f} perm q95 {q95:.4f}")
    res["pass"] = bool(all(m["pass"] for m in res["models"].values()))
    return res


# ---------------------------------------------------------------- driver
def _dump(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=lambda o: o.item()) + "\n")


def run(log=print):
    cfg = json.loads(CONFIG.read_text())
    assert cfg["status"] == "registered_before_computation"
    population = load_population()
    lines = load_profile_lines(population)
    log(f"Profile lines: {len(lines):,}")

    r1, lines, baskets, per_cust = check1(lines, cfg)
    _dump("check1.json", r1)
    log(f"check1: pack {r1['pack_line_share']:.3f}, cust>=0.5 {r1['share_customers_pack_ge_half']:.3f}, "
        f"IQR {r1['customer_pack_share_iqr']:.3f}, tier rho {r1['tier_pricing']['median_rho']:.3f} -> pass={r1['pass']}")
    summary = {"check1_pass": r1["pass"]}
    if not r1["pass"]:
        _dump("summary.json", summary)
        return summary

    features = customer_features(lines, baskets, per_cust, population, r1["use_relative_price"])
    features.to_csv(OUT / "customer_form_features.csv", index_label="customer_id")
    r2 = check2(features, population)
    _dump("check2.json", r2)
    log(f"check2: bulk in C2 {r2['bulk_share_in_C2']:.3f}, scattered in C0/C1 {r2['scattered_share_in_C0_C1']:.3f}, "
        f"R2 {r2['R2_on_RFM']}, ARI {r2['ARI']:.3f} -> stop={r2['stop']}")
    summary["check2_stop"] = r2["stop"]
    if r2["stop"]:
        _dump("summary.json", summary)
        return summary

    taxonomy = pd.read_csv(REPO / "data/taxonomy/item_taxonomy_v1.csv", dtype=str, keep_default_na=False)
    r3 = check3(features, population, taxonomy, log)
    _dump("check3.json", r3)
    summary["check3_pass"] = r3["pass"]
    _dump("summary.json", summary)
    log(f"summary: {summary}")
    return summary
