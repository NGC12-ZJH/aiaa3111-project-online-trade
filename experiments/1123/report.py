"""Summarize the frozen three-partition experiment from aggregate outputs."""

import argparse
import json
from pathlib import Path

import pandas as pd


HERE = Path(__file__).resolve().parent
LABELS = {"rfm": "纯 RFM", "rfm_form": "RFM＋采购形态", "form": "纯采购形态",
          "G": "全局 G", "popular": "纯热门"}
METRICS = {"raw_coverage": "全店共购覆盖", "reliable_coverage": "原版可靠覆盖",
           "strict_reliable_coverage": "严格可靠覆盖", "hit_at_5": "Hit@5"}


def df(out, name):
    return pd.read_csv(out / f"{name}.csv", keep_default_na=False, dtype={"seed": str})


def info(out, name):
    return json.loads((out / f"{name}.json").read_text(encoding="utf-8"))


def table(columns, rows):
    return "\n".join(["| " + " | ".join(columns) + " |",
                      "| " + " | ".join(["---"] * len(columns)) + " |",
                      *["| " + " | ".join(map(str, r)) + " |" for r in rows]])


def percent(value):
    return f"{value:.2%}"


def band(row):
    return f"{100 * row.difference:+.2f} [{100 * row.low95:+.2f}, {100 * row.high95:+.2f}]"


def summarize(out):
    profile, discovery = (info(out, name) for name in ("profile_audit", "discovery_audit"))
    validation, freeze = (info(out, name) for name in ("validation_audit", "freeze"))
    test = info(out, "test/audit")
    p, b = (freeze["selection"][k] for k in ("config", "budget"))
    sections = [
        "# 1123 三种分群完整结果",
        f"在同一批订单和同一规则容量下比较三种分群。Validation 统一选出 **{p}／{b}**，"
        f"Test 评价冻结的 **{test['systems']} 套**规则库，属于历史 Test 补充评价。详见 [实验协议](../README.md)。",
        "## Profile 分群与 Discovery 组库",
        f"三种分群各使用 {profile['profile_customers']:,} 名 Profile 顾客。"
        f"价格分位线为 £{profile['price_bands'][0]:.2f} 和 £{profile['price_bands'][1]:.2f}。"
        f"Discovery 挖掘样本为同一批 {discovery['sample']['eligible_baskets']:,} 单，"
        f"核对原纯 RFM、A1 与全局 G 的 {discovery['original_rfm_and_global_paths_reproduced']:,} 个入库位置。",
    ]
    groups = df(out, "profile_clusters")
    rows = []
    for name, block in groups.groupby("variant", sort=False):
        rows.append((LABELS[name], "／".join(f"{n:,}" for n in block.customers),
                     "／".join(f"{n:,}" for n in block.discovery_orders)))
    sections += [table(["分群方法", "三群 Profile 顾客数", "三群 Discovery 订单数"], rows)]
    sections.append("顾客分区的一致程度（ARI）为" + "，".join(
        f"{LABELS[left]} vs {LABELS[right]} {score:.3f}"
        for pair, score in profile["pairwise_ari"].items() for left, right in [pair.split("_vs_")]) + "。")
    sections += ["## Validation 选择",
                 f"全店 {validation['sample']['all']:,} 单，有顾客 ID {validation['sample']['identified']:,} 单。"
                 "容量评分对 G 和三套 L 的平均值各给一半权重，每 10 个组合扣 0.50 个百分点。"]
    ranking = df(out, "validation_ranking")
    winner_rows = [(LABELS.get(r.selection, "三种分群共同"), f"{r.config}／{r.budget}", f"{r.score_pp:.4f}")
                   for r in ranking.loc[ranking["rank"].eq(1)].itertuples(index=False)]
    sections.append(table(["选参方式", "选中配置", "扣成本评分"], winner_rows))
    common_rows = ranking.loc[ranking.selection.eq("common")].head(5)
    sections.append(table(["共同排名", "配置", "覆盖得分（pp）", "扣成本评分"],
                          [(r.rank, f"{r.config}／{r.budget}", f"{r.coverage_pp:.3f}", f"{r.score_pp:.4f}")
                           for r in common_rows.itertuples(index=False)]))
    val = df(out, "validation_systems")
    vr = df(out, "validation_recommendation")
    main_val = val.loc[val.control.eq("GL") & val.config.eq(p) & val.budget.eq(b)].set_index("method")
    top_val = vr.loc[vr.control.ne("A1") & vr["sample"].eq("all")].set_index("method")
    sections.append(table(["共同配置下", "全店覆盖", "原版可靠覆盖", "原版质量通过率", "Hit@5"],
                          [(LABELS[key], percent(main_val.loc[key, "raw_coverage"]),
                            percent(main_val.loc[key, "reliable_coverage"]),
                            percent(main_val.loc[key, "quality_pass_share"]), percent(top_val.loc[key, "hit_at_5"]))
                           for key in ("G", "rfm", "rfm_form", "form")]))
    sections += ["[Validation 全网格](validation_systems.csv) · [选参排名](validation_ranking.csv) · "
                 "[Validation 随机对照](validation_A1.csv)",
                 "## Test 结果",
                 f"全店 **{test['sample']['all']:,}** 单，有顾客 ID **{test['sample']['identified']:,}** 单，"
                 f"推荐可遮挡订单 **{test['sample']['maskable']:,}** 单。"
                 f"其中 {test['unable_to_fill_five']} 单未见候选不足五个，按实际候选评价。"]
    systems = df(out, "test/systems").loc[lambda x: x.control.eq("GL")].set_index("method")
    rec = df(out, "test/recommendation")
    main_rec = rec.loc[rec.control.ne("A1") & rec["sample"].eq("all")].set_index("method")
    rows = []
    for key in ("G", "rfm", "rfm_form", "form"):
        s, t = systems.loc[key], main_rec.loc[key]
        rows.append((LABELS[key], percent(s.raw_coverage), percent(s.reliable_coverage), percent(s.quality_pass_share),
                     percent(s.strict_quality_pass_share), percent(t.hit_at_5), f"{t.ndcg_at_5:.4f}",
                     int(t.net_hits_vs_popular), int(t.net_hits_vs_G)))
    sections += [f"共同纯热门基线 Hit@5 为 **{percent(main_rec.loc['popular','hit_at_5'])}**。",
                 table(["方法", "全店覆盖", "可靠覆盖", "原版通过率", "严格版通过率",
                        "Hit@5", "NDCG@5", "比纯热门净增单", "比 G 净增单"], rows)]
    cover_cmp = df(out, "test/coverage_comparisons")
    hit_cmp = df(out, "test/recommendation_comparisons").loc[lambda x: x["sample"].eq("all")]
    rows = []
    for key in ("rfm", "rfm_form", "form"):
        for metric in ("raw_coverage", "reliable_coverage", "hit_at_5"):
            source = hit_cmp if metric == "hit_at_5" else cover_cmp
            r = source.loc[source.variant.eq(key) & source.metric.eq(metric)].iloc[0]
            rows.append((LABELS[key], METRICS[metric], percent(r.L), percent(r.A1_median), f"{r.A1_ge_L}/100"))
    sections += ["### 与各自 A1 比较", table(["方法", "指标", "真实 L", "A1 中位数", "A1 ≥ L"], rows)]
    ci = df(out, "test/paired_intervals").set_index("metric")
    rows = []
    for name in ci.index:
        pair, metric = name.split(":")
        target, baseline = pair.split("_minus_")
        if metric == "strict_reliable_coverage":
            continue
        rows.append((f"{LABELS[target]} − {LABELS[baseline]}", METRICS[metric], band(ci.loc[name])))
    sections += ["### 配对差值", table(["对比", "指标", "差值（pp）和 95% 区间"], rows),
                 "[冻结清单](frozen_rule_lists.csv) · [冻结记录](freeze.json) · [Test 覆盖和质量](test/systems.csv) · "
                 "[Test 推荐与分样本结果](test/recommendation.csv) · [配对区间表](test/paired_intervals.csv)"]
    (out / "README.md").write_text("\n\n".join(sections) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path, nargs="?", default=HERE / "results")
    summarize(parser.parse_args().out)
