"""Four alternative comparisons of segmented vs global rule lists (configs/future_B/comparisons.json).

C1 small-budget coverage curve, C2 leave-one-out hit@k, C3 worst-group gain, C4 revenue-weighted coverage.
Validation results are descriptive only (the motivating lead was found on Validation).
"""

import json
import multiprocessing as mp
import time

import numpy as np
import pandas as pd

from online_trade.extra_eval import e9
from online_trade.extra_eval import engine as E

from . import experiment as X
from . import precheck as P

CONFIG = P.REPO / "configs/future_B/comparisons.json"
OUT = P.REPO / "results/tables/future_B/comparisons"
LABELS = P.REPO / "results/tables/future_B/experiment/labels.csv"
LABELS_SHA = "a129b88e27de7b7f2ee09e32e501dbb5d7304fb518bb0ed0022b3ecfb518d892"
BUDGETS = (5, 10, 20, 50, 100)
SMALL = (5, 10, 20)
C2_BUDGETS = (100, 20)
KS = (1, 3, 5)
C2_CONTROLS = {"F": ("A1", "B2"), "F6": ("A1", "R1")}
PRIMARY_CONTROL = {"F": "B2", "F6": "R1"}
G = ("GL", "G", "")

_S = {}  # shared state for forked C2 workers


def setup(period):
    assert E.sha256(LABELS) == LABELS_SHA, "frozen labels changed"
    labels = pd.read_csv(LABELS, dtype=str)
    population = P.load_population()
    cust_feat = pd.read_csv(P.OUT / "customer_form_features.csv", dtype={"customer_id": str}).set_index("customer_id")
    ctrl = X.controls(labels, population, cust_feat)
    systems, maps = X.build_systems(labels, ctrl)
    pool = E.build_pool()
    disc = E.Period("discovery", pool, systems, maps)
    per = E.Period(period, pool, systems, maps)
    return systems, pool, disc, per


def build_lists(pool, disc, key):
    counts = E.scope_counts(disc, pool, key)
    ranked = {g: E.p5_ranked(pool, cnt, n) for g, (cnt, n) in counts.items()}
    lists = {b: e9.build(pool, ranked, b)[0] for b in BUDGETS}
    return counts, ranked, lists


# ---------------------------------------------------------------- C2 leave-one-out
def _group_rules(pool, cnt, n, ranked, combo_set):
    """Directed P5 rules of one scope whose combination is in the list, sorted for candidate ranking."""
    rules = np.array([r for r in ranked if pool.r_joint[r] in combo_set], dtype=np.int64)
    if len(rules) == 0:
        return None
    j, a, c, conf, lift, inc = E.rule_stats(pool, cnt, n)
    ant = [pool.combos[pool.r_ant[r]] for r in rules]
    a1 = np.array([t[0] for t in ant])
    a2 = np.array([t[1] if len(t) > 1 else -1 for t in ant])
    con = np.array([pool.combos[pool.r_con[r]][0] for r in rules])
    cf, jj = conf[rules], j[rules]
    order = np.lexsort((con, -jj, -cf))
    return dict(ant_rows=pool.r_ant[rules][order], a1=a1[order], a2=a2[order], con=con[order])


def loo_system(key):
    pool, per, counts_all, ranked_all, lists_all = _S["pool"], _S["per"], _S["counts"], _S["ranked"], _S["lists"]
    groups = per.groups[key]
    out = {}
    for b in C2_BUDGETS:
        hits = {k: np.zeros(per.n) for k in KS}
        cases = np.zeros(per.n)
        for g, combos in lists_all[key][b].items():
            cnt, n = counts_all[key][g]
            gr = _group_rules(pool, cnt, n, ranked_all[key][g], set(combos))
            orders = np.flatnonzero(groups == g)
            if gr is None:
                for o in orders:
                    size = int(per.x[o].sum())
                    cases[o] = size if size >= 2 else 0
                continue
            fired_all = per.hits[gr["ant_rows"]][:, orders].tocsc()
            for col, o in enumerate(orders):
                S = np.flatnonzero(per.x[o])
                if len(S) < 2:
                    continue
                cases[o] = len(S)
                f = fired_all.indices[fired_all.indptr[col]:fired_all.indptr[col + 1]]
                if len(f) == 0:
                    continue
                f = np.sort(f)  # keep the registered candidate order
                a1, a2, con = gr["a1"][f], gr["a2"][f], gr["con"][f]
                in_s = per.x[o][con]
                for c in S:
                    m = (a1 != c) & (a2 != c) & (~in_s | (con == c))
                    if not m.any():
                        continue
                    cc = con[m]
                    _, first = np.unique(cc, return_index=True)
                    ranked_cons = cc[np.sort(first)]
                    pos = np.flatnonzero(ranked_cons == c)
                    if len(pos):
                        for k in KS:
                            if pos[0] < k:
                                hits[k][o] += 1
        out[b] = dict(cases=cases, **{f"hit{k}": hits[k] for k in KS})
    return key, out


# ---------------------------------------------------------------- statistics
def boot_diff(per, left, right, denom, weights):
    """Paired customer bootstrap of (sum left - sum right) / sum denom, with per-order vectors."""
    l, r, d = (np.asarray(per.cust_matrix @ v.astype(np.float64)).ravel() for v in (left, right, denom))
    est = (l.sum() - r.sum()) / d.sum()
    s = (weights @ (l - r)) / (weights @ d)
    return 100 * est, 100 * np.quantile(s, 0.025), 100 * np.quantile(s, 0.975)


def position(real, values):
    pos = E.random_position(real, np.asarray(values))
    return {"median": pos["random_median"], "p95": pos["random_p95"], "p": pos["empirical_p"]}


def family(systems, target):
    return {c: [k for k in systems if k[0] == f"{target}:{c}"] for c in X.CONTROLS_FOR[target]}


def run(period="validation", log=print):
    t0 = time.time()
    cfg = json.loads(CONFIG.read_text())
    assert cfg["status"] == "registered_before_computation"
    out = OUT / period
    out.mkdir(parents=True, exist_ok=True)
    systems, pool, disc, per = setup(period)
    weights = E.bootstrap_weights(len(per.customers))
    amount = per.baskets.gross_purchase_amount.astype(float).to_numpy()
    ones = np.ones(per.n)
    log(f"{len(systems)} systems, {per.n} {period} orders ({time.time() - t0:.0f}s)")

    c2_systems = [G, ("GL", "L", ""), ("GL", "F", ""), ("GL", "F6", "")]
    for target, ctrls in C2_CONTROLS.items():
        for c in ctrls:
            c2_systems += [k for k in systems if k[0] == f"{target}:{c}"]
    c2_set = set(c2_systems)
    counts, ranked, lists, cov = {}, {}, {}, {}
    for key in systems:
        cnt, rk, lists[key] = build_lists(pool, disc, key)
        if key in c2_set:  # counts are large; keep them only where C2 needs them
            counts[key], ranked[key] = cnt, rk
        cov[key] = {b: e9.coverage(per, key, lists[key][b]) for b in BUDGETS}
    log(f"lists and coverage built ({time.time() - t0:.0f}s)")

    # per-system metrics for C1, C3, C4
    rows = []
    gcov = cov[G]
    for key in systems:
        groups = per.groups[key]
        rec = dict(control=key[0], method=key[1], seed=key[2])
        for b in BUDGETS:
            c = cov[key][b]
            rec[f"C1_cov_B{b}"] = c.mean()
            rec[f"C4_rev_B{b}"] = (amount * c).sum() / amount.sum()
            if key[1] != "G":
                gl = {g: gcov[b][groups == g].mean() for g in np.unique(groups)}
                own = {g: c[groups == g].mean() for g in gl}
                worst = min(gl, key=lambda g: (gl[g], g))
                rec[f"C3_worst_gain_B{b}"] = own[worst] - gl[worst]
                rec[f"C3_worst_group_B{b}"] = worst
                rec[f"C3_equal_gain_B{b}"] = np.mean([own[g] - gl[g] for g in gl])
        for m in ("C1_cov", "C4_rev") + (("C3_worst_gain", "C3_equal_gain") if key[1] != "G" else ()):
            rec[f"{m}_small"] = np.mean([rec[f"{m}_B{b}"] for b in SMALL])
        rows.append(rec)
    sysdf = pd.DataFrame(rows)
    sysdf.to_csv(out / "C134_systems.csv", index=False)

    summary = []
    for target in ("L", "F", "F6"):
        key = ("GL", target, "")
        real = sysdf[(sysdf.control == "GL") & (sysdf.method == target)].iloc[0]
        g = sysdf[(sysdf.control == "GL") & (sysdf.method == "G")].iloc[0]
        fam = {c: sysdf[sysdf.control == f"{target}:{c}"] for c in X.CONTROLS_FOR.get(target, [])}
        for metric in ["C1_cov", "C4_rev", "C3_worst_gain", "C3_equal_gain"]:
            for b in list(BUDGETS) + ["small"]:
                col = f"{metric}_B{b}" if b != "small" else f"{metric}_small"
                row = dict(target=target, metric=metric, budget=b, real=real[col])
                if metric in ("C1_cov", "C4_rev"):
                    row["G"] = g[col]
                    bs = SMALL if b == "small" else (b,)
                    left = np.mean([cov[key][x] for x in bs], axis=0)
                    right = np.mean([cov[G][x] for x in bs], axis=0)
                    w = ones if metric == "C1_cov" else amount
                    row["minus_G_pp"], row["ci_low_pp"], row["ci_high_pp"] = boot_diff(per, left * w, right * w, w, weights)
                if metric.startswith("C3"):
                    row["worst_group"] = real.get(f"C3_worst_group_B{b}", "") if b != "small" else ""
                for c, d in fam.items():
                    row.update({f"{c}_{k}": v for k, v in position(real[col], d[col]).items()})
                summary.append(row)
    pd.DataFrame(summary).to_csv(out / "C134_summary.csv", index=False)
    log(f"C1/C3/C4 done ({time.time() - t0:.0f}s)")

    # C2 leave-one-out (parallel)
    _S.update(pool=pool, per=per, counts=counts, ranked=ranked, lists=lists)
    res = {}
    with mp.get_context("fork").Pool(6) as workers:
        for i, (key, r) in enumerate(workers.imap_unordered(loo_system, c2_systems, chunksize=4)):
            res[key] = r
            if (i + 1) % 50 == 0:
                log(f"  C2 {i + 1}/{len(c2_systems)} ({time.time() - t0:.0f}s)")
    rows = []
    for key, r in res.items():
        rec = dict(control=key[0], method=key[1], seed=key[2])
        for b in C2_BUDGETS:
            for k in KS:
                rec[f"hit{k}_B{b}"] = r[b][f"hit{k}"].sum() / r[b]["cases"].sum()
                cust_h = np.asarray(per.cust_matrix @ r[b][f"hit{k}"]).ravel()
                cust_c = np.asarray(per.cust_matrix @ r[b]["cases"]).ravel()
                ok = cust_c > 0
                rec[f"macro_hit{k}_B{b}"] = float(np.mean(cust_h[ok] / cust_c[ok]))
            rec[f"cases_B{b}"] = int(r[b]["cases"].sum())
        rows.append(rec)
    c2 = pd.DataFrame(rows)
    c2.to_csv(out / "C2_systems.csv", index=False)
    c2sum = []
    for target in ("L", "F", "F6"):
        key = ("GL", target, "")
        real = c2[(c2.control == "GL") & (c2.method == target)].iloc[0]
        g = c2[(c2.control == "GL") & (c2.method == "G")].iloc[0]
        for b in C2_BUDGETS:
            for k in KS:
                col = f"hit{k}_B{b}"
                row = dict(target=target, budget=b, k=k, real=real[col], G=g[col],
                           macro_real=real[f"macro_{col}"], macro_G=g[f"macro_{col}"])
                row["minus_G_pp"], row["ci_low_pp"], row["ci_high_pp"] = boot_diff(
                    per, res[key][b][f"hit{k}"], res[G][b][f"hit{k}"], res[G][b]["cases"], weights)
                for c in C2_CONTROLS.get(target, ()):
                    row.update({f"{c}_{kk}": v for kk, v in position(real[col], c2[c2.control == f"{target}:{c}"][col]).items()})
                c2sum.append(row)
    pd.DataFrame(c2sum).to_csv(out / "C2_summary.csv", index=False)
    log(f"C2 done ({time.time() - t0:.0f}s)")

    # registered primary statistics H1-H4 (F6 vs G and R1)
    s, c2s = pd.DataFrame(summary), pd.DataFrame(c2sum)
    h = []
    pick = lambda m, b="small": s[(s.target == "F6") & (s.metric == m) & (s.budget.astype(str) == str(b))].iloc[0]
    for name, r, interval in (("H1 small-budget coverage", pick("C1_cov"), True),
                              ("H3 worst-group gain (small budgets)", pick("C3_worst_gain"), False),
                              ("H4 revenue-weighted coverage (small budgets)", pick("C4_rev"), True)):
        h.append(dict(hypothesis=name, F6=r.real, G=r.get("G", np.nan), minus_G_pp=r.get("minus_G_pp", np.nan),
                      ci_low_pp=r.get("ci_low_pp", np.nan), ci_high_pp=r.get("ci_high_pp", np.nan),
                      R1_median=r.R1_median, R1_p95=r.R1_p95, R1_p=r.R1_p,
                      looks_favourable=bool((r.ci_low_pp > 0 if interval else r.real > 0) and r.R1_p <= 0.05)))
    r = c2s[(c2s.target == "F6") & (c2s.budget == 100) & (c2s.k == 3)].iloc[0]
    h.insert(1, dict(hypothesis="H2 leave-one-out hit@3 (B=100)", F6=r.real, G=r.G, minus_G_pp=r.minus_G_pp,
                     ci_low_pp=r.ci_low_pp, ci_high_pp=r.ci_high_pp, R1_median=r.R1_median, R1_p95=r.R1_p95,
                     R1_p=r.R1_p, looks_favourable=bool(r.ci_low_pp > 0 and r.R1_p <= 0.05)))
    hdf = pd.DataFrame(h)
    hdf.to_csv(out / "primary_H1_H4.csv", index=False)
    (out / "manifest.json").write_text(json.dumps(dict(
        protocol_sha256=E.sha256(CONFIG), period=period, labels_sha256=LABELS_SHA, systems=len(systems),
        c2_systems=len(c2_systems), elapsed_seconds=round(time.time() - t0, 1),
        outputs={p.name: E.sha256(p) for p in sorted(out.glob("*.csv"))}), indent=2) + "\n")
    log(f"done ({time.time() - t0:.0f}s)")
    log(hdf.to_string())
