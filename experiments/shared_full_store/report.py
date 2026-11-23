"""Create the readable summary from the completed aggregate outputs."""

import argparse
from pathlib import Path

from run import MEASURES, read_csv, read_json


NAMES = {
    "raw_coverage": "全店原始覆盖",
    "reliable_coverage": "有 ID 订单的可靠覆盖",
    "strict_reliable_coverage": "有 ID 订单的严格可靠覆盖",
    "quality_pass_share": "原版质量通过率",
    "strict_quality_pass_share": "严格质量通过率",
    "accepted_store_coverage": "通过原版验收的规则在全店的覆盖",
}
LABELS = {
    "all": "全部",
    "profile": "历史顾客",
    "identified_non_profile": "有 ID 的非历史顾客",
    "anonymous": "匿名订单",
}
CHOICE_LABELS = {
    "two_low_gain_steps": "已观察到连续两档低增量",
    "within_tolerance_plateau_unconfirmed": "达到覆盖要求，预算平台尚未确认",
    "best_available_shortfall": "没有档位同时达到四项覆盖要求，选最大短缺最小的档位",
}


def percent(value):
    return f"{value:.2%}"


def points(value):
    return f"{100 * value:+.2f}"


def table(columns, rows):
    return "\n".join(["| " + " | ".join(columns) + " |",
                      "| " + " | ".join(["---"] * len(columns)) + " |",
                      *["| " + " | ".join(map(str, row)) + " |" for row in rows]])


def report(out):
    discovery = read_json(out / "discovery_audit.json")
    validation = read_json(out / "validation_audit.json")
    spec = read_json(out / "freeze.json")
    test = read_json(out / "test/audit.json")
    choice = spec["selection"]
    config, budget = choice["config"], choice["budget"]
    sections = [
        "# D 组重做结果 · 去重共享与全店评价",
        "依据 [本轮协议](../README.md) 执行。Test 使用已公布过结果的历史时段，属于补充评价。",
        f"Discovery 共 **{discovery['sample']['eligible_baskets']:,}** 单，为 G、L 和 100 套 A1 重建规则顺序。"
        f"与既有去重路径逐项对上 **{discovery['prefixes_verified_against_existing_100']:,}** 个前 100 名额。"
        " 各配置的共同扫描上限为 " + "、".join(f"{c} {b}" for c, b in discovery["capacity_limits"].items()) + "。",
        "## Validation 选择",
        f"冻结 **{config}／{budget}**。{CHOICE_LABELS[choice['criterion']]}。"
        f"原始覆盖用全店 {validation['sample']['all']:,} 单，可靠覆盖用有 ID 的 {validation['sample']['identified']:,} 单。",
    ]
    grid = read_csv(out / "validation_selection_grid.csv")
    rows = []
    local = grid.loc[grid.config.eq(config) & grid.budget.between(budget - 20, budget + 20)]
    for r in local.itertuples(index=False):
        rows.append((r.budget, percent(r.raw_coverage_G), percent(r.raw_coverage_L),
                     percent(r.reliable_coverage_G), percent(r.reliable_coverage_L),
                     f"{r.raw_coverage_gain_pp_G:+.2f}／{r.raw_coverage_gain_pp_L:+.2f}",
                     f"{r.reliable_coverage_gain_pp_G:+.2f}／{r.reliable_coverage_gain_pp_L:+.2f}",
                     f"{r.max_shortfall_pp:.2f}"))
    sections += [table(["预算", "G 全店覆盖", "L 全店覆盖", "G 可靠覆盖", "L 可靠覆盖",
                        "本档全店增量 G／L（pp）", "本档可靠增量 G／L（pp）", "最大短缺（pp）"], rows)]
    choices = read_csv(out / "validation_choices.csv")
    sections += [table(["质量口径", "容许差距（pp）", "选中", "状态"],
                       [("原版" if r.quality_metric == "reliable_coverage" else "严格版",
                         r.tolerance_pp, f"{r.config}／{r.budget}", CHOICE_LABELS[r.selection_status])
                        for r in choices.itertuples(index=False)]),
                 "[全网格系统结果](validation_systems.csv) · [选参网格](validation_selection_grid.csv) · [A1 对照](validation_A1.csv)",
                 "## Test 覆盖与质量",
                 f"全店 **{test['sample']['all']:,}** 单，有 ID **{test['sample']['identified']:,}** 单。"
                 f"每套系统使用冻结的 {budget} 个不同组合。"]
    comp = read_csv(out / "test/coverage_comparisons.csv")
    ci = read_csv(out / "test/paired_intervals.csv").set_index("metric")
    rows = []
    for r in comp.itertuples(index=False):
        delta = points(r.L_minus_G)
        if r.metric in MEASURES:
            bounds = ci.loc[r.metric]
            delta += f" [{points(bounds.low95)}, {points(bounds.high95)}]"
        rows.append((NAMES[r.metric], percent(r.G), percent(r.L), delta, percent(r.A1_median), f"{r.A1_ge_L}/100"))
    sections.append(table(["指标", "G", "L", "L−G（pp，含可用区间）", "A1 中位数", "A1 ≥ L"], rows))
    methods = read_csv(out / "test/systems.csv").loc[lambda x: x.control.eq("GL")].set_index("method")
    sections.append(table(["共购覆盖范围", "订单", "G", "L"], [
        (LABELS[label], f"{methods.loc['G', label+'_orders']:,}",
         percent(methods.loc["G", label+"_raw_coverage"]), percent(methods.loc["L", label+"_raw_coverage"]))
        for label in LABELS
    ]))
    rec = read_csv(out / "test/recommendation.csv")
    rec_comp = read_csv(out / "test/recommendation_comparisons.csv")
    sections += ["## Test 推荐",
                 f"可遮挡订单 **{test['sample']['maskable']:,}** 单。每单同一遮挡。"
                 f"有 {test['unable_to_fill_five']} 单的未见候选不足五个，按实际候选评价。"]
    if (out / "runner_recovery.json").exists():
        sections.append("首次运行在五项断言处停止。边界修正保留了原冻结名单、排序及样本。"
                        "[修复记录](runner_recovery.json)")
    rows = []
    for label in LABELS:
        block = rec.loc[rec["sample"].eq(label) & rec.control.ne("A1")].set_index("method")
        row = rec_comp.loc[rec_comp["sample"].eq(label) & rec_comp.metric.eq("hit_at_5")].iloc[0]
        rows.append((LABELS[label], f"{row.top_orders:,}", percent(block.loc["popular", "hit_at_5"]),
                     percent(row.G), percent(row.L), percent(row.A1_median), f"{row.A1_ge_L}/100"))
    sections.append(table(["范围", "订单", "纯热门", "G＋热门", "L＋热门", "A1 中位数", "A1 ≥ L"], rows))
    headline = rec.loc[rec["sample"].eq("all") & rec.control.ne("A1")].set_index("method")
    rows = []
    for trial, metric, method, baseline in [
        ("G 相对纯热门", "G_hit_at_5_vs_popular", "G", "popular"),
        ("L 相对纯热门", "L_hit_at_5_vs_popular", "L", "popular"),
        ("L 相对 G", "hit_at_5", "L", "G"),
    ]:
        row, band = headline.loc[method], ci.loc[metric]
        rows.append((trial, int(row[f"new_hits_vs_{baseline}"]), int(row[f"lost_hits_vs_{baseline}"]),
                     f"{int(row[f'net_hits_vs_{baseline}']):+}", points(band.L_minus_G),
                     f"[{points(band.low95)}, {points(band.high95)}]"))
    sections += [table(["推荐对照", "新命中", "丢失", "净变化（单）", "Hit@5 差（pp）", "配对 95% 区间（pp）"], rows),
                 "[冻结记录](freeze.json) · [冻结名单](frozen_rule_lists.csv) · [Test 覆盖与质量](test/systems.csv) · "
                 "[逐系统推荐及 NDCG@5](test/recommendation.csv) · [配对区间](test/paired_intervals.csv)"]
    (out / "README.md").write_text("\n\n".join(sections) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path, nargs="?", default=Path(__file__).resolve().parent / "results")
    report(parser.parse_args().out)
