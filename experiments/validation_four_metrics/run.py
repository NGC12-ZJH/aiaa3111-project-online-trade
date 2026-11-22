"""Evaluate four dimensions of frozen rule lists on Validation."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


KEYS = ["config", "budget", "control", "method", "seed"]
K = 5


def rate(count, total):
    return count / total if total else np.nan


def distribution(out, name, values, tails=(25, 75)):
    values = [v for v in values if np.isfinite(v)]
    out[f"{name}_n"] = len(values)
    out[f"{name}_median"] = float(np.median(values)) if values else np.nan
    for tail in tails:
        out[f"{name}_p{tail:02}"] = float(np.percentile(values, tail)) if values else np.nan


def low_bits_union(masks):
    result = 0
    for mask in masks:
        result |= mask
    return result


def weights_for(mask, weights):
    packed = mask.to_bytes((len(weights) + 7) // 8, "little")
    unpacked = np.unpackbits(np.frombuffer(packed, dtype=np.uint8), bitorder="little", count=len(weights))
    return weights[unpacked.astype(bool)].sum()


class MaskedBaskets:
    def __init__(self, orders, basket_ids):
        self.target = defaultdict(int)
        self.observed = defaultdict(int)
        self.examples = []
        for i, (basket, basket_id) in enumerate(zip(orders.baskets, basket_ids)):
            if len(basket) < 2:
                continue
            categories = sorted(basket)
            digest = hashlib.sha256(f"validation-basket-v1|{basket_id}".encode()).digest()
            target = categories[int.from_bytes(digest[:8], "big") % len(categories)]
            bit = 1 << i
            remaining = basket - {target}
            self.examples.append((bit, remaining, target))
            self.target[target] |= bit
            for item in remaining:
                self.observed[item] |= bit
        self.n = len(self.examples)
        self.all = low_bits_union(self.target.values())
        assert self.n == self.all.bit_count()
        self.premises = {}

    def trigger(self, premise):
        if premise not in self.premises:
            mask = self.all
            for item in premise:
                mask &= self.observed[item]
            self.premises[premise] = mask
        return self.premises[premise]

    def evaluate(self, proposals, verify=False):
        occupied = [self.all, 0, 0, 0, 0, 0]
        emitted = defaultdict(int)
        hit_at_rank = [0] * K
        for category, available in proposals:
            available &= ~emitted[category] & ~occupied[K]
            if not available:
                continue
            emitted[category] |= available
            hits = available & self.target[category]
            for rank in range(K, 0, -1):
                if hits:
                    hit_at_rank[rank - 1] += (hits & occupied[rank - 1] & ~occupied[rank]).bit_count()
                occupied[rank] |= available & occupied[rank - 1]
        issued = sum(mask.bit_count() for mask in occupied[1:])
        hits = sum(hit_at_rank)
        assert hits <= occupied[1].bit_count() <= self.n and issued <= self.n * K
        if verify:
            for bit, _, target in self.examples[::47]:
                chosen = []
                for category, available in proposals:
                    if available & bit and category not in chosen:
                        chosen.append(category)
                    if len(chosen) == K:
                        break
                observed = {c for c, mask in emitted.items() if mask & bit}
                assert set(chosen) == observed
                assert target not in observed or target in chosen
                assert sum(bool(mask & bit) for mask in occupied[1:]) == len(chosen)
            self.verify_exact_ranks(proposals, hit_at_rank)
        return {
            "masked_orders": self.n,
            "recommendable_orders": occupied[1].bit_count(),
            "recommendable_order_rate": occupied[1].bit_count() / self.n,
            "top5_recommendations": issued,
            "top5_hits": hits,
            "hit_at_1": hit_at_rank[0] / self.n,
            "hit_at_3": sum(hit_at_rank[:3]) / self.n,
            "hit_at_5": hits / self.n,
            "precision_at_5": hits / (K * self.n),
            "issued_precision_at_5": rate(hits, issued),
            "ndcg_at_5": sum(count / np.log2(rank + 2) for rank, count in enumerate(hit_at_rank)) / self.n,
            "distinct_top5_consequents": sum(bool(mask) for mask in emitted.values()),
        }

    def verify_exact_ranks(self, proposals, expected):
        hits = [0] * K
        for bit, _, target in self.examples:
            chosen = set()
            for category, available in proposals:
                if not available & bit or category in chosen:
                    continue
                chosen.add(category)
                if category == target:
                    hits[len(chosen) - 1] += 1
                    break
                if len(chosen) == K:
                    break
        assert hits == expected


def evidence(orders, premise, consequent, scope):
    antecedent = orders.mask(premise) & scope
    outcome = orders.items.get(consequent, 0) & scope
    a, c, j = antecedent.bit_count(), outcome.bit_count(), (antecedent & outcome).bit_count()
    base = rate(c, scope.bit_count())
    confidence = rate(j, a)
    return a, confidence, confidence - base, rate(confidence, base)


def scope_gaps(orders, rows, scopes):
    records = []
    for r in rows:
        scope = scopes[r.group_id]
        inside = evidence(orders, r.ant, r.con[0], scope)
        outside = evidence(orders, r.ant, r.con[0], orders.all ^ scope)
        conf_gap = inside[1] - outside[1]
        added_gap = inside[2] - outside[2]
        records.append((inside[0] >= 20 and outside[0] >= 20, conf_gap, added_gap))
    supported = [row for row in records if row[0]]
    result = {
        "group_evidence_comparable_slots": len(supported),
        "group_evidence_comparable_share": rate(len(supported), len(rows)),
        "group_both_positive_slots": sum(c > 0 and a > 0 for _, c, a in supported),
        "group_both_positive_share": rate(sum(c > 0 and a > 0 for _, c, a in supported), len(supported)),
    }
    distribution(result, "group_confidence_gap_pp", [100 * row[1] for row in supported])
    distribution(result, "group_added_value_gap_pp", [100 * row[2] for row in supported])
    return result


def evaluate_system(discovery, validation, masked, rows, flow, scopes, idf, amount, verify):
    added, lifts, changes, confs = [], [], [], []
    validation_antecedent_counts = []
    antecedents_by_consequent = defaultdict(int)
    proposals = []
    seen_shared = set()
    for r in rows:
        if flow == "shared":
            if r.rule_id in seen_shared:
                continue
            seen_shared.add(r.rule_id)
            disc_scope, val_scope = discovery.all, validation.all
        else:
            disc_scope, val_scope = scopes[0][r.group_id], scopes[1][r.group_id]
        category = r.con[0]
        antecedents_by_consequent[category] |= validation.mask(r.ant) & val_scope
        proposals.append((category, masked.trigger(r.ant) & ~masked.observed[category] & val_scope))
        a, confidence, association, lift = evidence(validation, r.ant, category, val_scope)
        d_confidence = evidence(discovery, r.ant, category, disc_scope)[1]
        validation_antecedent_counts.append(a)
        confs.append(confidence)
        added.append(100 * association)
        lifts.append(lift)
        changes.append(100 * (confidence - d_confidence))

    joint_by_consequent = {
        category: triggers & validation.items.get(category, 0)
        for category, triggers in antecedents_by_consequent.items()
    }
    triggered = low_bits_union(antecedents_by_consequent.values())
    covered = low_bits_union(joint_by_consequent.values())
    pair_count = sum(m.bit_count() for m in antecedents_by_consequent.values())
    joint_count = sum(m.bit_count() for m in joint_by_consequent.values())
    money = int(weights_for(covered, amount))
    idf_covered_weight = 0.0
    visited = 0
    for category, hits in sorted(joint_by_consequent.items(), key=lambda entry: -idf[entry[0]]):
        idf_covered_weight += (hits & ~visited).bit_count() * idf[category]
        visited |= hits
    assert visited == covered and joint_count <= pair_count and money <= amount.sum()
    result = {
        "covered_orders": covered.bit_count(),
        "coverage": covered.bit_count() / validation.n,
        "triggered_orders": triggered.bit_count(),
        "order_any_hit_on_trigger": rate(covered.bit_count(), triggered.bit_count()),
        "triggered_order_consequent_pairs": pair_count,
        "hit_order_consequent_pairs": joint_count,
        "trigger_precision_micro": rate(joint_count, pair_count),
        "distinct_consequents": len(antecedents_by_consequent),
        "distinct_triggered_consequents": sum(bool(mask) for mask in antecedents_by_consequent.values()),
        "gross_covered_minor_currency": money,
        "gross_total_minor_currency": int(amount.sum()),
        "monetary_weighted_coverage": money / amount.sum(),
        "idf_covered_weight": idf_covered_weight,
        "evaluated_rule_identities": len(confs),
        "validation_antecedent_20_share": rate(sum(a >= 20 for a in validation_antecedent_counts), len(confs)),
    }
    distribution(result, "validation_confidence", confs)
    distribution(result, "validation_added_value_pp", added)
    distribution(result, "validation_lift", lifts)
    distribution(result, "confidence_change_pp", changes)
    result.update(masked.evaluate(proposals, verify=verify))
    return result


def random_summary(systems):
    metrics = [
        "trigger_precision_micro", "order_any_hit_on_trigger", "hit_at_5", "ndcg_at_5",
        "recommendable_order_rate", "validation_added_value_pp_median", "validation_lift_median",
        "idf_weighted_coverage", "confidence_change_pp_median", "group_confidence_gap_pp_median",
        "group_added_value_gap_pp_median", "group_both_positive_share", "monetary_weighted_coverage",
        "distinct_consequents", "distinct_top5_consequents",
    ]
    comparisons = []
    for (config, budget, flow), frame in systems.groupby(["config", "budget", "flow"]):
        local = frame.loc[frame.method.eq("L")].iloc[0]
        random = frame.loc[frame.control.eq("A1")]
        assert len(random) == 100
        for metric in metrics:
            value, baseline = local[metric], random[metric].dropna()
            if not np.isfinite(value) or baseline.empty:
                continue
            comparisons.append({
                "config": config, "budget": budget, "flow": flow, "metric": metric,
                "L": value, "A1_n": len(baseline), "A1_min": baseline.min(),
                "A1_median": baseline.median(), "A1_max": baseline.max(),
                "A1_at_least_L": int(baseline.ge(value).sum()),
            })
    return pd.DataFrame(comparisons)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = args.repo.resolve()
    sys.path.insert(0, str(root / "src"))
    from online_trade.evaluation.validation import load_inputs, load_period

    local = root / "data/processed/local/D_validation"
    _, taxonomy, true, mappings, frozen, _ = load_inputs(
        local, root, {"configs": ("P1", "P2", "P3", "P4", "P5")}
    )
    discovery, _, _ = load_period(local, "discovery", taxonomy, true)
    validation, _, _ = load_period(local, "validation", taxonomy, true)
    frozen = frozen[frozen.control.isin(["GL", "A1"])].copy()
    frozen["confidence"] = frozen.joint_count / frozen.antecedent_count
    frozen["lift"] = frozen.confidence / (frozen.consequent_count.astype(int) / frozen.n_baskets.astype(int))
    frozen = frozen.sort_values(
        ["confidence", "joint_count", "lift", "rule_id", "group_id"],
        ascending=[False, False, False, True, True],
    )
    orders = pd.read_csv(local / "validation_baskets.csv", dtype=str, keep_default_na=False)
    orders = orders.loc[orders.is_eligible_for_main_comparison.eq("1")]
    assert orders.customer_id.tolist() == validation.customers
    from decimal import Decimal
    amount = np.array([int(Decimal(value) * 100) for value in orders.gross_purchase_amount], dtype=np.int64)
    assert np.all(amount > 0)
    masked = MaskedBaskets(validation, orders.basket_id)
    categories = set(discovery.items) | set(validation.items)
    frequencies = {c: discovery.items.get(c, 0).bit_count() for c in categories}
    idf = {c: -np.log((count + 1) / (discovery.n + 1)) for c, count in frequencies.items()}
    idf_total = sum(max((idf[c] for c in basket), default=0) for basket in validation.baskets)

    pop = [(c, masked.all & ~masked.observed[c])
           for c in sorted(frequencies, key=lambda c: (-frequencies[c], c)) if frequencies[c] > 0]
    popularity = masked.evaluate(pop, verify=True)
    base = pd.read_csv(root / "results/tables/validation/system_metrics.csv",
                       dtype={"seed": str}, keep_default_na=False)
    base = base.loc[base.period.eq("validation")].set_index(KEYS + ["flow"])
    records = []
    verify_count = 1
    for (control, method, seed), block in frozen.groupby(["control", "method", "seed"]):
        mapping = mappings[control, method, seed]
        groups = sorted(block.group_id.unique())
        scopes = [{g: index.scope(mapping, g) if mapping is not None else index.all for g in groups}
                  for index in (discovery, validation)]
        for config_budget, group in block.groupby(["config", "budget"]):
            config, budget = config_budget
            rows = list(group.itertuples(index=False))
            assert len(rows) == budget
            gaps = scope_gaps(validation, rows, scopes[1]) if method != "G" else {}
            for flow in ["restricted", "shared"]:
                verify = (config, budget) == ("P5", 100) and method in ("G", "L")
                result = evaluate_system(discovery, validation, masked, rows, flow, scopes, idf, amount, verify)
                verify_count += int(verify)
                key = (config, budget, control, method, seed, flow)
                previous = base.loc[key]
                assert result["covered_orders"] == previous.covered_orders, key
                assert result["triggered_orders"] == previous.triggered_orders, key
                assert result["idf_covered_weight"] <= idf_total + 1e-9, key
                records.append({
                    **dict(zip(KEYS + ["flow"], key)),
                    **result, "idf_weighted_coverage": result["idf_covered_weight"] / idf_total,
                    **(gaps if flow == "restricted" else {}),
                })
        if method != "R" or int(seed) % 20 == 0:
            print("Verified", control, method, seed, flush=True)

    args.out.mkdir(exist_ok=True, parents=True)
    systems = pd.DataFrame(records).sort_values(KEYS + ["flow"])
    assert len(systems) == 3060
    assert systems.masked_orders.eq(masked.n).all()
    systems.to_csv(args.out / "systems.csv", index=False)
    systems.loc[systems.method.isin(["G", "L"])].to_csv(args.out / "p1_p5_global_local.csv", index=False)
    random_summary(systems).to_csv(args.out / "a1_comparison.csv", index=False)
    pd.DataFrame([popularity]).to_csv(args.out / "popularity_baseline.csv", index=False)
    meta = {
        "validation_orders": validation.n, "validation_customers": len(validation.by_customer),
        "discovery_orders_for_scoring": discovery.n, "masked_eligible_orders": masked.n,
        "gross_total_minor_currency": int(amount.sum()), "idf_total_weight": idf_total,
        "rule_system_flows_reconciled_to_official_counts": len(systems),
        "systems_exhaustively_checked_by_scalar_topk": verify_count,
        "random_seeds": 100,
    }
    (args.out / "verification.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta), flush=True)


if __name__ == "__main__":
    main()
