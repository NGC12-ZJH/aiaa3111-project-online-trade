"""Chinese comparison report; does not choose a configuration."""
from pathlib import Path
import base64
import html
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/tables/validation_quality'


def table(d):
    return '| '+' | '.join(d.columns)+' |\n|'+'|'.join(['---']*len(d.columns))+'|\n'+'\n'.join('| '+' | '.join(map(str,r))+' |' for r in d.itertuples(index=False,name=None))


def main():
    s=pd.read_csv(OUT/'GL_quality_summary.csv')
    r=pd.read_csv(OUT/'random_quality_comparisons.csv')
    sensitivity=pd.read_csv(OUT/'GL_sensitivity.csv')
    tabs={}
    for flow in ['restricted','shared']:
        rows=[]
        for budget in [20,50,100]:
            for config in ['P1','P2','P3','P4','P5']:
                data=s.query('config==@config and budget==@budget and flow==@flow')
                g=data.loc[data.method.eq('G')].iloc[0];l=data.loc[data.method.eq('L')].iloc[0]
                random=r.query("config==@config and budget==@budget and flow==@flow and control=='A1' and metric=='quality_coverage'").iloc[0]
                rows.append({'配置':config,'预算':budget,'原G覆盖':f'{g.raw_coverage:.2%}','原L覆盖':f'{l.raw_coverage:.2%}',
                             '可靠G覆盖':f'{g.quality_coverage:.2%}','可靠L覆盖':f'{l.quality_coverage:.2%}',
                             'G名额保持':f'{g.accepted_slot_share:.1%}','L名额保持':f'{l.accepted_slot_share:.1%}',
                             'A1可靠覆盖中位数':f'{random.random_median:.2%}'})
        tabs[flow]=pd.DataFrame(rows)
    statuses=s.query("budget==100 and flow=='restricted'").sort_values(['config','method'])
    status_table=pd.DataFrame({'配置':statuses.config,'方法':statuses.method,'未触发':statuses.not_triggered,
                               '证据不足':statuses.insufficient_evidence,'关联幅度不足':statuses.effect_below_minimum,
                               '三品类增量不足':statuses.increment_below_minimum,'统计证据不足':statuses.uncertainty_unresolved,
                               '通过':statuses.accepted})
    # Sensitivity differences relative to the pre-recorded primary definition.
    ref=s[['config','budget','method','flow','quality_coverage','accepted_slot_share']]
    merged=sensitivity.merge(ref,on=['config','budget','method','flow'],suffixes=('','_primary'),validate='many_to_one')
    merged['coverage_change_pp']=100*(merged.quality_coverage-merged.quality_coverage_primary)
    sens=[]
    for setting,d in merged.groupby('setting',sort=False):
        sens.append({'验收定义':setting,'可靠覆盖变化最小/百分点':f'{d.coverage_change_pp.min():.2f}',
                     '可靠覆盖变化最大/百分点':f'{d.coverage_change_pp.max():.2f}'})
    sens=pd.DataFrame(sens)
    figure=ROOT/'results/figures/validation_quality';figure.mkdir(parents=True,exist_ok=True)
    fig,axes=plt.subplots(1,3,figsize=(14,4.8),sharey=True)
    for ax,budget in zip(axes,[20,50,100]):
        x=np.arange(5)
        for method,color in [('G','#1261a0'),('L','#d45d00')]:
            d=s.query("flow=='restricted' and budget==@budget and method==@method").sort_values('config')
            ax.plot(x,d.raw_coverage*100,'--',color=color,alpha=.4,label=f'{method} raw')
            ax.plot(x,d.quality_coverage*100,'o-',color=color,label=f'{method} accepted-rule coverage')
        d=r.query("flow=='restricted' and budget==@budget and control=='A1' and metric=='quality_coverage'").sort_values('config')
        med=d.random_median.to_numpy()*100
        ax.errorbar(x,med,yerr=np.vstack([med-d.random_min.to_numpy()*100,d.random_max.to_numpy()*100-med]),fmt='.',color='#6b7785',capsize=3,label='A1 median and seed range')
        ax.set_xticks(x,['P1','P2','P3','P4','P5']);ax.set_title(f'Total budget {budget}');ax.set_ylim(0,100);ax.grid(axis='y',alpha=.2)
    axes[0].set_ylabel('Validation orders covered (%)')
    handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',ncol=3,fontsize=9,frameon=False)
    fig.suptitle('Uniform future-quality acceptance | restricted flow | retrospective metric')
    fig.tight_layout(rect=[0,.16,1,.93]);fig.savefig(figure/'quality_coverage.png',dpi=170);plt.close(fig)
    text=f'''# Validation统一质量补算结果

2026-11-18 · 主标准quality_v1 · **只比较，不推荐配置、不冻结Test、不运行Test。**

## 先看什么

先读[一页验收方案](validation_quality_plan.md)。本批次把“未来仍然出现”与“未来仍有可靠且足够幅度的关联”分开。所有P1–P5使用相同验收门槛。原规则清单、原始覆盖率与旧报告保持不变。

主标准：前件≥20单/10人，联合≥10单/5人，单人联合贡献≤50%；confidence超过后件基础率至少5个百分点、lift≥1.2；三品类比两个单前件都至少提高5个百分点；按顾客聚类的近似检验经系统内BY校正≤0.05。阈值是工作性定义，不是公认最优值；敏感性全部并列报告。

**可靠关联覆盖率**：只让本期通过统一验收的冻结规则贡献订单覆盖，分母仍为全部4,862张主比较订单。同一期数据既用于验收也用于计数，所以这是回顾性关联保持指标，不能表述为未来部署后的预测效果。原部署清单不删改、不补位。

**与旧表的区别：** 这里的保持率是通过共同质量标准的比例，不是旧表“仍达各自冻结门槛”的比例。例如P5原门槛还要求原支持度/置信度和10pp增量，本次共同标准使用5pp增量、lift1.2与基础率提升等条件；两种通过率不能当作同一指标比较。

## 限群使用：主比较

{table(tabs['restricted'])}

## 共享使用：补充比较

共享时在全部4,862张订单上重新计算质量；不是把原群内的“通过”直接带到共享场景。同一方向规则去重后匹配，但重复来源仍占原名额。

{table(tabs['shared'])}

![原覆盖与可靠关联覆盖](../results/figures/validation_quality/quality_coverage.png)

## 预算100：为什么没有通过

以下为限群模式，按规则名额统计，每行相加为100。类别按顺序互斥：未触发→证据不足→关联幅度不足→三品类增量不足→统计证据不足→通过。详细表另有独立证据量与集中度字段，不应把“证据不足”和“统计证据不足”解释为关联被证明不存在。

{table(status_table)}

## 敏感性：门槛改变后会变化多少

下表显示所有G/L配置、预算和使用方式，相对主标准的可靠覆盖变化范围。每次只改一项定义；主标准不因结果更好而替换。完整随机对照见 `sensitivity_random_comparisons.csv`。

{table(sens)}

## 统计口径与限制

- 重复订单按顾客聚类；使用ratio差值的delta-method近似标准误和t分布，不是逐规则2,000次bootstrap，也不是精确检验。小群和稀疏规则的近似可能不准，因此同时有证据量门槛。
- 每个系统把所有P1–P5/预算的验收身份合并去重，原范围与全局共享范围共同校正。三品类把关联及两个增量的单侧p取最大值，要求同时有证据；BY主校正允许检验间依赖。校正家族内重复规则不重复增加检验次数。
- q≤0.05是系统内名义错误发现率标准，不是每条规则有95%概率正确。不同系统之间未做总体校正；随机上尾比例仍是描述统计，不作全研究显著性结论。
- 置信度提升/三品类增量的区间是逐项95%区间，不是多重校正后的同时区间。统计方法与公式见[方法说明](validation_quality_methods.md)。
- 关联/增量检验只检验是否为正；5个百分点与lift1.2是点估计幅度要求，不代表区间下限也超过该幅度。
- G的样本更多，通常检验力更高；小群通过较少可能反映证据较弱，不能直接推成偏好较弱，需结合证据不足比例和效应量解读。
- 保持率分母包含全部原名额，证据不足规则不会被排除来抬高通过率。另报告去重后的保持率，避免规则重复名额造成误读。
- 对Discovery的置信度变化、置信度比例及lift比例只作描述，没有假装两个时期样本相互独立来生成变化区间。
- 本批次在已看过Validation结果之后新增，属于探索性扩展，不得写成预注册。无配置选择、无最终Test结论。

## 输出文件

| 文件 | 内容 |
|---|---|
| `configs/validation_quality.json` | 补算前保存的主门槛、11套敏感性定义、校正家族 |
| `results/tables/validation_quality/GL_quality_summary.csv` | G/L主标准全配置结果，60行 |
| `results/tables/validation_quality/system_quality.csv` | 全部6,660条逐种子系统结果 |
| `results/tables/validation_quality/random_quality_comparisons.csv` | S/A1/A2质量对照，270行 |
| `results/tables/validation_quality/GL_sensitivity.csv` | 11套定义的G/L结果 |
| `results/tables/validation_quality/sensitivity_random_comparisons.csv` | 全定义随机对照汇总 |
| `results/tables/validation_quality/GL_rule_quality.csv` | G/L逐方向规则、评价范围、客户证据、区间与校正值 |
| `results/tables/validation_quality/family_audit.csv` | 各系统实际检验家族大小 |
| `results/tables/validation_quality/run_manifest.json` | 输入来源、方案哈希、代码哈希和核验记录 |

全部逐规则质量与逐种子敏感性明细位于被忽略的 `data/processed/local/D_validation/quality_rule_evidence.csv.gz`、`quality_sensitivity_systems.csv.gz`。

复现：`python -X utf8 scripts/run_validation_quality.py`，然后 `python -X utf8 scripts/report_validation_quality.py`。无需GPU、不重新挖规则。
'''
    (ROOT/'docs/validation_quality_results.md').write_text(text,encoding='utf-8')
    image=base64.b64encode((figure/'quality_coverage.png').read_bytes()).decode()
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Validation统一质量比较</title><style>body{font:15px/1.7 "Microsoft YaHei",sans-serif;color:#183044;max-width:1250px;margin:36px auto;padding:0 20px}h1,h2{color:#1261a0}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:7px;border-bottom:1px solid #dbe5ed;text-align:right}th{background:#edf4f9}img{width:100%}.note{background:#edf4f9;padding:18px}</style><h1>Validation统一质量比较</h1><p>2026-11-18 · CPU · 只比较，不推荐配置，未评价Test</p><p class="note">可靠关联覆盖是用同一期Validation验收后得到的回顾性指标，不是预测准确率。统一证据量、lift/置信度提升、三品类增量和系统内BY校正；不删除或补齐冻结清单。详见同目录一页方案和方法说明。</p>'''
    page+=f'<img src="data:image/png;base64,{image}">'
    for title,d in [('限群使用（主比较）',tabs['restricted']),('共享使用（补充）',tabs['shared']),('预算100规则状态',status_table),('验收门槛敏感性',sens)]:
        page+=f'<h2>{html.escape(title)}</h2>'+d.to_html(index=False,escape=True)
    page+='</html>'
    (ROOT/'docs/validation_quality_results.html').write_text(page,encoding='utf-8')
    print(tabs['restricted'].to_string(index=False))
    print('Saved Chinese quality report, HTML, figure and sensitivity interpretation.')


if __name__=='__main__':main()
