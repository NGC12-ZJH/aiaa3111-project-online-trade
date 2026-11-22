"""Validation-only comparison using nested and actually deduplicated rule budgets."""
from collections import defaultdict
from importlib.util import module_from_spec, spec_from_file_location
from itertools import combinations
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

BUDGETS = tuple(range(10, 101, 10))
UNITS = ("combination", "direction")
CONFIGS = ("P1", "P2", "P3", "P4", "P5")
G = ("GL", "G", "")
L = ("GL", "L", "")
QUALITY = dict(min_antecedent_orders=20, min_joint_orders=10, min_antecedent_customers=10,
               min_joint_customers=5, max_customer_joint_share=.5, min_confidence_uplift=.05,
               min_lift=1.2, min_triple_increment_pp=5, adjustment="BY", alpha=.05)


def prepare_index(repo, discovery):
    src = repo / "experiments/discovery_residual_refill/run.py"
    spec = spec_from_file_location("discovery_reconstruction", src)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    index = module.DirectionIndex(discovery)
    names = sorted(discovery.items)
    components = [(i,) for i in range(len(names))]
    components.extend(combinations(range(len(names)), 2))
    components.extend(x for x in combinations(range(len(names)), 3)
                      if discovery.mask(names[i] for i in x).bit_count() >= 20)
    assert len(components) == len(index.masks)
    terms = [tuple(names[i] for i in x) for x in components]
    definitions = {str(i): (terms[a], terms[c])
                   for i, (a, c) in enumerate(zip(index.antecedent, index.consequent))}
    return index, definitions


def nested_pool(index, per_group_ranks, sizes, unit):
    """At each position favor the group furthest below its proportional cumulative share."""
    groups = sorted(per_group_ranks)
    denominator = sum(sizes.values())
    used, pool = set(), []
    contributed = dict.fromkeys(groups, 0)
    pointers = dict.fromkeys(groups, 0)
    for position in range(1, max(BUDGETS) + 1):
        eligible = []
        for group in groups:
            ranking = per_group_ranks[group]
            while pointers[group] < len(ranking):
                r = ranking[pointers[group]]
                key = r if unit == "direction" else int(index.joint[r])
                if key not in used:
                    break
                pointers[group] += 1
            if pointers[group] < len(ranking):
                eligible.append(group)
        if not eligible:
            raise ValueError(f"Fewer than {position} unique {unit} entries in {groups}")
        owner = min(eligible, key=lambda g: (contributed[g] * denominator - position * sizes[g], g))
        r = per_group_ranks[owner][pointers[owner]]
        key = r if unit == "direction" else int(index.joint[r])
        used.add(key)
        pool.append((r, owner, pointers[owner] + 1))
        contributed[owner] += 1
        pointers[owner] += 1
    assert len(used) == len(pool) == 100
    return pool


def rows_for(system, pools, index, complete, antecedents, validation, scopes, accepted, raw_store):
    method = system[1]
    n = validation.n
    for (config, unit), roster in pools.items():
        shared = scoped = good = trigger = 0
        passed = 0
        previous = defaultdict(int)
        selected_joints = set()
        for i, (r, g, _rank) in enumerate(roster, 1):
            hit = complete[r]
            shared |= hit
            scoped |= hit & scopes[g]
            trigger |= antecedents[r]
            selected_joints.add(int(index.joint[r]))
            if r in accepted:
                good |= hit
                passed += 1
            if i not in BUDGETS:
                continue
            values = {"shared_covered": shared.bit_count(), "restricted_covered": scoped.bit_count(),
                      "reliable_covered": good.bit_count(), "shared_triggered": trigger.bit_count()}
            assert (good & ~shared) == 0 and scoped & ~shared == 0
            assert all(count >= previous[key] for key, count in values.items())
            if unit == "combination":
                assert len(selected_joints) == i
            prefix = dict(control=system[0], method=method, seed=system[2], config=config, unit=unit, budget=i,
                          orders=n, unique_directional=i, unique_combinations=len(selected_joints),
                          accepted_slots=passed, accepted_share=passed / i)
            row = {**prefix, **values}
            values.pop("shared_triggered")
            for key, count in values.items():
                row[key + "_rate"] = count / n
                row[key + "_gain_pp"] = 100 * (count - previous[key]) / n
            if system in (G, L):
                customer = validation.by_customer.values()
                row["shared_customer_macro"] = np.mean([(shared & c).bit_count()/c.bit_count() for c in customer])
                row["reliable_customer_macro"] = np.mean([(good & c).bit_count()/c.bit_count() for c in customer])
                raw_store[method, config, unit, i] = {"raw": shared, "reliable": good, "restricted": scoped}
            yield row
            previous.update(values)


def summary(systems):
    keys = ["config", "unit", "budget"]
    metrics = ["shared_covered_rate", "reliable_covered_rate", "restricted_covered_rate",
               "shared_covered_gain_pp", "reliable_covered_gain_pp", "restricted_covered_gain_pp"]
    pairs = []
    for values, data in systems.groupby(keys, sort=True):
        gl = data.loc[data.control.eq("GL")].set_index("method")
        for control in ("A1", "S", "A2"):
            random = data.loc[data.control.eq(control)]
            for metric in metrics:
                draws = random[metric]
                upper = int(draws.ge(gl.loc["L", metric]).sum())
                pairs.append(dict(zip(keys, values)) | {
                    "control": control, "measure": metric, "G": gl.loc["G", metric], "L": gl.loc["L", metric],
                    "L_minus_G": gl.loc["L", metric] - gl.loc["G", metric],
                    "random_seeds": len(draws), "random_min": draws.min(), "random_median": draws.median(),
                    "random_max": draws.max(), "random_ge_L": upper, "upper_tail": (1 + upper)/(1 + len(draws)),
                })
    return pd.DataFrame(pairs)


def select_budget(gl):
    """Compare both methods to their best reliable shared coverage on the grid."""
    x = gl.loc[gl.unit.eq("combination")].pivot(index=["config", "budget"], columns="method",
                                                values="reliable_covered_rate").reset_index()
    x["G_shortfall_pp"] = 100 * (x.G.max() - x.G)
    x["L_shortfall_pp"] = 100 * (x.L.max() - x.L)
    x["worst_shortfall_pp"] = x[["G_shortfall_pp", "L_shortfall_pp"]].max(axis=1)
    decisions = []
    for label, data in [("all", x)] + [(p, x.loc[x.config.eq(p)]) for p in CONFIGS]:
        table = data.copy()
        table["G_shortfall_pp"] = 100 * (table.G.max() - table.G)
        table["L_shortfall_pp"] = 100 * (table.L.max() - table.L)
        table["worst_shortfall_pp"] = table[["G_shortfall_pp", "L_shortfall_pp"]].max(axis=1)
        for cap in (.5, 1., 2.):
            passed = table.loc[table.worst_shortfall_pp.le(cap + 1e-10)]
            style = "within" if len(passed) else "best_available"
            order = ["budget", "worst_shortfall_pp", "config"] if len(passed) else [
                "worst_shortfall_pp", "budget", "config"]
            chosen = (passed if len(passed) else table).sort_values(order).iloc[0]
            decisions.append({"range": label, "tolerance_pp": cap, "state": style, **chosen.to_dict()})
    return x, pd.DataFrame(decisions)


def intervals(validation, masks):
    repeats = 1500
    customers = list(validation.by_customer.values())
    n = len(customers)
    rng = np.random.default_rng(1122)
    weight = rng.multinomial(n, np.full(n, 1/n), size=repeats).astype(float)
    counts = weight @ np.array([c.bit_count() for c in customers])
    captions, contrasts = [], []

    def add(l, r, metadata):
        captions.append(metadata | {"delta_pp": 100 * (l.bit_count() - r.bit_count()) / validation.n})
        contrasts.append([(l & c).bit_count() - (r & c).bit_count() for c in customers])

    for p in CONFIGS:
        for unit in UNITS:
            for metric in ("raw", "reliable", "restricted"):
                for b in BUDGETS:
                    l = masks["L", p, unit, b][metric]
                    g = masks["G", p, unit, b][metric]
                    add(l, g, {"config": p, "unit": unit, "budget": b, "measure": metric, "contrast": "L_minus_G"})
                    for method in ("G", "L"):
                        current = masks[method, p, unit, b][metric]
                        if b > 10:
                            ref = masks[method, p, unit, b - 10][metric]
                            add(current, ref, {"config": p, "unit": unit, "budget": b,
                                               "measure": metric, "contrast": method + "_add_10"})
                        if b != 100:
                            perfect = masks[method, p, unit, 100][metric]
                            add(perfect, current, {"config": p, "unit": unit, "budget": b,
                                                   "measure": metric, "contrast": method + "_100_minus_B"})
    for i in range(0, len(contrasts), 100):
        estimates = 100 * (weight @ np.array(contrasts[i:i+100], dtype=float).T) / counts[:, None]
        for row, lo, hi in zip(captions[i:i+100], *np.quantile(estimates, [.025, .975], axis=0)):
            row.update(low95_pp=lo, high95_pp=hi)
    return pd.DataFrame(captions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    repo = args.repo.resolve()
    sys.path.insert(0, str(repo / "src"))
    from online_trade.evaluation.validation import load_inputs, load_period
    from online_trade.evaluation.quality import QualityEvidence, adjust_fdr, classify

    local = repo / "data/processed/local/D_validation"
    core, tax, true, mappings, frozen, configs = load_inputs(local, repo, {"configs": CONFIGS})
    disc, _, _ = load_period(local, "discovery", tax, true)
    val, _, _ = load_period(local, "validation", tax, true)
    index, definitions = prepare_index(repo, disc)
    expected = pd.read_csv(core / "scope_summary.csv", dtype={"seed": str,"group_id": str}, keep_default_na=False)
    key_cols = ["control", "method", "seed", "group_id", "config"]
    expected = expected.pivot(index=key_cols, columns="length", values="rules")
    originals = dict(tuple(frozen.groupby(key_cols)))
    counts_checked = 0
    roster_checks = 0
    results, gl_masks, pool_rows = [], {}, []
    evidence = QualityEvidence(val, disc, {}, definitions)
    complete, antecedents = {}, {}
    for system, mapping in mappings.items():
        groups = ("GLOBAL",) if system == G else ("0", "1", "2")
        pools = {}
        sizes, scopes = {}, {}
        ratings = defaultdict(dict)
        for g in groups:
            s = disc.all if system == G else disc.scope(mapping, g)
            sizes[g] = s.bit_count()
            scopes[g] = val.all if system == G else val.scope(mapping, g)
            for p, ranking, counts in index.ranks(s, sizes[g], configs):
                key = (*system, g, p)
                assert counts == tuple(expected.loc[key, [0, 2, 3]].astype(int)), (key,counts)
                counts_checked += 1
                ratings[p][g] = ranking
                for _, old in originals[key].groupby("budget"):
                    old = old.sort_values("rank_within_group")
                    assert index.ids[ranking[:len(old)]].tolist() == old.rule_id.tolist(), key
                    roster_checks += 1
        assert sum(sizes.values()) == disc.n and sum(m.bit_count() for m in scopes.values()) == val.n
        for p, ranking in ratings.items():
            for u in UNITS:
                pools[p, u] = nested_pool(index, ranking, sizes, u)
                if system in (G, L) or system[0] == "A1":
                    for position, (r, group, rank) in enumerate(pools[p, u], start=1):
                        ant, con = definitions[str(r)]
                        pool_rows.append((*system, p, u, position, group, index.ids[r], rank,
                                          " + ".join(ant), con[0]))
        family = sorted({r for rows in pools.values() for r, _, _ in rows})
        facts = [evidence.get("GLOBAL", str(r)) for r in family]
        q = adjust_fdr([x["p_combined"] for x in facts], "BY")
        valid = {r for r, fact, value in zip(family, facts, q)
                 if classify({**fact, "q_BY": value}, QUALITY) == "accepted"}
        for r in family:
            if r not in complete:
                a, c = definitions[str(r)]
                antecedents[r] = val.mask(a)
                complete[r] = antecedents[r] & val.mask(c)
        results.extend(rows_for(system, pools, index, complete, antecedents, val, scopes, valid, gl_masks))
        if system in (G, L) or int(system[2]) % 20 == 0:
            print("Verified and evaluated", system, flush=True)
    assert counts_checked == 3320 and roster_checks == 9960
    args.out.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(results)
    assert len(frame) == 22200
    frame.to_csv(args.out / "all_systems.csv", index=False)
    gl = frame.loc[frame.control.eq("GL")]
    gl.to_csv(args.out / "global_local_curves.csv", index=False)
    summary(frame).to_csv(args.out / "random_comparisons.csv", index=False)
    pd.DataFrame(pool_rows, columns=["control","method","seed","config","unit","position","owner",
                                     "rule_id","rank_in_cluster","antecedent","consequent"]).to_csv(
        args.out / "global_local_A1_rule_paths.csv.gz", index=False)
    x, choices = select_budget(gl)
    x.to_csv(args.out / "selection_scores.csv", index=False)
    choices.to_csv(args.out / "selection_sensitivity.csv", index=False)
    intervals(val, gl_masks).to_csv(args.out / "paired_intervals.csv", index=False)
    checks = {"verified_candidate_counts": counts_checked, "verified_original_group_rule_lists": roster_checks,
              "orders": val.n, "customers": len(val.by_customer), "actual_budget_grid": BUDGETS,
              "systems": len(mappings), "evaluation_rows": len(frame), "group_random_seeds": {"S":20,"A1":100,"A2":100},
              "reliable_metric":"quality_v1_shared_BY_family_over_all_dense_budgets_and_both_identities",
              "test_accessed": False}
    (args.out / "verification.json").write_text(json.dumps(checks, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(checks), flush=True)


if __name__ == "__main__":
    main()
