"""Report the frozen P5/90 historical Test follow-up."""
import hashlib
import json
from pathlib import Path
import re
import sys

import pandas as pd


def pct(v):
    return f"{v:.2%}"


def delta(v):
    return f"{100*v:+.2f}"


def main(folder):
    p=folder/"results"
    raw=(folder/"freeze.json").read_bytes()
    freeze=json.loads(raw)
    audit=json.loads((p/"verification.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(raw).hexdigest()==audit["freeze_sha256"]
    s=pd.read_csv(p/"system_metrics.csv")
    a=pd.read_csv(p/"a1_comparisons.csv").set_index("metric")
    i=pd.read_csv(p/"paired_intervals.csv").query("contrast == 'L_minus_G'").set_index(["quality","metric"])
    overlap=pd.read_csv(p/"coverage_overlap.csv").set_index("quality")
    detail=pd.read_csv(p/"GL_rule_quality.csv")
    gl=s.loc[s.control.eq("GL")].set_index("method")
    assert len(s)==102 and len(detail)==180 and s.unique_combinations.eq(90).all()
    assert s.strict_orders.le(s.base_orders).all() and s.base_orders.le(s.raw_orders).all()
    for k in ("raw","base","strict"):
        q=overlap.loc[k]
        assert q.both+q.G_only==gl.loc["G",k+"_orders"]
        assert q.both+q.L_only==gl.loc["L",k+"_orders"]
        assert abs(a.loc[k+"_coverage","L_minus_G"]-i.loc[k,"order"].estimate)<1e-10

    title={"raw":"原始订单覆盖","strict":"严格可靠订单覆盖","base":"原 quality_v1 可靠订单覆盖"}
    table=["| 指标 | G | L | L−G，配对 95% 区间 pp | A1 中位 | A1 范围 | A1 ≥ L |",
           "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for k in ("raw","strict","base"):
        b,c=a.loc[k+"_coverage"],i.loc[k,"order"]
        table.append(f"| {title[k]} | {pct(b.G)} | {pct(b.L)} | {delta(c.estimate)} [{delta(c.low95)}, {delta(c.high95)}] | {pct(b.A1_median)} | {pct(b.A1_min)}–{pct(b.A1_max)} | {b.A1_ge_L:.0f}/100 |")
    differences="\n".join(table)
    sample=audit["sample"]
    fb=audit["fallback"]
    macro=i.loc["strict","customer_macro"]
    overlap_rows=["| 指标 | 两边都覆盖 | 只被 G 覆盖 | 只被 L 覆盖 | 任一覆盖 |",
                  "| --- | ---: | ---: | ---: | ---: |"]
    for k in ("raw","strict","base"):
        rr=overlap.loc[k]
        overlap_rows.append(f"| {title[k]} | {rr.both:,} | {rr.G_only:,} | {rr.L_only:,} | {rr.union:,} |")
    overlap_table="\n".join(overlap_rows)
    g,l=gl.loc["G"],gl.loc["L"]
    report=f"""# Test 补充评价 · P5／90 去重共享

在本轮加载 Test 前，冻结于 {freeze['recorded_at']}。G、L 和 100 套 A1 各有 90 个不同的无向品类组合，规则来源、归属与所保留的方向来自冻结 Discovery 清单，所有主样本订单均可匹配对应系统的共享规则。本轮沿用已对原 P5／100 限群方案公布结果的历史 Test 时段，作为新口径的补充评价。

Test 时段为 2011‑06‑01 至 2011‑12‑01（不含结束日）。主比较纳入 **{sample['eligible_baskets']:,} 张订单、{sample['eligible_customers']:,} 名历史顾客**，占全部 {sample['all_valid_baskets']:,} 单的 **{pct(sample['eligible_share'])}**。其余 {fb['orders']:,} 单用 G90 全局回退，共购覆盖 **{fb['G_hits']:,} 单（{pct(fb['G_coverage'])}）**。

## 订单覆盖

{differences}

严格可靠覆盖使用 quality_v1 的证据量、Lift、三品类增量与统计要求，Added Value 的最低要求为 10 个百分点。原 quality_v1 对照将该门槛设为 5 个百分点。每个系统以冻结的 90 个方向为一个 BY 校正家族，两套质量标准共用相同 q 值。这里的可靠覆盖是在 Test 内验收后由合格规则贡献的完整共购，清单本身不重新选择。

严格质量通过条数为 **G {g.strict_passed}/90、L {l.strict_passed}/90**。原 quality_v1 对应 **G {g.base_passed}/90、L {l.base_passed}/90**。严格可靠顾客等权覆盖为 **G {pct(g.strict_customer_macro)}、L {pct(l.strict_customer_macro)}**，L−G {delta(macro.estimate)} pp，配对 95% 区间 [{delta(macro.low95)}, {delta(macro.high95)}]。

### 同一批订单上，两边覆盖哪些单

{overlap_table}

A1 的种子分布以固定真实 L 为对照，达到或超过包括并列。G/L 的区间按同一批历史顾客配对重抽 2,000 次。Validation 的密集网格曾用跨配置和预算的大校正家族，本轮只检验已冻的 P5／90，质量通过率的时间比较需要注明这个区别。

## 文件

- [冻结协议](freeze.json) · [102 套冻结规则清单](frozen_rule_lists.csv)
- [逐系统与逐种子指标](results/system_metrics.csv) · [A1 对照](results/a1_comparisons.csv) · [顾客配对区间](results/paired_intervals.csv)
- [覆盖重叠](results/coverage_overlap.csv) · [G/L 逐规则质量](results/GL_rule_quality.csv) · [样本核验](results/verification.json)
"""
    assert all((folder/x).is_file() for x in re.findall(r"\]\(([^)]+)\)",report))
    (folder/"README.md").write_text(report,encoding="utf-8")
    for table in (differences,overlap_table):
        print(table)
    print("Pass",g.strict_passed,l.strict_passed,"of 90; fallback",fb)


if __name__=="__main__":
    main(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent)
