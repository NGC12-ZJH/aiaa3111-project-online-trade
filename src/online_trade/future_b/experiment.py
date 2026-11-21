"""Future work B formal experiment (EXPLORATORY), exactly as registered in configs/future_B/experiment.json.

Profile: order features -> two-stage segmentation F (Sokol & Holy style) and backup F6 (form split inside
each RFM cluster). Controls S / A1 / B1 / B2 (F) and S / A1 / R1 (F6). Discovery: category difference (M1)
and list building. Validation: E9 (M2), E10 (M3), E5a (M4), size-stratified E9 (M5). Test is not read.
"""

import json
import time
from itertools import combinations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

from online_trade.clustering.activity_control import stratify
from online_trade.extra_eval import e5, e9, e10
from online_trade.extra_eval import engine as E
from online_trade.taxonomy import category_controls as CC

from . import precheck as P

CONFIG = P.REPO / "configs/future_B/experiment.json"
OUT = P.REPO / "results/tables/future_B/experiment"
ORDER_FEATURES = ["basket_size", "qty_per_line", "pack_share", "unit_price", "business_hours"]
SEEDS = range(1000, 1100)
A1_BOUNDS, A1_LABELS = [1, 2, 4, 9, None], ["1", "2", "3-4", "5-9", "10+"]


def _cap(x):
    q = np.quantile(x, 0.95)
    return np.minimum(x, q) / q


# ---------------------------------------------------------------- Profile: features and segmentation
def order_features(lines):
    """One row per Profile order; `lines` already carries is_pack and month from precheck.check1."""
    lines = lines.assign(is_pack=lines.is_pack.astype(float))
    lines = lines.assign(rel_price=lines.unit_price / lines.groupby(["stock_code", "month"]).unit_price.transform("median"))
    g = lines.groupby("invoice_id")
    dt = g.invoice_datetime.first()
    o = pd.DataFrame({
        "customer_id": g.customer_id.first(),
        "basket_size": _cap(np.log1p(g.stock_code.nunique())),
        "qty_per_line": _cap(np.log1p(g.quantity.median())),
        "pack_share": g.is_pack.mean(),  # NaN-skipping: lines outside the pack denominator are ignored
        "unit_price": _cap(g.rel_price.median()),
        "business_hours": ((dt.dt.weekday < 5) & dt.dt.hour.between(9, 16)).astype(float),
        "n_items": g.stock_code.nunique(),
    })
    o["pack_share"] = o.pack_share.fillna(o.pack_share.median())
    assert o[ORDER_FEATURES].notna().all().all()
    return o


def choose_k_order(x, log=print):
    rows, best = [], {}
    for k in range(3, 9):
        fits = [KMeans(n_clusters=k, n_init=1, random_state=s).fit(x) for s in range(50)]
        labels = [f.labels_ for f in fits]
        aris = [adjusted_rand_score(a, b) for a, b in combinations(labels, 2)]
        best[k] = min(fits, key=lambda f: f.inertia_)
        rows.append(dict(K=k, median_pairwise_ARI=float(np.median(aris)), p10_ARI=float(np.quantile(aris, .1)),
                         best_inertia=float(best[k].inertia_)))
        log(f"  K_order={k}: median ARI {rows[-1]['median_pairwise_ARI']:.3f}")
    table = pd.DataFrame(rows)
    ok = table[table.median_pairwise_ARI >= 0.80]
    k = int(ok.K.min()) if len(ok) else int(table.loc[table.median_pairwise_ARI.idxmax(), "K"])
    return k, best[k], table


def rename_by(labels, score, prefix=""):
    """Rename integer labels '0','1',... by ascending mean score."""
    s = pd.Series(score).groupby(np.asarray(labels)).mean().sort_values()
    m = {old: f"{prefix}{i}" for i, old in enumerate(s.index)}
    return np.array([m[v] for v in labels])


def segment(population, orders, cust_feat, log=print):
    x = orders[ORDER_FEATURES].to_numpy()
    k, model, ktable = choose_k_order(x, log)
    orders = orders.assign(order_type=model.labels_)
    centers = pd.DataFrame(model.cluster_centers_, columns=ORDER_FEATURES)
    centers["share_of_orders"] = orders.order_type.value_counts(normalize=True).sort_index().to_numpy()
    shares = pd.crosstab(orders.customer_id, orders.order_type, normalize="index").reindex(population.index)
    assert shares.notna().all().all()
    km = KMeans(n_clusters=3, n_init=10, random_state=42).fit(shares.to_numpy())
    F = rename_by(km.labels_, cust_feat.loc[shares.index, "basket_size"].to_numpy())
    # F6: two form sub-groups inside each RFM cluster
    z = StandardScaler().fit_transform(cust_feat.loc[population.index, ORDER_FEATURES].to_numpy())
    F6 = np.empty(len(population), dtype=object)
    for c in (0, 1, 2):
        m = population.cluster_id.to_numpy() == c
        lab = KMeans(n_clusters=2, n_init=10, random_state=42).fit(z[m]).labels_
        F6[m] = rename_by(lab, cust_feat.loc[population.index[m], "basket_size"].to_numpy(), prefix=f"{c}-")
    labels = pd.DataFrame({"customer_id": population.index, "rfm": population.cluster_id.astype(str).to_numpy(),
                           "F": F, "F6": F6.astype(str)})
    profile = shares.copy()
    profile.columns = [f"type{c}_share" for c in profile.columns]
    return labels, ktable, k, centers, profile


def describe(labels, population, cust_feat, profile):
    lab = labels.set_index("customer_id")
    rows = []
    for name in ("F", "F6"):
        d = cust_feat.join(lab[name]).join(population[["recency", "frequency", "monetary"]]).join(profile)
        g = d.groupby(name)
        desc = g[ORDER_FEATURES + ["recency", "frequency", "monetary"] + list(profile.columns)].mean()
        desc["customers"] = g.size()
        desc["monetary_share"] = g.monetary.sum() / d.monetary.sum()
        desc.insert(0, "segmentation", name)
        rows.append(desc.reset_index().rename(columns={name: "group"}))
    tree = DecisionTreeClassifier(max_depth=3, random_state=0).fit(cust_feat.loc[lab.index, ORDER_FEATURES], lab.F)
    comp = {}
    for name in ("F", "F6"):
        a, b = lab[name].to_numpy(), lab.rfm.to_numpy()
        comp[name] = dict(ARI_vs_RFM=float(adjusted_rand_score(a, b)),
                          purity_RFM_given_group=P.purity(a, b), purity_group_given_RFM=P.purity(b, a),
                          crosstab={str(k): {str(c): int(v) for c, v in r.items()}
                                    for k, r in pd.crosstab(lab[name], lab.rfm).iterrows()})
    comp["F_tree"] = dict(train_accuracy=float(tree.score(cust_feat.loc[lab.index, ORDER_FEATURES], lab.F)),
                          rules=export_text(tree, feature_names=ORDER_FEATURES, decimals=3))
    return pd.concat(rows, ignore_index=True), comp


# ---------------------------------------------------------------- random controls
def shuffle_within(labels, strata, seeds):
    labels, strata = np.asarray(labels), np.asarray(strata)
    pos = [np.flatnonzero(strata == s) for s in np.unique(strata)]
    out = {}
    for seed in seeds:
        rng = np.random.default_rng(seed)
        z = labels.copy()
        for p in pos:
            z[p] = rng.permutation(z[p])
        out[seed] = z
    return out


def controls(labels, population, cust_feat):
    ids = labels.customer_id.to_numpy()
    a1 = stratify(population.loc[ids, "frequency"].to_numpy(), A1_BOUNDS, A1_LABELS).to_numpy()
    bs = cust_feat.loc[ids, "basket_size"].rank(method="first")
    b1 = pd.qcut(bs, 5, labels=False).astype(str).to_numpy()
    b2 = np.char.add(np.char.add(a1.astype(str), "|"), pd.qcut(bs, 3, labels=False).astype(str).to_numpy())
    one = np.zeros(len(ids), dtype=int)
    spec = {"F": {"S": one, "A1": a1, "B1": b1, "B2": b2},
            "F6": {"S": one, "A1": a1, "R1": labels.rfm.to_numpy()}}
    out = {}
    for target, strata_map in spec.items():
        for control, strata in strata_map.items():
            for seed, z in shuffle_within(labels[target].to_numpy(), strata, SEEDS).items():
                assert (pd.Series(z).value_counts().sort_index() == labels[target].value_counts().sort_index()).all()
                out[(f"{target}:{control}", "R", str(seed))] = dict(zip(ids, z))
    return out


# ---------------------------------------------------------------- evaluation
def build_systems(labels, ctrl):
    ids = labels.customer_id
    maps = {("GL", "G", ""): {c: "GLOBAL" for c in ids},
            ("GL", "L", ""): dict(zip(ids, labels.rfm)),
            ("GL", "F", ""): dict(zip(ids, labels.F)),
            ("GL", "F6", ""): dict(zip(ids, labels.F6))}
    maps.update(ctrl)
    return list(maps), maps


def target_of(key):
    if key[0] == "GL":
        return key[1]
    return key[0].split(":")[0]


def m1_category(pool, disc, systems):
    """Discovery category difference, same definitions as category_controls.evaluate (rest_bc / pair_bc).

    Only the difference metrics are computed here (evaluate's fixed-budget coverage part assumes every
    group has enough strict rules, which does not hold for six groups)."""
    total = np.asarray(pool.hits.sum(1)).ravel()
    rows = []
    for key in systems:
        if key[1] == "G":
            continue
        groups = disc.groups[key]
        sup = {}
        rec = dict(control=key[0], method=key[1], seed=key[2], target=target_of(key))
        rest = {2: [], 3: []}
        for g in np.unique(groups):
            mask = groups == g
            cnt = np.rint(pool.hits @ mask.astype(np.float32))
            n = int(mask.sum())
            sup[g] = cnt / n
            out = (total - cnt) / (disc.n - n)
            for k in (2, 3):
                m = pool.length == k
                rest[k].append(CC.bray_curtis(sup[g][m], out[m]))
        for k in (2, 3):
            m = pool.length == k
            rec[f"rest_bc_len{k}"] = float(np.mean(rest[k]))
            rec[f"pair_bc_len{k}"] = float(np.mean([CC.bray_curtis(sup[a][m], sup[b][m]) for a, b in combinations(sorted(sup), 2)]))
        rows.append(rec)
    return pd.DataFrame(rows)


def positions(df, metric_col, filt, controls_for):
    """Real row vs each random control of its family."""
    rows = []
    for target, ctrls in controls_for.items():
        d = df[filt(df)] if filt else df
        real = d[(d.control == "GL") & (d.method == target)]
        if real.empty:
            continue
        v = float(real[metric_col].iloc[0])
        row = dict(target=target, metric=metric_col, real=v)
        for c in ctrls:
            vals = d[d.control == f"{target}:{c}"][metric_col].to_numpy()
            pos = E.random_position(v, vals)
            row.update({f"{c}_median": pos["random_median"], f"{c}_p95": pos["random_p95"], f"{c}_p": pos["empirical_p"]})
        rows.append(row)
    return rows


CONTROLS_FOR = {"F": ["S", "A1", "B1", "B2"], "F6": ["S", "A1", "R1"]}


def run(log=print):
    t0 = time.time()
    cfg = json.loads(CONFIG.read_text())
    assert cfg["status"] == "registered_before_computation"
    OUT.mkdir(parents=True, exist_ok=True)
    pre = json.loads(P.CONFIG.read_text())
    population = P.load_population()
    lines = P.load_profile_lines(population)
    _, lines, baskets, per_cust = P.check1(lines, pre)
    cust_feat = P.customer_features(lines, baskets, per_cust, population, relative_price=True)
    orders = order_features(lines)
    log(f"Profile orders {len(orders):,} ({time.time() - t0:.0f}s)")

    labels, ktable, k, centers, profile = segment(population, orders, cust_feat, log)
    labels.to_csv(OUT / "labels.csv", index=False)
    ktable.to_csv(OUT / "k_order_selection.csv", index=False)
    centers.to_csv(OUT / "order_type_centers.csv", index_label="order_type")
    desc, comp = describe(labels, population, cust_feat, profile)
    desc.to_csv(OUT / "group_description.csv", index=False)
    (OUT / "partition_comparison.json").write_text(json.dumps(dict(K_order=k, **comp), indent=2, ensure_ascii=False) + "\n")
    log(f"K_order={k}; F sizes {labels.F.value_counts().sort_index().tolist()}; ARI(F,RFM)={comp['F']['ARI_vs_RFM']:.3f}")

    ctrl = controls(labels, population, cust_feat)
    systems, maps = build_systems(labels, ctrl)
    pool = E.build_pool()
    disc = E.Period("discovery", pool, systems, maps)
    val = E.Period("validation", pool, systems, maps)
    periods = {"discovery": disc, "validation": val}
    log(f"{len(systems)} systems loaded ({time.time() - t0:.0f}s)")

    # M1
    m1 = m1_category(pool, disc, systems)
    m1.to_csv(OUT / "M1_category_systems.csv", index=False)
    m1_pos = []
    for metric in ("rest_bc_len2", "rest_bc_len3", "pair_bc_len2"):
        m1_pos += positions(m1, metric, None, CONTROLS_FOR)
    pd.DataFrame(m1_pos).to_csv(OUT / "M1_summary.csv", index=False)
    log(f"M1 done ({time.time() - t0:.0f}s)")

    # M2 + M5: E9
    weights = {p: E.bootstrap_weights(len(per.customers)) for p, per in periods.items()}
    records, masks = [], {}
    for key in systems:
        rec, mk, _ = e9.run_system(pool, disc, [disc, val], key, None)
        records += rec
        masks[key] = mk
    e9df = pd.DataFrame(records)
    e9df.to_csv(OUT / "M2_E9_systems.csv", index=False)
    m2 = []
    for (budget, period), d in e9df.groupby(["budget", "period"], sort=False):
        g = masks[("GL", "G", "")][period, budget]
        for target in ("L", "F", "F6"):
            cov = masks[("GL", target, "")][period, budget]
            ci = E.paired_interval(periods[period], cov, g, weights[period])
            row = dict(budget=budget, period=period, target=target, G=g.mean(), real=cov.mean(),
                       minus_G_pp=100 * ci["order"][0], ci_low_pp=100 * ci["order"][1], ci_high_pp=100 * ci["order"][2],
                       macro_minus_G_pp=100 * ci["customer_macro"][0])
            for c in CONTROLS_FOR.get(target, []):
                pos = E.random_position(cov.mean(), d[d.control == f"{target}:{c}"].coverage.to_numpy())
                row.update({f"{c}_median": pos["random_median"], f"{c}_p95": pos["random_p95"], f"{c}_p": pos["empirical_p"]})
            m2.append(row)
    m2 = pd.DataFrame(m2)
    m2.to_csv(OUT / "M2_E9_summary.csv", index=False)
    # M5: size bins on Validation, B=100
    b = E.load_period("validation")[0]
    raw = P._snapshot_csv("data/processed/A_data_preparation/baskets.csv.gz")
    n_items = b.basket_id.map(raw.set_index("basket_id")["items"].map(lambda s: len(json.loads(s))))
    bins = pd.cut(n_items, [0, 5, 15, 30, np.inf], labels=["1-5", "6-15", "16-30", "31+"]).astype(str).to_numpy()
    m5 = []
    for key in systems:
        cov = masks[key]["validation", 100]
        row = dict(control=key[0], method=key[1], seed=key[2])
        for lab in ("1-5", "6-15", "16-30", "31+"):
            row[f"cov_{lab}"] = cov[bins == lab].mean()
        row["weighted"] = sum((bins == lab).mean() * row[f"cov_{lab}"] for lab in ("1-5", "6-15", "16-30", "31+"))
        row["equal_weight"] = np.mean([row[f"cov_{lab}"] for lab in ("1-5", "6-15", "16-30", "31+")])
        m5.append(row)
    m5 = pd.DataFrame(m5)
    m5.to_csv(OUT / "M5_size_bins_systems.csv", index=False)
    m5_pos = []
    for metric in ["weighted", "equal_weight"] + [f"cov_{l}" for l in ("1-5", "6-15", "16-30", "31+")]:
        rows = positions(m5, metric, None, CONTROLS_FOR)
        g = m5[(m5.control == "GL") & (m5.method == "G")][metric].iloc[0]
        for r in rows:
            r["G"] = g
        m5_pos += rows
    pd.DataFrame(m5_pos).to_csv(OUT / "M5_summary.csv", index=False)
    pd.Series(bins).value_counts(normalize=True).rename("share").to_csv(OUT / "M5_bin_shares.csv", index_label="bin")
    log(f"M2/M5 done ({time.time() - t0:.0f}s)")

    # M3: E10
    rec10 = []
    for key in systems:
        rec, _, _ = e10.run_system(pool, disc, [disc, val], key)
        rec10 += rec
    e10df = pd.DataFrame(rec10)
    e10df.to_csv(OUT / "M3_E10_systems.csv", index=False)
    m3 = []
    for (budget, variant, period), d in e10df.groupby(["budget", "variant", "period"], sort=False):
        if variant not in ("V1_restricted", "V1_shared", "V3_restricted", "V3_shared") or period != "validation":
            continue
        for r in positions(d, "coverage", None, CONTROLS_FOR):
            r.update(budget=budget, variant=variant, period=period,
                     G=float(d[(d.control == "GL") & (d.method == "G")].coverage.iloc[0]))
            m3.append(r)
    pd.DataFrame(m3).to_csv(OUT / "M3_E10_summary.csv", index=False)
    log(f"M3 done ({time.time() - t0:.0f}s)")

    # M4: E5a
    ret = []
    real_rules = []
    for key in systems:
        if key[1] == "G":
            continue
        sel = e5.select_specific(pool, disc, key)
        ev = e5.evaluate_rules(val, pool, key, sel, k=e5.K_PRIMARY)
        ret += e5.retention_summary(ev, key)
        if key[0] == "GL" and len(ev):
            name = lambda c: " + ".join(pool.cols[i] for i in pool.combos[c])
            for r in ev.itertuples():
                real_rules.append(dict(system=key[1], group=r.group, rank=r.rank, antecedent=name(pool.r_ant[r.rule]),
                                       consequent=name(pool.r_con[r.rule]), discovery_advantage_pp=r.discovery_advantage_pp,
                                       validation_advantage_pp=r.future_advantage_pp, direction_retained=r.direction_retained,
                                       q_BY=r.q_BY))
    ret = pd.DataFrame(ret)
    ret.to_csv(OUT / "M4_E5a_systems.csv", index=False)
    pd.DataFrame(real_rules).to_csv(OUT / "M4_E5a_real_rules.csv", index=False)
    allg = ret[ret.group == "ALL"]
    m4 = positions(allg, "direction_retention", None, CONTROLS_FOR)
    for r in m4:
        r["real_rules"] = int(allg[(allg.control == "GL") & (allg.method == r["target"])].rules.iloc[0])
    m4.append(dict(target="L", metric="direction_retention",
                   real=float(allg[(allg.control == "GL") & (allg.method == "L")].direction_retention.iloc[0]),
                   real_rules=int(allg[(allg.control == "GL") & (allg.method == "L")].rules.iloc[0])))
    pd.DataFrame(m4).to_csv(OUT / "M4_E5a_summary.csv", index=False)
    log(f"M4 done ({time.time() - t0:.0f}s)")

    # registered interpretation
    m1s = pd.DataFrame(m1_pos)
    interp = []
    for target, primary in (("F", "B2"), ("F6", "R1")):
        p1 = m1s[(m1s.target == target) & (m1s.metric == "rest_bc_len2")].iloc[0]
        p2 = m2[(m2.target == target) & (m2.period == "validation") & (m2.budget == 100)].iloc[0]
        a1_any = p1["A1_p"] <= 0.05 or p2["A1_p"] <= 0.05
        both_primary = p1[f"{primary}_p"] <= 0.05 and p2[f"{primary}_p"] <= 0.05
        if both_primary:
            verdict = "form_adds_information"
        elif a1_any and not (p1[f"{primary}_p"] <= 0.05 or p2[f"{primary}_p"] <= 0.05):
            verdict = "only_basket_size" if target == "F" else "only_rfm_split"
        elif not a1_any:
            verdict = "nothing_beyond_random"
        else:
            verdict = "mixed"
        fg = "beats_G" if p2.ci_low_pp > 0 else ("tie_with_G" if p2.ci_high_pp >= 0 else "worse_than_G")
        interp.append(dict(target=target, primary_control=primary, M1_real=p1.real, M1_A1_p=p1["A1_p"],
                           M1_primary_p=p1[f"{primary}_p"], M2_real=p2.real, M2_G=p2.G, M2_minus_G_pp=p2.minus_G_pp,
                           M2_ci=f"[{p2.ci_low_pp:.2f}, {p2.ci_high_pp:.2f}]", M2_A1_p=p2["A1_p"],
                           M2_primary_p=p2[f"{primary}_p"], verdict=verdict, vs_G=fg))
    pd.DataFrame(interp).to_csv(OUT / "interpretation.csv", index=False)
    (OUT / "manifest.json").write_text(json.dumps(dict(
        protocol_sha256=E.sha256(CONFIG), test_read=False, systems=len(systems), K_order=k,
        elapsed_seconds=round(time.time() - t0, 1),
        outputs={p.name: E.sha256(p) for p in sorted(OUT.glob("*.csv"))}), indent=2) + "\n")
    log(f"done ({time.time() - t0:.0f}s)")
    log(pd.DataFrame(interp).to_string())
