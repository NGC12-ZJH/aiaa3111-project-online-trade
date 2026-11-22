from pathlib import Path
import json,hashlib,sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__import__('os').environ.get('PATTERN_PROJECT_ROOT', str(Path(__file__).resolve().parent)));O=R/'ranking_gap_sensitivity'
d=pd.read_csv(O/'comparison.csv');m=pd.read_csv(O/'system_metrics.csv',dtype={'seed':str},keep_default_na=False);a=pd.read_csv(O/'allocation_audit.csv')
assert len(m)==39960 and len(d)==540
assert (m.actual+m.shortfall==m.budget).all()
assert (m.new_orders-m.lost_orders==m.net_orders).all()
assert m[m.method.eq('G')].groupby(['period','config','budget','flow']).covered_orders.nunique().eq(1).all()
# All comparisons preserve frozen rule choices across periods.
s=pd.read_csv(O/'selected_rules_evidence.csv.gz',dtype={'seed':str,'group':str},keep_default_na=False,low_memory=False)
for col in ['discovery_target_a','discovery_rest_a','discovery_target_antecedent_customers','discovery_rest_antecedent_customers']:s[col]=pd.to_numeric(s[col],errors='coerce')
gated=s[s.variant.ne('original')&s.method.ne('G')]
assert (gated.discovery_target_a>=20).all() and (gated.discovery_rest_a>=20).all()
assert (gated.discovery_target_antecedent_customers>=10).all() and (gated.discovery_rest_antecedent_customers>=10).all()
# Independent array membership recount for all G/L choices, both periods/flows.
sys.path.insert(0,str(O/'vendor'));from validation import load_period
S=R/'category_P1_P5_handoff';tax=pd.read_csv(S/'inputs/item_taxonomy_v1.csv',dtype=str);lab=pd.read_csv(S/'inputs/customer_clusters.csv',dtype=str);tm=dict(zip(tax.stock_code,tax.l2_id));true=dict(zip(lab.customer_id,lab.cluster_id));count=0
gl=s[s.control.eq('GL')]
for period in ['discovery','validation']:
 ind=load_period(O/'inputs',period,tm,true)[0];cache={};groups=np.array([true[c] for c in ind.customers])
 for key,z in gl.groupby(['method','config','budget','variant']):
  method,config,B,variant=key;local=np.zeros(ind.n,bool);shared=local.copy()
  for r in z.itertuples():
   if r.rule_id not in cache:
    items=set(json.loads(r.antecedent)+json.loads(r.consequent));cache[r.rule_id]=np.array([items.issubset(b) for b in ind.baskets])
   h=cache[r.rule_id];shared|=h;local|=h if method=='G' else h&(groups==r.group)
  for flow,h in [('restricted',local),('shared',shared)]:
   target=m[m.period.eq(period)&m.control.eq('GL')&m.method.eq(method)&m.config.eq(config)&m.budget.eq(B)&m.variant.eq(variant)&m.flow.eq(flow)];assert len(target)==1 and target.covered_orders.iloc[0]==h.sum();count+=1
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False})
fig,axes=plt.subplots(2,3,figsize=(15,8))
for i,flow in enumerate(['restricted','shared']):
 for j,B in enumerate([20,50,100]):
  ax=axes[i,j];t=np.arange(5)
  for v,label in [('original','L原排序'),('evidence_frequency','L同证据频次排序'),('evidence_gap','L差异排序')]:
   z=d[d.period.eq('validation')&d.flow.eq(flow)&d.budget.eq(B)&d.control.eq('A1')&d.variant.eq(v)].sort_values('config');ax.plot(t,100*z.L,'o-',label=label)
  ax.plot(t,100*z.G,'k--',label='G不变');ax.plot(t,100*z.R_median,':',label='A1差异排序中位数');ax.set_xticks(t,z.config);ax.set_title(f'Validation {flow} B={B}');ax.set_ylabel('订单覆盖率 %');ax.legend(fontsize=7);ax.grid(alpha=.2)
fig.tight_layout();fig.savefig(O/'validation_ranking_coverage.png',dpi=160);plt.close(fig)
view=d[d.period.eq('validation')&d.flow.eq('restricted')&d.budget.eq(100)&d.control.eq('A1')][['config','variant','G','L','R_median','random_ge_L','L_new_orders','L_lost_orders','L_D_signals','L_V_signals_kept','L_direction_retention','L_median_confidence_gap_pp']].copy()
view.to_csv(O/'Validation_B100_main.csv',index=False)
for col in ['G','L','R_median','L_direction_retention']:view[col]=view[col].map(lambda v:f'{v:.2%}' if pd.notna(v) else '不可估')
view.L_median_confidence_gap_pp=view.L_median_confidence_gap_pp.round(2)
def md(z):return '| '+' | '.join(z.columns)+' |\n|'+'|'.join(['---']*len(z.columns))+'|\n'+'\n'.join('| '+' | '.join(map(str,r))+' |' for r in z.itertuples(index=False,name=None))
gap=m[m.period.eq('validation')&m.control.eq('GL')&m.method.eq('L')&m.variant.eq('evidence_gap')];freq=m[m.period.eq('validation')&m.control.eq('GL')&m.method.eq('L')&m.variant.eq('evidence_frequency')];j=gap.merge(freq,on=['config','budget','flow'],suffixes=('_gap','_freq'));better=int((j.covered_orders_gap>j.covered_orders_freq).sum());equal=int((j.covered_orders_gap==j.covered_orders_freq).sum())
text=f'''# 群体特色排序敏感性分析

基于D提交4461750、C原始P1–P5完整合格候选和冻结数据快照2ae672b。D的Test结果已公开，本实验是新增探索性分析，不替换既有冻结方案，不使用Test，不将Validation比较包装成新的独立最终检验。

## 设计

Discovery定义所有选择，Validation只评价。五配置×预算20/50/100，S20、A1/A2各100种子。原群订单配额、重复占名额、限群/共享语义保持不变；本实验不是去重补满预算实验。G保持原始频次清单。

三方案：original=原始频次排序；evidence_frequency=前件群内外各≥20单且各≥10名顾客后按频次排序；evidence_gap=同样证据要求，按群内−群外confidence差降序，平局按联合次数、confidence、lift降序、rule_id升序。不额外强制正差值或正基础率调整差，以免混入另一套筛选。候选不足记录缺额，不借位。

两新方案的直接差异仅为排序；original与新方案的差异同时包括证据要求。随机组与真实群同样处理。所有规则从本范围原生P1–P5合格候选中选择，不用Validation覆盖或差值补位。

## 当前结果

在Validation的30个配置/预算/匹配方式中，差异排序相对同证据频次排序覆盖更高{better}个，持平{equal}个，更低{30-better-equal}个。覆盖和群内外差值必须分开解释，选择高差值并不以覆盖最大化为目标。

限群、预算100、A1主对照：

'''+md(view)+'''

![Validation覆盖](validation_ranking_coverage.png)

## 群体优势的评价边界

输出同一所选规则在Discovery/Validation的目标/群外前件次数、联合次数、独立前件客户数、confidence差及基础率调整后关联差。描述性信号定义为Discovery置信度差≥5pp且关联差>0；方向保持要求Validation两项差值都>0。该定义不是D完整的质量/集中度/BY候选标准，不应直接把本报告的保持率与D原保持率横向等同。

本批次未重算新规则联合检验和BY家族，因此不报告“显著群体特异规则数”，不能复用D旧规则的q值。新排名会集中选择Discovery较大的差值，未来衰减应如实保留。零前件不可估，不填为0；证据不足仍保留在固定名额与方向保持分母中。

## 文件

- selected_rules_evidence.csv.gz：三方案冻结清单及逐规则两时期证据，group为贡献群。
- system_metrics.csv：39960条系统评价，含完整覆盖、新增/丢失/共同覆盖、差值中位数、方向保持；按名额计方向指标，重复规则不可当独立样本。
- comparison.csv：S/A1/A2按种子汇总；上尾比例未经跨指标校正，仅作描述。
- allocation_audit.csv：每群名额和缺额。
- protocol.json：预先写入的选择规则；verification.json：核验结果。

原始13320条D/V覆盖结果逐项复现。G跨方案不变。两新方案的客户证据门槛逐行核对；G/L共360条系统覆盖另用订单集合/布尔数组独立重算一致。没有进行新规则的确认性显著性检验。

保存本地，未上传GitHub。
'''
(O/'排序敏感性分析报告.md').write_text(text,encoding='utf-8')
v=json.loads((O/'verification.json').read_text());v.update(independent_GL_coverage_checks=count,gate_checks_passed=True,shortfall_rows=int(a.shortfall.gt(0).sum()));(O/'verification.json').write_text(json.dumps(v,indent=2),encoding='utf-8');print('RECOUNT',count,'SHORTFALL',int(a.shortfall.gt(0).sum()));print(view.to_string(index=False))
