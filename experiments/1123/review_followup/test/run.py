"""Evaluate the 1123 B2 and greedy-global rule lists on Test at fixed P5/120."""
import argparse
from copy import copy
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pandas as pd
from threadpoolctl import threadpool_limits


HERE = Path(__file__).resolve().parent
VARIANTS = ("rfm", "rfm_form", "form")
METHODS = ("G", *VARIANTS, "G_greedy")
CONFIG, BUDGET = "P5", 120
NAMES = {"G": "普通 G", "rfm": "纯 RFM", "rfm_form": "RFM＋采购形态",
         "form": "纯采购形态", "G_greedy": "贪心 G"}


def load_common(repository):
    sys.path.insert(0, str(repository / "src"))
    loader = spec_from_file_location("common1123", repository / "experiments/shared_full_store/run.py")
    common = module_from_spec(loader)
    loader.loader.exec_module(common)
    return common


def verify_rosters(common, roster):
    expected = {("GL", method, "") for method in METHODS}
    expected |= {("B2", v, str(s)) for v in VARIANTS for s in range(1000, 1100)}
    assert set(roster[common.KEY].itertuples(index=False, name=None)) == expected
    assert set(roster.config) == {CONFIG}
    combos = {rid: tuple(sorted(a + c)) for rid, (a, c) in common.parts(roster).items()}
    for _, library in roster.groupby(common.KEY, sort=False):
        assert sorted(library.position) == list(range(1, BUDGET + 1))
        assert len({combos[rid] for rid in library.rule_id}) == BUDGET


def freeze(common, project, inputs, out):
    main = project / "results"
    review = project / "review_followup/results"
    spec = common.read_json(main / "freeze.json")
    assert (spec["selection"]["config"], spec["selection"]["budget"]) == (CONFIG, BUDGET)
    assert spec["quality"] == common.QUALITY and spec["strict_quality"] == common.STRICT_QUALITY
    assert spec["bootstrap"] == common.BOOTSTRAP
    assert all(spec["input_hashes"][name] == digest for name, digest in inputs.hashes().items())
    for name in ("discovery_popularity.csv", "frozen_rule_lists.csv"):
        assert common.sha(main / name) == spec["artifact_hashes"][name]
    prior = common.read_csv(main / "frozen_rule_lists.csv")
    roster = common.read_csv(review / "validation_rosters.csv")
    original_methods = set(METHODS) - {"G_greedy"}
    retained = lambda table: table.loc[table.control.eq("GL") & table.method.isin(original_methods)]
    pd.testing.assert_frame_equal(retained(prior).reset_index(drop=True),
                                  retained(roster).reset_index(drop=True))
    roster = roster.loc[roster.control.isin(["GL", "B2"])].copy()
    verify_rosters(common, roster)
    out.mkdir(parents=True, exist_ok=False)
    common.csv(roster, out / "rosters.csv")
    common.write_json(out / "freeze.json", {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": CONFIG, "budget": BUDGET, "systems": 305,
        "test_window": spec["test_window"], "a_snapshot_commit": spec["a_snapshot_commit"],
        "source_baskets_sha256": spec["source_baskets_sha256"],
        "quality": common.QUALITY, "strict_quality": common.STRICT_QUALITY, "bootstrap": common.BOOTSTRAP,
        "runner_sha256": common.sha(Path(__file__)),
        "source_hashes": {name: common.sha(project / name) for name in (
            "results/freeze.json", "results/discovery_popularity.csv", "review_followup/results/validation_rosters.csv")},
        "rosters_sha256": common.sha(out / "rosters.csv"), "input_hashes": inputs.hashes(),
        "greedy_comparators": list(METHODS[:-1]),
        "B2_comparator": "real library of the same segmentation, 100 stored seeds each",
    })
    print("Frozen 305 saved rule libraries.", flush=True)


def replay_check(common, project, systems, recommendation):
    def compare(saved, current):
        identity = current.control.eq("GL") & current.method.isin(METHODS[:-1])
        old = common.read_csv(project / "results/test" / saved).loc[lambda d: d.control.eq("GL")]
        keys = common.KEY + (["sample"] if "sample" in old else [])
        new = current.loc[identity, old.columns]
        pd.testing.assert_frame_equal(old.sort_values(keys).reset_index(drop=True),
                                      new.sort_values(keys).reset_index(drop=True),
                                      check_dtype=False, rtol=1e-12, atol=1e-12)

    compare("systems.csv", systems)
    compare("recommendation.csv", recommendation)


def evaluate(common, project, inputs, snapshot_repo, out):
    spec = common.read_json(out / "freeze.json")
    assert not (out / "audit.json").exists()
    assert spec["runner_sha256"] == common.sha(Path(__file__))
    assert spec["rosters_sha256"] == common.sha(out / "rosters.csv")
    assert spec["input_hashes"] == inputs.hashes()
    assert all(common.sha(project / name) == digest for name, digest in spec["source_hashes"].items())
    roster = common.read_csv(out / "rosters.csv")
    verify_rosters(common, roster)
    snapshot = copy(inputs)
    snapshot.repo = snapshot_repo
    period = common.test_period(snapshot, spec)
    assert period.audit == common.read_json(project / "results/test/audit.json")["sample"]
    systems, quality, cover = common.coverage_systems(inputs, period, roster, BUDGET)
    popular = common.read_csv(project / "results/discovery_popularity.csv").l2_id.tolist()
    top, hits, eligible = common.recommend(inputs.repo, period, roster, popular)
    replay_check(common, project, systems, top)
    print("Reproduced all four main 1123 systems on the same orders; computing comparisons.", flush=True)

    merged = systems.merge(top.loc[top["sample"].eq("all"), common.KEY + ["hit_at_5", "ndcg_at_5", "top_orders"]],
                           on=common.KEY, validate="one_to_one")
    real = merged.loc[merged.control.eq("GL")].set_index("method").loc[list(METHODS)]
    distributions = []
    for variant in VARIANTS:
        draws = merged.loc[merged.control.eq("B2") & merged.method.eq(variant)]
        assert len(draws) == 100
        for metric in (*common.MEASURES, "quality_pass_share", "strict_quality_pass_share", "hit_at_5", "ndcg_at_5"):
            values, actual = draws[metric], real.loc[variant, metric]
            ge = int(values.ge(actual - 1e-12).sum())
            distributions.append(dict(variant=variant, metric=metric, true_value=actual, B2_median=values.median(),
                                      B2_min=values.min(), B2_max=values.max(), B2_ge_true=ge,
                                      descriptive_upper_tail=(1 + ge) / 101))
    b2 = pd.DataFrame(distributions)

    runs, scopes, changes = [], {}, []
    for baseline in METHODS[:-1]:
        left = (*cover[baseline, CONFIG, BUDGET], hits["GL", baseline, ""])
        right = (*cover["G_greedy", CONFIG, BUDGET], hits["GL", "G_greedy", ""])
        for metric, a, b in zip((*common.MEASURES, "hit_at_5"), left, right):
            label = f"G_greedy_minus_{baseline}:{metric}"
            scope = period.identified if metric in common.MEASURES[1:] else period.store
            orders = eligible if metric == "hit_at_5" else scope.all
            scopes[label] = scope
            runs.append((label, a, b, orders))
            add, lose, both = (b & ~a).bit_count(), (a & ~b).bit_count(), (a & b).bit_count()
            changes.append(dict(comparison=label, baseline=baseline, measure=metric, orders=orders.bit_count(),
                                both=both, newly_matched=add, no_longer_matched=lose, net=add-lose))
    paired = pd.DataFrame(changes).merge(common.intervals(period, runs, scopes).rename(
        columns={"metric": "comparison", "L_minus_G": "difference"}), on="comparison", validate="one_to_one")
    for name, frame in {"systems": merged, "GL_quality": quality, "recommendation": top,
                        "B2_comparisons": b2, "greedy_paired": paired}.items():
        common.csv(frame, out / f"{name}.csv")
    (out / "RESULTS.md").write_text(report(common, real, b2, paired, period.audit), encoding="utf-8")
    common.write_json(out / "audit.json", {"sample": period.audit, "systems": len(merged),
        "baseline_replay_verified": True, "freeze_sha256": common.sha(out / "freeze.json"),
        "B2_seeds_per_segmentation": 100, "maskable_orders": eligible.bit_count()})
    print((out / "RESULTS.md").read_text(encoding="utf-8"), flush=True)


def report(common, real, b2, paired, sample):
    metric_names = dict(raw_coverage="全店覆盖", reliable_coverage="原版可靠覆盖",
                        strict_reliable_coverage="严格可靠覆盖", hit_at_5="Hit@5")
    lines = ["# 1123 · B2 与贪心 G Test 补测", "",
             "固定 P5／120，直接使用 1123 保存的普通 G、三套真实分群、贪心 G 和 300 套 B2 名单。",
             f"全店覆盖用 {sample['all']:,} 张订单，规则质量与可靠覆盖用 {sample['identified']:,} 张有 ID 订单，"
             f"Hit@5 用 {sample['maskable']:,} 张可遮挡订单。", "", "## Test 结果", "",
             "| 规则库 | 全店覆盖 | 覆盖单数 | 原版可靠覆盖 | 严格可靠覆盖 | 严格质量通过 | Hit@5 |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for method, r in real.iterrows():
        lines.append(f"| {NAMES[method]} | {r.raw_coverage:.2%} | {r.raw_coverage_count:,} | {r.reliable_coverage:.2%} | "
                     f"{r.strict_reliable_coverage:.2%} | {r.strict_quality_pass_share_count}/120 | {r.hit_at_5:.2%} |")
    lines += ["", "## 贪心 G 的配对差值", "",
              "差值为贪心 G 减去表中对照，区间来自 2,000 次配对重抽。", "",
              "| 对照 | 指标 | 差值 pp [95% CI] | 新增 | 损失 | 净增 |", "| --- | --- | ---: | ---: | ---: | ---: |"]
    for r in paired.itertuples(index=False):
        lines.append(f"| {NAMES[r.baseline]} | {metric_names[r.measure]} | {100*r.difference:+.2f} "
                     f"[{100*r.low95:+.2f}, {100*r.high95:+.2f}] | {r.newly_matched} | {r.no_longer_matched} | {r.net:+d} |")
    lines += ["", "## 真实分群与 B2 对照", "", "| 真实分群 | 指标 | 真实 | B2 中位数 [最小, 最大] | B2 ≥ 真实 |",
              "| --- | --- | ---: | ---: | ---: |"]
    for r in b2.loc[b2.metric.isin(metric_names)].itertuples(index=False):
        lines.append(f"| {NAMES[r.variant]} | {metric_names[r.metric]} | {r.true_value:.2%} | {r.B2_median:.2%} "
                     f"[{r.B2_min:.2%}, {r.B2_max:.2%}] | {r.B2_ge_true}/100 |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "test"])
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--snapshot-repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=HERE / "results")
    args = parser.parse_args()
    project = args.project.resolve()
    repo = project.parent / "repository"
    common = load_common(repo)
    with threadpool_limits(limits=2):
        inputs = common.Inputs(repo)
        if args.action == "freeze":
            freeze(common, project, inputs, args.out.resolve())
        else:
            evaluate(common, project, inputs, args.snapshot_repo.resolve(), args.out.resolve())


if __name__ == "__main__":
    main()
