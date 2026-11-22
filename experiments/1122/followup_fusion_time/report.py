"""Build the paired comparison report for fusion and temporal experiments."""
import json
from pathlib import Path

import pandas as pd


def percent(v):
    return f"{v:.2%}"


def pp(v):
    return f"{v:+.2f}"


def ci(row):
    return f"[{pp(row.low95_pp)}, {pp(row.high95_pp)}]"


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |",
                      *["| " + " | ".join(map(str, row)) + " |" for row in rows]])


def report(root):
    output = root / "results"
    meta = json.loads((output / "checks.json").read_text(encoding="utf-8"))
    f = pd.read_csv(output / "fusion_late.csv")
    pair = pd.read_csv(output / "fusion_paired.csv")
    time = pd.read_csv(output / "time_late_paired.csv")
    season = pd.read_csv(output / "season_late_paired.csv")
    by_window = pd.read_csv(output / "time_by_window.csv", dtype={"train_end_exclusive": str, "eval_end_exclusive": str})
    assert (by_window.train_end_exclusive < by_window.eval_end_exclusive).all()
    assert by_window.eval_end_exclusive.max() == meta["validation_end_exclusive"] == "2011-06-01"
    assert meta["max_source_order"] < meta["validation_end_exclusive"]
    for x in (f, pair, time, season):
        assert (x.hits - x.baseline_hits).eq(x.net_orders).all()
        assert (x.new_hits - x.lost_hits).eq(x.net_orders).all()

    arms = {"G100": "G 前100", "G200": "G 前100＋后续100", "G100_L100_restricted": "G 前100＋L 限群100",
            "G100_L100_shared": "G 前100＋L 共享100"}
    chosen = f.loc[f.aggregation_selected_on_early].set_index("arm")
    originals = meta["fusion_baseline_late_hits"] / meta["fusion_late"]
    prior_gated = meta["prior_gated_g_tail_late_hits"] / meta["fusion_late"]
    fusion = table(["候选池", "前段选定的规则聚合", "权重 G / 补充 / 热门",
                    "后段 Hit@5", "新增 / 丢失 / 净增", "相对原 G＋L1 pp", "95% 区间 pp"], [
        (label, "折扣第二条" if r.aggregation == "discounted" else "最强一条",
         f"{r.w_G:g} / {r.w_extra:g} / {r.w_pop:g}", percent(r.rate),
         f"{r.new_hits}/{r.lost_hits}/{r.net_orders:+}", pp(r.delta_pp), ci(r))
        for arm, label in arms.items() for r in [chosen.loc[arm]]
    ])
    lt = table(["对照", "净命中", "差值 pp", "95% 区间 pp"], [
        (f"{arms[r.left]} 对 {arms.get(r.right, '原门控 G 尾段')}", f"{r.net_orders:+}", pp(r.delta_pp), ci(r))
        for r in pair.itertuples() if r.left in arms
    ])
    time_table = table(["方案", "对照", "后段 Hit@5", "新增 / 丢失 / 净增", "差值 pp", "95% 区间 pp"],
                       [(r.arm, r.reference, percent(r.rate), f"{r.new_hits}/{r.lost_hits}/{r.net_orders:+}",
                         pp(r.delta_pp), ci(r)) for r in time.itertuples()])
    st = table(["季节门槛", "权重底座", "后段单数", "新增 / 丢失 / 净增", "差值 pp", "95% 区间 pp"], [
        ({"strict": "65%", "s35": "35%", "s20": "20%"}[r.policy], r.reference, r.orders,
         f"{r.new_hits}/{r.lost_hits}/{r.net_orders:+}", pp(r.delta_pp), ci(r))
        for r in season.query("subset == 'all'").itertuples()
    ])
    effects = table(["季节标签占 Discovery 品类订单行比例", "入选 L2 候选数", "后段有淡季规则触发的订单"], [
        ({"strict": "65%", "s35": "35%", "s20": "20%"}[policy], len(gr),
         meta["late_off_season_trigger_orders"].get(policy, 0))
        for policy, gr in meta["strong_seasonal_l2"].items()
    ])

    md = f"""# 1122 后续两轮 · 分数融合与时间季节

两轮都使用原 Test 开始前的数据。Discovery 生成候选，Validation 前段（2010‑12 至 2011‑02）挑参数，后段（2011‑03 至 2011‑05）对照。前段 {meta['fusion_early']:,} 张、后段 {meta['fusion_late']:,} 张，均为固定 Profile 顾客的同一套遮挡订单。两轮使用相同五个推荐位置和固定 Discovery L1 条件热门。正式 Test 未执行。由于完整 Validation 在先前项目中已经看过，后段属于扩展回测。

## 第一轮 · 让多条规则参与完整 Top‑5

前次的 G＋L1 兜底为 **{percent(originals)}**，L1 兜底＋门控 G 尾段为 **{percent(prior_gated)}**，这两项均已逐批复现。这里允许所有候选参与五项排序。局部候选排除 G 前100 已选方向规则，沿用 Added Value 选池及向全局收缩的置信度。G 后续与 L 都额外给 100 条，因此这两个来源可以同预算比较。

每个后件分别保留最强规则，以及第二条前件与最强规则互不重叠的证据。折扣分数为 p1＋0.5×(1−p1)×p2。它只用于排序。规则和 L1 条件热门分数按有限网格加权，表内权重和聚合方式只由前段决定。所有推荐排除已在可见篮里的品类。

{fusion}

### 配对强基线

{lt}

两种聚合各自的最佳权重与命中、折扣相对最强规则的配对差都在结果表中。G100 对比原 G 检验只改打分的效果，G200 对比 G100＋L100 检验给局部池相同新增规则预算后的效果。

## 第二轮 · 固定规则库，拆开时间衰减与季节开关

固定 G 前100 条候选资格、L1 榜单和排序的平局规则。每个回测窗口只在起点用之前订单更新置信度。比较固定 Discovery、纳入 Validation 已结束月份的扩窗等权、在相同扩窗样本上按时间指数加权。半衰期 90／180／365 天只用前段比较，选到 **{meta['half_life_selected_early']} 天**。权重差异降低有效样本量，覆盖与有效样本另表记录。

{time_table}

### 季节开关敏感性

拟合端按 Discovery 中带季节标签的 SKU 行占 L2 商品行的比例，标记偏节日的后件。圣诞启用月为 10–12 月、复活节为 3–4 月。开关只跳过淡季规则触发，依然允许 L1 榜单兜底。原先 65% 严格定义在训练数据没有命中，所以加测 35% 和 20%，作为低纯度品类可能被误伤的敏感性实验。门槛依据训练占比，未按后段命中优化。

{effects}

{st}

季节开关只说明在当前 L2 粒度的效果。单个高占比 L2 仍可能同时包含大量常青款，淡季触发切片也可以从附表查看。

## 复算与明细

在本目录执行 python -B run.py，再执行 python -B report.py。继承 1122 的预处理快照与 L1 兜底。
- [融合前段选参](results/fusion_tuning.csv) · [后段结果](results/fusion_late.csv) · [配对比较](results/fusion_paired.csv)
- [每窗时间权重结果](results/time_by_window.csv) · [后段时间配对](results/time_late_paired.csv) · [有效样本量](results/time_effective_sample.csv)
- [L2 季节标签计数](results/season_flags.csv) · [季节开关后段配对](results/season_late_paired.csv)
- [核验记录](results/checks.json)
"""
    (root / "两轮实验结果.md").write_text(md, encoding="utf-8")
    print(fusion, lt, time_table, effects, st, sep="\n")


if __name__ == "__main__":
    report(Path(__file__).resolve().parent)
