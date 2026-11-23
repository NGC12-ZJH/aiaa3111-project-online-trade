"""Discovery-only shared residual coverage with equal directed-rule budgets."""
from fractions import Fraction
from hashlib import sha256
from itertools import combinations
from pathlib import Path
import argparse
import json
import math
import sys

import numpy as np
import pandas as pd


BUDGETS = (20, 50, 100)
GROUPS = ("0", "1", "2")
GLOBAL = ("GL", "G", "")


class DirectionIndex:
    def __init__(self, orders):
        names = sorted(orders.items)
        masks = {(i,): orders.items[name] for i, name in enumerate(names)}
        for pair in combinations(range(len(names)), 2):
            a, b = pair
            masks[pair] = masks[a,] & masks[b,]
        for a, b, c in combinations(range(len(names)), 3):
            hit = masks[a, b] & masks[c,]
            if hit.bit_count() >= 20:
                masks[a, b, c] = hit
        positions = {items: i for i, items in enumerate(masks)}
        self.masks = list(masks.values())
        ids, directions = [], []
        for items, mask in masks.items():
            if len(items) < 2 or mask.bit_count() < 20:
                continue
            for c in items:
                lhs = tuple(i for i in items if i != c)
                one = tuple(sorted((lhs[0], c)))
                two = tuple(sorted((lhs[-1], c)))
                payload = ["l2", [names[i] for i in lhs], [names[c]]]
                ids.append(sha256(json.dumps(payload).encode()).hexdigest()[:16])
                directions.append((
                    positions[items], positions[lhs], positions[c,],
                    positions[one], positions[two], positions[lhs[0],],
                    positions[lhs[-1],], len(items),
                ))
        assert len(set(ids)) == len(ids)
        self.ids = np.array(ids)
        self.id_keys = np.array([int(i, 16) for i in ids], dtype=np.uint64)
        self.joint, self.antecedent, self.consequent, self.first_pair, self.second_pair, \
            self.first_item, self.second_item, self.length = np.array(directions).T

    def cover(self, rules):
        result = 0
        for rule in rules:
            result |= self.masks[self.joint[rule]]
        return result

    def ranks(self, scope, n, configs):
        counts = np.array([(mask & scope).bit_count() for mask in self.masks], dtype=np.int32)
        generation_support = max(.01, 20 / n)
        all_joint = counts[self.joint]
        indices = np.flatnonzero(
            (all_joint >= math.ceil(generation_support * n)) & (all_joint / n >= generation_support)
        )
        joint = all_joint[indices]
        ant = counts[self.antecedent[indices]]
        con = counts[self.consequent[indices]]
        support = joint / n
        confidence = joint / ant
        lift = confidence / (con / n)
        lengths = self.length[indices]
        first = counts[self.first_pair[indices]] / counts[self.first_item[indices]]
        second = counts[self.second_pair[indices]] / counts[self.second_item[indices]]
        increment = (confidence - np.maximum(first, second)) * 100
        order = np.lexsort((self.id_keys[indices], -lift, -confidence, -joint))
        for config, threshold in configs.items():
            eligible = (
                (support >= threshold["support"])
                & (confidence >= threshold["confidence"])
                & (lift >= threshold["lift"])
                & (joint >= threshold["min_joint_count"])
                & (ant >= threshold["min_antecedent_count"])
            )
            min_increment = threshold["triple_increment_pp"]
            if pd.notna(min_increment):
                eligible &= (lengths == 2) | (increment >= min_increment - 1e-10)
            chosen = order[eligible[order]]
            yield config, indices[chosen].tolist(), (
                len(chosen), int((lengths[chosen] == 2).sum()), int((lengths[chosen] == 3).sum())
            )


def allocate(budget, sizes):
    parts = {group: divmod(budget * n, sum(sizes.values())) for group, n in sizes.items()}
    quota = {group: whole for group, (whole, _) in parts.items()}
    priority = sorted(sizes, key=lambda group: (-parts[group][1], group))
    for group in priority[:budget - sum(quota.values())]:
        quota[group] += 1
    return quota


def pool_for_budget(rankings, sizes, quota, budget):
    owner = {}
    contributed = dict.fromkeys(GROUPS, 0)
    for group in GROUPS:
        for rule in rankings[group][:quota[group]]:
            if rule not in owner:
                owner[rule] = group
                contributed[group] += 1
    initial = tuple(owner)
    assert all(len(rankings[group]) >= quota[group] for group in GROUPS)
    tails = {group: iter(rankings[group][quota[group]:]) for group in GROUPS}
    next_rules = dict.fromkeys(GROUPS)
    while len(owner) < budget:
        for group, tail in tails.items():
            if next_rules[group] is None or next_rules[group] in owner:
                next_rules[group] = next((rule for rule in tail if rule not in owner), None)
        group = min(
            (group for group in GROUPS if next_rules[group] is not None),
            key=lambda group: (Fraction(contributed[group], sizes[group]), group),
        )
        owner[next_rules[group]] = group
        contributed[group] += 1
    return initial, owner


def compare(orders, index, global_rules, initial, final):
    global_hit = index.cover(global_rules)
    residual = orders.all ^ global_hit
    initial_hit, final_hit = index.cover(initial), index.cover(final)
    assert initial_hit & final_hit == initial_hit
    global_orders = global_hit.bit_count()
    residual_orders = residual.bit_count()
    before, after = (initial_hit & residual).bit_count(), (final_hit & residual).bit_count()
    return {
        "discovery_orders": orders.n,
        "global_orders": global_orders,
        "global_coverage": global_orders / orders.n,
        "global_residual_orders": residual_orders,
        "initial_unique_rules": len(initial),
        "final_unique_rules": len(final),
        "refill_rules": len(final) - len(initial),
        "final_unique_itemsets": len({index.joint[rule] for rule in final}),
        "initial_shared_orders": initial_hit.bit_count(),
        "final_shared_orders": final_hit.bit_count(),
        "final_shared_coverage": final_hit.bit_count() / orders.n,
        "initial_rescued_orders": before,
        "initial_rescue_rate": before / residual_orders,
        "rescued_orders": after,
        "rescue_rate": after / residual_orders,
        "refill_increment_rescued_orders": after - before,
        "lost_global_orders_if_replacing": (global_hit & ~final_hit).bit_count(),
        "global_plus_pool_unique_rules": len(set(global_rules).union(final)),
        "global_plus_pool_orders": global_orders + after,
        "global_plus_pool_coverage": (global_orders + after) / orders.n,
    }


def summaries(results):
    rows = []
    for (config, budget), frame in results.groupby(["config", "budget"]):
        real = frame.query("method == 'L'").iloc[0]
        for control in ("A1", "S", "A2"):
            values = frame.loc[frame.control.eq(control), "rescued_orders"]
            upper = int(values.ge(real.rescued_orders).sum())
            residual = real.global_residual_orders
            rows.append({
                **real.to_dict(),
                "random_control": control,
                "random_seeds": len(values),
                "random_rescued_min": int(values.min()),
                "random_rescued_median": values.median(),
                "random_rescued_max": int(values.max()),
                "random_rescue_rate_median": values.median() / residual,
                "real_minus_random_median_orders": real.rescued_orders - values.median(),
                "random_at_least_real": upper,
                "descriptive_upper_tail": (upper + 1) / (len(values) + 1),
            })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = args.repo.resolve()
    sys.path.insert(0, str(root / "src"))
    from online_trade.evaluation.validation import load_inputs, load_period

    local = root / "data/processed/local/D_validation"
    core, taxonomy, true, mappings, originals, configs = load_inputs(
        local, root, {"configs": ("P1", "P2", "P3", "P4", "P5")}
    )
    orders, _, _ = load_period(local, "discovery", taxonomy, true)
    index = DirectionIndex(orders)
    keys = ["control", "method", "seed", "group_id", "config"]
    source = pd.read_csv(core / "scope_summary.csv", dtype={"seed": str, "group_id": str}, keep_default_na=False)
    expected_counts = source.pivot(index=keys, columns="length", values="rules")
    expected_sizes = source.query("length == 0").set_index(keys)["n_baskets"]
    original_groups = dict(tuple(originals.groupby(keys + ["budget"], sort=False)))
    prior = pd.read_csv(
        root / "results/tables/validation_specificity/complementarity_systems.csv",
        dtype={"seed": str}, keep_default_na=False,
    ).query("period == 'discovery' and flow == 'shared'")
    prior = prior.set_index(["control", "method", "seed", "config", "budget"])

    result_rows, refill_rows, globals_by_config = [], [], {}
    checks = dict(scope_config_counts=0, original_group_selections=0, original_shared_systems=0,
                  full_budget_systems=0)
    for system, mapping in mappings.items():
        rankings = {config: {} for config in configs}
        sizes = {}
        for group in ("GLOBAL",) if system == GLOBAL else GROUPS:
            scope = orders.all if system == GLOBAL else orders.scope(mapping, group)
            sizes[group] = n = scope.bit_count()
            for config, ranked, counts in index.ranks(scope, n, configs):
                key = (*system, group, config)
                expected = tuple(expected_counts.loc[key, [0, 2, 3]].astype(int))
                assert counts == expected, (key, counts, expected)
                assert n == expected_sizes.loc[key], key
                checks["scope_config_counts"] += 1
                rankings[config][group] = ranked
        assert sum(sizes.values()) == orders.n, system

        for config, ranked in rankings.items():
            if system == GLOBAL:
                globals_by_config[config] = ranked["GLOBAL"]
            for budget in BUDGETS:
                quota = allocate(budget, sizes)
                for group, group_quota in quota.items():
                    key = (*system, group, config, budget)
                    source_selection = original_groups[key].sort_values("rank_within_group")
                    frozen = source_selection.rule_id.tolist()
                    reconstructed = index.ids[ranked[group][:group_quota]].tolist()
                    assert frozen == reconstructed, (
                        key, next(((i, a, b) for i, (a, b) in enumerate(zip(frozen, reconstructed)) if a != b),
                                  (len(frozen), len(reconstructed))),
                    )
                    assert source_selection.allocated_budget.eq(group_quota).all(), key
                    checks["original_group_selections"] += 1

                global_rules = globals_by_config[config][:budget]
                labels = dict(zip(["control", "method", "seed", "config", "budget"], (*system, config, budget)))
                if system == GLOBAL:
                    initial, final = global_rules, global_rules
                else:
                    initial, final = pool_for_budget(ranked, sizes, quota, budget)
                    for position, (rule, group) in enumerate(final.items(), start=1):
                        refill_rows.append({
                            **labels, "pool_position": position, "rule_id": index.ids[rule],
                            "contributing_group": group, "refill": position > len(initial),
                            "rank_in_group": ranked[group].index(rule) + 1,
                        })
                assert len(final) == len(set(final)) == budget, labels
                metrics = compare(orders, index, global_rules, initial, final)
                if system != GLOBAL:
                    old = prior.loc[(*system, config, budget)]
                    assert metrics["global_orders"] == old.global_covered_orders, labels
                    assert metrics["initial_shared_orders"] == old.local_covered_orders, labels
                    assert metrics["initial_rescued_orders"] == old.local_only_complete_orders, labels
                    checks["original_shared_systems"] += 1
                checks["full_budget_systems"] += 1
                result_rows.append({**labels, **metrics})
        if system[1] != "R" or int(system[2]) % 20 == 0:
            print("Verified and evaluated", system, flush=True)

    assert checks["scope_config_counts"] == len(expected_counts)
    assert checks["original_group_selections"] == len(original_groups)
    assert checks["original_shared_systems"] == len(prior)
    assert checks["full_budget_systems"] == 3330
    args.out.mkdir(parents=True, exist_ok=True)
    results = pd.DataFrame(result_rows)
    results.to_csv(args.out / "systems.csv", index=False)
    summaries(results).to_csv(args.out / "comparison.csv", index=False)
    pd.DataFrame(refill_rows).to_csv(args.out / "local_random_rule_pools.csv.gz", index=False)
    (args.out / "verification.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(checks), flush=True)


if __name__ == "__main__":
    main()
