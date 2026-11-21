"""Shared counting engine for the registered extra evaluations E10, E9 and E5.

Every list is built from Discovery counts and evaluated on later periods with the same
category mapping as C and D (taxonomy_v1 l2, `other` dropped, one count per category per
basket, empty baskets kept in the denominator). Protocols: configs/extra_eval/*.json.

Test is locked: `load_period("test")` refuses to run until configs/extra_eval/FREEZE.json exists.
"""

import hashlib
import io
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

from online_trade.taxonomy.category_controls import Pool, allocate

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = "2ae672b7ea6edb7f5e1561b6a64823004dea833e"
BASKETS_SHA256 = "30aef702f812ab42224271871271daff5b4e37a594696eee82208252198367bf"
LOCAL = ROOT / "data/processed/local"
FREEZE = ROOT / "configs/extra_eval/FREEZE.json"
WINDOWS = {"discovery": ("2010-06-01", "2010-12-01"), "validation": ("2010-12-01", "2011-06-01"),
           "test": ("2011-06-01", "2011-12-01")}
EXPECTED_ORDERS = {"discovery": 7521, "validation": 4862, "test": 5730}
P5 = dict(support=0.02, confidence=0.4, lift=1.3, joint=20, antecedent=20, increment=0.10)
BUDGETS = (20, 50, 100)
GROUPS = ("0", "1", "2")
CONTROLS = {"A1": ("random_groups_A1_profile_frequency.csv", range(1000, 1100)),
            "S": ("random_groups.csv", range(42, 62)),
            "A2": ("random_groups_A2_discovery_baskets.csv", range(1000, 1100))}


def config(name):
    return json.loads((ROOT / "configs/extra_eval" / f"{name}.json").read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- inputs
def taxonomy_columns():
    tax = pd.read_csv(ROOT / "data/taxonomy/item_taxonomy_v1.csv", dtype=str, keep_default_na=False)
    mapping = tax.set_index("stock_code").l2_id.to_dict()
    cols = sorted({v for v in mapping.values() if v not in ("other", "")})
    return mapping, cols


def load_period(period):
    """Eligible (Profile-customer) baskets of one period and their basket x l2 matrix."""
    if period == "test" and not FREEZE.exists():
        raise PermissionError("Test is locked until configs/extra_eval/FREEZE.json is committed")
    raw = subprocess.check_output(["git", "show", f"{SNAPSHOT}:data/processed/A_data_preparation/baskets.csv.gz"],
                                  cwd=ROOT)
    assert hashlib.sha256(raw).hexdigest() == BASKETS_SHA256, "snapshot baskets changed"
    b = pd.read_csv(io.BytesIO(raw), compression="gzip", dtype=str, keep_default_na=False)
    b = b[b.split.eq(period) & b.is_eligible_for_main_comparison.eq("1")].reset_index(drop=True)
    lo, hi = WINDOWS[period]
    assert len(b) == EXPECTED_ORDERS[period] and b.basket_id.is_unique
    assert ((b.invoice_date >= lo) & (b.invoice_date < hi)).all()
    mapping, cols = taxonomy_columns()
    index = {c: i for i, c in enumerate(cols)}
    x = np.zeros((len(b), len(cols)), dtype=bool)
    for i, items in enumerate(b["items"]):
        codes = json.loads(items)
        assert all(c in mapping for c in codes), "unmapped stock code"
        cats = {mapping[c] for c in codes if mapping[c] not in ("other", "")}
        x[i, [index[c] for c in cats]] = True
    return b[["basket_id", "customer_id", "gross_purchase_amount"]].copy(), x, cols


def load_systems():
    """Customer -> group mapping for G, L and every random seed, in a fixed order."""
    true = pd.read_csv(LOCAL / "customer_clusters.csv", dtype=str)
    assert len(true) == 2684 and true.customer_id.is_unique
    systems = [("GL", "G", ""), ("GL", "L", "")]
    maps = {("GL", "G", ""): {c: "GLOBAL" for c in true.customer_id},
            ("GL", "L", ""): dict(zip(true.customer_id, true.cluster_id))}
    for control, (name, seeds) in CONTROLS.items():
        r = pd.read_csv(LOCAL / name, dtype=str)
        assert set(r.seed) == set(map(str, seeds))
        for seed, z in r.groupby("seed", sort=False):
            assert z.customer_id.is_unique and set(z.customer_id) == set(true.customer_id)
            key = (control, "R", seed)
            systems.append(key)
            maps[key] = dict(zip(z.customer_id, z.random_group_id))
    return systems, maps


class Period:
    """One period's baskets, combo hits, customer index and per-system basket groups."""

    def __init__(self, name, pool, systems, maps):
        self.name = name
        self.baskets, x, cols = load_period(name)
        assert cols == pool.cols
        self.n = len(self.baskets)
        self.x = x
        self.hits = combo_hits(x, pool.combos)              # combos x baskets (bool, csr)
        self.hits_csc = self.hits.tocsc()
        self.customers, cust_idx = np.unique(self.baskets.customer_id.to_numpy(), return_inverse=True)
        self.cust_of_basket = cust_idx
        self.cust_matrix = sparse.csr_matrix((np.ones(self.n, dtype=np.float64), (cust_idx, np.arange(self.n))),
                                             shape=(len(self.customers), self.n))
        self.orders_per_customer = np.asarray(self.cust_matrix.sum(1)).ravel()
        self.groups = {key: self.baskets.customer_id.map(maps[key]).to_numpy() for key in systems}
        self.cust_groups = {key: pd.Series(self.customers).map(maps[key]).to_numpy() for key in systems}
        for g in self.groups.values():
            assert not pd.isna(g).any()
        self._cust_combo = None

    @property
    def cust_combo(self):
        """customers x combos joint counts (csc), built lazily for E5."""
        if self._cust_combo is None:
            self._cust_combo = (self.cust_matrix @ self.hits.T.astype(np.float32)).tocsc()
        return self._cust_combo

    def covered(self, combo_rows, basket_mask=None):
        """Boolean vector of baskets containing at least one of the combos."""
        rows = np.fromiter(combo_rows, dtype=np.int64)
        if len(rows) == 0:
            hit = np.zeros(self.n, bool)
        else:
            hit = np.asarray(self.hits[rows].sum(0)).ravel() > 0
        return hit if basket_mask is None else hit & basket_mask

    def customer_hits(self, covered):
        return np.asarray(self.cust_matrix @ covered.astype(np.float64)).ravel()

    def summary(self, covered):
        hits = self.customer_hits(covered)
        return dict(covered_orders=int(covered.sum()), coverage=covered.mean(),
                    customer_macro_coverage=float(np.mean(hits / self.orders_per_customer)))


def combo_hits(x, combos):
    rows, cols = [], []
    for r, c in enumerate(combos):
        hit = np.flatnonzero(x[:, list(c)].all(1))
        rows.append(np.full(len(hit), r))
        cols.append(hit)
    return sparse.csr_matrix((np.ones(sum(map(len, rows)), dtype=bool), (np.concatenate(rows), np.concatenate(cols))),
                             shape=(len(combos), x.shape[0]))


# ---------------------------------------------------------------- rules
def scope_counts(period, pool, key):
    """Counts of every pool combination in every group of one system (dict group -> vector)."""
    groups = period.groups[key]
    out = {}
    for g in np.unique(groups):
        mask = (groups == g).astype(np.float32)
        out[g] = (np.rint(period.hits.astype(np.float32) @ mask)).astype(np.int64), int(mask.sum())
    return out


def rule_stats(pool, cnt, n):
    j, a, c = cnt[pool.r_joint], cnt[pool.r_ant], cnt[pool.r_con]
    with np.errstate(divide="ignore", invalid="ignore"):
        conf = np.where(a > 0, j / a, np.nan)
        lift = np.where(c > 0, conf / (c / n), np.nan)
        three = pool.r_length == 3
        c1 = np.full(len(j), np.nan)
        c2 = np.full(len(j), np.nan)
        c1[three] = cnt[pool.r_s1[three]] / cnt[pool.r_s1_ant[three]]
        c2[three] = cnt[pool.r_s2[three]] / cnt[pool.r_s2_ant[three]]
        inc = np.where(three, conf - np.fmax(c1, c2), np.nan)
    return j, a, c, conf, lift, inc


def p5_ranked(pool, cnt, n):
    """Indices of directed rules passing P5 in one scope, in C's ranking order."""
    j, a, c, conf, lift, inc = rule_stats(pool, cnt, n)
    three = pool.r_length == 3
    inc_ok = ~three | (inc >= P5["increment"] - 1e-10)
    ok = ((j / n + 1e-12 >= P5["support"]) & (j >= P5["joint"]) & (a >= P5["antecedent"])
          & (conf + 1e-12 >= P5["confidence"]) & (lift + 1e-12 >= P5["lift"]) & inc_ok)
    idx = np.flatnonzero(ok)
    order = np.lexsort((pool.rule_id[idx], -lift[idx], -conf[idx], -j[idx]))
    return idx[order]


def subsets_of(pool, combo_row):
    c = pool.combos[combo_row]
    if len(c) < 3:
        return ()
    return tuple(pool.row[s] for s in ((c[0], c[1]), (c[0], c[2]), (c[1], c[2])))


def redundant(pool, combo_row, kept):
    """True if the combination is already kept or a superset of a kept combination."""
    return combo_row in kept or any(s in kept for s in subsets_of(pool, combo_row))


def combo_walk(pool, ranked, limit, start=0, kept=None):
    """Walk a ranked directed-rule list keeping new, non-superset combinations.

    Returns (kept combo rows in order, directed rule of each, next position)."""
    kept = set() if kept is None else kept
    rows, rules, pos = [], [], start
    while pos < len(ranked) and len(rows) < limit:
        r = ranked[pos]
        cr = pool.r_joint[r]
        pos += 1
        if not redundant(pool, cr, kept):
            kept.add(cr)
            rows.append(cr)
            rules.append(r)
    return rows, rules, pos


def system_sizes(period, key):
    groups = period.groups[key]
    return {g: int((groups == g).sum()) for g in np.unique(groups)}


# ---------------------------------------------------------------- statistics
def bootstrap_weights(n_customers, repeats=2000, seed=20261121):
    rng = np.random.default_rng(seed)
    return rng.multinomial(n_customers, np.full(n_customers, 1 / n_customers), size=repeats).astype(np.float64)


def paired_interval(period, cov_left, cov_right, weights):
    """Order-level and customer-macro left - right with a customer bootstrap percentile interval."""
    tot = period.orders_per_customer
    left, right = period.customer_hits(cov_left), period.customer_hits(cov_right)
    out = {}
    est = (left.sum() - right.sum()) / tot.sum()
    samples = (weights @ (left - right)) / (weights @ tot)
    out["order"] = (est, *np.quantile(samples, [0.025, 0.975]))
    est = np.mean((left - right) / tot)
    samples = (weights @ ((left - right) / tot)) / len(tot)
    out["customer_macro"] = (est, *np.quantile(samples, [0.025, 0.975]))
    return out


def random_position(real, values):
    values = np.asarray(values, dtype=float)
    ge = int((values >= real - 1e-12).sum())
    return dict(random_n=len(values), random_median=float(np.median(values)), random_p95=float(np.quantile(values, .95)),
                random_min=float(values.min()), random_max=float(values.max()), random_ge_real=ge,
                empirical_p=(1 + ge) / (1 + len(values)))


def build_pool():
    disc_b, x, cols = load_period("discovery")
    return Pool(x, cols)
