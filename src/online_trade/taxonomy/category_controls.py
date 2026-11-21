"""Category-level (taxonomy_v1 l2) comparison of real RFM groups against random control groups.

Reproduces C's category-level Discovery set-up on `c/pattern-mining-taxonomy` (same snapshot baskets,
same frozen taxonomy, `other` dropped, within-basket de-duplication, empty baskets kept in the
denominator) and evaluates every grouping with the same two families of metrics:

1. how different the groups are: Bray-Curtis distance between category-combination supports,
   group vs rest of Discovery and between groups (2- and 3-category combinations separately);
2. C's fixed-budget system comparison (strict config + 3-category increment >= 5pp, budgets 20/50/100).

All 2/3-category combinations with >= 20 joint baskets overall are counted exhaustively, which is
equivalent to C's FP-Growth + threshold pipeline for every rule that can pass the thresholds.
Discovery data only; nothing here touches Validation or Test.
"""

import hashlib
import io
import json
import subprocess
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import sparse

SNAPSHOT = "2ae672b7ea6edb7f5e1561b6a64823004dea833e"
BASKETS_SHA256 = "30aef702f812ab42224271871271daff5b4e37a594696eee82208252198367bf"
STRICT = dict(support=0.03, joint=20, antecedent=20, confidence=0.5, lift=1.5, increment=0.05)
BUDGETS = (20, 50, 100)
MIN_POOL_JOINT = 20


# ---------------------------------------------------------------- inputs
def load_discovery_baskets(repo):
    """The 7,521 eligible Discovery baskets from A's frozen snapshot (identical bytes to C's input)."""
    raw = subprocess.check_output(
        ["git", "show", f"{SNAPSHOT}:data/processed/A_data_preparation/baskets.csv.gz"], cwd=repo)
    assert hashlib.sha256(raw).hexdigest() == BASKETS_SHA256, "snapshot baskets changed"
    b = pd.read_csv(io.BytesIO(raw), compression="gzip", dtype=str, keep_default_na=False)
    b = b[b.split.eq("discovery") & b.is_eligible_for_main_comparison.eq("1")].reset_index(drop=True)
    assert len(b) == 7521 and b.basket_id.is_unique
    return b


def category_matrix(baskets, taxonomy):
    """Boolean basket x l2 matrix; `other` removed before de-duplication, empty baskets kept."""
    mapping = taxonomy.set_index("stock_code").l2_id.to_dict()
    items = baskets["items"].map(json.loads)
    assert all(c in mapping for row in items for c in row), "unmapped stock code"
    mapped = items.map(lambda row: sorted({mapping[c] for c in row if mapping[c] not in ("other", "")}))
    cols = sorted({c for row in mapped for c in row})
    index = {c: i for i, c in enumerate(cols)}
    x = np.zeros((len(baskets), len(cols)), dtype=bool)
    for i, row in enumerate(mapped):
        x[i, [index[c] for c in row]] = True
    return x, cols


# ---------------------------------------------------------------- candidate pool and rules
class Pool:
    """All singles plus 2/3-category combinations with >= MIN_POOL_JOINT joint baskets overall."""

    def __init__(self, x, cols):
        self.cols = cols
        n_cat = x.shape[1]
        xi = x.astype(np.int32)
        pair_counts = xi.T @ xi
        combos = [(i,) for i in range(n_cat)]
        combos += [(i, j) for i, j in combinations(range(n_cat), 2) if pair_counts[i, j] >= MIN_POOL_JOINT]
        pairs = [c for c in combos if len(c) == 2]
        for i, j in pairs:
            both = x[:, i] & x[:, j]
            counts = both.astype(np.int32) @ xi
            combos += [(i, j, k) for k in range(j + 1, n_cat) if counts[k] >= MIN_POOL_JOINT]
        self.combos = combos
        self.row = {c: r for r, c in enumerate(combos)}
        rows, colsx = [], []
        for r, c in enumerate(combos):
            hit = np.flatnonzero(x[:, list(c)].all(1))
            rows.append(np.full(len(hit), r))
            colsx.append(hit)
        self.hits = sparse.csr_matrix((np.ones(sum(map(len, rows)), dtype=np.float32),
                                       (np.concatenate(rows), np.concatenate(colsx))),
                                      shape=(len(combos), x.shape[0]))
        self.length = np.array([len(c) for c in combos])
        self.total = np.asarray(self.hits.sum(1)).ravel()
        self._rules()

    def _rules(self):
        """Directional rules A->B and {A,B}->C over the pool, with C's rule_id hashing."""
        ant, con, joint, s1, s2 = [], [], [], [], []
        for c in self.combos:
            if len(c) == 1:
                continue
            for consequent in c:
                antecedent = tuple(k for k in c if k != consequent)
                ant.append(self.row[antecedent])
                con.append(self.row[(consequent,)])
                joint.append(self.row[c])
                if len(antecedent) == 2:  # single-antecedent rules for the confidence increment
                    s1.append(self.row[tuple(sorted((antecedent[0], consequent)))])
                    s2.append(self.row[tuple(sorted((antecedent[1], consequent)))])
                else:
                    s1.append(-1)
                    s2.append(-1)
        self.r_ant, self.r_con, self.r_joint = map(np.array, (ant, con, joint))
        self.r_s1, self.r_s2 = np.array(s1), np.array(s2)
        self.r_s1_ant = np.array([self.r_ant_of(a, s) for a, s in zip(ant, s1)])
        self.r_s2_ant = np.array([self.r_ant_of(a, s, second=True) for a, s in zip(ant, s2)])
        self.r_length = self.length[self.r_joint]
        name = lambda r: [self.cols[k] for k in self.combos[r]]
        self.rule_id = np.array([
            hashlib.sha256(json.dumps(["l2", name(a), name(c)]).encode()).hexdigest()[:16]
            for a, c in zip(ant, con)])

    def r_ant_of(self, antecedent_row, single_row, second=False):
        """Row of the single antecedent used by the single-antecedent rule A->C (or B->C)."""
        if single_row < 0:
            return -1
        a = self.combos[antecedent_row]
        return self.row[(a[1] if second else a[0],)]


# ---------------------------------------------------------------- groupings
def indicator(assignments, labels):
    """Sparse basket x (system, group) indicator for a (systems x baskets) label matrix."""
    n_sys, n = assignments.shape
    rows, cols = [], []
    for s in range(n_sys):
        for gi, g in enumerate(labels):
            hit = np.flatnonzero(assignments[s] == g)
            rows.append(hit)
            cols.append(np.full(len(hit), s * len(labels) + gi))
    return sparse.csr_matrix((np.ones(sum(map(len, rows)), dtype=np.float32),
                              (np.concatenate(rows), np.concatenate(cols))),
                             shape=(n, n_sys * len(labels)))


def bray_curtis(a, b):
    return np.abs(a - b).sum() / (a + b).sum()


def strict_rules(pool, cnt, n):
    """Indices of rules passing C's strict + increment config in one scope, in C's ranking order."""
    j, a, c = cnt[pool.r_joint], cnt[pool.r_ant], cnt[pool.r_con]
    with np.errstate(divide="ignore", invalid="ignore"):
        conf = np.where(a > 0, j / a, np.nan)
        lift = np.where(c > 0, conf / (c / n), np.nan)
        three = pool.r_length == 3
        c1 = np.full(len(j), np.nan)
        c2 = np.full(len(j), np.nan)
        c1[three] = cnt[pool.r_s1[three]] / cnt[pool.r_s1_ant[three]]
        c2[three] = cnt[pool.r_s2[three]] / cnt[pool.r_s2_ant[three]]
    inc_ok = ~three | (conf - np.fmax(c1, c2) >= STRICT["increment"] - 1e-12)
    ok = ((j / n >= STRICT["support"]) & (j >= STRICT["joint"]) & (a >= STRICT["antecedent"])
          & (conf >= STRICT["confidence"]) & (lift >= STRICT["lift"]) & inc_ok)
    idx = np.flatnonzero(ok)
    order = np.lexsort((pool.rule_id[idx], -lift[idx], -conf[idx], -j[idx]))
    return idx[order]


def allocate(sizes, budget):
    """Largest-remainder quota by Discovery baskets; ties broken by group id (C's rule)."""
    raw = {g: budget * n / sum(sizes.values()) for g, n in sizes.items()}
    quota = {g: int(v) for g, v in raw.items()}
    for g in sorted(raw, key=lambda g: (-(raw[g] - quota[g]), g))[:budget - sum(quota.values())]:
        quota[g] += 1
    return quota


def evaluate(pool, assignments, labels, global_rules):
    """Metrics for each system (row of `assignments`): difference metrics and fixed-budget coverage."""
    n_sys, n_baskets = assignments.shape
    counts = np.rint((pool.hits @ indicator(assignments, labels)).toarray()).astype(np.int64)
    global_set = set(global_rules.tolist())
    hit_cache = {}

    def hit(r):
        if r not in hit_cache:
            hit_cache[r] = pool.hits[r].toarray().ravel() > 0
        return hit_cache[r]

    rows, group_rows = [], []
    for s in range(n_sys):
        sizes = {g: int((assignments[s] == g).sum()) for g in labels}
        sup_in, ranked = {}, {}
        rec = {"system": s}
        for gi, g in enumerate(labels):
            cnt = counts[:, s * len(labels) + gi]
            n = sizes[g]
            sup_in[g] = cnt / n
            sup_out = (pool.total - cnt) / (n_baskets - n)
            ranked[g] = strict_rules(pool, cnt, n)
            grow = {"system": s, "group_id": g, "n_baskets": n, "strict_rules": len(ranked[g])}
            for k in (2, 3):
                m = pool.length == k
                grow[f"rest_bc_len{k}"] = bray_curtis(sup_in[g][m], sup_out[m])
            group_rows.append(grow)
        for k in (2, 3):
            m = pool.length == k
            rec[f"rest_bc_len{k}"] = np.mean([r[f"rest_bc_len{k}"] for r in group_rows[-len(labels):]])
            rec[f"pair_bc_len{k}"] = np.mean([bray_curtis(sup_in[a][m], sup_in[b][m])
                                              for a, b in combinations(labels, 2)])
        local = set(np.concatenate([ranked[g] for g in labels]).tolist())
        rec["local_strict_rules_union"] = len(local)
        rec["local_not_global_share"] = len(local - global_set) / len(local) if local else np.nan
        for budget in BUDGETS:
            quota = allocate(sizes, budget)
            covered = np.zeros(n_baskets, bool)
            for g in labels:
                mask = assignments[s] == g
                for r in ranked[g][:quota[g]]:
                    covered |= hit(pool.r_joint[r]) & mask
            assert sum(min(quota[g], len(ranked[g])) for g in labels) == budget
            rec[f"coverage_B{budget}"] = covered.mean()
        rows.append(rec)
    return pd.DataFrame(rows), pd.DataFrame(group_rows)


def global_system(pool, n_baskets):
    """G: one scope over all Discovery baskets."""
    ranked = strict_rules(pool, np.rint(pool.total).astype(np.int64), n_baskets)
    out = {"strict_rules": len(ranked)}
    for budget in BUDGETS:
        covered = np.zeros(n_baskets, bool)
        for r in ranked[:budget]:
            covered |= pool.hits[pool.r_joint[r]].toarray().ravel() > 0
        out[f"coverage_B{budget}"] = covered.mean()
    return out, ranked


def compare(real, random, metrics):
    """Real vs one random control: random median/range, count >= real, one-sided empirical p."""
    out = []
    for m in metrics:
        r = random[m].to_numpy()
        v = float(real[m])
        ge = int((r >= v - 1e-12).sum())
        out.append({"metric": m, "real": v, "random_median": np.median(r), "random_p5": np.quantile(r, .05),
                    "random_p95": np.quantile(r, .95), "random_min": r.min(), "random_max": r.max(),
                    "n_random": len(r), "random_ge_real": ge, "empirical_p": (1 + ge) / (1 + len(r))})
    return pd.DataFrame(out)
