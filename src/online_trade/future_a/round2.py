"""Round 2 of future work A: Discovery labels + rules re-mined by the new groups, evaluated on Validation.

Registered: configs/future_A/round2.json. Test is never read (extra_eval engine lock).
"""

import json
import platform
import subprocess
import time

import numpy as np
import pandas as pd

from online_trade.clustering.activity_control import matched_permutations, stratify
from online_trade.extra_eval import e5, e9, e10
from online_trade.extra_eval import engine as E
from online_trade.extra_eval.e10 import ranked_lists

from . import precheck as P

OUT = E.ROOT / "results/tables/future_A/round2"
PROTOCOL = E.ROOT / "configs/future_A/round2.json"
A2P_SEEDS = range(2000, 2100)
A2_BOUNDS, A2_LABELS = [0, 1, 2, 4, 9, None], ["0", "1", "2", "3-4", "5-9", "10+"]
GL_G, GL_L, R2_L = ("GL", "G", ""), ("GL", "L", ""), ("R2", "L", "")
E10_VARIANTS = ("V1_restricted", "V1_shared", "V3_shared")


def new_labels():
    frozen = P.frozen_labels()
    orders = P.load_orders()
    val_b, _, _ = E.load_period("validation")
    out = P.labels_drift(orders, frozen, set(val_b.customer_id))
    labels = out[7]
    sizes = labels.P1.value_counts().sort_index().tolist()
    assert sizes == [1053, 829, 802], f"P1 sizes changed: {sizes}"
    return labels


def a2p_controls(labels, disc_baskets):
    counts = labels.customer_id.map(disc_baskets.customer_id.value_counts()).fillna(0).to_numpy()
    strata = stratify(counts, A2_BOUNDS, A2_LABELS)
    perms = matched_permutations(labels.P1, strata, A2P_SEEDS)
    real = pd.crosstab(strata, labels.P1.to_numpy())
    maps = {}
    for seed, row in zip(A2P_SEEDS, perms):
        got = pd.crosstab(strata, row).reindex(index=real.index, columns=real.columns, fill_value=0)
        assert (got.to_numpy() == real.to_numpy()).all(), seed
        maps[("A2p", "R", str(seed))] = dict(zip(labels.customer_id, row))
    return maps, pd.Series(strata).value_counts().sort_index()


def pos(real, values, prefix):
    p = E.random_position(real, np.asarray(values, dtype=float))
    return {f"{prefix}_{k}": v for k, v in p.items() if k != "random_n"}


def ci_cols(val, left, right, weights, prefix):
    ci = E.paired_interval(val, left, right, weights)
    return {f"{prefix}_pp": 100 * ci["order"][0], f"{prefix}_ci_low_pp": 100 * ci["order"][1],
            f"{prefix}_ci_high_pp": 100 * ci["order"][2], f"{prefix}_macro_pp": 100 * ci["customer_macro"][0],
            f"{prefix}_macro_ci_low_pp": 100 * ci["customer_macro"][1],
            f"{prefix}_macro_ci_high_pp": 100 * ci["customer_macro"][2]}


def run():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    labels = new_labels()
    pool = E.build_pool()
    systems, maps = E.load_systems()
    disc_b, _, _ = E.load_period("discovery")
    a2p_maps, strata_sizes = a2p_controls(labels, disc_b)
    maps.update(a2p_maps)
    maps[R2_L] = dict(zip(labels.customer_id, labels.P1))
    a1 = [k for k in systems if k[0] == "A1"]
    a2p = list(a2p_maps)
    keys = [GL_G, GL_L, R2_L] + a1 + a2p
    disc = E.Period("discovery", pool, keys, maps)
    val = E.Period("validation", pool, keys, maps)
    weights = E.bootstrap_weights(len(val.customers))
    active = set(labels.customer_id[labels.active_in_discovery])
    active_mask = val.baskets.customer_id.isin(active).to_numpy()
    print(f"inputs ready: {len(keys)} systems ({time.time() - started:.1f}s)", flush=True)

    # ---------------- E9 (primary)
    e9_records, e9_masks, e9_lists = [], {}, {}
    for i, key in enumerate(keys):
        rec, masks, built = e9.run_system(pool, disc, [val], key, None)
        e9_records += rec
        e9_masks[key], e9_lists[key] = masks, built
        if i % 50 == 0:
            print(f"  E9 system {i + 1}/{len(keys)} ({time.time() - started:.1f}s)", flush=True)
    swap = {b: e9.coverage(val, R2_L, e9_lists[GL_L][b]) for b in E.BUDGETS}
    e9_df = pd.DataFrame(e9_records)
    rows = []
    for b in E.BUDGETS:
        cov = lambda key: e9_masks[key][("validation", b)]
        d = e9_df[e9_df.budget.eq(b)].set_index(["control", "method", "seed"]).sort_index()
        row = dict(budget=b, G=cov(GL_G).mean(), L_orig=cov(GL_L).mean(), L_swap=swap[b].mean(), L_new=cov(R2_L).mean(),
                   G_macro=val.summary(cov(GL_G))["customer_macro_coverage"],
                   L_orig_macro=val.summary(cov(GL_L))["customer_macro_coverage"],
                   L_new_macro=val.summary(cov(R2_L))["customer_macro_coverage"],
                   L_new_shortfall=int(d.loc[R2_L, "shortfall"]))
        row.update(ci_cols(val, cov(R2_L), cov(GL_L), weights, "new_minus_orig"))
        row.update(ci_cols(val, cov(R2_L), cov(GL_G), weights, "new_minus_G"))
        row.update(ci_cols(val, cov(R2_L), swap[b], weights, "new_minus_swap"))
        row.update(pos(row["L_new"], d.loc["A2p"].coverage, "A2p"))
        row.update(pos(row["L_orig"], d.loc["A1"].coverage, "A1"))
        # sensitivity: customers active in Discovery only
        row.update(active_baskets=int(active_mask.sum()), G_active=cov(GL_G)[active_mask].mean(),
                   L_orig_active=cov(GL_L)[active_mask].mean(), L_new_active=cov(R2_L)[active_mask].mean())
        rows.append(row)
    e9_sum = pd.DataFrame(rows)
    r = e9_sum.set_index("budget").loc[100]
    if r.new_minus_orig_ci_low_pp > 0:
        verdict = "refresh_helps" if r.A2p_empirical_p <= 0.05 else "refresh_helps_like_any_split"
    elif r.new_minus_orig_ci_high_pp < 0:
        verdict = "refresh_hurts"
    else:
        verdict = "no_gain"
    print(f"E9 done ({time.time() - started:.1f}s): {verdict}", flush=True)

    # list description of L_new vs G (Discovery)
    ranked, sizes = ranked_lists(disc, pool, R2_L)
    counts = E.scope_counts(disc, pool, R2_L)
    desc_new = e9.describe_real(pool, disc, ranked, sizes, e9_lists[R2_L], e9_lists[GL_G], counts).assign(system="L_new")
    ranked_o, sizes_o = ranked_lists(disc, pool, GL_L)
    desc_orig = e9.describe_real(pool, disc, ranked_o, sizes_o, e9_lists[GL_L], e9_lists[GL_G],
                                 E.scope_counts(disc, pool, GL_L)).assign(system="L_orig")
    list_desc = pd.concat([desc_orig, desc_new])

    # ---------------- E10 (descriptive)
    e10_records, e10_masks = [], {}
    for key in keys:
        rec, masks, _ = e10.run_system(pool, disc, [val], key)
        e10_records += [x for x in rec if x["variant"] in E10_VARIANTS]
        e10_masks[key] = masks
    e10_df = pd.DataFrame(e10_records)
    rows = []
    for variant in E10_VARIANTS:
        for b in E.BUDGETS:
            m = lambda key: e10_masks[key][("validation", b, variant)]
            d = e10_df[e10_df.variant.eq(variant) & e10_df.budget.eq(b)].set_index(["control", "method", "seed"]).sort_index()
            row = dict(variant=variant, budget=b, G=m(GL_G).mean(), L_orig=m(GL_L).mean(), L_new=m(R2_L).mean(),
                       G_distinct=int(d.loc[GL_G, "distinct_combinations"]),
                       L_orig_distinct=int(d.loc[GL_L, "distinct_combinations"]),
                       L_new_distinct=int(d.loc[R2_L, "distinct_combinations"]))
            row.update(ci_cols(val, m(R2_L), m(GL_L), weights, "new_minus_orig"))
            row.update(ci_cols(val, m(R2_L), m(GL_G), weights, "new_minus_G"))
            row.update(pos(row["L_new"], d.loc["A2p"].coverage, "A2p"))
            rows.append(row)
    e10_sum = pd.DataFrame(rows)
    print(f"E10 done ({time.time() - started:.1f}s)", flush=True)

    # ---------------- E5 (descriptive)
    g_rows = e5.g_list(pool, disc, 100 + 3 * 20)
    ret_rows, gain_rows, sel_real = [], [], {}
    for key in [GL_L, R2_L] + a1 + a2p:
        sel = e5.select_specific(pool, disc, key)
        ev = e5.evaluate_rules(val, pool, key, sel, k=e5.K_PRIMARY)
        ret_rows += e5.retention_summary(ev, key)
        lists = {g: [(it["combo"], False) for it in items] for g, items in sel.items()}
        row, _, _ = e5.gain_rows(pool, val, key, g_rows, lists, 50, 10, "unconfirmed")
        gain_rows.append(row)
        if key[0] in ("GL", "R2"):
            sel_real[key[0]] = (sel, ev)
    ret = pd.DataFrame(ret_rows)
    gains = pd.DataFrame(gain_rows)
    e5_sum = []
    for real_key, control in [(GL_L, "A1"), (R2_L, "A2p")]:
        for group in ("ALL", "0", "1", "2"):
            rr = ret[(ret.control == real_key[0]) & (ret.group == group)]
            if rr.empty:
                continue
            rr = rr.iloc[0]
            vals = ret[(ret.control == control) & (ret.group == group)].direction_retention.dropna()
            row = dict(system="L_orig" if real_key == GL_L else "L_new", control=control, group=group, rules=rr.rules,
                       direction_retention=rr.direction_retention, evidence_retained=rr.evidence_retained)
            if len(vals) and pd.notna(rr.direction_retention):
                row.update(pos(rr.direction_retention, vals, control))
            e5_sum.append(row)
        g = gains[gains.control.eq(real_key[0])].iloc[0]
        row = dict(system="L_orig" if real_key == GL_L else "L_new", control=control, group="E5b_gain_pp",
                   rules=np.nan, direction_retention=g.gain_pp, evidence_retained=np.nan)
        row.update(pos(g.gain_pp, gains[gains.control.eq(control)].gain_pp, control))
        e5_sum.append(row)
    e5_sum = pd.DataFrame(e5_sum)
    print(f"E5 done ({time.time() - started:.1f}s)", flush=True)

    # ---------------- write
    e9_df.to_csv(OUT / "E9_system_metrics.csv", index=False)
    e9_sum.to_csv(OUT / "E9_summary.csv", index=False)
    list_desc.to_csv(OUT / "list_description.csv", index=False)
    e10_df.to_csv(OUT / "E10_system_metrics.csv", index=False)
    e10_sum.to_csv(OUT / "E10_summary.csv", index=False)
    ret.to_csv(OUT / "E5_retention_by_system.csv", index=False)
    gains.to_csv(OUT / "E5_gain_by_system.csv", index=False)
    e5_sum.to_csv(OUT / "E5_summary.csv", index=False)
    name = lambda c: " + ".join(pool.cols[k] for k in pool.combos[c])
    lists_rows = [dict(system=s, budget=100, group=g, rank=i, combination=name(c))
                  for s, key in [("L_orig", GL_L), ("L_new", R2_L)]
                  for g, combos in e9_lists[key][100].items() for i, c in enumerate(combos, 1)]
    pd.DataFrame(lists_rows).to_csv(OUT / "lists_B100.csv", index=False)
    decision = dict(H_R2=dict(budget=100, L_new_minus_L_orig_pp=r.new_minus_orig_pp,
                              ci=[r.new_minus_orig_ci_low_pp, r.new_minus_orig_ci_high_pp],
                              A2p_empirical_p=r.A2p_empirical_p, verdict=verdict),
                    secondary=dict(L_new_minus_G_pp=r.new_minus_G_pp, L_new_minus_G_ci=[r.new_minus_G_ci_low_pp, r.new_minus_G_ci_high_pp],
                                   L_new_minus_L_swap_pp=r.new_minus_swap_pp,
                                   L_new_minus_L_swap_ci=[r.new_minus_swap_ci_low_pp, r.new_minus_swap_ci_high_pp]))
    (OUT / "decision.json").write_text(json.dumps(decision, indent=2, default=float) + "\n", encoding="utf-8")
    files = sorted(OUT.glob("*.csv")) + [OUT / "decision.json"]
    manifest = dict(protocol="configs/future_A/round2.json", protocol_sha256=E.sha256(PROTOCOL), test_read=False,
                    git_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=E.ROOT, text=True).strip(),
                    python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__,
                    systems=len(keys), a2p_strata_sizes=strata_sizes.to_dict(),
                    checks=dict(new_label_sizes=[1053, 829, 802]),
                    elapsed_seconds=round(time.time() - started, 1), outputs={p.name: E.sha256(p) for p in files})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(decision, indent=2, default=float))
    print(f"round2 done in {time.time() - started:.1f}s", flush=True)
