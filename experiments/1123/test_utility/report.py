"""Create the report from the frozen recommendation replays."""

import argparse
import json
from pathlib import Path

import pandas as pd


HERE = Path(__file__).resolve().parent
CMP = {
    "l1": ("L1 条件兜底", "G120＋全局热门", "G120＋L1 热门"),
    "pool": ("扩大全局规则池", "融合 G100＋L1", "融合 G200＋L1"),
    "ranking_diagnostic": ("排序诊断", "规则优先 G100＋L1", "融合 G100＋L1"),
    "sku_asof": ("顾客此前购买历史", "品类内热门 SKU", "订单前个人历史 SKU"),
    "sku_frozen": ("冻结历史敏感性", "品类内热门 SKU", "Discovery 截止个人历史 SKU"),
    "sku_update_diagnostic": ("历史更新诊断", "Discovery 截止个人历史 SKU", "订单前个人历史 SKU"),
}
SAMPLES = {"all": "全店", "profile": "Profile 老顾客", "identified_non_profile": "有 ID 的非 Profile 顾客",
           "anonymous": "匿名", "identified": "全部有 ID"}


def table(fields, rows):
    return "\n".join(["| " + " | ".join(fields) + " |", "| " + " | ".join(["---"] * len(fields)) + " |",
                      *["| " + " | ".join(map(str, row)) + " |" for row in rows]])


def summarize(out):
    comparisons = pd.read_csv(out / "comparisons.csv")
    audit = json.loads((out / "audit.json").read_text(encoding="utf-8"))
    sample, history = audit["sample"], audit["sku_history"]
    sections = [
        "# 1123 三项推荐补测 · Test 结果",
        f"历史 Test 补测。全店共 {sample['all']:,} 单，其中 **{sample['maskable']:,}** 单可遮挡。"
        f"SKU 主比较使用其中 **{history['identified_orders']:,}** 张有顾客 ID 的订单。"
        f"原 1123 的 G120＋全局热门命中数复现为 **{audit['original_G120_hit_count_reproduced']:,}** 单。",
        "## 主比较与诊断",
    ]
    rows = []
    for r in comparisons.loc[comparisons.primary_sample].itertuples():
        label, left, right = CMP[r.metric]
        rows.append((label, left, right, f"{r.orders:,}", f"{r.baseline_hit5:.2%} → {r.treatment_hit5:.2%}",
                     f"{r.new_hits:,}／{r.lost_hits:,}／{r.net_hits:+,}",
                     f"{r.delta_pp:+.2f} [{r.low95_pp:+.2f}, {r.high95_pp:+.2f}]"))
    sections += [table(["比较", "基线", "对照方案", "订单", "Hit@5", "新中／丢失／净变化（单）",
                        "差值（pp）及配对 95% 区间"], rows),
                 "L1 兜底与扩池看品类 Hit@5。个人历史看商品 Hit@5，两个 SKU 方案共享同一份融合 G200 品类推荐。",
                 f"有 ID 的订单中，**{history['identified_orders_using_history']:,}** 单至少一个推荐品类"
                 f"能用个人历史选 SKU，**{history['identified_orders_all_popular_fallback']:,}** 单的推荐品类全部回退热门。",
                 "## 分样本结果"]
    core = comparisons.loc[comparisons.metric.isin(["l1", "pool", "sku_asof"])]
    sections.append(table(["比较", "订单范围", "订单", "基线 Hit@5", "处理后 Hit@5", "净增单数"], [
        (CMP[r.metric][0], SAMPLES[r.sample], f"{r.orders:,}", f"{r.baseline_hit5:.2%}",
         f"{r.treatment_hit5:.2%}", f"{r.net_hits:+,}")
        for r in core.itertuples()
    ]))
    sections.append("[计算协议](../README.md) · [冻结记录](freeze.json) · [完整对照表](comparisons.csv) · [样本核验](audit.json)")
    if (out / "runner_recovery.json").exists():
        sections.append("首次执行在旧融合接口的兼容字段处中止。修复后使用原冻结清单完成评价。"
                        "补上的先验字段在本次共享全局融合中权重为零。 [运行修复记录](runner_recovery.json)")
    (out / "README.md").write_text("\n\n".join(sections) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path, nargs="?", default=HERE / "results")
    summarize(parser.parse_args().out)
