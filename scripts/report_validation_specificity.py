"""Explain list differences separately from persistent group-specific effects."""
from pathlib import Path
import html
import base64
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/tables/validation_specificity'


def pct(value):return '不可估' if pd.isna(value) else f'{value:.1%}'


def md(d):
    return '| '+' | '.join(d.columns)+' |\n|'+'|'.join(['---']*len(d.columns))+'|\n'+'\n'.join('| '+' | '.join(map(str,r))+' |' for r in d.itertuples(index=False,name=None))


def main():
    s=pd.read_csv(OUT/'GL_advantage_summary.csv');groups=pd.read_csv(OUT/'GL_group_advantage_summary.csv')
    content=pd.read_csv(OUT/'GL_rule_set_difference.csv');paired=pd.read_csv(OUT/'GL_rule_advantage_retention.csv')
    random=pd.read_csv(OUT/'random_advantage_comparisons.csv');coverage=pd.read_csv(OUT/'GL_complementarity.csv')
    cases=pd.read_csv(OUT/'GL_supported_survivor_examples.csv')
    summaries=[]
    for r in s.sort_values(['budget','config']).itertuples():
        c=content.loc[content.config.eq(r.config)&content.budget.eq(r.budget)&content.level.eq('system')].iloc[0]
        summaries.append({'配置':r.config,'预算':r.budget,'L不同规则':c.local_unique_rules,'名单Jaccard':f'{c.jaccard_rules:.1%}',
                          'L不在G前B':c.local_novel_rules,'D优势候选名额':r.discovery_advantage_candidates,
                          'V支持优势名额':r.validation_supported_slots,'D候选中未来仍支持':r.surviving_advantage_slots,
                          '优势保持率':pct(r.advantage_survival_rate),'严格强于每群名额':r.strict_supported_slots})
    main_table=pd.DataFrame(summaries)
    group_table=groups.query('budget==100').sort_values(['config','group_id'])
    group_table=pd.DataFrame({'配置':group_table.config,'群':group_table.group_id.map(lambda x:f'C{x}'),'名额':group_table.selected_slots,
                              'D优势候选':group_table.discovery_advantage_candidates,'V支持优势':group_table.validation_supported_slots,
                              '保持的D候选':group_table.surviving_advantage_slots,'保持率':group_table.advantage_survival_rate.map(pct),
                              'V置信度差中位数pp':group_table.validation_confidence_gap_pp_median.map(lambda x:f'{x:+.2f}'),
                              'V关联提升差中位数pp':group_table.validation_association_gap_pp_median.map(lambda x:f'{x:+.2f}')})
    rr=random.query("budget==100 and control=='A1' and metric=='validation_supported_share'").sort_values('config')
    random_table=pd.DataFrame({'配置':rr.config,'真实V优势比例':rr.real.map(pct),'A1中位数':rr.random_median.map(pct),
                               'A1范围':[f'{pct(a)}–{pct(b)}' for a,b in zip(rr.random_min,rr.random_max)],
                               'A1≥真实次数':rr.random_ge_real.map(lambda x:f'{int(x)}/100' if pd.notna(x) else '不可估')})
    direction_rows=[]
    for r in s.query('budget==100').sort_values('config').itertuples():
        ref=random.loc[random.config.eq(r.config)&random.budget.eq(100)&random.control.eq('A1')&random.metric.eq('both_directions_kept_rate')].iloc[0]
        direction_rows.append({'配置':r.config,'D优势候选':r.discovery_advantage_candidates,'未来方向保持':r.candidate_both_directions_kept,
                               '真实保持率':pct(r.both_directions_kept_rate),'A1中位数':pct(ref.random_median),'A1≥真实次数':f'{int(ref.random_ge_real)}/100'})
    direction_table=pd.DataFrame(direction_rows)
    hint=paired.loc[paired.advantage_candidate_D.astype(bool)&paired.advantage_candidate_V.astype(bool)].sort_values(['q_one_vs_rest_BY_V','confidence_gap_vs_rest_pp_V'],ascending=[True,False]).head(5)
    cv=coverage.query("period=='validation' and budget==100 and flow=='restricted'").sort_values('config')
    coverage_table=pd.DataFrame({'配置':cv.config,'仅L完整覆盖':cv.local_only_complete_orders,'仅G完整覆盖':cv.global_only_complete_orders,
                                 '双方都完整覆盖':cv.shared_complete_orders,'L−G净订单':cv.net_order_difference,
                                 '仅L前件触达':cv.local_only_antecedent_orders})
    tax=json.loads((ROOT/'configs/taxonomy/taxonomy_v1.json').read_text(encoding='utf-8'))
    labels={r['id']:r.get('name_zh',r['id']) for r in tax['l2']}
    def rule_name(r):
        return '＋'.join(labels.get(x,x) for x in json.loads(r.antecedent))+' → '+'＋'.join(labels.get(x,x) for x in json.loads(r.consequent))
    erows=[]
    for r in cases.head(8).itertuples():
        erows.append({'目标群':f'C{r.group_id}','规则':rule_name(r),'D群内−群外pp':f'{r.confidence_gap_vs_rest_pp_D:+.2f}',
                      'V群内−群外pp':f'{r.confidence_gap_vs_rest_pp_V:+.2f}','V区间pp':f'[{r.confidence_gap_ci95_low_pp_V:+.2f}, {r.confidence_gap_ci95_high_pp_V:+.2f}]',
                      'V关联提升差pp':f'{r.association_gap_vs_rest_pp_V:+.2f}','V校正q':f'{r.q_one_vs_rest_BY_V:.3g}'})
    hintrows=[]
    for r in hint.itertuples():
        hintrows.append({'目标群':f'C{r.group_id}','规则':rule_name(r),'D置信度差pp':f'{r.confidence_gap_vs_rest_pp_D:+.2f}',
                         'V置信度差pp':f'{r.confidence_gap_vs_rest_pp_V:+.2f}','V关联提升差pp':f'{r.association_gap_vs_rest_pp_V:+.2f}',
                         'BY校正q':f'{r.q_one_vs_rest_BY_V:.3g}','BH校正q':f'{r.q_one_vs_rest_BH_V:.3g}'})
    hint_table=pd.DataFrame(hintrows)
    examples=md(pd.DataFrame(erows)) if erows else '当前共同定义和校正下，没有Discovery优势候选在Validation继续得到足够支持；这不等于证明所有群体都没有差异。'
    figdir=ROOT/'results/figures/validation_specificity';figdir.mkdir(parents=True,exist_ok=True)
    fig,ax=plt.subplots(figsize=(8,6))
    for g,color in [(0,'#1261a0'),(1,'#d45d00'),(2,'#25804a')]:
        p=paired.loc[paired.group_id.eq(g)]
        ax.scatter(p.confidence_gap_vs_rest_pp_D,p.confidence_gap_vs_rest_pp_V,s=25,alpha=.6,label=f'C{g}',color=color)
    ax.axhline(0,color='#777',lw=.8);ax.axvline(0,color='#777',lw=.8)
    ax.axhline(5,color='#aaa',lw=.8,ls='--');ax.axvline(5,color='#aaa',lw=.8,ls='--')
    ax.set_xlabel('Discovery confidence(target) minus confidence(rest), pp');ax.set_ylabel('Validation confidence(target) minus confidence(rest), pp')
    ax.set_title('Do group advantages persist?\nOne dot per frozen target-group / rule identity; not a significance plot')
    ax.grid(alpha=.15);ax.legend(frameon=False);fig.tight_layout();fig.savefig(figdir/'confidence_gap_retention.png',dpi=170);plt.close(fig)
    hybrid_path=ROOT/'results/tables/validation_hybrid/paired_comparisons.csv'
    hybrid_note='已有G50+L50去重匹配K实验见 [同预算合并实验](validation_hybrid_results.md)；该实验使用共享规则，与限群比较分开解释。'
    if hybrid_path.exists():
        h=pd.read_csv(hybrid_path);h=h.query("comparison=='HYBRID_minus_G_K' and metric=='order'")
        ht=pd.DataFrame({'配置':h.config,'去重后K':h.K,'合并−G前K/百分点':h.estimate.map(lambda x:f'{x*100:+.2f}'),
                         '95%区间pp':[f'[{a*100:+.2f},{b*100:+.2f}]' for a,b in zip(h.ci95_low,h.ci95_high)],'净增加订单':h.net_orders})
        hybrid_note+='\n\n'+md(ht)+'\n\n这是额外探索：P3有补充收益，但其他配置不支持普遍收益；尚无随机合并匹配K对照，不能归因为RFM独有优势。'
    text=f'''# Validation补算：分群规则与Global到底有什么不同？

2026-11-19 · **Validation 阶段探索性分析。**

先读[补算方案](../methods.md#群体差异与优势保持方案)。本批次把“名单不同”“同一规则在群内更强”“群体优势未来保持”“给Global补充覆盖”分成四层，避免相互替代。

## 先看结论：有方向性信号，但单条规则的强证据不足

- 名单确有差异。P5/100的L共有71条不同方向规则，其中22条不在G前100，新增占L不同规则约31.0%；方向规则Jaccard为40.2%。这不等于Global从未发现这些规则。
- 不少Discovery群体优势方向保持。P5/100有19个优势候选名额，其中15个在Validation仍同时保持正的置信度差与基础率调整后关联差，保持率78.9%，A1中位数52.6%。但方向保持不要求仍达到5pp，也不代表单条规则有足够统计证据。
- 按本次固定的证据量、效果幅度和BY校正主标准，真实L没有规则通过全部“未来群体优势”要求。这不否定旧报告中的群内可靠关联；旧问题没有要求群内显著强于群外。
- BH敏感性下有1个真实群规则身份通过；该身份BY q约0.069、BH q约0.010。保留为提示性案例，不据此改主校正、不宣称确认性发现。
- 互补覆盖仍见已有P3合并匹配K结果；有用的补充规则，不一定是严格意义上的群体特有规则。

## 一、名单差异和优势保持

{md(main_table)}

解释：名单Jaccard=方向规则交集/并集。L不同规则数可能小于名额预算，因为不同群重复占名额。“不在G前B”只表示没进同预算Top榜，**不表示Global未发现/未通过全局门槛**；本批次未读取完整全局合格候选池。D候选=Discovery已出现至少5pp群内对群外置信度优势、正的相对基础率关联优势，并符合共同点估计证据门槛。

“V支持优势”包含原来没有达到D候选门槛、后来才更强的规则；“保持的D候选”才是D候选且V仍有支持。保持率分母包含未来未触发/证据不足的全部D候选，分母为0时记不可估，不记0%。名额数包括不同群同一方向规则；不等于独立商品组合数。

## 二、同一条规则：目标群与群外比较

主差值为 `Conf(目标群)−Conf(其余两群合并)`。因为群外和目标群顾客互斥，比“群内减包含自身的Global”更清楚。与此同时计算：

`关联提升差 = [Conf(目标群)−后件基础率(目标群)]−[Conf(群外)−后件基础率(群外)]`。

这样不会仅因为后件在目标群本来更热门，就把高confidence称为更强关联。lift目标/Global、lift目标/群外比值也输出，但只作诊断；零/缺失分母不造无穷值。

Validation支持主优势要求：共同目标群证据量/集中度/效应/三品类增量门槛通过；群外前件至少20单、10人；置信度差≥5pp、关联提升差>0；新联合检验的系统内BY q≤0.05。旧质量检验q值不复用。严格特异性还要分别强于另外每个群，而不是仅强于合并群外。

预算100的群体诊断：

{md(group_table)}

## 三、哪些优势在未来仍有支持？

以下案例来自所有配置/预算的冻结规则身份联合，不是独立重复实验，也不是推荐效果。只展示D已有候选且V继续支持的前8个，完整正面与负面规则都保留。

{examples}

### 方向保持与随机对照

{md(direction_table)}

这里保留的是“正方向”，不等于通过5pp幅度和BY要求。效应保留比例也显示部分优势减弱，例如P5/100候选的V/D置信度差比例中位数约0.51。随机候选集合不同、分母数量不同，因此它是探索性系统对照，不是单条规则显著性的替代。

### 提示性案例：不是主标准通过案例

{md(hint_table) if len(hint_table) else '暂无点估计候选。'}

本表专门展示原有D候选中V点估计仍满足条件的例子，BY未通过者仍是“证据未解决”。它不替代全量正负结果，也不等于新发现已被证实。

![Discovery到Validation群间差异](../../../../results/figures/validation_specificity/confidence_gap_retention.png)

图中点位仅是差值，右上角不自动等于有统计证据；须看计数、不同顾客数、相对基础率差异和校正值。效应保留比例=V置信度差/D置信度差，只在D差值≥5pp且可估时计算，可大于1或为负，不截断。

## 四、相对活跃度随机对照，有多突出？

预算100，比较“Validation有支持优势的名额比例”；每个随机种子形成一个系统结果：

{md(random_table)}

全部S、A1、A2与各预算见 `random_advantage_comparisons.csv`。这是探索性上尾统计，不是全研究显著性检验。保持率若某随机种子没有D候选，单列不可估种子数，不把它伪装成0%保持。

## 五、名单不同是否带来独有覆盖？

以下为Validation、预算100、限群使用：

{md(coverage_table)}

“仅L完整覆盖”是前后件都出现且G没有完整覆盖；“仅L前件触达”只看前件，两者不能混用。净订单=仅L完整覆盖−仅G完整覆盖。L能覆盖部分G遗漏订单，与G总体更高并不矛盾。

{hybrid_note}

## 统计和科学边界

- 假设单位是顾客，同人订单相关性通过比率影响函数处理；目标群/群外方差相加，t自由度取两边顾客数较小值减1。区间为逐项近似区间，不是同时区间或精确检验。
- 对每个真实或随机系统，联合五配置/三预算所有去重(群,规则)身份，把one-vs-rest与严格两种检验放入同一家族BY校正。BH只作诊断。没有做全研究所有系统的总体错误率保证。
- 三品类仍要求相对简单规则增量，但主群间差异不能只由商品热门程度解释。小群证据弱不等于没有特色。
- Discovery只是描述性定义候选，不将同一数据的筛选当作独立发现检验；Validation标准是在已有结果之后新增，明确是探索性扩展。
- 这是观察性共购：不计算Precision/Recall/F1，没有隐藏后件的推荐任务；没有因果增销解释。
- 方向保持/效果保留与统计支持分别报告。缺少证据，不应写成“已证明不存在群体差异”。Test尚未使用。

## 输出文件与复现

|文件|内容|
|---|---|
|configs/validation_specificity.json|计算前固定的定义、校正家族和边界|
|GL_rule_set_difference.csv|真实L的方向/组合重合、新增比例，含各群诊断|
|GL_rule_strength.csv|真实L各冻结规则在D/V的目标/群外/其他群/Global证据|
|GL_rule_advantage_retention.csv|同一规则身份的D/V配对与效应保留|
|GL_advantage_summary.csv|真实系统各配置/预算候选、支持、方向与保持|
|GL_group_advantage_summary.csv|按C0/C1/C2分开的相同统计|
|GL_supported_survivor_examples.csv|所有得到未来支持的Discovery候选案例|
|advantage_system_summary.csv|真实及全部随机种子的系统统计|
|random_advantage_comparisons.csv|S/A1/A2系统比较与不可估种子数|
|GL_complementarity.csv / complementarity_systems.csv|完整独有、前件独有、共同与净覆盖|
|family_audit.csv / run_manifest.json|校正家族、输入输出/代码哈希和核验|

所有表位于 `results/tables/validation_specificity/`。随机逐规则明细、完整群诊断和全部名单差异位于忽略目录 `data/processed/local/D_validation/`，不含进功能分支。先运行原输入准备和 `scripts/run_validation.py`，再执行 `python -X utf8 scripts/run_validation_specificity.py`、`python -X utf8 scripts/report_validation_specificity.py`。无需GPU，不重新挖规则。
'''
    (ROOT/'docs/evaluation/validation/details/validation_specificity_results.md').write_bytes(text.encode('utf-8'))
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>群体差异与优势保持</title><style>body{font:15px/1.7 "Microsoft YaHei",sans-serif;max-width:1280px;margin:36px auto;padding:0 20px;color:#183044}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:7px;border-bottom:1px solid #dbe5ed;text-align:right}th{background:#edf4f9}h1,h2{color:#1261a0}img{width:100%;max-width:900px}.note{background:#edf4f9;padding:18px}</style><h1>Validation：群体差异与优势保持</h1><p>2026-11-19 · Validation 探索性补算</p><p class="note">名单不同 ≠ 同一规则在群内更强 ≠ 优势能在未来保持 ≠ 系统覆盖更好。四层证据分别报告。Top榜缺席不等于Global未发现；统计证据不足不等于无差异。</p>'''
    for title,d in [('名单差异与优势保持',main_table),('预算100按群诊断',group_table),('A1随机对照',random_table),('方向保持与A1',direction_table),('独有覆盖与净差',coverage_table)]:page+=f'<h2>{html.escape(title)}</h2>'+d.to_html(index=False,escape=True)
    encoded=base64.b64encode((figdir/'confidence_gap_retention.png').read_bytes()).decode();page+=f'<h2>群体优势跨期变化</h2><img src="data:image/png;base64,{encoded}"><p>全部规则和统计限制见同目录validation_specificity_results.md。</p></html>'
    (ROOT/'docs/evaluation/validation/details/validation_specificity_results.html').write_bytes(page.encode('utf-8'))
    print(main_table.to_string(index=False));print('Saved specificity comparison report and offline HTML.')


if __name__=='__main__':main()
