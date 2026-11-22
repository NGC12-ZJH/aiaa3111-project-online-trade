"""Discovery-ranked recommendation and residual experiments on Validation."""
from collections import defaultdict
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from itertools import combinations
from pathlib import Path
import argparse
import json
import sys

import numpy as np
import pandas as pd


GROUPS = ("0", "1", "2")
BUDGETS = (20, 50, 100)
KEYS = ["config", "budget"]
K = 5


def import_local(name, path):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ratio(num, den):
    return num / den if den else np.nan


def union(masks):
    result = 0
    for mask in masks:
        result |= mask
    return result


def replay(proposals, masked):
    """Return exact-rank hit masks and how many recommendation positions are filled."""
    occupied = [masked.all] + [0] * K
    hits = [0] * K
    emitted = defaultdict(int)
    for category, eligible in proposals:
        eligible &= ~emitted[category] & ~occupied[K]
        if not eligible:
            continue
        emitted[category] |= eligible
        target = eligible & masked.target[category]
        for rank in range(K, 0, -1):
            hits[rank - 1] |= target & occupied[rank - 1] & ~occupied[rank]
            occupied[rank] |= eligible & occupied[rank - 1]
    return hits, occupied


def top_metrics(hits, occupied, subset):
    n = subset.bit_count()
    ranks = [(mask & subset).bit_count() for mask in hits]
    return {
        "top_orders": n, "top1_hit_orders": ranks[0], "top5_hit_orders": sum(ranks),
        "hit_at_1": ratio(ranks[0], n), "hit_at_5": ratio(sum(ranks), n),
        "ndcg_at_5": ratio(sum(count / np.log2(i + 2) for i, count in enumerate(ranks)), n),
        "five_recommendation_orders": (occupied[K] & subset).bit_count(),
        "recommendation_slots": sum((mask & subset).bit_count() for mask in occupied[1:]),
    }


def popularity(discovery, masked, discovery_scopes, validation_scopes):
    proposals = []
    for group, scope in discovery_scopes.items():
        counts = {category: (mask & scope).bit_count() for category, mask in discovery.items.items()}
        for category in sorted(counts, key=lambda c: (-counts[c], c)):
            if counts[category]:
                proposals.append((category, validation_scopes[group] & masked.all & ~masked.observed[category]))
    return proposals


def reorder(index, scope, config_ranks):
    """Reorder exactly the same qualifying Discovery candidate set."""
    counts = np.array([(mask & scope).bit_count() for mask in index.masks], dtype=np.int32)
    outside = np.array([mask.bit_count() for mask in index.masks], dtype=np.int32) - counts
    size = scope.bit_count()
    out = {}
    for config, ranked in config_ranks.items():
        eligible = np.array(ranked, dtype=np.int32)
        joint = counts[index.joint[eligible]]
        ant = counts[index.antecedent[eligible]]
        con = counts[index.consequent[eligible]]
        other_ant = outside[index.antecedent[eligible]]
        other_joint = outside[index.joint[eligible]]
        conf = joint / ant
        lift = conf / (con / size)
        added = conf - con / size
        other_conf = np.divide(other_joint, other_ant, out=np.zeros(len(eligible)), where=other_ant >= 20)
        gap = conf - other_conf
        leading = (index.id_keys[eligible], -lift, -conf, -joint)
        added_order = np.lexsort((*leading, -added))
        gap_order = np.lexsort((*leading, -gap))
        out[config] = {
            "added_value": [(int(eligible[i]), float(added[i])) for i in added_order],
            "confidence_gap": [(int(eligible[i]), float(gap[i])) for i in gap_order if other_ant[i] >= 20],
        }
    return out


def compare_summary(rows, random_label, system_label, keys, metrics):
    frame = pd.DataFrame(rows)
    output = []
    for values, group in frame.groupby(keys, sort=True):
        real = group.loc[group.system.eq(system_label)]
        random = group.loc[group.system.eq(random_label)]
        if real.empty or random.empty:
            continue
        assert len(real) == 1 and len(random) == 100, values
        for metric in metrics:
            value = real.iloc[0][metric]
            numbers = random[metric].dropna()
            output.append({
                **dict(zip(keys, values)), "metric": metric, "L": value, "A1_n": len(numbers),
                "A1_min": numbers.min(), "A1_median": numbers.median(), "A1_max": numbers.max(),
                "A1_at_least_L": int(numbers.ge(value).sum()),
            })
    return pd.DataFrame(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = args.repo.resolve()
    sys.path.insert(0, str(root / "src"))
    from online_trade.evaluation.validation import load_inputs, load_period

    common = import_local("residual_replay", root / "experiments/discovery_residual_refill/run.py")
    top = import_local("validation_four_metrics", root / "experiments/validation_four_metrics/run.py")
    local = root / "data/processed/local/D_validation"
    cfg = ("P1", "P2", "P3", "P4", "P5")
    core, taxonomy, true, mappings, frozen, configs = load_inputs(local, root, {"configs": cfg})
    discovery, _, _ = load_period(local, "discovery", taxonomy, true)
    validation, _, _ = load_period(local, "validation", taxonomy, true)

    val_rows = pd.read_csv(local / "validation_baskets.csv", dtype=str, keep_default_na=False)
    eligible = val_rows.loc[val_rows.is_eligible_for_main_comparison.eq("1")]
    assert eligible.customer_id.tolist() == validation.customers
    masked = top.MaskedBaskets(validation, eligible.basket_id)
    strata = {"all": masked.all, **{g: validation.scope(true, g) & masked.all for g in GROUPS}}
    assert sum(strata[g].bit_count() for g in GROUPS) == masked.n
    index = common.DirectionIndex(discovery)
    direction_by_id = {identifier: i for i, identifier in enumerate(index.ids)}
    names = sorted(discovery.items)
    components = [(i,) for i in range(len(names))]
    components.extend(combinations(range(len(names)), 2))
    components.extend(
        parts for parts in combinations(range(len(names)), 3)
        if discovery.mask(names[i] for i in parts).bit_count() >= 20
    )
    assert len(components) == len(index.masks)
    premises = [tuple(names[i] for i in component) for component in components]

    @lru_cache(maxsize=None)
    def bits(rule):
        premise = premises[index.antecedent[rule]]
        consequent, = premises[index.consequent[rule]]
        trigger = masked.trigger(premise) & ~masked.observed[consequent]
        complete = validation.mask((*premise, consequent))
        return premise, consequent, trigger, complete

    scope_keys = ["control", "method", "seed", "group_id", "config"]
    scope_counts = pd.read_csv(core / "scope_summary.csv", dtype={"seed": str, "group_id": str},
                               keep_default_na=False).query("length == 0").set_index(scope_keys)
    original_metrics = pd.read_csv(root / "results/tables/validation/system_metrics.csv",
                                   dtype={"seed": str}, keep_default_na=False)
    original_metrics = original_metrics.query("period == 'validation' and flow == 'restricted'").set_index(
        ["control", "method", "seed", *KEYS]
    )
    original_top = pd.read_csv(root / "experiments/validation_four_metrics/systems.csv",
                               dtype={"seed": str}, keep_default_na=False)
    original_top = original_top.query("flow == 'restricted'").set_index(["control", "method", "seed", *KEYS])
    frozen = frozen[frozen.control.isin(["GL", "A1"])].copy()
    frozen["disc_conf"] = frozen.joint_count / frozen.antecedent_count
    frozen["disc_lift"] = frozen.disc_conf / (frozen.consequent_count.astype(int) / frozen.n_baskets.astype(int))
    frozen = frozen.sort_values(
        ["disc_conf", "joint_count", "disc_lift", "rule_id", "group_id"],
        ascending=[False, False, False, True, True],
    )
    frozen_blocks = dict(tuple(frozen.groupby(["control", "method", "seed", *KEYS])))
    global_pop = popularity(discovery, masked, {"GLOBAL": discovery.all}, {"GLOBAL": validation.all})
    hybrid, residual, selections, globals_by_config = [], [], [], {}
    checks = dict(candidate_scope_configs=0, candidate_original_order=0, original_top_reconciled=0,
                  original_complete_reconciled=0, hybrid_full_top5=0, residual_filled=0)

    ordered_systems = [("GL", "G", ""), ("GL", "L", "")]
    ordered_systems += [("A1", "R", str(seed)) for seed in range(1000, 1100)]
    for control, method, seed in ordered_systems:
        mapping = mappings[control, method, seed]
        groups = ("GLOBAL",) if method == "G" else GROUPS
        disc_scopes = {g: discovery.all if mapping is None else discovery.scope(mapping, g) for g in groups}
        val_scopes = {g: validation.all if mapping is None else validation.scope(mapping, g) for g in groups}
        sizes = {g: mask.bit_count() for g, mask in disc_scopes.items()}
        pop = global_pop if method == "G" else popularity(discovery, masked, disc_scopes, val_scopes)
        pop_hits, pop_slots = replay(pop, masked)
        assert pop_slots[K] == masked.all
        alternatives = {}
        native_by_group = {}
        for g, scope in disc_scopes.items():
            native = {}
            for config, ranked, counts in index.ranks(scope, sizes[g], configs):
                native[config] = ranked
                assert int(scope_counts.loc[(control, method, seed, g, config), "rules"]) == counts[0]
                checks["candidate_scope_configs"] += 1
            native_by_group[g] = native
            if method != "G":
                alternatives[g] = reorder(index, scope, native)

        for config in cfg:
            for budget in BUDGETS:
                rule_key = (control, method, seed, config, budget)
                roster = frozen_blocks[rule_key]
                proposals, full_masks = [], []
                for g, group in roster.groupby("group_id"):
                    ranked = group.sort_values("rank_within_group")
                    reconstructed = native_by_group[g][config][:len(ranked)]
                    assert index.ids[reconstructed].tolist() == ranked.rule_id.tolist(), (*rule_key, g)
                    checks["candidate_original_order"] += 1
                for r in roster.itertuples():
                    rule = direction_by_id[r.rule_id]
                    premise, category, trigger, complete = bits(rule)
                    assert premise == r.ant and (category,) == r.con, r.rule_id
                    scope = val_scopes[r.group_id]
                    proposals.append((category, trigger & scope))
                    full_masks.append(complete & scope)
                full = union(full_masks)
                assert full.bit_count() == original_metrics.loc[rule_key, "covered_orders"]
                checks["original_complete_reconciled"] += 1

                original_hits, original_slots = replay(proposals, masked)
                original_hit_mask = union(original_hits)
                assert original_hit_mask.bit_count() == int(original_top.loc[rule_key, "top5_hits"])
                checks["original_top_reconciled"] += 1
                hybrid_hits, hybrid_slots = replay(proposals + pop, masked)
                hybrid_hit_mask = union(hybrid_hits)
                assert hybrid_slots[K] == masked.all
                assert original_hit_mask & hybrid_hit_mask == original_hit_mask
                checks["hybrid_full_top5"] += 1

                if method == "G":
                    globals_by_config[config, budget] = (
                        set(roster.rule_id), validation.all & ~full, masked.all & ~hybrid_hit_mask, hybrid_hit_mask,
                    )
                global_ids, cooc_missed, top_missed, global_top = globals_by_config[config, budget]
                for stratum, subset in strata.items():
                    final = top_metrics(hybrid_hits, hybrid_slots, subset)
                    original = top_metrics(original_hits, original_slots, subset)
                    pop_only = top_metrics(pop_hits, pop_slots, subset)
                    hybrid.append({
                        "config": config, "budget": budget, "system": "A1" if method == "R" else method,
                        "seed": seed, "true_stratum": stratum, **final,
                        "rules_only_hit_at_5": original["hit_at_5"], "pop_only_hit_at_5": pop_only["hit_at_5"],
                        "rule_plus_pop_minus_pop_pp": 100 * (final["hit_at_5"] - pop_only["hit_at_5"]),
                        "rule_plus_pop_minus_rules_pp": 100 * (final["hit_at_5"] - original["hit_at_5"]),
                        "wins_vs_g_orders": (hybrid_hit_mask & ~global_top & subset).bit_count(),
                        "losses_vs_g_orders": (global_top & ~hybrid_hit_mask & subset).bit_count(),
                    })
                if method == "G":
                    continue

                quota = common.allocate(budget, sizes)
                for score_kind in ("added_value", "confidence_gap"):
                    pool = []
                    for g in GROUPS:
                        ranked = [(rule, score) for rule, score in alternatives[g][config][score_kind]
                                  if index.ids[rule] not in global_ids][:quota[g]]
                        for pos, (rule, score) in enumerate(ranked, start=1):
                            selections.append({
                                "config": config, "budget": budget, "system": "A1" if method == "R" else method,
                                "seed": seed, "sort": score_kind, "group": g, "rank_after_exclusion": pos,
                                "rule_id": index.ids[rule], "discovery_score": score,
                            })
                            pool.append((rule, g, score))
                    if len(pool) == budget:
                        checks["residual_filled"] += 1
                    assert not global_ids.intersection(index.ids[rule] for rule, _, _ in pool)
                    pool.sort(key=lambda row: (-row[2], index.ids[row[0]], row[1]))
                    for flow in ("restricted", "shared"):
                        rec, joint = [], []
                        for rule, g, _ in pool:
                            _, cat, trig, complete = bits(rule)
                            scope = val_scopes[g] if flow == "restricted" else validation.all
                            rec.append((cat, trig & scope & top_missed))
                            joint.append(complete & scope)
                        recovered_complete = (union(joint) & cooc_missed).bit_count()
                        residual_hits, residual_slots = replay(rec, masked)
                        recovered_top = union(residual_hits).bit_count()
                        residual.append({
                            "config": config, "budget": budget, "system": "A1" if method == "R" else method,
                            "seed": seed, "sort": score_kind, "flow": flow,
                            "selected_slots": len(pool), "selected_unique_rules": len({r for r, _, _ in pool}),
                            "g_complete_missed_orders": cooc_missed.bit_count(),
                            "complete_rescued_orders": recovered_complete,
                            "complete_rescue_rate": ratio(recovered_complete, cooc_missed.bit_count()),
                            "g_hybrid_top5_missed_orders": top_missed.bit_count(),
                            "top5_rescued_orders": recovered_top,
                            "top5_rescue_rate": ratio(recovered_top, top_missed.bit_count()),
                            "top5_residual_recommendable_orders": residual_slots[1].bit_count(),
                        })
        if method != "R" or int(seed) % 10 == 0:
            print("Verified", control, method, seed, flush=True)

    assert len(hybrid) == 6120 and len(residual) == 6060
    args.out.mkdir(parents=True, exist_ok=True)
    h, r = pd.DataFrame(hybrid), pd.DataFrame(residual)
    h.to_csv(args.out / "hybrid_systems.csv", index=False)
    h.loc[h.system.isin(["G", "L"])].to_csv(args.out / "hybrid_global_local.csv", index=False)
    r.to_csv(args.out / "residual_systems.csv", index=False)
    pd.DataFrame(selections).to_csv(args.out / "residual_rule_lists.csv.gz", index=False)
    compare_summary(hybrid, "A1", "L", [*KEYS, "true_stratum"],
                    ["hit_at_5", "ndcg_at_5", "rule_plus_pop_minus_pop_pp"]).to_csv(
        args.out / "hybrid_a1_comparison.csv", index=False)
    compare_summary(residual, "A1", "L", [*KEYS, "sort", "flow"],
                    ["complete_rescued_orders", "top5_rescued_orders"]).to_csv(
        args.out / "residual_a1_comparison.csv", index=False)
    checks["validation_orders"] = validation.n
    checks["masked_orders"] = masked.n
    checks["hybrid_total_rows"] = len(h)
    checks["residual_total_rows"] = len(r)
    checks["residual_unfilled_rows"] = int(r.selected_slots.lt(r.budget).sum())
    (args.out / "verification.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(checks), flush=True)


if __name__ == "__main__":
    main()
