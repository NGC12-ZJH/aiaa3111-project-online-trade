"""Create the budget-selection report from the Validation-only replay."""
import json
import os
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


CONFIGS = ["P1", "P2", "P3", "P4", "P5"]
BUDGETS = list(range(10, 101, 10))


def pct(v):
    return f"{v:.2%}"


def pp(v):
    return f"{v:+.2f}"


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |",
                      *["| " + " | ".join(map(str, row)) + " |" for row in rows]])


def main(output, repo):
    gl = pd.read_csv(output / "global_local_curves.csv")
    rand = pd.read_csv(output / "random_comparisons.csv")
    ints = pd.read_csv(output / "paired_intervals.csv")
    choice = pd.read_csv(output / "selection_sensitivity.csv")
    audit = json.loads((output / "verification.json").read_text(encoding="utf-8"))
    assert len(gl) == 200 and set(gl.budget) == set(BUDGETS)
    const = gl.query("unit == 'combination'").set_index(["config", "method", "budget"])
    a1 = rand.query("unit == 'combination' and control == 'A1'").set_index(["config", "budget", "measure"])
    for metric in ("shared_covered", "reliable_covered", "restricted_covered"):
        assert gl[metric + "_gain_pp"].ge(0).all()
        for _, g in gl.groupby(["unit","config","method"]):
            ordered = g.sort_values("budget")
            previous = ordered[metric].shift().fillna(0)
            assert (abs((ordered[metric] - previous) / audit["orders"] * 100 - ordered[metric + "_gain_pp"]) < 1e-9).all()
    selected = choice.query("range == 'all' and tolerance_pp == 1.0").iloc[0]
    cfg, b = selected.config, int(selected.budget)
    g, l = const.loc[cfg,"G",b], const.loc[cfg,"L",b]
    select_rand = a1.loc[cfg,b,"reliable_covered_rate"]
    same_a1 = a1.loc[cfg,b,"shared_covered_rate"]
    chosen_int = ints.query("config == @cfg and budget == @b and contrast == 'L_minus_G' and unit == 'combination' and measure == 'reliable'").iloc[0]

    def grid(field, fmt, first=10):
        return table(["实际预算", *CONFIGS], [
            (b, *[" / ".join(fmt(const.loc[p,m,b][field]) for m in ("G","L")) for p in CONFIGS])
            for b in BUDGETS if b >= first
        ])

    randgrid = table(["实际预算", *CONFIGS], [(b, *[f"{a1.loc[p,b,'reliable_covered_rate'].random_ge_L}/100"
                                                    for p in CONFIGS]) for b in BUDGETS])
    tail = table(["配置","G 80→90","G 90→100","G 80→100","L 80→90","L 90→100","L 80→100"], [
        (p, *[cell for m in ("G","L") for cell in (
            pp(const.loc[p,m,90].reliable_covered_gain_pp),
            pp(const.loc[p,m,100].reliable_covered_gain_pp),
            pp(100*(const.loc[p,m,100].reliable_covered_rate-const.loc[p,m,80].reliable_covered_rate)),
        )]) for p in CONFIGS])
    decisions = table(["比较范围", "容许少覆盖 pp", "配置 / 预算", "G 可靠", "L 可靠", "最大短缺 pp", "结果"], [
        ("全部配置" if r.range == "all" else r.range, r.tolerance_pp, f"{r.config} / {int(r.budget)}",
         pct(r.G), pct(r.L), f"{r.worst_shortfall_pp:.2f}",
         "达到门槛" if r.state == "within" else "用最接近的一档")
        for r in choice.itertuples()])
    official = pd.read_csv(repo / "results/tables/validation/GL_summary.csv")
    native = official.query("config == 'P5' and budget == 100 and flow == 'shared'").set_index("method")
    old_l = native.loc["L"]
    dup = table(["P5 / 100 方案", "系统", "实际方向规则", "实际无向组合", "共享原覆盖", "限群原覆盖"], [
        ("原名单", m, int(native.loc[m,"unique_rules"]), int(native.loc[m,"unique_combinations"]),
         pct(native.loc[m,"coverage"]),
         pct(official.query("config == 'P5' and budget == 100 and flow == 'restricted' and method == @m").coverage.iloc[0]))
        for m in ("G","L")
    ] + [
        (("无向" if u == "combination" else "有向") + "去重补齐", r.method, int(r.unique_directional),
         int(r.unique_combinations), pct(r.shared_covered_rate), pct(r.restricted_covered_rate))
        for u in ("combination","direction")
        for r in gl.query("config == 'P5' and budget == 100 and unit == @u").itertuples()
    ])

    fig, axes = plt.subplots(2,2,figsize=(10.7,7.2),sharex=True)
    colors = ["#667487","#11728B","#B75F32","#644FAA","#167C58"]
    for j, m in enumerate(("G","L")):
        for p, color in zip(CONFIGS, colors):
            f = const.loc[p,m].sort_index()
            axes[0,j].plot(f.index, f.reliable_covered_rate*100, "o-", linewidth=2, markersize=3.5,
                           color=color, label=p)
            axes[1,j].plot(f.index[1:], f.reliable_covered_gain_pp.iloc[1:], "o-", linewidth=1.8,
                           markersize=3.5, color=color)
        axes[0,j].set_title(f"{m}  |  Reliable shared coverage")
        axes[1,j].set_title(f"{m}  |  Gain per additional 10 combinations")
        axes[0,j].set_ylabel("Covered validation orders (%)")
        axes[1,j].set_ylabel("Percentage-point gain")
        axes[1,j].set_xlabel("Unique undirected combinations")
        for ax in axes[:,j]:
            ax.axvline(b, color="#444", linewidth=.8, linestyle=":", alpha=.6)
            ax.set_xticks(BUDGETS)
            ax.grid(alpha=.22)
            ax.spines[["top","right"]].set_visible(False)
    handles, labels = axes[0,0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=5, frameon=False, loc="lower center", bbox_to_anchor=(.5,.005))
    fig.suptitle("Validation budget curves by configuration",fontsize=15,weight="bold")
    fig.tight_layout(rect=(0,.055,1,.95))
    fig.savefig(output / "coverage_and_increment.png",dpi=175)
    plt.close(fig)

    restricted = gl.query("unit == 'combination'").pivot(
        index=["config","budget"], columns="method", values="restricted_covered_rate").reset_index()
    restricted["max_shortfall_pp"] = 100 * (restricted[["G","L"]].max() - restricted[["G","L"]]).max(axis=1)
    restrict_near = restricted.loc[restricted.max_shortfall_pp.le(1.)]
    if restrict_near.empty:
        restricted_best = restricted.sort_values(["max_shortfall_pp","budget","config"]).iloc[0]
    else:
        restricted_best = restrict_near.sort_values(["budget","max_shortfall_pp","config"]).iloc[0]
    restricted.to_csv(output / "restricted_selection_raw.csv", index=False)
    maxima = table(["配置","100 个组合 G 可靠","100 个组合 L 可靠","100 个组合 L 限群原覆盖"],
                   [(p,pct(const.loc[p,"G",100].reliable_covered_rate),
                     pct(const.loc[p,"L",100].reliable_covered_rate),
                     pct(const.loc[p,"L",100].restricted_covered_rate)) for p in CONFIGS])
    state = "两边都达到 1 个百分点容许差距" if selected.state == "within" else "没有组合同时达到 1 个百分点容许差距；按最小最大差距选"
    entry = os.path.relpath(repo / "experiments/validation_budget_redesign/README.md", output).replace(os.sep, "/")
    report = f"""# Validation 密集预算与跨群去重重跑

全部结果使用冻结 Discovery 候选和同一批 **{audit['orders']:,} 张 Validation 订单、{audit['customers']:,} 名顾客**。P1–P5 各跑 10／20／…／100。每个 G、L、A1、A2、S 都独立使用相同的唯一规则预算。没有调用正式 Test。

按本轮工作标准，**推荐验证设置为 {cfg}／{b} 个无向组合、共享匹配**，{state}。G/L 原覆盖分别为 **{pct(g.shared_covered_rate)}／{pct(l.shared_covered_rate)}**，可靠覆盖为 **{pct(g.reliable_covered_rate)}／{pct(l.reliable_covered_rate)}**。L 的可靠覆盖相对 G 为 {pp(chosen_int.delta_pp)} pp，顾客配对 95% 区间 [{pp(chosen_int.low95_pp)}, {pp(chosen_int.high95_pp)}]。在相同配置与预算，A1 可靠中位数为 {pct(select_rand.random_median)}，{int(select_rand.random_ge_L)}/100 套达到或超过 L。原覆盖对应为 {pct(same_a1.random_median)} 和 {int(same_a1.random_ge_L)}/100。

这一页的 P1／90 来自原 quality_v1。后续严质量选参、冻结 P5／90 及 Test 补测见 [本轮实验入口]({entry})。

![各配置覆盖和每增加十个组合的边际贡献](coverage_and_increment.png)

## 规则怎么选

- G 按原 Discovery 排名顺序取下一条尚未入库的规则。L 和每一个随机种子各自维护三个群的原有排序。加入第 k 条时，优先选目前贡献最落后于其订单占比配额的群，三群平局按群号。取该群下一条尚未出现的规则。在共享主口径下，所有订单都能匹配最终池。限群原覆盖另报，重复身份只由首次进入清单的归属群服务。
- 两种预算单位各重跑一遍。有向去重以 rule_id 为单位。主口径以无向品类组合为单位，例如 A→B 和 B→A 只占一个名额。给定系统、配置与单位，20 档是 30 档的前 20 条，依此类推。覆盖增量是后档比前档多覆盖的订单占比，每单只算一次。
- 可靠覆盖沿用 quality_v1 的证据量、关联幅度、三品类增量和 BY 校正。每个系统把本次两种去重单位、所有配置与预算入选规则取并集做一次校正，再固定各条是否通过。该量是同一 Validation 期质量验收之后的回顾性共购覆盖。
- 核对了 {audit['verified_candidate_counts']:,} 个群范围与配置的候选数量及二／三品类拆分、{audit['verified_original_group_rule_lists']:,} 份旧名单的顺序。新选择只使用 Discovery 排名，所有新预算均达到设定的唯一数量。

## 覆盖曲线

主口径为无向组合去重、共享匹配。每格依次为 **G / L**。

### 原订单覆盖率

{grid("shared_covered_rate", pct)}

### 可靠订单覆盖率

{grid("reliable_covered_rate", pct)}

### 每多 10 条的可靠覆盖增量（百分点）

{grid("reliable_covered_gain_pp", pp, 20)}

### 80 到 100，拆成两步

{tail}

### A1 可靠覆盖达到或超过 L 的种子数

{randgrid}

## Validation 怎么选 P 和预算

以各自能达到的最高可靠覆盖为参考，G 和 L 分别计算少了多少百分点。给一个容许差距，例如 1 pp，找两边都满足的**最小预算**，同预算选两边最大短缺更小的配置。如果没有共同达标，就找最大短缺最小的一档。按单个 P 查看时，以该 P 自己的最高覆盖为参考。容许差距是此轮比较的工作标准，表并列 0.5／1／2 pp，也保留所有原始曲线。A1 用来解释分群对照表现，不按某格随机排名挑参数。

{decisions}

只看满预算 100 时的五套配置对照如下。限群应用若更重要，可从限群原覆盖另行比较。按同样 1 pp 规则应用于**限群原覆盖**，取 **{restricted_best.config}／{int(restricted_best.budget)}**，G／L 为 **{pct(restricted_best.G)}／{pct(restricted_best.L)}**，最大短缺 {restricted_best.max_shortfall_pp:.2f} pp。

{maxima}

### 为什么要补足实际规则数

下面对照原 P5／100 与新去重路径。两种新去重的方向条数都达到名额，无向去重同时保证组合数达到名额。

{dup}

## 文件

- [全系统逐种子曲线](all_systems.csv) · [G/L 曲线和逐档增量](global_local_curves.csv) · [A1、A2、S 比较](random_comparisons.csv)
- [配对差及置信区间](paired_intervals.csv) · [选参每格分数](selection_scores.csv) · [容许差距敏感性](selection_sensitivity.csv) · [限群原覆盖选参备查](restricted_selection_raw.csv)
- [G、L、A1 可复核规则次序](global_local_A1_rule_paths.csv.gz) · [核对记录](verification.json)

从仓库根目录用 python -B experiments/validation_budget_redesign/run.py --out experiments/validation_budget_redesign/results 复算，然后用 python -B experiments/validation_budget_redesign/report.py 生成图与报告。继续沿用 D 的冻结 Discovery 输入和本地 Validation 数据。
"""
    (output / "README.md").write_text(report, encoding="utf-8")
    print("Selected", cfg, b, state, pct(g.reliable_covered_rate), pct(l.reliable_covered_rate))
    print(decisions.splitlines()[2:5])
    print(tail)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "results"
    main(directory, Path(sys.argv[2]) if len(sys.argv) > 2 else root)
