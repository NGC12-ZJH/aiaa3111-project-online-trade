"""Reproduce the stricter Validation quality and budget-selection checks."""
import argparse
from pathlib import Path
import sys

import pandas as pd

KEYS = ["control", "method", "seed"]
BASE = dict(min_antecedent_orders=20, min_joint_orders=10, min_antecedent_customers=10,
            min_joint_customers=5, max_customer_joint_share=.5, min_confidence_uplift=.05,
            min_lift=1.2, min_triple_increment_pp=5, adjustment="BY", alpha=.05)
STRICT = {**BASE, "min_confidence_uplift": .10}
SENSITIVITY = {
    "quality_v1": {},
    "lift_1.5": {"min_lift": 1.5},
    "added_value_10pp": {"min_confidence_uplift": .10},
    "triple_gain_10pp": {"min_triple_increment_pp": 10},
    "evidence_30_15_15_8": {"min_antecedent_orders": 30, "min_joint_orders": 15,
                           "min_antecedent_customers": 15, "min_joint_customers": 8},
    "lift_1.5_and_added_value_10pp": {"min_lift": 1.5, "min_confidence_uplift": .10},
}


def run(repo, output):
    sys.path.insert(0, str(repo / "src"))
    from online_trade.evaluation.validation import load_inputs, load_period
    from online_trade.evaluation.quality import QualityEvidence, adjust_fdr, classify

    local = repo / "data/processed/local/D_validation"
    _, taxonomy, customers, *_ = load_inputs(local, repo, {"configs": ("P1", "P2", "P3", "P4", "P5")})
    disc, _, _ = load_period(local, "discovery", taxonomy, customers)
    val, _, _ = load_period(local, "validation", taxonomy, customers)
    source = repo / "experiments/validation_budget_redesign/results"
    lists = pd.read_csv(source / "global_local_A1_rule_paths.csv.gz", dtype=str, keep_default_na=False)
    lists["position"] = lists.position.astype(int)
    definitions = {r.rule_id: (tuple(r.antecedent.split(" + ")), (r.consequent,)) for r in lists.itertuples()}
    evidence = QualityEvidence(val, disc, {}, definitions)
    masks = {rid: val.mask(a + b) for rid, (a, b) in definitions.items()}
    known = pd.read_csv(source / "global_local_curves.csv").set_index(["config", "unit", "budget", "method"])
    rows, sensitivity = [], []
    for key, rows_for_system in lists.groupby(KEYS, sort=False):
        control, method, seed = key
        unique = sorted(set(rows_for_system.rule_id))
        facts = [evidence.get("GLOBAL", rid) for rid in unique]
        adjusted = adjust_fdr([f["p_combined"] for f in facts], "BY")
        evaluated = {rid: {**f, "q_BY": float(q)} for rid, f, q in zip(unique, facts, adjusted)}
        strict = {rid for rid, f in evaluated.items() if classify(f, STRICT) == "accepted"}
        base = {rid for rid, f in evaluated.items() if classify(f, BASE) == "accepted"} if control == "GL" else set()
        for config, full in rows_for_system.loc[rows_for_system.unit.eq("combination")].groupby("config"):
            roster = full.sort_values("position")
            hit = base_hit = accepted = base_accepted = 0
            for r in roster.itertuples():
                if r.rule_id in strict:
                    accepted += 1
                    hit |= masks[r.rule_id]
                if r.rule_id in base:
                    base_accepted += 1
                    base_hit |= masks[r.rule_id]
                if r.position % 10 == 0:
                    count = hit.bit_count()
                    rows.append(dict(zip(KEYS, key)) | {"config": config, "budget": r.position, "orders": val.n,
                                "accepted": accepted, "accepted_share": accepted / r.position,
                                "hits": count, "reliable_coverage": count / val.n})
                    if control == "GL":
                        frozen = known.loc[(config, "combination", r.position, method)]
                        assert (base_accepted, base_hit.bit_count()) == (frozen.accepted_slots, frozen.reliable_covered)
            if control == "GL" and config in ("P1", "P5"):
                ninety = roster.loc[roster.position.le(90)]
                for setting, threshold in SENSITIVITY.items():
                    ids = [rid for rid in ninety.rule_id if classify(evaluated[rid], BASE | threshold) == "accepted"]
                    matched = 0
                    for rid in ids:
                        matched |= masks[rid]
                    assert len(ninety) == 90
                    sensitivity.append({"config": config, "method": method, "budget": 90, "setting": setting,
                                        "accepted": len(ids), "accepted_share": len(ids)/90,
                                        "hits": matched.bit_count(), "reliable_coverage": matched.bit_count()/val.n})
    systems = pd.DataFrame(rows)
    assert len(systems) == 5100
    gl = systems.loc[systems.control.eq("GL")].pivot(index=["config", "budget"], columns="method",
                                                       values="reliable_coverage").reset_index()
    gl["G_shortfall_pp"] = 100 * (gl.G.max() - gl.G)
    gl["L_shortfall_pp"] = 100 * (gl.L.max() - gl.L)
    gl["worst_shortfall_pp"] = gl[["G_shortfall_pp", "L_shortfall_pp"]].max(axis=1)
    comparisons = []
    for (config, b), frame in systems.groupby(["config", "budget"]):
        real = frame.loc[frame.method.eq("L"), "reliable_coverage"].iloc[0]
        a1 = frame.loc[frame.control.eq("A1"), "reliable_coverage"]
        assert len(a1) == 100
        comparisons.append({"config": config, "budget": b, "A1_min": a1.min(),
                            "A1_median": a1.median(), "A1_max": a1.max(),
                            "A1_ge_L": int(a1.ge(real).sum())})
    decisions = []
    for tolerance in (.5, 1., 1.5, 2.):
        subset = gl.loc[gl.worst_shortfall_pp.le(tolerance + 1e-10)]
        choice = subset.sort_values(["budget", "worst_shortfall_pp", "config"]).iloc[0]
        decisions.append({"tolerance_pp": tolerance, **choice.to_dict()})
    choice = pd.DataFrame(decisions)
    assert choice.query("tolerance_pp == 1")[["config", "budget"]].values.tolist() == [["P5", 90]]
    output.mkdir(parents=True, exist_ok=True)
    systems.to_csv(output / "strict_validation_systems.csv", index=False)
    gl.merge(pd.DataFrame(comparisons), on=["config", "budget"], validate="one_to_one").to_csv(
        output / "strict_validation_grid.csv", index=False)
    choice.to_csv(output / "strict_validation_selection.csv", index=False)
    pd.DataFrame(sensitivity).to_csv(output / "quality_gate_sensitivity_P1_P5_90.csv", index=False)
    print(choice.to_string(index=False), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "results")
    args = p.parse_args()
    run(args.repo.resolve(), args.out)
