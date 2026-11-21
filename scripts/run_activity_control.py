#!/usr/bin/env python3
"""Activity-matched random control vs C's category-level (taxonomy_v1) results, Discovery only.

Builds the activity-matched random groups (configs/experiment.json -> activity_matched_control),
then evaluates the real RFM groups, the existing head-count-only random groups (S, 20 seeds) and the
two activity-matched controls (A1, A2; 100 seeds each) with C's category-level metrics.

Usage (from the repository root; needs data/processed/local/customer_clusters.csv and random_groups.csv):
    python scripts/run_activity_control.py
    python scripts/run_activity_control.py --repeats 10   # quick trial
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from online_trade.clustering.activity_control import build_controls  # noqa: E402
from online_trade.taxonomy import category_controls as cc  # noqa: E402

# C's published numbers on c/pattern-mining-taxonomy (commit 0673ce3); used only as a reproduction check.
C_REFERENCE = {"G_strict_rules": 1116, "L_strict_rules": {"0": 2371, "1": 856, "2": 1500},
               "G_coverage": {20: .5505917, 50: .6324957, 100: .6612153},
               "L_coverage": {20: .3878474, 50: .5212073, 100: .5931392},
               "S_coverage_median": {20: .3756, 50: .5117, 100: .5915},
               "L_local_not_global_share": .6835479}
METRICS = ["rest_bc_len2", "rest_bc_len3", "pair_bc_len2", "pair_bc_len3", "local_not_global_share",
           "coverage_B20", "coverage_B50", "coverage_B100"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/experiment.json")
    parser.add_argument("--repeats", type=int, default=None, help="override activity-control repeats (trials)")
    parser.add_argument("--out", type=Path, default=ROOT / "results/tables/activity_control")
    args = parser.parse_args()
    start = time.perf_counter()

    cfg = json.loads(args.config.read_text(encoding="utf-8"))["activity_matched_control"]
    if args.repeats:
        cfg["repeats"] = args.repeats
    local = ROOT / "data/processed/local"
    clusters = pd.read_csv(local / "customer_clusters.csv", dtype={"customer_id": str, "cluster_id": str})
    size_only = pd.read_csv(local / "random_groups.csv", dtype={"customer_id": str, "random_group_id": str})
    taxonomy = pd.read_csv(ROOT / "data/taxonomy/item_taxonomy_v1.csv", dtype=str, keep_default_na=False)
    baskets = cc.load_discovery_baskets(ROOT)
    labels = sorted(clusters.cluster_id.unique())

    # 1. activity-matched random groups (customer level, git-ignored)
    controls = build_controls(clusters, baskets.customer_id.value_counts(), cfg)
    for name, frame in controls.items():
        frame.to_csv(local / f"random_groups_{name}.csv", index=False)
    systems = {"S_size_only": size_only, **controls}

    # 2. basket-level assignment matrices: real (1 row) and each control (one row per seed)
    real_assign = baskets.customer_id.map(clusters.set_index("customer_id").cluster_id).to_numpy()[None, :]
    assign = {}
    for name, frame in systems.items():
        seeds = sorted(frame.seed.unique())
        assign[name] = np.vstack([baskets.customer_id.map(frame[frame.seed.eq(s)].set_index("customer_id")
                                                          .random_group_id).to_numpy() for s in seeds])
        assert not pd.isna(assign[name]).any()

    # 3. activity audit: does each control reproduce the real groups' Discovery volume?
    profile_orders = clusters.set_index("customer_id").frequency
    audit = []
    for name, matrix in [("real", real_assign), *assign.items()]:
        for g in labels:
            n = (matrix == g).sum(1)
            frame = clusters if name == "real" else systems[name]
            col = "cluster_id" if name == "real" else "random_group_id"
            prof = frame[frame[col].eq(g)].groupby("seed" if name != "real" else (lambda _: 0)).customer_id \
                .apply(lambda ids: profile_orders.loc[ids].sum())
            audit.append({"grouping": name, "group_id": g, "seeds": len(n),
                          "discovery_baskets_median": float(np.median(n)), "discovery_baskets_min": int(n.min()),
                          "discovery_baskets_max": int(n.max()), "profile_orders_median": float(prof.median())})
    audit = pd.DataFrame(audit)

    # 4. exhaustive category pool, G, and every grouping
    x, cols = cc.category_matrix(baskets, taxonomy)
    pool = cc.Pool(x, cols)
    g_metrics, g_ranked = cc.global_system(pool, len(baskets))
    print(f"pool: {len(pool.combos)} combinations, {len(pool.rule_id)} directional rules; "
          f"G strict rules {g_metrics['strict_rules']}", flush=True)
    results, group_results = {}, {}
    for name, matrix in [("real", real_assign), *assign.items()]:
        results[name], group_results[name] = cc.evaluate(pool, matrix, labels, g_ranked)
        print(f"evaluated {name}: {len(matrix)} systems ({time.perf_counter() - start:.0f}s)", flush=True)

    # 5. reproduction check against C's numbers (same data, same thresholds)
    real = results["real"].iloc[0]
    real_groups = group_results["real"].set_index("group_id")
    checks = {
        "G strict rules": (g_metrics["strict_rules"], C_REFERENCE["G_strict_rules"]),
        **{f"C{g} strict rules": (int(real_groups.loc[g, "strict_rules"]), v)
           for g, v in C_REFERENCE["L_strict_rules"].items()},
        **{f"G coverage B{b}": (round(g_metrics[f"coverage_B{b}"], 6), round(v, 6))
           for b, v in C_REFERENCE["G_coverage"].items()},
        **{f"L coverage B{b}": (round(real[f"coverage_B{b}"], 6), round(v, 6))
           for b, v in C_REFERENCE["L_coverage"].items()},
        **{f"S coverage median B{b}": (round(results["S_size_only"][f"coverage_B{b}"].median(), 4), v)
           for b, v in C_REFERENCE["S_coverage_median"].items()},
        "L local-not-global share": (round(real.local_not_global_share, 6),
                                     round(C_REFERENCE["L_local_not_global_share"], 6)),
    }
    check_rows = [{"check": k, "ours": a, "C": b, "match": abs(a - b) < 1e-4} for k, (a, b) in checks.items()]
    check_frame = pd.DataFrame(check_rows)
    print(check_frame.to_string(index=False))

    # 6. outputs
    args.out.mkdir(parents=True, exist_ok=True)
    systems_frame = pd.concat([results[n].assign(grouping=n) for n in results])
    groups_frame = pd.concat([group_results[n].assign(grouping=n) for n in group_results])
    comparison = pd.concat([cc.compare(real, results[n], METRICS).assign(control=n) for n in assign])
    per_group = []
    for name in assign:
        for g in labels:
            r = groups_frame[groups_frame.grouping.eq(name) & groups_frame.group_id.eq(g)]
            for m in ["rest_bc_len2", "rest_bc_len3", "strict_rules"]:
                v = real_groups.loc[g, m]
                ge = int((r[m] >= v - 1e-12).sum())
                per_group.append({"control": name, "group": f"C{g}", "metric": m, "real": v,
                                  "random_median": r[m].median(), "random_max": r[m].max(),
                                  "random_n_baskets_median": r.n_baskets.median(), "random_ge_real": ge,
                                  "empirical_p": (1 + ge) / (1 + len(r))})
    pd.DataFrame(per_group).to_csv(args.out / "per_group_real_vs_controls.csv", index=False)
    systems_frame.to_csv(args.out / "system_metrics.csv", index=False)
    groups_frame.to_csv(args.out / "group_metrics.csv", index=False)
    comparison.to_csv(args.out / "real_vs_controls.csv", index=False)
    audit.to_csv(args.out / "activity_audit.csv", index=False)
    check_frame.to_csv(args.out / "reproduction_check_vs_C.csv", index=False)
    pd.DataFrame([{"system": "G", **g_metrics}]).to_csv(args.out / "global_metrics.csv", index=False)
    manifest = {"config": cfg, "pool_combinations": len(pool.combos), "pool_rules": len(pool.rule_id),
                "n_baskets": len(baskets), "n_categories": len(cols), "snapshot": cc.SNAPSHOT,
                "strict": cc.STRICT, "budgets": cc.BUDGETS, "reproduction_all_match": bool(check_frame.match.all()),
                "elapsed_seconds": round(time.perf_counter() - start, 1)}
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    pd.set_option("display.width", 200)
    print(audit.to_string(index=False))
    print(comparison.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
