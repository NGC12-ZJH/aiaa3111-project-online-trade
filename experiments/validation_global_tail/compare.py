"""Compare the next Global rules to residual local rules on fixed Validation misses."""
from functools import lru_cache
from itertools import combinations
from pathlib import Path
import argparse
import json
import sys

import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = args.repo.resolve()
    sys.path.extend([str(root / "src"), str(root / "experiments/validation_hybrid_residual")])
    from online_trade.evaluation.validation import load_inputs, load_period
    from run import import_local, popularity, replay, union

    common = import_local("common_refill", root / "experiments/discovery_residual_refill/run.py")
    masking = import_local("previous_masking", root / "experiments/validation_four_metrics/run.py")
    folder = root / "experiments/validation_hybrid_residual"
    local = root / "data/processed/local/D_validation"
    config_names = ["P1", "P2", "P3", "P4", "P5"]
    _, taxonomy, true, _, frozen, configs = load_inputs(local, root, {"configs": config_names})
    disc, _, _ = load_period(local, "discovery", taxonomy, true)
    val, _, _ = load_period(local, "validation", taxonomy, true)
    orders = pd.read_csv(local / "validation_baskets.csv", dtype=str, keep_default_na=False)
    orders = orders.loc[orders.is_eligible_for_main_comparison.eq("1")]
    assert orders.customer_id.tolist() == val.customers
    masked = masking.MaskedBaskets(val, orders.basket_id)
    pop = popularity(disc, masked, {"GLOBAL": disc.all}, {"GLOBAL": val.all})
    index = common.DirectionIndex(disc)
    ids = {identifier: i for i, identifier in enumerate(index.ids)}
    names = sorted(disc.items)
    components = [(i,) for i in range(len(names))]
    components.extend(combinations(range(len(names)), 2))
    components.extend(parts for parts in combinations(range(len(names)), 3)
                      if disc.mask(names[i] for i in parts).bit_count() >= 20)
    assert len(components) == len(index.masks)

    @lru_cache(maxsize=None)
    def rule_details(r):
        premise = tuple(names[i] for i in components[index.antecedent[r]])
        category, = (names[i] for i in components[index.consequent[r]])
        trigger = masked.trigger(premise) & ~masked.observed[category]
        joint = index.masks[index.joint[r]].bit_count()
        confidence = joint / index.masks[index.antecedent[r]].bit_count()
        base = index.masks[index.consequent[r]].bit_count() / disc.n
        return category, trigger, val.mask((*premise, category)), confidence, joint, confidence / base

    def replay_rules(rules, scope, subset):
        rec, full = [], []
        for r, g in rules:
            category, trig, complete = rule_details(r)[:3]
            rec.append((category, trig & scope[g] & subset))
            full.append(complete & scope[g])
        hits, slots = replay(rec, masked)
        return union(hits), union(full), slots[1]

    def global_conf_order(r):
        conf, joint, lift = rule_details(r)[3:]
        return -conf, -joint, -lift, index.ids[r]

    source_g = pd.read_csv(folder / "hybrid_global_local.csv").query("system == 'G' and true_stratum == 'all'")
    source_g = source_g.set_index(["config", "budget"])
    prev_l = pd.read_csv(folder / "residual_systems.csv").query("system == 'L'")
    prev_l = prev_l.set_index(["config", "budget", "sort", "flow"])
    selected = pd.read_csv(folder / "residual_rule_lists.csv.gz", dtype={"group": str, "rule_id": str})
    selected = selected.query("system == 'L'").sort_values(["discovery_score", "rule_id", "group"],
                                                           ascending=[False, True, True])
    scopes = {g: val.scope(true, g) for g in ("0", "1", "2")}
    rows = []
    comparisons = []
    for config, ranking, _ in index.ranks(disc.all, disc.n, configs):
        for budget in (20, 50, 100):
            g_top = ranking[:budget]
            g_tail = ranking[budget:2 * budget]
            assert len(g_tail) == budget and not set(g_top).intersection(g_tail)
            original = frozen.loc[frozen.method.eq("G") & frozen.config.eq(config) & frozen.budget.eq(budget)]
            assert index.ids[g_top].tolist() == original.sort_values("rank_within_group").rule_id.tolist()
            rec = [rule_details(r)[:2] for r in sorted(g_top, key=global_conf_order)]
            hits, _ = replay(rec + pop, masked)
            base_hit = union(hits)
            full = union(rule_details(r)[2] for r in g_top)
            subset = masked.all & ~base_hit
            full_subset = val.all & ~full
            assert base_hit.bit_count() == int(source_g.loc[(config, budget), "top5_hit_orders"])
            shared = {g: val.all for g in (*scopes, "GLOBAL")}
            for sort, roster in (("confidence_priority", sorted(g_tail, key=global_conf_order)),
                                 ("native_global_rank", g_tail)):
                top, cooc, available = replay_rules([(r, "GLOBAL") for r in roster], shared, subset)
                rows.append({
                    "config": config, "budget": budget, "method": "global_tail", "sort": sort, "flow": "shared",
                    "global_rank_start": budget + 1, "global_rank_end": 2 * budget, "unique_rules": len(roster),
                    "g_top5_misses": subset.bit_count(), "top5_rescued": top.bit_count(),
                    "misses_with_recommendations": available.bit_count(),
                    "g_complete_misses": full_subset.bit_count(), "complete_rescued": (cooc & full_subset).bit_count(),
                })
                if sort == "confidence_priority":
                    tail_top, tail_complete = top, cooc & full_subset

            for sort in ("added_value", "confidence_gap"):
                chosen = selected.loc[selected.config.eq(config) & selected.budget.eq(budget) & selected["sort"].eq(sort)]
                roster = [(ids[row.rule_id], row.group) for row in chosen.itertuples(index=False)]
                assert len(roster) == budget and not set(g_top).intersection(r for r, _ in roster)
                for flow, scope in (("restricted", scopes), ("shared", shared)):
                    top, cooc, available = replay_rules(roster, scope, subset)
                    cooc &= full_subset
                    old = prev_l.loc[(config, budget, sort, flow)]
                    assert subset.bit_count() == old.g_hybrid_top5_missed_orders
                    assert full_subset.bit_count() == old.g_complete_missed_orders
                    assert top.bit_count() == old.top5_rescued_orders
                    assert cooc.bit_count() == old.complete_rescued_orders
                    rows.append({
                        "config": config, "budget": budget, "method": "local_residual", "sort": sort, "flow": flow,
                        "unique_rules": len({r for r, _ in roster}), "g_top5_misses": subset.bit_count(),
                        "top5_rescued": top.bit_count(), "misses_with_recommendations": available.bit_count(),
                        "g_complete_misses": full_subset.bit_count(), "complete_rescued": cooc.bit_count(),
                    })
                    for metric, local_hit, tail_hit in (
                        ("top5", top, tail_top), ("complete", cooc, tail_complete)
                    ):
                        comparisons.append({
                            "config": config, "budget": budget, "local_sort": sort, "local_flow": flow, "metric": metric,
                            "global_tail_rescued": tail_hit.bit_count(), "local_rescued": local_hit.bit_count(),
                            "both": (local_hit & tail_hit).bit_count(),
                            "global_tail_only": (tail_hit & ~local_hit).bit_count(),
                            "local_only": (local_hit & ~tail_hit).bit_count(),
                            "local_minus_tail": local_hit.bit_count() - tail_hit.bit_count(),
                        })

    results, pairs = pd.DataFrame(rows), pd.DataFrame(comparisons)
    assert len(results) == 90 and len(pairs) == 120
    assert (pairs.both + pairs.global_tail_only).eq(pairs.global_tail_rescued).all()
    assert (pairs.both + pairs.local_only).eq(pairs.local_rescued).all()
    args.out.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.out / "global_tail_and_local.csv", index=False)
    pairs.to_csv(args.out / "paired_rescues.csv", index=False)
    (args.out / "verification.json").write_text(json.dumps({
        "global_baselines_reconciled": 15, "local_results_reconciled": 60,
        "system_results": len(results), "paired_comparisons": len(pairs),
    }, indent=2) + "\n", encoding="utf-8")
    print(results.query("config == 'P5' and budget == 100").to_string(index=False))
    print(pairs.query("config == 'P5' and budget == 100").to_string(index=False))


if __name__ == "__main__":
    main()
