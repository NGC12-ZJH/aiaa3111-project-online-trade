"""Build the decision report and verify that all three Validation routes completed."""
from pathlib import Path
import json

import numpy as np
import pandas as pd


def pct(x):
    return f"{x:.2%}"


def delta(x):
    return f"{x:+.2f}"


def interval(row):
    return f"[{row.low95_pp:+.2f}, {row.high95_pp:+.2f}]"


def table(headers, rows):
    return "\n".join([
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(map(str, row)) + " |" for row in rows),
    ])


def report(out):
    folder = out.parent
    ab, c = out / "route_ab", out / "route_c"
    audit = json.loads((out / "audit/source_and_checks.json").read_text(encoding="utf-8"))
    a_meta = json.loads((ab / "ab_manifest.json").read_text(encoding="utf-8"))
    c_meta = json.loads((c / "c_manifest.json").read_text(encoding="utf-8"))
    a = pd.read_csv(ab / "a_systems.csv")
    ar = pd.read_csv(ab / "a_random_summary.csv")
    ai = pd.read_csv(ab / "a_paired_intervals.csv")
    slot = pd.read_csv(ab / "b_slot5_systems.csv")
    sri = pd.read_csv(ab / "b_slot5_paired_intervals.csv")
    sr = pd.read_csv(ab / "b_slot5_random_summary.csv")
    policy = pd.read_csv(ab / "b_top5_policies.csv")
    greedy = pd.read_csv(ab / "b_greedy.csv")
    shrink = pd.read_csv(ab / "shrinkage_calibration.csv")
    cr = pd.read_csv(c / "c_aggregate.csv")
    cf = pd.read_csv(c / "c_folds.csv")
    train = pd.read_csv(c / "c_training_windows.csv")
    assert a_meta["seeds_for_each_RFM_variant"] >= 1
    assert c_meta["evaluation_cutoff_exclusive"] == audit["cutoff_exclusive"] == "2011-06-01"
    assert str(audit["maximum_date_in_analysis"]) < audit["cutoff_exclusive"]
    assert train.until_exclusive.max() <= "2011-05-01"
    assert cf.evaluation_until.max() == audit["cutoff_exclusive"]
    assert set(ar.random_n) == set(sr.random_n) == {a_meta["seeds_for_each_RFM_variant"]}
    assert a.loc[a.metric.isin(["raw", "quality_v1"]), "selected_rules"].eq(
        a.loc[a.metric.isin(["raw", "quality_v1"]), "budget"]).all()
    for data in (a, slot, cr, cf):
        assert (data.hits - data.baseline_hits).eq(data.net_orders).all()
        assert (data.new_hits - data.lost_hits).eq(data.net_orders).all()
        assert (data.hits <= data.orders).all()
    assert not ai.empty and not policy.empty and not cr.empty and not sri.empty

    budget = 100
    systems = {"global": "G", "frequency": "仅频次", "rfm": "纯 RFM", "rfm_form": "RFM＋形态",
               "rfm_form_country": "RFM＋形态＋地区", "rfm_form_cancel": "RFM＋形态＋历史取消"}
    a100 = a.loc[a.budget.eq(budget) & a.identity.eq("combination") & a.partition.eq("all")
                 & a.seed.isna()].set_index(["system", "metric"])
    ari = pd.read_csv(out / "audit/profile_stability.csv").groupby("system").ARI_to_full_profile_partition.median()
    r100 = ar.query("budget == 100 and identity == 'combination' and partition == 'all'").set_index(["real", "metric"])
    arows = []
    for name, label in systems.items():
        raw, quality = a100.loc[name, "raw"], a100.loc[name, "quality_v1"]
        if (name, "raw") in r100.index:
            r = r100.loc[name, "raw"]
            randset = f"{pct(r.A1_median)}，{int(r.A1_ge_L)}/{int(r.random_n)}"
        else:
            randset = "—"
        arows.append((label, pct(raw.rate), pct(quality.rate), pct(raw.customer_macro),
                      f"{int(quality.accepted_rules_all_validation)}/100", randset))
    atable = table(["系统", "原共购覆盖", "可靠覆盖", "顾客等权原覆盖", "验收规则数", "匹配 A1 原覆盖中位，达到或超过次数"], arows)
    aiv = ai.query("system == 'rfm_form' and reference == 'global' and partition == 'all' and metric == 'raw'").iloc[0]
    arfm = ai.query("system == 'rfm_form' and reference == 'rfm' and partition == 'all' and metric == 'raw'").iloc[0]
    aq = ai.query("system == 'rfm_form' and reference == 'global' and partition == 'all' and metric == 'quality_v1'").iloc[0]
    a_ninfer = "达到" if aiv.low95_pp > -1 else "未达到"
    a_seasonal = ai.query("system == 'rfm_form' and reference == 'global' and metric == 'raw'").set_index("partition")
    aq_random = r100.loc["rfm_form", "quality_v1"]
    l_seasonal = ar.query("budget == 100 and identity == 'combination' and real == 'rfm_form' and metric == 'raw'").set_index("partition")
    seasonal = pd.read_csv(ab / "a_season_monthly_rules.csv")
    seasonal["cohort"] = np.where(seasonal.month.lt("2010-12"), "早一年同月（回溯）", "Validation")
    s = seasonal.groupby(["cohort", "seasonal_exposed"], as_index=False).agg(
        rule_months=("rule_id", "size"), triggered=("antecedent_orders", "sum"), joint=("joint_orders", "sum"),
    )
    stab = table(["时期", "规则类型", "规则×月数", "触发次数", "合计 confidence"],
                 [(r.cohort, "含季节暴露品类" if r.seasonal_exposed else "其余",
                   r.rule_months, r.triggered, pct(r.joint / r.triggered)) for r in s.itertuples()])

    bnames = {
        "global_tail": "G 后续第 101–200 条", "global_added": "G 余池按 Added Value 重排",
        "rfm_form_added_shared": "L Added Value 共享", "rfm_form_gap_shared": "L 群内外差共享",
        "rfm_form_gap_restricted": "L 群内外差限群", "rfm_form_shrunk_m50": "L 收缩 m=50 限群",
    }
    bs = sri.query("partition == 'all'").set_index("system")
    rows = [(label, pct(bs.loc[name].rate), bs.loc[name].new_hits, bs.loc[name].lost_hits,
             delta(bs.loc[name].delta_pp), interval(bs.loc[name])) for name, label in bnames.items()]
    btable = table(["第五位来源", "整套 Hit@5", "新增命中", "丢失命中", "净变化 pp", "配对 95% 区间 pp"], rows)
    b0 = policy.query("partition == 'all' and system == 'global_rules_plus_global_pop'").iloc[0]
    bp = policy.query("partition == 'all' and system == 'global_popularity'").iloc[0]
    bl = policy.query("partition == 'all' and system == 'rfm_form_rules_plus_group_pop'").iloc[0]
    base_arms = sri.query("partition == 'all'")
    local_arms = base_arms.loc[base_arms.system.str.startswith("rfm_form_") &
                              ~base_arms.system.str.contains("_vs_")]
    best_local = local_arms.sort_values("delta_pp", ascending=False).iloc[0]
    b_pair = bs.loc["rfm_form_gap_shared_vs_global_tail"]
    br = sr.query("partition == 'all' and real == 'rfm_form_gap_shared'").iloc[0]
    greedy_table = greedy.loc[greedy.seed.isna()].pivot(index="system", columns="algorithm", values="rate")
    greed_a1 = greedy.query("system == 'A1_rfm_form' and algorithm == 'greedy'").rate
    assert len(greed_a1) == a_meta["seeds_for_each_RFM_variant"]
    gb = table(["系统", "早窗候选原排序", "在 Discovery 后段按边际覆盖选"],
               [(systems[k], pct(r.native), pct(r.greedy)) for k, r in greedy_table.iterrows()])
    brier = table(["收缩 m", "Validation Brier 越低越好", "规则×订单触发次数"],
                  [(r.m, f"{r.brier:.5f}", r.rule_order_trials) for r in shrink.itertuples()])

    cnames = {
        "cart_fixed": "静态当单形态", "hybrid_fixed": "静态历史＋当单形态",
        "hybrid_features_refreshed": "仅刷新历史特征", "global_rolling": "滚动 G",
        "cart_rolling": "滚动当单形态", "hybrid_rolling": "滚动历史＋当单形态",
    }
    cn = cr.query("segment == 'all' and reference == 'global_fixed'").set_index("system")
    crows = []
    for name, label in cnames.items():
        row = cn.loc[name]
        crows.append((label, pct(row.rate), row.routed, row.actually_replaced_fifth,
                      row.new_hits, row.lost_hits, delta(row.delta_pp), interval(row)))
    ctable = table(["方案", "Hit@5", "通过路由", "实际换第五位", "新增", "丢失", "净变化 pp", "配对 95% 区间 pp"], crows)
    segments = {
        "identified_first_order": "有 ID 的首单", "identified_no_history_at_origin": "窗口开始时无历史",
        "anonymous": "匿名", "profile_member": "最初 Profile 顾客",
    }
    cs = cr.query("system == 'cart_fixed' and reference == 'global_fixed'").set_index("segment")
    csplit = table(["分层", "可评订单", "路由通过", "实际换第五位", "Δ pp", "95% 区间 pp"],
                   [(name, cs.loc[key].orders, cs.loc[key].routed, cs.loc[key].actually_replaced_fifth,
                     delta(cs.loc[key].delta_pp), interval(cs.loc[key])) for key, name in segments.items()])
    crolling = cr.query("segment == 'all' and system == 'hybrid_rolling' and reference == 'global_rolling'").iloc[0]
    cap = cr.query("segment == 'all' and system == 'global_fixed'").iloc[0]
    cold = cs.loc["identified_first_order"]
    anon = cs.loc["anonymous"]
    c_recommend = cn.loc["hybrid_features_refreshed"]
    gates = table(
        ["路线", "当前最有解释力的比较", "本轮决策"],
        [
            ("A", f"形态共享 L 对 G {delta(aiv.delta_pp)} pp，冬春方向一致", "保留形态分群，作为共购发现主路线"),
            ("B", f"最佳 L 提升 {delta(best_local.delta_pp)} pp，G 尾段提升 {delta(bs.loc['global_tail'].delta_pp)} pp",
             "保留 G 尾段做固定第五位，L 留作候选互补和收缩诊断"),
            ("C", f"仅刷新画像的历史＋当单版对固定 G {delta(c_recommend.delta_pp)} pp；首单当单路由 {delta(cold.delta_pp)} pp",
             "保留较简单的固定规则＋历史特征刷新，独立报告冷启动；滚动重训作对照"),
        ],
    )

    markdown = f"""# 1122 重做实验 · 三条路线结果

本轮是 **Validation 和向前滚动回测**。使用的最新数据为 {audit['maximum_date_in_analysis']}，所有训练和评价时间都早于 2011‑06‑01。A、B 在固定历史顾客集合比较，C 将匿名与无历史订单纳入。采用冻结 L2 分类、P5 资格门槛和主预算 100。A 另报告 20／50／100 预算与两种去重单位。基于清洗快照独立复跑，采购形态的特征配方和名额策略由本方案实现。

## 三条路线的决定

{gates}

这些决定只反映本轮前置实验；冻结 Test 留在本轮之外。

## 路线 A · 规则发现

复现检查得到原版 Validation 的 G 3,640 单、L 限群 3,057 单、L 共享 3,425 单。下表为新版在同一批 {a_meta['validation_orders']:,} 张订单上的 **无向组合去重、补满 100、共享匹配**。全局和分群采用相同容量。可靠覆盖按当前 Validation 质量验收，按每套池做 BY 校正。分时段的可靠覆盖是该已验收池的覆盖切片。

{atable}

形态分群相对纯 RFM 的原覆盖差是 **{delta(arfm.delta_pp)} pp**，95% 区间 {interval(arfm)}。相对 G 的原覆盖差是 **{delta(aiv.delta_pp)} pp**，区间 {interval(aiv)}，以方案示例的 −1 pp 作为预先给定的非劣界值时**{a_ninfer}**。相对 G 的可靠覆盖差为 **{delta(aq.delta_pp)} pp**，区间 {interval(aq)}。频次分档切点为 {a_meta['frequency_split_inclusive']} 次，按照前置频次区间做 A1 的每套标签置换。纯 RFM 与形态版 20 次 80% Profile 子样本的 ARI 中位数分别为 {ari['rfm']:.3f}、{ari['rfm_form']:.3f}。

冬季、春季相对 G 的原覆盖差分别是 **{delta(a_seasonal.loc['winter'].delta_pp)}** 和 **{delta(a_seasonal.loc['spring'].delta_pp)} pp**。对应的形态 A1 达到真实分群的次数分别是 **{int(l_seasonal.loc['winter'].A1_ge_L)}/100** 和 **{int(l_seasonal.loc['spring'].A1_ge_L)}/100**。全期可靠覆盖的 A1 中位为 **{pct(aq_random.A1_median)}**，达到或超过 L 的为 **{int(aq_random.A1_ge_L)}/100**。加入地区或历史取消后，全期共享覆盖未超过单用形态的方案。

### 季节诊断

Discovery 行中季节标签占比至少 20% 的 L2 类别定义为季节暴露品类。下面按训练期冻结的 100 条全局规则分层。合计 confidence 用所有规则×月的联合次数除以前件次数。同一订单触发不同规则会贡献多次，这是规则效应诊断。

{stab}

月别表记录每条规则的前件次数、后件基础率和 Added Value。早一年同月份是对固定规则的回溯诊断，先观察置信度变化是否集中在季节规则。两个周期不足以把季节、货品可用性与时间漂移彻底分开。地区和取消字段是历史特征消融，取消率用历史取消发票占可识别发票比例做代理。

## 路线 B · 全局主池与固定 Slot‑5

在 {a_meta['masked_orders']:,} 张可遮挡订单里，纯全局热门的 Hit@5 为 **{pct(bp.rate)}**，G 规则优先＋全局热门为 **{pct(b0.rate)}**，形态 L＋本群热门为 **{pct(bl.rate)}**。下面保留 G 混合方案的前四位，只让候选接管第五位。无新候选时保留原第五位。所有可遮挡订单均进入分母。

{btable}

按群内外差选出的共享 L 相对 G 尾段接管的差是 **{delta(b_pair.delta_pp)} pp**，区间 {interval(b_pair)}。它相对原 G 的净变化为 {delta(br.L)} pp，A1 中位数为 {delta(br.A1_median)} pp，{int(br.A1_ge_L)}/{int(br.random_n)} 套随机系统达到或超过真实分群。各局部方案里点估计最高的是 **{best_local.system}**，相对原 G 为 {delta(best_local.delta_pp)} pp，区间 {interval(best_local)}。多方案中的最高点估计供诊断，是否达到 +0.5 pp、配对区间下限高于零以及超过 G 尾段与 A1，需要逐项核对。

### 收缩与边际贪心消融

收缩只改变同一批局部 Added Value 候选的得分。Brier 在原所属群的实际触发事件上计算。效应的校准改善与 Top‑5 净命中分开看。

{brier}

贪心候选取 2010‑06 至 2010‑09，训练侧优化用 2010‑10 至 2010‑11 的增量覆盖。两种方法使用相同资格、无向组合与实际预算。贪心在每群前 500 条候选及旧基线已选候选构成的前沿上工作。下表为随后 Validation 原覆盖。

{gb}

同样跑贪心的 A1 原覆盖中位数为 **{pct(greed_a1.median())}**，{int(greed_a1.ge(greedy_table.loc["rfm_form","greedy"]).sum())}/{len(greed_a1)} 套达到或超过形态 L。贪心这里优化的是原共购覆盖。

## 路线 C · 只看可见购物篮的路由与滚动更新

扫描 {c_meta['all_pretest_validation_orders']:,} 张 Validation 订单，其中 {c_meta['maskable_before_common_top5_check']:,} 张能做遮挡。统一排除有系统无法推荐五项的 {c_meta['excluded_fewer_than_5_candidates']:,} 张后，固定 Top‑5 对照保留 {c_meta['masked_eval_orders']:,} 张。模型只从可见商品行计算件数、SKU 数及价格带。每个回测窗口只用起点以前的数据拟合路由和规则。可见篮选不出有用候选时保留全局第 5 项。基准固定 G＋全局热门 Hit@5 为 **{pct(cap.rate)}**。

{ctable}

上表统一与固定 G 比。要剥离全局滚动本身的变化，需要同滚动 G 对照。滚动历史＋当单形态相对滚动 G 的 Hit@5 净变化为 **{delta(crolling.delta_pp)} pp**，95% 区间 {interval(crolling)}。下面以固定当单形态模型展开看冷启动。首单是数据中首次观察到的有效订单。「窗口开始时无历史」还可包含该窗口内的后续订单，分层可能重合。

{csplit}

有 ID 的首单里，实际换第五位 {cold.actually_replaced_fifth} 单，净命中 {cold.net_orders:+} 单；匿名订单净命中 {anon.net_orders:+} 单。可路由率和命中收益分开评价。全局兜底给所有**可遮挡订单**都能补齐五项，路由是否激活、是否找到候选、是否真的改变第 5 项各有计数。三个回测窗口及各自训练结束时间见 C 附表。

## 核验与复现

- 原版覆盖三项核验通过。逐种子保留了 100 套匹配 RFM 和 100 套匹配形态分群的 A1 口径。200 次置换的频数分层一致。遮挡后改动目标商品的数量和单价，在抽样订单上不影响可见特征。Slot‑5 位图与逐单复算逐项核对。结果表检查了配对新增减丢失等于净变化，日期截止早于原 Test。
- 这是对课程历史数据的扩展回测。完整采购形态重跑的原始清单未放在实验目录，不能据此判定配方完全相同。C 用档内历史快照并以窗口为单位刷新，不主张结账时的可见状态已在线验证。
- 复算使用同级 repository 中的品类标签、冻结 A 数据快照和共用指标／规则工具。依赖 Python、pandas、NumPy、scikit-learn、SciPy 和 threadpoolctl。在 1122 文件夹执行 python -B run.py 即可。可选 --route ab、--route c、--route audit 分开复算，--cache 可指定临时缓存路径。

### 结果入口

- A · [指标全集](results/route_ab/a_systems.csv) · [频次匹配随机对照](results/route_ab/a_random_summary.csv) · [配对区间](results/route_ab/a_paired_intervals.csv) · [月度季节证据](results/route_ab/a_season_monthly_rules.csv) · [采购形态画像](results/audit/profile_groups.csv)
- B · [推荐策略](results/route_ab/b_top5_policies.csv) · [固定 Slot‑5](results/route_ab/b_slot5_paired_intervals.csv) · [随机对照](results/route_ab/b_slot5_random_summary.csv) · [收缩](results/route_ab/shrinkage_calibration.csv) · [贪心](results/route_ab/b_greedy.csv)
- C · [总体和冷启动分层](results/route_c/c_aggregate.csv) · [逐窗口](results/route_c/c_folds.csv) · [训练窗口](results/route_c/c_training_windows.csv)
- [输入和核验记录](results/audit/source_and_checks.json)
"""
    (folder / "1122_三路线结果.md").write_text(markdown, encoding="utf-8")
    print(f"All three routes reconciled and reported in {folder / '1122_三路线结果.md'}", flush=True)
