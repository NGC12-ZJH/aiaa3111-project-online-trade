"""E9: same number of slots per customer -- one list per group vs one global list (configs/extra_eval/E9.json)."""

import numpy as np
import pandas as pd

from .e10 import ranked_lists
from .engine import BUDGETS, combo_walk, paired_interval, random_position


def build(pool, ranked, budget):
    """Top `budget` combinations (E10 V3 de-duplication) for every group of a system."""
    lists, last_rule = {}, {}
    for g, r in ranked.items():
        rows, rules, _ = combo_walk(pool, r, budget)
        lists[g], last_rule[g] = rows, (rules[-1] if rules else None)
    return lists, last_rule


def coverage(period, key, lists):
    cov = np.zeros(period.n, bool)
    groups = period.groups[key]
    for g, rows in lists.items():
        cov |= period.covered(set(rows), groups == g)
    return cov


def run_system(pool, disc, periods, key, g_lists):
    ranked, sizes = ranked_lists(disc, pool, key)
    records, masks, built = [], {}, {}
    for budget in BUDGETS:
        lists, _ = build(pool, ranked, budget)
        built[budget] = lists
        for period in periods:
            cov = coverage(period, key, lists)
            masks[period.name, budget] = cov
            records.append(dict(control=key[0], method=key[1], seed=key[2], budget=budget, period=period.name,
                                slots_per_customer=budget, stored_combinations=len(set().union(*map(set, lists.values()))),
                                shortfall=sum(budget - len(v) for v in lists.values()), **period.summary(cov)))
    return records, masks, built


def describe_real(pool, disc, ranked, sizes, lists_L, lists_G, counts):
    """Discovery description of the real per-group lists against G's list."""
    rows = []
    for budget in BUDGETS:
        gset = set(lists_G[budget]["GLOBAL"])
        for g, combos in lists_L[budget].items():
            s = set(combos)
            last = combos[-1] if combos else None
            rows.append(dict(budget=budget, group=g, discovery_baskets=sizes[g], combinations=len(combos),
                             jaccard_with_G=len(s & gset) / len(s | gset), not_in_G=len(s - gset),
                             last_combination_joint=int(counts[g][0][last]) if last is not None else np.nan))
    return pd.DataFrame(rows)


def per_group(periods, lists_L, lists_G):
    """For each group's orders: coverage by its own list vs by G's list."""
    rows = []
    for name, period in periods.items():
        groups = period.groups[("GL", "L", "")]
        for budget in BUDGETS:
            gcov = period.covered(set(lists_G[budget]["GLOBAL"]))
            for g, combos in lists_L[budget].items():
                m = groups == g
                own = period.covered(set(combos))
                rows.append(dict(period=name, budget=budget, group=g, orders=int(m.sum()),
                                 own_list=own[m].mean(), G_list=gcov[m].mean(),
                                 own_minus_G_pp=100 * (own[m].mean() - gcov[m].mean())))
    return pd.DataFrame(rows)


def summarize(records, gl_masks, periods, weights):
    df = pd.DataFrame(records)
    rows = []
    for (budget, period), d in df.groupby(["budget", "period"], sort=False):
        g, l = d[d.method.eq("G")].iloc[0], d[d.method.eq("L")].iloc[0]
        ci = paired_interval(periods[period], gl_masks["L"][period, budget], gl_masks["G"][period, budget], weights[period])
        row = dict(budget=budget, period=period, G=g.coverage, L=l.coverage, L_minus_G_pp=100 * (l.coverage - g.coverage),
                   ci_low_pp=100 * ci["order"][1], ci_high_pp=100 * ci["order"][2],
                   G_macro=g.customer_macro_coverage, L_macro=l.customer_macro_coverage,
                   L_minus_G_macro_pp=100 * ci["customer_macro"][0],
                   macro_ci_low_pp=100 * ci["customer_macro"][1], macro_ci_high_pp=100 * ci["customer_macro"][2])
        for control in ("A1", "S", "A2"):
            pos = random_position(l.coverage, d[d.control.eq(control)].coverage)
            row.update({f"{control}_{k}": v for k, v in pos.items() if k != "random_n"})
        rows.append(row)
    return pd.DataFrame(rows)


def interpretation(summary):
    out = []
    for _, r in summary[summary.period.eq("validation")].iterrows():
        if r.ci_low_pp <= 0 <= r.ci_high_pp:
            verdict = "split_was_the_cause"
        elif r.ci_low_pp > 0:
            verdict = "group_lists_help" if r.A1_empirical_p <= 0.05 else "help_from_any_split"
        else:
            verdict = "group_lists_worse"
        out.append(dict(budget=r.budget, L_minus_G_pp=r.L_minus_G_pp, ci_low_pp=r.ci_low_pp, ci_high_pp=r.ci_high_pp,
                        A1_empirical_p=r.A1_empirical_p, verdict=verdict))
    return pd.DataFrame(out)
