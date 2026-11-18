"""Render comparison-only Validation tables and a standalone HTML report."""
from pathlib import Path
import html
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/tables/validation'
DOC = ROOT / 'docs/validation_results.md'


def md_table(df):
    cols = list(df.columns)
    return '| ' + ' | '.join(cols) + ' |\n|' + '|'.join(['---'] * len(cols)) + '|\n' + '\n'.join('| ' + ' | '.join(map(str, row)) + ' |' for row in df.itertuples(index=False, name=None))


def main():
    metrics = pd.read_csv(OUT / 'system_metrics.csv')
    comp = pd.read_csv(OUT / 'random_comparisons.csv')
    ci = pd.read_csv(OUT / 'paired_customer_bootstrap.csv')
    audit = pd.read_csv(OUT / 'sample_audit.csv').query("period == 'validation'").iloc[0]
    restricted = comp.query("flow == 'restricted' and control == 'A1' and metric == 'coverage'").sort_values(['budget','config'])
    shared = comp.query("flow == 'shared' and control == 'A1' and metric == 'coverage'").sort_values(['budget','config'])
    def summary_table(data):
        rows=[]
        for row in data.itertuples():
            interval=ci.query("config == @row.config and budget == @row.budget and flow == @row.flow and contrast == 'L_minus_G' and metric == 'order'").iloc[0]
            rows.append({'配置':row.config,'总预算':row.budget,'G覆盖':f'{row.G:.2%}', 'L覆盖':f'{row.L:.2%}',
                         'A1中位数':f'{row.random_median:.2%}', 'A1范围':f'{row.random_min:.2%}–{row.random_max:.2%}',
                         'L−G百分点 [95% CI]':f'{100*row.L_minus_G:.2f} [{100*interval.ci95_low:.2f}, {100*interval.ci95_high:.2f}]',
                         'A1≥L次数':f'{row.random_ge_L}/100'})
        return pd.DataFrame(rows)
    main_table=summary_table(restricted); shared_table=summary_table(shared)
    fdir=ROOT/'results/figures/validation';fdir.mkdir(parents=True,exist_ok=True)
    fig, axes=plt.subplots(2,3,figsize=(14,8),sharey=True)
    for i,(flow,label) in enumerate([('restricted','Rules used within assigned group'),('shared','Same rules shared across groups')]):
        for j,budget in enumerate([20,50,100]):
            ax=axes[i,j]; d=comp.query("flow == @flow and budget == @budget and control == 'A1' and metric == 'coverage'").sort_values('config')
            x=np.arange(len(d)); med=d.random_median.to_numpy()*100
            ax.errorbar(x,med,yerr=np.vstack([med-d.random_min.to_numpy()*100,d.random_max.to_numpy()*100-med]),
                        fmt='o',capsize=4,color='#7b8794',label='A1 median and seed range')
            ax.plot(x,d.G*100,'s-',color='#1261a0',label='Global G');ax.plot(x,d.L*100,'o-',color='#d45d00',label='Cluster L')
            ax.set_xticks(x,d.config);ax.set_title(f'{label}\nTotal budget {budget}',fontsize=10);ax.grid(axis='y',alpha=.2)
            ax.set_ylim(0,100)
            if j==0:ax.set_ylabel('Validation co-occurrence coverage (%)')
    handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',ncol=3,frameon=False)
    fig.suptitle('Frozen Discovery rules evaluated on Validation | 4,862 eligible orders',fontsize=14)
    fig.tight_layout(rect=[0,.06,1,.95]);fig.savefig(fdir/'coverage_comparison.png',dpi=170);plt.close(fig)
    gl=metrics.query("control == 'GL' and flow == 'restricted'").sort_values(['budget','config','method'])
    stability=pd.DataFrame({'配置':gl.config,'预算':gl.budget,'方法':gl.method,'规则数':gl.actual_rule_count,
                            '未触发':gl.not_triggered,'触发但无共现':gl.triggered_no_joint,
                            '有共现但未达冻结门槛':gl.observed_below_threshold,'仍达冻结门槛':gl.meets_frozen_threshold,
                            '顾客等权覆盖':gl.customer_macro_coverage.map(lambda v:f'{v:.2%}')})
    win=int((restricted.L > restricted.G).sum());shared_win=int((shared.L > shared.G).sum())
    text=f'''# D：Validation 比较报告（2026-11-16）

**状态：仅比较，不推荐配置，不冻结 Test 方案。** 根据用户明确要求，不选择 P1–P5 中的任何配置，也不选择预算。下述结果来自本地 CPU 实算。

## 评价对象与口径

Validation 窗口为 `[2010-12-01, 2011-06-01)`。有效购物篮共 **{audit.all_valid_baskets:,}** 张，主比较纳入 **{audit.eligible_baskets:,}** 张、**{audit.eligible_customers:,}** 名 Profile 顾客，占全部有效购物篮 **{audit.eligible_order_share:.2%}**。品类映射后的空篮 **{audit.empty_l2_eligible_baskets}** 张，单品类篮 **{audit.single_l2_eligible_baskets}** 张，均保留在分母。

沿用 C 的 `taxonomy_v1`、Discovery 规则身份、排名和预算配额；不根据验证结果删规则、补位或改分组。比较五套参数、三个系统总预算、两种使用方式，以及 S（20种子）、A1/A2（各100种子）。**覆盖率表示订单同时包含规则前后件，不是推荐准确率或因果销售收益。**

主口径为 restricted（只使用所属群规则），主随机对照为 A1（Profile频次分层）。shared 只解除群限制，重复规则不返还预算；A2 使用 Discovery 活跃度，只作敏感性分析。两种使用方式分开解释。

## 实际观察

- 在15个“配置×预算”设置中，restricted 下 L 覆盖高于 G 的有 **{win}** 个；shared 下有 **{shared_win}** 个。完整结果全部列出，不挑选有利设置。
- G 与 L 使用相同系统总预算；L 把预算分给不同群，单个顾客可用规则数不同。`system_metrics.csv` 同时报告可用规则名额及顾客等权覆盖；本次未重新做等每用户预算的规则实验。
- 顾客抽样的配对95%区间使用2,000次 bootstrap，同一顾客的所有订单一起重抽。随机种子范围是随机结果的最小–最大值，**不是置信区间**；上尾统计未作多重比较校正，不作为确认性显著结论。

## 主比较：限群使用，A1对照

{md_table(main_table)}

## 补充比较：共享使用，A1对照

{md_table(shared_table)}

![Validation覆盖率](../results/figures/validation/coverage_comparison.png)

## G/L规则在未来的状态

以下状态按规则原所属范围评价；shared 的规则未来质量仍保留原范围口径，不能当作共享部署的全局规则置信度。门槛包括原支持度、置信度、lift、最低联合/前件计数，以及适用时的三品类增量。状态不改变部署清单。

{md_table(stability)}

零前件时置信度和lift留空；有前件但后件未出现时置信度为0、lift不可估。三品类增量从Validation的两个单前件重新计算。因为未来各群样本数不同，“未达门槛”可能由最低计数不足造成，不能简单当作关联消失。完整逐规则证据在忽略目录 `data/processed/local/D_validation/validation_rule_evidence.csv.gz`。

## 非Profile顾客的全局回退

主比较之外的 **{audit.non_profile_baskets:,}** 张有效订单另行应用同一G清单，其中 **{audit.identified_non_profile_baskets:,}** 张属于有标识的非Profile顾客，**{audit.anonymous_baskets:,}** 张为匿名订单，结果见 `non_profile_global_fallback.csv`。匿名订单不合并为一名顾客，也不纳入顾客bootstrap。不把这些订单只加到G的主比较分母里，也不给无未来订单的历史顾客制造空篮。

## 输入、核验与限制

- A快照：`2ae672b7ea6edb7f5e1561b6a64823004dea833e`；C交接：`ac2b8a3338198c24c7cf6203aa623be11a02d2f8`。核心ZIP及全部输入哈希见 `run_manifest.json`。
- 先复算C的 **6,660** 条Discovery系统指标，覆盖/触达/独立规则/组合计数全部一致，并逐一核对全部预算选中规则的Discovery计数，然后才计算Validation。
- 本次计算 **6,660** 条Validation系统指标；核对预算总数、群内配额、重复计数、完整命中包含于前件命中、共享覆盖包含限群覆盖。
- 本次只评价C的冻结预算清单品类规则，不重新挖掘、不重新聚类，也不评价整个候选池。SKU层的独立未来评价不在本批次内。
- taxonomy覆盖全期商品编码且含人工修订；冻结标签不等于全部预处理只使用历史信息，需要沿用B的方法披露。A1对高频群C2的置换空间有限。
- **未评价Test、未推荐配置、未生成最终冻结方案。** 后续由全组确定选择目标和最终方案后再开展Test。

## 文件与复现

入口：`python -X utf8 scripts/prepare_validation_inputs.py`，然后 `python -X utf8 scripts/run_validation.py`，最后 `python -X utf8 scripts/report_validation.py`。首次克隆建议执行 `git config --local core.autocrlf false` 和 `git config --local core.eol lf`，以保持冻结CSV的Git原始字节。依赖版本见 `requirements-validation.txt`。

| 文件 | 内容 |
|---|---|
| `configs/validation.json` | 计算前写定的比较范围及口径 |
| `results/tables/validation/GL_summary.csv` | G/L全配置结果与原范围规则状态 |
| `results/tables/validation/system_metrics.csv` | 全部逐种子系统指标 |
| `results/tables/validation/random_comparisons.csv` | 三种随机对照、三种覆盖口径 |
| `results/tables/validation/paired_customer_bootstrap.csv` | G、L及L−G的顾客配对区间 |
| `results/tables/validation/sample_audit.csv` | 纳入范围与空篮审计 |
| `results/tables/validation/non_profile_global_fallback.csv` | 非Profile顾客的全局回退 |
| `results/tables/validation/discovery_replay.csv` | 对C的Discovery复算结果 |
| `results/tables/validation/run_manifest.json` | 版本、输入/输出哈希和检查记录 |

所有顾客级输入、规则证据及逐订单指标都保存在 `data/processed/local/D_validation/`，不进入功能分支。人工科学复核尚待团队完成；程序测试与复算不能替代人工审阅。
'''
    DOC.write_text(text,encoding='utf-8')
    # A simple standalone report, with image embedded; no external packages or scripts.
    import base64
    encoded=base64.b64encode((fdir/'coverage_comparison.png').read_bytes()).decode()
    tables=''.join(f'<h2>{html.escape(title)}</h2>{table.to_html(index=False,escape=True)}' for title,table in [('限群使用（主比较）',main_table),('共享使用（补充）',shared_table),('原范围规则状态',stability)])
    page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Validation 比较报告</title><style>body{{font:15px/1.6 "Microsoft YaHei",sans-serif;max-width:1250px;margin:40px auto;padding:0 24px;color:#183044}}h1,h2{{color:#1261a0}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{padding:8px;border-bottom:1px solid #dce5ed;text-align:right}}th{{background:#eef4f9}}img{{width:100%}}.note{{padding:18px;background:#eef4f9;border-radius:10px}}</style><h1>D · Validation 比较报告</h1><p>2026-11-16 · 本地CPU · 五套配置 × 三个预算</p><p class="note">仅比较，不推荐配置、不冻结方案、未评价Test。主比较为4,862张Validation订单、1,458名历史客户；A1为主随机对照。覆盖指完整共现，不等于推荐准确率。</p><img src="data:image/png;base64,{encoded}">{tables}<h2>复算与边界</h2><p>C的6,660条Discovery系统计数及预算规则计数复算一致。Validation输出6,660条系统指标；95%区间按顾客配对bootstrap 2,000次。随机范围不是置信区间，多指标未作校正。完整说明、复现命令及文件索引见同目录validation_results.md。</p></html>'''
    (ROOT/'docs/validation_results.html').write_text(page,encoding='utf-8')
    print('Saved comparison report, HTML and coverage figure.')
    print(main_table.to_string(index=False))


if __name__=='__main__':main()
