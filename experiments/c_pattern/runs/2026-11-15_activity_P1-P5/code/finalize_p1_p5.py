from pathlib import Path
import json,hashlib,shutil
import numpy as np
import pandas as pd
R=Path('C:/Users/83946/Desktop/intro2datamining/project');O=R/'category_P1_P5_handoff'
controls=['GL','S','A1','A2'];cfg={'P1':(.01,.2,1,None),'P2':(.02,.4,1.3,None),'P3':(.03,.5,1.5,None),'P4':(.02,.4,1.3,5),'P5':(.02,.4,1.3,10)}
scope=pd.concat([pd.read_csv(O/'summaries'/f'scope_summary_{c}.csv',dtype={'seed':str,'group_id':str},keep_default_na=False) for c in controls],ignore_index=True)
alloc=pd.concat([pd.read_csv(O/'summaries'/f'allocation_audit_{c}.csv',dtype={'seed':str,'group_id':str},keep_default_na=False) for c in controls],ignore_index=True)
metrics=pd.concat([pd.read_csv(O/'summaries'/f'system_metrics_{c}.csv',dtype={'seed':str},keep_default_na=False) for c in controls],ignore_index=True)
assert len(scope)==9960 and len(alloc)==9960 and len(metrics)==6660
assert len(list((O/'evidence').glob('*.csv.gz')))==664
assert scope.groupby('control').scope_id.nunique().to_dict()=={'GL':4,'S':60,'A1':300,'A2':300}
assert not scope.duplicated(['scope_id','config','length']).any()
# Reconcile P1-P4 against previous screening counts, using integer counts.
for control in controls:
 src=pd.read_csv(R/'category_screening/scope_summary.csv',dtype={'seed':str,'group_id':str},keep_default_na=False) if control in ['GL','S'] else pd.read_csv(R/f'activity_controls_{control}/l2/screening_counts.csv',dtype={'seed':str,'group_id':str},keep_default_na=False)
 src=src[src.method.ne('R') if control=='GL' else src.method.eq('R')]
 for p,c,inc in [('P1','baseline',False),('P2','moderate',False),('P3','strict',False),('P4','moderate',True)]:
  incval=('increment5pp' if inc else 'no_increment') if control in ['GL','S'] else inc
  z=src[src.config.eq(c)&src.increment.eq(incval)&src.length.isin([2,3])]
  new=scope[scope.control.eq(control)&scope.config.eq(p)&scope.length.isin([2,3])]
  j=new.merge(z,on=['method','seed','group_id','length'],suffixes=('_new','_old'));assert len(j)==len(new) and (j.rules_new==j.rules_old).all(),(control,p)
for name,d in [('scope_summary',scope),('allocation_audit',alloc),('system_metrics',metrics)]:d.to_csv(O/f'{name}.csv',index=False)
scope[scope['empty']].to_csv(O/'empty_scope_checks.csv',index=False)
alloc[alloc.shortfall.gt(0)].to_csv(O/'budget_shortfalls.csv',index=False)
rows=[]
for (p,B,flow),z in metrics.groupby(['config','budget','flow']):
 g=z[z.method.eq('G')].coverage.iloc[0];l=z[z.method.eq('L')].coverage.iloc[0]
 for c,n in [('S',20),('A1',100),('A2',100)]:
  v=z[z.control.eq(c)&z.method.eq('R')].coverage;assert len(v)==n
  rows.append(dict(config=p,budget=B,flow=flow,control=c,G=g,L=l,random_median=v.median(),random_min=v.min(),random_max=v.max(),random_ge_L=int((v>=l-1e-12).sum()),upper_tail=(1+(v>=l-1e-12).sum())/(n+1)))
comp=pd.DataFrame(rows);comp.to_csv(O/'coverage_comparison.csv',index=False)
# Independent verification of every exported selected-rule system against source baskets.
b=pd.read_csv(R/'discovery_baskets.csv',dtype=str);x=np.load(R/'category_patterns/discovery_l2.npy');cols=json.loads((R/'category_patterns/l2_items.json').read_text());N=len(b);ALL=(1<<N)-1
def bits(v):return int.from_bytes(np.packbits(v,bitorder='little').tobytes(),'little')
cb={c:bits(x[:,i]) for i,c in enumerate(cols)};cache={}
def hit(items):
 k=tuple(sorted(items))
 if k not in cache:
  v=ALL
  for c in k:v &=cb[c]
  cache[k]=v
 return cache[k]
lab=pd.read_csv(R/'labels/customer_clusters.csv',dtype=str);assign={('GL','G',''):pd.Series('GLOBAL',index=b.index),('GL','L',''):b.customer_id.map(lab.set_index('customer_id').cluster_id)}
for c in ['S','A1','A2']:
 path=R/'labels/random_groups.csv' if c=='S' else R/f'activity_controls_{c}/random_groups_{c}_{"profile_frequency" if c=="A1" else "discovery_baskets"}.csv'
 rr=pd.read_csv(path,dtype=str)
 for seed,z in rr.groupby('seed'):assign[(c,'R',seed)]=b.customer_id.map(z.set_index('customer_id').random_group_id)
verified=0;selectedrows=0
for c in controls:
 for p in cfg:
  sel=pd.read_csv(O/'selected_rules'/f'{p}_{c}.csv.gz',dtype={'seed':str,'group_id':str},keep_default_na=False);assert sel['passes_'+p].all();selectedrows+=len(sel)
  for (method,seed,B),z in sel.groupby(['method','seed','budget']):
   assignment=assign[(c,method,seed)];local=shared=0
   for g,q in z.groupby('group_id'):
    mask=bits(assignment.eq(g).to_numpy());assert q.rank_within_group.tolist()==list(range(1,len(q)+1))
    for r in q.itertuples():h=hit(json.loads(r.antecedent)+json.loads(r.consequent));local|=h&mask;shared|=h
   for flow,v in [('restricted',local),('shared',shared)]:
    target=metrics[metrics.control.eq(c)&metrics.config.eq(p)&metrics.method.eq(method)&metrics.seed.eq(seed)&metrics.budget.eq(B)&metrics.flow.eq(flow)];assert len(target)==1 and target.covered_orders.iloc[0]==v.bit_count();assert target.actual.iloc[0]==len(z);verified+=1
  print('VERIFIED',c,p,flush=True)
assert verified==6660
inputs=[R/'labels/customer_clusters.csv',R/'labels/random_groups.csv',R/'activity_controls_A1/random_groups_A1_profile_frequency.csv',R/'activity_controls_A2/random_groups_A2_discovery_baskets.csv',R/'taxonomy_analysis/item_taxonomy_v1.csv',R/'taxonomy_analysis/taxonomy_v1.json',R/'category_patterns/l2_items.json']
for f in inputs:shutil.copy2(f,O/'inputs'/f.name)
pd.DataFrame([dict(config=p,support=v[0],confidence=v[1],lift=v[2],min_joint_count=20,min_antecedent_count=20,triple_increment_pp=v[3]) for p,v in cfg.items()]).to_csv(O/'configurations.csv',index=False)
def md(d):return '| '+' | '.join(d.columns)+' |\n|'+'|'.join(['---']*len(d.columns))+'|\n'+'\n'.join('| '+' | '.join(map(str,r))+' |' for r in d.itertuples(index=False,name=None))
real=scope[scope.control.eq('GL')&scope.length.isin([2,3])].pivot(index=['method','group_id','config'],columns='length',values='rules').reset_index().rename(columns={2:'二品类规则',3:'三品类规则'});real.columns=list(map(str,real.columns));real.to_csv(O/'GL_rule_counts.csv',index=False)
summary=comp[comp.control.eq('A1')].copy()
for col in ['G','L','random_median','random_min','random_max']:summary[col]=summary[col].map(lambda v:f'{100*v:.2f}%')
summary.upper_tail=summary.upper_tail.round(4)
text='''# 给D：P1–P5品类层Discovery交接包

## 本次交付与定位

五套配置均已基于同一Discovery证据筛选完成，未重新跑FP-Growth，未使用Validation/Test。A1为主随机对照；S为参考；A2为敏感性分析。此前“严格档+5pp”不在这五套中，不能替代P3或P4。

范围为品类层l2_id：订单内去重，排除other，冻结taxonomy v1。Discovery共有7521个订单；空篮和单品类篮仍计入分母。G/L共用一份输出（control=GL）；随机S种子42–61共20个，A1/A2种子1000–1099各100个。共664个范围、222个系统。A1/A2相同seed编号不表示同一分组，所有关联必须包含control。

## 五套配置

|配置|support|confidence|lift|联合/前件最低次数|三品类增量|
|---|---|---|---|---|---|
|P1 Loose|1%|20%|1.0|各20|不启用|
|P2 Moderate|2%|40%|1.3|各20|不启用|
|P3 Strict|3%|50%|1.5|各20|不启用|
|P4 Moderate+|2%|40%|1.3|各20|≥5pp|
|P5 Moderate++|2%|40%|1.3|各20|≥10pp|

三品类规则仅为AB→C：增量=conf(AB→C)−max(conf(A→C),conf(B→C))，不是相对百分比。字段confidence_increment_pp以百分点表示。两个单前件置信度直接从证据计算，不要求单前件规则通过本配置。二品类A→B不检查增量，因此P2/P4/P5二品类规则完全一致。门槛包含等号；增量浮点容差1e-10pp。

## 先读哪些文件

- `configurations.csv`：冻结的五套参数。
- `selected_rules/Px_GL.csv.gz`：G/L的预算20/50/100选中规则，带完整Discovery证据；D可首先评价这部分。
- `selected_rules/Px_A1.csv.gz`：主随机对照的100个种子。S/A2同名文件用于补充。
- `eligible_rules/Px_<control>.csv.gz`：本配置所有合格规则清单，列为scope_id、rule_id、rank_within_group；这是完整清单，不仅是Top榜单。
- `evidence/<scope_id>.csv.gz`：该范围P1合格规则的共享证据，包含passes_P1…passes_P5、群内外次数、support/confidence/lift、增量与两个单前件规则ID。因为P2–P5均为P1子集，各配置证据都在此。用(scope_id,rule_id)关联对应清单；不要只用rule_id，也不要依赖行号。全局的群外分母为0，相关率留空。
- `scope_summary.csv`：每配置每范围的规则数、去重商品组合数、全体合格规则覆盖率和空组标记。length=0为二/三品类合计，2和3分开列；不能把三者相加。
- `allocation_audit.csv`：每预算的各组配额、实际规则数、长度组成和缺额。
- `system_metrics.csv`：每个随机种子独立的全系统覆盖率，包含限群和共享两种口径。
- `coverage_comparison.csv`：G/L与各随机对照的中位数、范围和经验上尾比例。
- `empty_scope_checks.csv`、`budget_shortfalls.csv`：空组与缺额明细；只有表头表示没有此类情况。
- `inputs/`：冻结的真实群标签、三种随机标签、taxonomy及l2词表。
- `load_rules.py`：按配置与范围读取/导出完整合格规则证据的示例工具。

## 固定预算和评价口径

系统总预算20/50/100；G独占预算，L和每个随机种子按各组Discovery订单数使用最大余数法分配，平局按group_id。排序为joint_count降序、confidence降序、lift降序、rule_id升序；二/三品类混合排序，不设长度配额，不额外做语义分层。不同群同一规则和反向规则分别占名额。若候选不足则如实记录缺额，不从其他群补位。

restricted：只匹配订单所属群的规则。shared：将同一批群规则合并供所有订单匹配，重复规则不返还预算。两者是不同使用场景，Validation前应确定主评价口径；不要看结果后切换主口径。

coverage：订单同时含前件和后件，匹配任一规则即计一次，分母7521。antecedent_coverage：仅前件命中。这些不是推荐准确率或因果增益。合格规则数按有方向的规则计；unique_combinations按不分方向的商品集合计。规则总量、组合数和预算名额不能混用。

## D在Validation阶段怎么用

1. 将五套配置×三种预算作为事先约定的比较集合。直接使用本包冻结的选中规则，不按Validation表现重新排序或替换规则。群标签、taxonomy与Discovery配额也保持冻结；新客户和未覆盖SKU/l2的处理应事先约定并单列覆盖率。
2. 在Validation订单上重算联合/前件/后件次数、support/confidence/lift、覆盖率与规则保留情况。评价低计数/零前件时标为证据不足或未触达，不能沿用Discovery置信度；零分母应留空而非伪造为0。
3. 增量验证要同步重算两个单前件置信度，二品类不套用增量筛选。报告Validation下仍满足预设门槛的比例，但不要悄悄删掉失败规则后重新补满预算。
4. 为每个种子输出一个系统指标，再汇总100次A1。不能把三个组或三个组对当独立重复；A1为主，S/A2结果分开报告。A2用了Discovery活跃度，不能宣称为完全只用Profile信息的部署对照。
5. 事先确定选择目标和并列处理：例如优先验证覆盖、规则稳定性或增量价值。不要只凭Discovery最大覆盖选择配置。Validation用于选择，Test仅用于最终冻结方案评价。

经验上尾比例=(1+随机≥L次数)/(1+种子数)，并列含1e-12比例容差；不是p=0，不作未经约定的多重比较显著性结论。本包未读取B的结果，未运行Validation/Test，未上传GitHub。

## G/L规则数量

'''+md(real)+'\n\n## A1主对照的Discovery覆盖率\n\n'+md(summary)+'\n'
text+='\n## 完整性检查\n\n'+f'664个范围、9960行范围统计、6660行系统评价；全部{verified}条预算/匹配方式覆盖率已由导出的规则在源订单上独立重算一致。P1–P4规则数逐范围复现旧筛选结果；P2/P4/P5二品类一致；P5⊆P4⊆P2⊆P1且P3⊆P2。空范围记录{int(scope["empty"].sum())}条（含长度口径），预算缺额记录{int(alloc.shortfall.gt(0).sum())}条。\n'
(O/'D交接说明_P1-P5.md').write_text(text,encoding='utf-8')
manifest=dict(status='passed',scope_count=664,system_count=222,configs=cfg,scope_summary_rows=len(scope),system_metric_rows=len(metrics),selected_rows=selectedrows,independently_verified_metric_rows=verified,empty_scope_rows=int(scope['empty'].sum()),budget_shortfall_rows=int(alloc.shortfall.gt(0).sum()),validation_used=False)
(O/'verification.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(manifest));print(real.to_string(index=False))
