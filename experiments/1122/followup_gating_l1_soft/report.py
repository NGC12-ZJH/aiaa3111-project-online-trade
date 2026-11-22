"""Summarize the three follow-up experiments and check paired counts."""
from pathlib import Path
import json
import sys

import pandas as pd


def pct(x):
    return f"{x:.2%}"


def pp(x):
    return f"{x:+.2f}"


def ci(row):
    return f"[{pp(row.low95_pp)}, {pp(row.high95_pp)}]"


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |",
                      *["| " + " | ".join(map(str, row)) + " |" for row in rows]])


def main(output):
    info = json.loads((output / "verification.json").read_text(encoding="utf-8"))
    f = pd.read_csv(output / "fallback.csv")
    g = pd.read_csv(output / "slot5.csv")
    o = pd.read_csv(output / "slot5_source.csv")
    marginal = pd.read_csv(output / "slot5_marginal_gate.csv")
    c = pd.read_csv(output / "soft_late.csv")
    assert info["source_maximum_date"] < info["evaluation_end_exclusive"] == "2011-06-01"
    for frame in (f, g, o, c, marginal):
        assert ((frame.new_hits - frame.lost_hits) == frame.net_orders).all()
        assert ((frame.hits - frame.baseline_hits) == frame.net_orders).all()
    selection = info["conditional_fallback_selected_early"]
    f_rollup = f.query("window == 'late'").set_index(["fallback", "policy"])
    fn = {"global_pop": "全站热门", "l1_pop": "L1 条件热门", "form_l1_pop": "采购形态 × L1 条件热门"}
    fallback_table = table(
        ["兜底榜单", "只用热门 Hit@5", "G＋热门 Hit@5", "G＋热门净变化 pp", "95% 区间 pp"],
        [(label, pct(f_rollup.loc[(key, "pop_only"), "rate"]), pct(f_rollup.loc[(key, "rules_plus_pop"), "rate"]),
          pp(f_rollup.loc[(key, "rules_plus_pop"), "delta_pp"]), ci(f_rollup.loc[(key, "rules_plus_pop")]))
         for key, label in fn.items()],
    )
    f_slice = f.query("policy == 'rules_plus_pop' and window in ['late_same_l1', 'late_cross_l1'] and fallback != 'global_pop'")
    slice_table = table(["兜底", "遮挡品类与主 L1", "订单数", "Hit@5 净变化 pp", "95% 区间 pp"],
                        [(fn[r.fallback], "同大类" if r.window == "late_same_l1" else "跨大类", r.orders,
                          pp(r.delta_pp), ci(r)) for r in f_slice.itertuples()])

    g_late = g.query("window == 'late'").set_index(["candidate", "fallback", "scenario"])
    marginal_g = marginal.query("candidate == 'G_tail' and fallback == 'global_pop'").iloc[0]
    uncond = o.query("candidate == 'L_gap_shared' and scenario == 'unconditional'")
    assert uncond.new_hits.sum() == 94 and uncond.lost_hits.sum() == 81
    origin_table = table(["原第五位来源", "全期新增", "全期丢失"], [
        ("G 规则" if name == "original_fifth_rule" else "全站热门兜底", hits.new_hits.sum(), hits.lost_hits.sum())
        for name, hits in uncond.groupby("source")])
    gn = {"G_tail": "G 尾段", "L_gap_shared": "L 群内外差 · 共享", "L_shrunk_restricted": "L 收缩 · 限群"}
    gate_rows = []
    for candidate, cn in gn.items():
        for fallback in ("global_pop", selection):
            un = g_late.loc[candidate, fallback, "unconditional"]
            sel = g_late.loc[candidate, fallback, "selected_gate"]
            chosen = {"pop_only": "仅热门", "weak": f"热门或 G confidence < {sel.threshold:g}",
                      "margin": f"热门或候选高 {sel.threshold:g}", "keep": "保留原第五位"}[sel.gate]
            gate_rows.append((cn, fn[fallback], f"{un.new_hits}/{un.lost_hits}/{un.net_orders:+}",
                              chosen, f"{sel.new_hits}/{sel.lost_hits}/{sel.net_orders:+}", pct(sel.rate),
                              pp(sel.delta_pp), ci(sel), pp(sel.delta_pp_vs_original_global)))
    gate_table = table(["候选", "兜底", "无门控 新中/丢失/净增", "前段选定门控", "有门控 新中/丢失/净增",
                        "有门控 Hit@5", "相对同兜底的原第五位 pp", "95% 区间 pp", "相对原 G＋全站热门 pp"], gate_rows)

    c_show = c.query("variant == 'soft_selected_early' and reference == 'hard_router'")
    cs = {"all": "全部", "identified_first_order": "有 ID 首单", "anonymous": "匿名",
          "near_boundary": "两中心距离接近"}
    soft_table = table(["路由", "订单", "单数", "前段选定温度", "软路由 Hit@5", "增/损/净",
                        "相对硬路由 pp", "95% 区间 pp"], [
        ("当单形态" if r.mode == "cart" else "历史＋当单", cs[r.stratum], r.orders,
         r.temperature, pct(r.rate), f"{r.new_hits}/{r.lost_hits}/{r.net_orders:+}",
         pp(r.delta_pp), ci(r)) for r in c_show.itertuples()
    ])
    retain = g_late.loc["G_tail", "global_pop", "unconditional"]
    original = f_rollup.loc["global_pop", "rules_plus_pop"]
    combo = g.query("window == 'late' and scenario == 'selected_gate'").sort_values("hits", ascending=False).iloc[0]
    report = f"""# 1122 三项追加实验结果

只用原 Test 开始前的数据。Discovery 截至 2010‑11‑30。2010‑12 至 2011‑02 用于挑门控、条件榜单和软路由温度，2011‑03 至 2011‑05 用于对照。完整原 Validation 已在前序实验看过，本轮属于同数据的分时段探索。A/B 后段共 {info['ab_late_masked']:,} 张固定 Profile 顾客遮挡订单；C 后段共 {info['c_late_masked']:,} 张，包含首单与匿名。比较时保持原遮挡目标和五个位置。

## 1．第五位门控

同一批 4,311 张原遮挡单上，无条件共享 L 的 94 单新增和 81 单丢失可按原第五位拆开。这里是全期诊断，用来查来源。

{origin_table}

后段原 G＋全站热门是 **{pct(original.rate)}**。门控预设仅热门、热门加低置信度、热门加相对分差，也允许保持原位。对每个候选与兜底组合，只在前段选门控，后段直接应用。置信度是 Discovery 的规则共购置信度或已收缩的分数。共享 L 使用选中该规则的来源群置信度作为分数。

{gate_table}

第五位的变化与同一个兜底下的原第五位配对；最后一列用共同的原 G＋全站热门作参照。作为强基线，原兜底＋无门控 G 尾段在后段达到 **{pct(retain.rate)}**；三套兜底与门控的交叉组合里，后段点估计最高的是 **{gn[combo.candidate]}＋{fn[combo.fallback]}，{pct(combo.rate)}**。这行仅用于结果诊断。用全站兜底时，同一批 G 尾段加入门控相对无门控为 **{pp(marginal_g.delta_pp)} pp**，配对 95% 区间 {ci(marginal_g)}。此区间直接衡量门控的边际贡献。前段选定的兜底和门控才用于主要比较；CSV 也留存 L1 条件榜单的交叉结果。

## 2．L1 条件热门

以可见篮中不同 L2 的所属 L1 多数票定义主 L1，平局按固定编号。用同样遮挡方式在 Discovery 统计目标 L2。候选仍来自全部已知 L2，先排除可见品类，稀疏上下文向全站或 L1 榜单平滑回退。后段结果如下。

{fallback_table}

前段在两个条件榜单中选的是 **{fn[selection]}**。跨大类与同大类拆分使用实际遮挡目标，仅作评价切片，推荐时不会读取目标。

{slice_table}

## 3．软路由

保持 1122 原有的固定 K-means、资格半径、群候选池和 G 混合前四项。硬路由基线使用最近群；软路由对三个群的平方距离做 Softmax。不同群只保留指向同一品类的最强规则，再按距离权重融合。归一化温度从预设的 0.15、0.4、1、2.5 里只用前段选择。群边界以最近两个中心距离相对差不超过 15% 定义，先用可见信息确定。资格半径外仍回退，软路由与原硬路由没有同时改变规则池。温度为 0 时逐订单复现原硬路由。

{soft_table}

是否改善看同批订单的新增减丢失。首单、匿名和边界标签可能重叠，分层区间作为诊断。

## 复算

- [热门兜底及同／跨大类拆分](results/fallback.csv)
- [第五位门控前段筛选](results/gate_tuning_early.csv) · [后段门控结果](results/slot5.csv) · [原第五位来源](results/slot5_source.csv) · [门控相对无门控的配对差](results/slot5_marginal_gate.csv)
- [软路由温度前段比较](results/soft_tuning_early.csv) · [软路由后段对照](results/soft_late.csv)
- [核对记录](results/verification.json)

在本目录运行 python -B run.py，然后运行 python -B report.py。输入和候选复用上一级 1122 及同级主仓库的预先冻结数据。
"""
    (output.parent / "三项追加实验结果.md").write_text(report, encoding="utf-8")
    print(fallback_table)
    print(origin_table)
    print(gate_table)
    print(soft_table)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "results")
