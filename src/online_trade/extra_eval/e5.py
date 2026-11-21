"""E5: do group-specific rules stay specific, and are group-specific slots worth it? (configs/extra_eval/E5.json)"""

import numpy as np
import pandas as pd
from scipy import stats

from .engine import combo_walk, p5_ranked, paired_interval, random_position, redundant, rule_stats, scope_counts

IN = dict(joint=20, joint_customers=10, max_share=0.5, antecedent=20, confidence=0.40, lift=1.3, increment=0.10)
OUT_ANT = dict(orders=20, customers=10)
MIN_ADV_PP = 5.0
K_MAX = 20
K_PRIMARY = 10
EVIDENCE = dict(ant_orders=20, ant_customers=10, joint_orders=10, joint_customers=5, max_share=0.5,
                out_ant_orders=20, out_ant_customers=10)


def by_adjust(p):
    """Benjamini-Yekutieli adjusted p-values."""
    p = np.asarray(p, dtype=float)
    m = len(p)
    if m == 0:
        return p
    order = np.argsort(p)
    h = np.sum(1 / np.arange(1, m + 1))
    adj = p[order] * m * h / np.arange(1, m + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(adj, 1)
    return out


def column_by_side(period, col, side_mask):
    """(distinct customers, total, max per customer) of one combo column restricted to customers in side_mask."""
    m = period.cust_combo
    start, end = m.indptr[col], m.indptr[col + 1]
    idx, val = m.indices[start:end], m.data[start:end]
    keep = side_mask[idx]
    val = val[keep]
    return int((val > 0).sum()), float(val.sum()), float(val.max()) if len(val) else 0.0


# ---------------------------------------------------------------- Discovery selection
def select_specific(pool, disc, key):
    """Up to K_MAX group-specific directed rules per group of a system, in registered order."""
    counts = scope_counts(disc, pool, key)
    total = sum(cnt for cnt, _ in counts.values())
    n_all = disc.n
    cust_groups = disc.cust_groups[key]
    out = {}
    for g, (cnt, n) in counts.items():
        j, a, c, conf, lift, inc = rule_stats(pool, cnt, n)
        three = pool.r_length == 3
        out_cnt = total - cnt
        n_out = n_all - n
        ja, aa, ca = out_cnt[pool.r_joint], out_cnt[pool.r_ant], out_cnt[pool.r_con]
        with np.errstate(divide="ignore", invalid="ignore"):
            conf_out = np.where(aa > 0, ja / aa, np.nan)
            adv = 100 * ((conf - c / n) - (conf_out - ca / n_out))
        ok = ((j >= IN["joint"]) & (a >= IN["antecedent"]) & (conf + 1e-12 >= IN["confidence"])
              & (lift + 1e-12 >= IN["lift"]) & (~three | (inc >= IN["increment"] - 1e-10))
              & (aa >= OUT_ANT["orders"]) & (adv >= MIN_ADV_PP - 1e-9))
        idx = np.flatnonzero(ok)
        order = idx[np.lexsort((pool.rule_id[idx], -conf[idx], -j[idx], -adv[idx]))]
        in_side, out_side = cust_groups == g, cust_groups != g
        kept, picked = set(), []
        for r in order:
            cr = pool.r_joint[r]
            if redundant(pool, cr, kept):
                continue
            jc, jt, jmax = column_by_side(disc, cr, in_side)
            if jc < IN["joint_customers"] or jmax / jt > IN["max_share"]:
                continue
            oc, _, _ = column_by_side(disc, pool.r_ant[r], out_side)
            if oc < OUT_ANT["customers"]:
                continue
            kept.add(cr)
            picked.append(dict(rule=int(r), combo=int(cr), discovery_advantage_pp=float(adv[r]), joint=int(j[r]),
                               confidence=float(conf[r]), lift=float(lift[r]), outside_confidence=float(conf_out[r])))
            if len(picked) == K_MAX:
                break
        out[g] = picked
    return out


# ---------------------------------------------------------------- future evaluation
def side_stats(period, pool, rule, side_mask):
    """Counts, customer evidence and the influence-function variance of d = J/A - C/N on one side."""
    cust = np.flatnonzero(side_mask)
    m = period.cust_combo
    col = lambda c: np.asarray(m[cust, c].todense()).ravel()
    J, A, C = col(pool.r_joint[rule]), col(pool.r_ant[rule]), col(pool.r_con[rule])
    Nn = period.orders_per_customer[cust]
    j, a, c, n = J.sum(), A.sum(), C.sum(), Nn.sum()
    res = dict(orders=n, customers=len(cust), joint=j, antecedent=a, consequent=c,
               ant_customers=int((A > 0).sum()), joint_customers=int((J > 0).sum()),
               max_share=float(J.max() / j) if j > 0 else np.nan)
    if a == 0 or n == 0:
        res.update(d=np.nan, var=np.nan)
        return res
    conf, base = j / a, c / n
    u = (J - conf * A) / a - (C - base * Nn) / n
    k = len(cust)
    res.update(confidence=conf, base=base, d=conf - base, var=k / (k - 1) * np.sum(u ** 2) if k > 1 else np.nan)
    return res


def evaluate_rules(period, pool, key, selected, k=K_PRIMARY):
    """Future advantage, evidence and test for the top-k selected rules of every group of a system."""
    groups = period.cust_groups[key]
    rows = []
    for g, rules in selected.items():
        for rank, item in enumerate(rules[:k], 1):
            r = item["rule"]
            ins, outs = side_stats(period, pool, r, groups == g), side_stats(period, pool, r, groups != g)
            adv = 100 * (ins["d"] - outs["d"])
            se = 100 * np.sqrt(ins["var"] + outs["var"])
            df = min(ins["customers"], outs["customers"]) - 1
            if np.isfinite(adv) and np.isfinite(se) and se > 0 and df > 0:
                p = float(stats.t.sf(adv / se, df))
            else:
                p = 1.0
            evidence = (ins["antecedent"] >= EVIDENCE["ant_orders"] and ins["ant_customers"] >= EVIDENCE["ant_customers"]
                        and ins["joint"] >= EVIDENCE["joint_orders"] and ins["joint_customers"] >= EVIDENCE["joint_customers"]
                        and (ins["max_share"] <= EVIDENCE["max_share"] if np.isfinite(ins["max_share"]) else False)
                        and outs["antecedent"] >= EVIDENCE["out_ant_orders"]
                        and outs["ant_customers"] >= EVIDENCE["out_ant_customers"])
            rows.append(dict(group=g, rank=rank, rule=r, combo=item["combo"],
                             discovery_advantage_pp=item["discovery_advantage_pp"], future_advantage_pp=adv,
                             se_pp=se, p_one_sided=p, evidence_ok=bool(evidence),
                             in_antecedent=ins["antecedent"], in_joint=ins["joint"], out_antecedent=outs["antecedent"],
                             direction_retained=bool(np.isfinite(adv) and adv > 0)))
    out = pd.DataFrame(rows)
    if len(out):
        out["q_BY"] = by_adjust(out.p_one_sided.to_numpy())
        out["evidence_retained"] = (out.future_advantage_pp >= MIN_ADV_PP) & out.evidence_ok & (out.q_BY <= 0.05)
        out["confirmed"] = out.direction_retained & out.evidence_ok
        with np.errstate(divide="ignore", invalid="ignore"):
            out["effect_ratio"] = out.future_advantage_pp / out.discovery_advantage_pp
    return out


def retention_summary(ev, key):
    base = dict(control=key[0], method=key[1], seed=key[2])
    rows = [dict(base, group="ALL", rules=len(ev),
                 direction_retention=ev.direction_retained.mean() if len(ev) else np.nan,
                 effect_ratio_median=ev.effect_ratio.median() if len(ev) else np.nan,
                 evidence_retained=int(ev.evidence_retained.sum()) if len(ev) else 0,
                 confirmed=int(ev.confirmed.sum()) if len(ev) else 0)]
    for g, d in ev.groupby("group") if len(ev) else []:
        rows.append(dict(base, group=g, rules=len(d), direction_retention=d.direction_retained.mean(),
                         effect_ratio_median=d.effect_ratio.median(), evidence_retained=int(d.evidence_retained.sum()),
                         confirmed=int(d.confirmed.sum())))
    return rows


# ---------------------------------------------------------------- E5b
def g_list(pool, disc, length):
    """G's P5 ranking with E10 V3 de-duplication."""
    cnt, n = scope_counts(disc, pool, ("GL", "G", ""))["GLOBAL"]
    rows, _, _ = combo_walk(pool, p5_ranked(pool, cnt, n), length)
    return rows


def hybrid_coverage(pool, period, key, g_rows, specific_combos, b0):
    """Hybrid (G top b0 + own-group specific) vs comparator (G top b0 + k_g')."""
    base = set(g_rows[:b0])
    groups = period.groups[key]
    hyb, comp = np.zeros(period.n, bool), np.zeros(period.n, bool)
    extra = {}
    for g, combos in specific_combos.items():
        add = [c for c in combos if not redundant(pool, c, base)]
        extra[g] = len(add)
        m = groups == g
        hyb |= period.covered(base | set(add), m)
        comp |= period.covered(set(g_rows[:b0 + len(add)]), m)
    return hyb, comp, extra


def gain_rows(pool, period, key, g_rows, lists, b0, k, version):
    """`lists[g]` holds (combo, confirmed) pairs in Discovery order; the confirmed version keeps
    only confirmed combos among the Discovery top k."""
    chosen = {g: [c for c, ok in v[:k] if version == "unconfirmed" or ok] for g, v in lists.items()}
    hyb, comp, extra = hybrid_coverage(pool, period, key, g_rows, chosen, b0)
    return dict(control=key[0], method=key[1], seed=key[2], period=period.name, version=version, B0=b0, k=k,
                hybrid=hyb.mean(), comparator=comp.mean(), gain_pp=100 * (hyb.mean() - comp.mean()),
                **{f"extra_slots_{g}": v for g, v in extra.items()}), hyb, comp
