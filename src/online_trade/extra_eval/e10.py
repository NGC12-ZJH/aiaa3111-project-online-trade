"""E10: how much of L's gap to G comes from duplicate slots (configs/extra_eval/E10.json)."""

import numpy as np

from .engine import BUDGETS, allocate, combo_walk, p5_ranked, redundant, subsets_of, system_sizes


def ranked_lists(period, pool, key):
    """Discovery ranking (P5) and basket count of every group of a system."""
    from .engine import scope_counts
    counts = scope_counts(period, pool, key)
    return {g: p5_ranked(pool, cnt, n) for g, (cnt, n) in counts.items()}, {g: n for g, (cnt, n) in counts.items()}


def build_lists(pool, ranked, sizes, method, budget):
    """All E10 variants for one system and budget.

    Returns {variant: {"flow": ..., "groups": {g: [combo rows]}, "directed": n, "refilled": n}} where
    `groups` lists the combinations each group's customers may use (restricted) or, for shared
    variants, a single pool under key "ALL"."""
    groups = sorted(ranked)
    quota = {"GLOBAL": budget} if method == "G" else allocate(sizes, budget)
    out = {}
    # V1 original: top q_g directed rules per group.
    v1 = {g: list(ranked[g][:quota[g]]) for g in groups}
    v1_rows = {g: [pool.r_joint[r] for r in v1[g]] for g in groups}
    out["V1_restricted"] = dict(groups=v1_rows, directed=sum(len(v) for v in v1.values()), refilled=0,
                                unique_directed=len(set().union(*map(set, v1.values()))))
    out["V1_shared"] = dict(groups={"ALL": [c for g in groups for c in v1_rows[g]]}, directed=out["V1_restricted"]["directed"],
                            refilled=0, unique_directed=out["V1_restricted"]["unique_directed"])
    # V2 teammate: merge by rule_id, refill directed rules by credited / baskets.
    if method == "G":
        out["V2_shared"] = out["V1_shared"]
    else:
        chosen, credit = [], {g: 0.0 for g in groups}
        seen = set()
        for g in groups:
            for r in v1[g]:
                if r not in seen:
                    seen.add(r)
                    chosen.append(r)
                    credit[g] += 1
        pos = {g: quota[g] for g in groups}
        refilled = 0
        while len(chosen) < budget:
            def nxt(g):
                while pos[g] < len(ranked[g]) and ranked[g][pos[g]] in seen:
                    pos[g] += 1
                return pos[g] < len(ranked[g])
            live = [g for g in groups if nxt(g)]
            if not live:
                break
            g = min(live, key=lambda g: (credit[g] / sizes[g], g))
            r = ranked[g][pos[g]]
            pos[g] += 1
            seen.add(r)
            chosen.append(r)
            credit[g] += 1
            refilled += 1
        out["V2_shared"] = dict(groups={"ALL": [pool.r_joint[r] for r in chosen]}, directed=len(chosen), refilled=refilled,
                                unique_directed=len(chosen))
    # V3 restricted: per-group combination walk with the original quota.
    v3, v3pos = {}, {}
    for g in groups:
        rows, _, p = combo_walk(pool, ranked[g], quota[g])
        v3[g], v3pos[g] = rows, p
    out["V3_restricted"] = dict(groups=v3, directed=None, refilled=0,
                                unique_directed=None)
    # V3 / V4 shared: merge, drop duplicates and supersets, refill combinations.
    for variant, fractional in (("V3_shared", False), ("V4_shared", True)):
        if method == "G":
            out[variant] = dict(groups={"ALL": v3["GLOBAL"]}, directed=None, refilled=0, unique_directed=None)
            continue
        owners = {}
        for g in groups:
            for c in v3[g]:
                owners.setdefault(c, []).append(g)
        pool_set, order, credit = set(), [], {g: 0.0 for g in groups}
        for g in groups:  # first-come merge in group order
            for c in v3[g]:
                if c in pool_set:
                    continue
                pool_set.add(c)
                order.append(c)
                if fractional:
                    for h in owners[c]:
                        credit[h] += 1 / len(owners[c])
                else:
                    credit[g] += 1
        for c in list(order):  # a merged triple whose pair arrived from another group adds nothing
            if any(s in pool_set for s in subsets_of(pool, c)):
                pool_set.discard(c)
                order.remove(c)
                share = owners[c] if fractional else [next(h for h in groups if c in v3[h])]
                for h in share:
                    credit[h] -= 1 / len(share)
        pos = dict(v3pos)
        refilled = 0
        while len(order) < budget:
            def nxt(g):
                while pos[g] < len(ranked[g]) and redundant(pool, pool.r_joint[ranked[g][pos[g]]], pool_set):
                    pos[g] += 1
                return pos[g] < len(ranked[g])
            live = [g for g in groups if nxt(g)]
            if not live:
                break
            g = min(live, key=lambda g: (credit[g] / sizes[g], g))
            c = pool.r_joint[ranked[g][pos[g]]]
            pos[g] += 1
            pool_set.add(c)
            order.append(c)
            credit[g] += 1
            refilled += 1
        out[variant] = dict(groups={"ALL": order}, directed=None, refilled=refilled, unique_directed=None)
    return out


def coverage_of(period, key, lists):
    """Covered basket vector for a variant: restricted uses each basket's own group list."""
    if "ALL" in lists["groups"]:
        return period.covered(set(lists["groups"]["ALL"]))
    cov = np.zeros(period.n, bool)
    groups = period.groups[key]
    for g, rows in lists["groups"].items():
        cov |= period.covered(set(rows), groups == g)
    return cov


def combos_of(lists):
    return set(c for rows in lists["groups"].values() for c in rows)


def run_system(pool, disc, periods, key, budgets=BUDGETS):
    ranked, sizes = ranked_lists(disc, pool, key)
    records, masks, list_records = [], {}, {}
    for budget in budgets:
        variants = build_lists(pool, ranked, sizes, key[1], budget)
        list_records[budget] = variants
        for variant, lists in variants.items():
            slots = sum(len(v) for v in lists["groups"].values())
            for period in periods:
                cov = coverage_of(period, key, lists)
                masks[period.name, budget, variant] = cov
                records.append(dict(control=key[0], method=key[1], seed=key[2], budget=budget, variant=variant,
                                    period=period.name, slots=slots, distinct_combinations=len(combos_of(lists)),
                                    directed_slots=lists["directed"], unique_directed=lists["unique_directed"],
                                    refilled=lists["refilled"], **period.summary(cov)))
    return records, masks, list_records


# ---------------------------------------------------------------- report
def summarize(records, gl_masks, periods, weights_by_period):
    """Real L vs G and vs every random control, per variant, budget and period."""
    import pandas as pd
    from .engine import paired_interval, random_position
    df = pd.DataFrame(records)
    rows = []
    for (variant, budget, period), d in df.groupby(["variant", "budget", "period"], sort=False):
        g = d[d.method.eq("G")].iloc[0]
        l = d[d.method.eq("L")].iloc[0]
        row = dict(variant=variant, budget=budget, period=period, G=g.coverage, L=l.coverage,
                   L_minus_G_pp=100 * (l.coverage - g.coverage), G_distinct=g.distinct_combinations,
                   L_distinct=l.distinct_combinations, L_refilled=l.refilled,
                   G_macro=g.customer_macro_coverage, L_macro=l.customer_macro_coverage)
        per = periods[period]
        ci = paired_interval(per, gl_masks["L"][period, budget, variant], gl_masks["G"][period, budget, variant],
                             weights_by_period[period])
        row.update(L_minus_G_ci_low_pp=100 * ci["order"][1], L_minus_G_ci_high_pp=100 * ci["order"][2],
                   L_minus_G_macro_pp=100 * ci["customer_macro"][0])
        for control in ("A1", "S", "A2"):
            r = d[d.control.eq(control)]
            pos = random_position(l.coverage, r.coverage)
            row.update({f"{control}_{k}": v for k, v in pos.items() if k in
                        ("random_median", "random_p95", "random_min", "random_max", "random_ge_real", "empirical_p")})
        rows.append(row)
    s = pd.DataFrame(rows)
    disc = s[s.period.eq("discovery")].set_index(["variant", "budget"]).L_minus_G_pp
    val = s[s.period.eq("validation")].set_index(["variant", "budget"]).L_minus_G_pp
    home = (val - disc).rename("home_advantage_pp").reset_index()
    return s, home


def interpretation(summary, home):
    """Apply the registered interpretation rules (Validation, E10.json)."""
    v = summary[summary.period.eq("validation")].set_index(["variant", "budget"])
    out = []
    for flow in ("restricted", "shared"):
        for b in BUDGETS:
            gap1, gap3 = v.loc[(f"V1_{flow}", b), "L_minus_G_pp"], v.loc[(f"V3_{flow}", b), "L_minus_G_pp"]
            out.append(dict(rule="gap_mainly_duplicates", flow=flow, budget=b, V1_gap_pp=gap1, V3_gap_pp=gap3,
                            ratio=abs(gap3) / abs(gap1) if gap1 else np.nan, passes=abs(gap3) <= 0.5 * abs(gap1)))
    for b in BUDGETS:
        d = 100 * abs(v.loc[("V3_shared", b), "L"] - v.loc[("V4_shared", b), "L"])
        out.append(dict(rule="attribution_irrelevant", flow="shared", budget=b, V3_vs_V4_pp=d, passes=d < 0.5))
    h = home.set_index(["variant", "budget"]).home_advantage_pp
    for variant in ("V1_restricted", "V1_shared"):
        out.append(dict(rule="discovery_overstates_G", flow=variant.split("_")[1], budget=100,
                        home_advantage_pp=h.loc[(variant, 100)], passes=h.loc[(variant, 100)] > 0))
    import pandas as pd
    return pd.DataFrame(out)


def list_table(pool, list_records, method):
    """Readable lists of one system (real G or L) for every variant and budget."""
    import pandas as pd
    rows = []
    for budget, variants in list_records.items():
        for variant, lists in variants.items():
            for g, combos in lists["groups"].items():
                for rank, c in enumerate(combos, 1):
                    rows.append(dict(method=method, budget=budget, variant=variant, list=g, rank=rank,
                                     combination=" + ".join(pool.cols[k] for k in pool.combos[c]),
                                     length=len(pool.combos[c])))
    return pd.DataFrame(rows)
