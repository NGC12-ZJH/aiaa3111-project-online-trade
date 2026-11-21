"""Verify the saved Test output and render its Chinese results summary."""
import io
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from online_trade.evaluation.validation import sha


def verify_coverage(spec, metrics):
    core = ROOT/'data/processed/local/D_validation/core'
    source = pd.read_csv(io.BytesIO(subprocess.check_output([
        'git','show', f"{spec['a_snapshot_commit']}:data/processed/A_data_preparation/baskets.csv.gz"
    ], cwd=ROOT)), compression='gzip', dtype=str, keep_default_na=False)
    source = source.loc[source.split.eq('test') & source.is_eligible_for_main_comparison.eq('1')]
    taxonomy = pd.read_csv(core/'inputs/item_taxonomy_v1.csv',dtype=str).set_index('stock_code').l2_id.to_dict()
    baskets = [(r.customer_id, {taxonomy[x] for x in json.loads(r.items) if taxonomy[x]!='other'}) for r in source.itertuples()]
    groups = pd.read_csv(core/'inputs/customer_clusters.csv',dtype=str).set_index('customer_id').cluster_id.to_dict()
    random = pd.read_csv(core/'inputs/random_groups_A1_profile_frequency.csv',dtype=str)
    a1 = random.loc[random.seed.eq('1000')].set_index('customer_id').random_group_id.to_dict()
    checked = 0
    for control,seed in [('GL',''),('A1','1000')]:
        rules = pd.read_csv(core/f'selected_rules/P5_{control}.csv.gz',dtype=str,keep_default_na=False)
        for (budget,method),selected in rules.loc[rules.seed.eq(seed)].groupby(['budget','method']):
            mapping = a1 if method=='R' else groups
            by_group = {}
            combined = []
            for r in selected.itertuples():
                rule = set(json.loads(r.antecedent)) | set(json.loads(r.consequent))
                by_group.setdefault(r.group_id,[]).append(rule)
                combined.append(rule)
            for flow in ['restricted','shared']:
                hits = sum(any(rule <= basket for rule in (combined if flow=='shared' or method=='G' else by_group[mapping[c]])) for c,basket in baskets)
                match = metrics.loc[metrics.budget.eq(int(budget)) & metrics.method.eq(method) & metrics.control.eq(control)
                                    & metrics.seed.eq(seed) & metrics.flow.eq(flow)]
                assert len(match)==1 and hits==match.iloc[0].covered_orders
                checked += 1
    return checked


def main():
    folder = ROOT/'results/tables/test'
    spec = json.loads((ROOT/'configs/test_frozen.json').read_text(encoding='utf-8'))
    manifest = json.loads((folder/'run_manifest.json').read_text(encoding='utf-8'))
    assert sha(ROOT/'configs/test_frozen.json')==manifest['freeze_sha256']
    for name,digest in manifest['output_hashes'].items():
        assert sha(folder/name)==digest,name
    raw = pd.read_csv(folder/'system_metrics.csv',dtype={'seed':str},keep_default_na=False)
    checked = verify_coverage(spec,raw)
    rc = pd.read_csv(folder/'random_comparisons.csv')
    ci = pd.read_csv(folder/'paired_customer_intervals.csv')
    quality = pd.read_csv(folder/'random_quality_comparisons.csv')
    shares = pd.read_csv(folder/'system_quality.csv')
    audit = manifest['sample']
    p3 = pd.read_csv(folder/'P3_hybrid_exploratory.csv').iloc[0]
    summary = []
    for flow in ['restricted','shared']:
        for budget in spec['budgets']:
            r = rc.query("flow==@flow and budget==@budget and control=='A1' and metric=='coverage'").iloc[0]
            c = ci.query("flow==@flow and budget==@budget and contrast=='L_minus_G' and metric=='order'").iloc[0]
            q = quality.query("flow==@flow and budget==@budget and control=='A1' and metric=='quality_coverage'").iloc[0]
            summary.append(f'| {flow} | {budget} | {r.G:.2%} | {r.L:.2%} | {r.random_median:.2%} | {int(r.random_ge_L)}/100 | {100*c.estimate:+.2f} [{100*c.low95:+.2f}, {100*c.high95:+.2f}] | {q.G:.2%} | {q.L:.2%} |')
    r = rc.query("flow=='restricted' and budget==100 and control=='A1' and metric=='coverage'").iloc[0]
    c = ci.query("flow=='restricted' and budget==100 and contrast=='L_minus_G' and metric=='customer_macro'").iloc[0]
    q = shares.query("flow=='restricted' and budget==100 and control=='GL'").set_index('method')
    fallback = pd.read_csv(folder/'non_profile_global_fallback.csv').query("budget==100 and scope=='all'").iloc[0]
    content = f'''# D 最终 Test 评价

冻结提交 `{manifest['freeze_commit'][:7]}`。采用 P5，主预算 100，限群使用，A1 为主随机对照。P5 的 20／50／100 预算曲线及共享模式一并报告。按 [冻结协议](../configs/test_frozen.json) 沿用 Discovery 规则清单、排名、群标签及配额。

Test 期为 2011-06-01 至 2011-12-01（不含末日）。全部有效订单 {audit['all_valid_baskets']:,} 张，主比较纳入 {audit['eligible_baskets']:,} 张、{audit['eligible_customers']:,} 名历史顾客，占 {audit['eligible_share']:.2%}。其余 {audit['non_profile_baskets']:,} 单另行做全局回退，100 条规则覆盖 {int(fallback.hits):,} 单（{fallback.coverage:.2%}）；含匿名订单 {audit['anonymous_baskets']:,} 张。主比较保留映射后的空篮与单品类篮。

| 使用方式 | 总预算 | G 原覆盖 | L 原覆盖 | A1 原覆盖中位数 | A1 原覆盖 ≥ L | L−G 百分点 [配对95%区间] | G 可靠覆盖 | L 可靠覆盖 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(summary)}

主比较下，L 相对 G 的顾客等权覆盖差为 {100*c.estimate:+.2f} 个百分点，配对95%区间 [{100*c.low95:+.2f}, {100*c.high95:+.2f}]。L 原覆盖相对 A1 中位数高出 {100*(r.L-r.random_median):+.2f} 个百分点，A1 范围为 {r.random_min:.2%}–{r.random_max:.2%}。随机范围按固定种子汇总，配对区间按顾客重抽 2,000 次，两者含义不同。

主预算下，G 和 L 通过共同质量验收的名额分别为 {q.loc['G','accepted_slot_share']:.0%}、{q.loc['L','accepted_slot_share']:.0%}。可靠覆盖使用同一期质量验收和订单覆盖，表示回顾性共购保持。`quality_v1` 在初次 Validation 后制定，在 Test 前已冻结。Test 的 BY 校正族只含冻结后所评价的 P5 规则，Validation 的校正族包含五套配置，两期的校正通过率口径有此区别。

P3 合并方案作为探索性补充。合并后 {int(p3.K)} 条规则，Test 共购覆盖为 {p3.hybrid_coverage:.2%}，同预算全局为 {p3.global_K_coverage:.2%}，差 {100*p3.difference:+.2f} 个百分点，逐项95%区间 [{100*p3.low95:+.2f}, {100*p3.high95:+.2f}]。仍缺少随机合并基线。

所有主比较使用相同订单与系统总名额。限群时每名顾客可用规则数取决于群配额，逐系统表已记录。覆盖度量完整共购，没有后件遮蔽预测。规则质量通过情况和随机对照均需按各自定义解读。

原始汇总、逐种子结果、顾客配对区间和质量结果在 [Test 输出](../results/tables/test/)；样本口径和文件哈希见 [运行记录](../results/tables/test/run_manifest.json)。原覆盖与质量计算各自重算的覆盖在全部 {len(raw):,} 行一致，另有 {checked} 组 G/L 和 A1 固定种子的覆盖通过逐订单独立核对。
'''
    (ROOT/'docs/test_results.md').write_bytes(content.encode('utf-8'))
    print(content)


if __name__=='__main__':
    main()
