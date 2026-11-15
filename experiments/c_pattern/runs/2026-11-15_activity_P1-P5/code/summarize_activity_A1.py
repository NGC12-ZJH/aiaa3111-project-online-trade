from pathlib import Path
import argparse,json,itertools
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser();p.add_argument('--root',required=True);R=Path(p.parse_args().root);O=R/'activity_controls_A1'
b=pd.read_csv(R/'discovery_baskets.csv',dtype=str);lab=pd.read_csv(R/'labels/customer_clusters.csv',dtype=str);rr=pd.read_csv(R/'labels/random_groups.csv',dtype=str);real=b.customer_id.map(lab.set_index('customer_id').cluster_id)
old=[]
for layer in ['sku','l2']:
 if layer=='sku':
  sel=pd.read_csv(R/'patterns/selected_rules.csv',dtype={'seed':str,'group_id':str},keep_default_na=False);sel=sel[sel.flow.eq('native')];x=np.load(R/'discovery.npy');cols=json.loads((R/'items.json').read_text())
 else:sel=pd.read_csv(R/'category_fixed_budget/selected_rules.csv',dtype={'seed':str,'group_id':str},keep_default_na=False,low_memory=False);x=np.load(R/'category_patterns/discovery_l2.npy');cols=json.loads((R/'category_patterns/l2_items.json').read_text())
 ix={c:i for i,c in enumerate(cols)};cache={}
 def hit(items):
  key=tuple(sorted(items))
  if key not in cache:cache[key]=x[:,[ix[c] for c in key]].all(1)
  return cache[key]
 for (method,seed,B),z in sel.groupby(['method','seed','budget']):
  assignment=pd.Series('GLOBAL',index=b.index) if method=='G' else real if method=='L' else b.customer_id.map(rr[rr.seed.eq(seed)].set_index('customer_id').random_group_id)
  cov=np.zeros(len(b),bool);shared=cov.copy()
  for row in z.itertuples():
   h=hit(json.loads(row.antecedent)+json.loads(row.consequent));shared|=h;cov|=h&assignment.eq(row.group_id).to_numpy()
  for flow,v in [('restricted',cov),('shared',shared)]:old.append(dict(layer=layer,control='S',method=method,seed=seed,budget=B,flow=flow,coverage=v.mean(),actual=len(z)))
old=pd.DataFrame(old);old.to_csv(O/'S_recomputed_system_metrics.csv',index=False)
combined=[old]
for layer in ['sku','l2']:
 d=pd.read_csv(O/layer/'system_metrics.csv',dtype={'seed':str},keep_default_na=False);d['layer']=layer;combined.append(d)
allm=pd.concat(combined,ignore_index=True);allm.to_csv(O/'all_system_metrics.csv',index=False);comparisons=[]
for (layer,flow,B),z in allm.groupby(['layer','flow','budget']):
 g=z[z.method.eq('G')].coverage.to_numpy();l=z[z.method.eq('L')].coverage.to_numpy();assert np.allclose(g,g[0]) and np.allclose(l,l[0])
 row=dict(layer=layer,flow=flow,budget=B,G=g[0],L=l[0])
 for control,n in [('S',20),('A1',100)]:
  v=z[z.method.eq('R')&z.control.eq(control)].coverage;assert len(v)==n
  row.update({control+'_median':v.median(),control+'_min':v.min(),control+'_max':v.max(),control+'_ge_real':int((v>=l[0]-1e-12).sum()),control+'_upper_tail':(1+(v>=l[0]-1e-12).sum())/(1+n)})
 comparisons.append(row)
comp=pd.DataFrame(comparisons);comp.to_csv(O/'S_vs_A1_coverage.csv',index=False)
sim=[]
for layer,path in [('sku',R/'random_similarity/seed_level_metrics.csv'),('l2',O/'S_l2_similarity_seed_metrics.csv')]:
 ss=pd.read_csv(path,dtype={'seed':str},keep_default_na=False)
 for metric,z in ss.groupby('metric'):
  l=z[z.method.eq('L')].value.iloc[0];v=z[z.method.eq('R')].value;sim.append(dict(layer=layer,control='S',metric=metric,real=l,median=v.median(),minimum=v.min(),maximum=v.max(),upper_tail=(1+(v>=l-1e-12).sum())/(1+len(v))))
for layer in ['sku','l2']:
 d=pd.read_csv(O/layer/'similarity_comparison.csv')
 for r in d.itertuples():sim.append(dict(layer=layer,control='A1',metric=r.metric,real=r.real,median=r.A1_median,minimum=r.A1_min,maximum=r.A1_max,upper_tail=r.empirical_upper_tail))
pd.DataFrame(sim).to_csv(O/'similarity_summary.csv',index=False)
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False,'font.size':10})
fig,axes=plt.subplots(2,2,figsize=(13,9))
for i,layer in enumerate(['sku','l2']):
 for j,flow in enumerate(['restricted','shared']):
  ax=axes[i,j];z=comp[comp.layer.eq(layer)&comp.flow.eq(flow)].sort_values('budget');B=z.budget.to_numpy()
  ax.plot(B,z.G*100,'o-',label='G',color='#254f7a');ax.plot(B,z.L*100,'o-',label='L',color='#d28c27')
  for control,off,color in [('S',-2,'#999'),('A1',2,'#248e84')]:
   med=z[control+'_median'].to_numpy()*100;lo=z[control+'_min'].to_numpy()*100;hi=z[control+'_max'].to_numpy()*100
   ax.errorbar(B+off,med,yerr=[med-lo,hi-med],fmt='s--',capsize=4,color=color,label=control+(' 20种子' if control=='S' else ' 100种子'))
  ax.set_title(('商品层' if layer=='sku' else '品类层')+' / '+('仅所属群' if flow=='restricted' else '全订单共享'));ax.set_xticks(B);ax.set_xlabel('系统总预算');ax.set_ylabel('完整订单覆盖率（%）');ax.legend(fontsize=9);ax.grid(alpha=.2)
fig.text(.02,.015,'Discovery探索；随机点为中位数、线段为最小—最大值，不是置信区间。商品层沿用原门槛；品类层严格档＋5pp增量。',fontsize=10);fig.tight_layout(rect=[0,.05,1,1]);fig.savefig(O/'S_A1_coverage.png',dpi=180);fig.savefig(O/'S_A1_coverage.svg');plt.close(fig)
def md(d):return '| '+' | '.join(d.columns)+' |\n|'+'|'.join(['---']*len(d.columns))+'|\n'+'\n'.join('| '+' | '.join(str(v) for v in row)+' |' for row in d.itertuples(index=False,name=None))
display=comp.copy()
for c in ['G','L','S_median','S_min','S_max','A1_median','A1_min','A1_max']:display[c]=display[c].map(lambda v:f'{v:.2%}')
for c in ['S_upper_tail','A1_upper_tail']:display[c]=display[c].round(4)
lines=['# A1历史活跃度匹配：100种子独立重跑','日期2026-11-15。A1为主对照，S为旧参考，A2未运行。未读取B的结果。两层都预先固定1000–1099全部100种子；每档每组Profile客户数及文件SHA-256均验证。只在Profile频次档内置换标签，不能解释为精确匹配Discovery篮大小或商品边际频率。','## 口径','商品层沿用原1% support、20联合/前件次数、20% confidence、lift≥1；品类层原生挖掘后记录三档筛选数量，主预算比较用严格档＋三品类增量≥5pp。G/L合格规则ID集合与旧实验逐项一致。每个种子一个系统值，预算20/50/100按Discovery订单数最大余数法分配，无补选；共享使用只解除群限制，不释放重复名额。','候选挖掘覆盖304范围。完整计数以npz保存，数组按candidate_rules.csv行序对齐，包含联合/前件/后件、群外计数、generated和分母。原S候选也纳入证据字典以便同口径比较，但不会冒充A1原生候选。','相似度：Top10/20按各范围当前配置合格原生规则去重组合；support距离固定在原S共同池上，避免候选池改变干扰S/A1对比；不是重新定义候选池后的正式置换检验。每种子三个组对/群外指标等权平均。品类层原S也按同一严格档与增量口径重算随机相似度，支持S/A1并列比较。','## 覆盖对照','![S与A1](S_A1_coverage.png)',md(display),'## 相似度',md(pd.DataFrame(sim).round(4)),'## 解释限制','单侧经验尾部比例=(1+随机指标≥真实的次数)/(1+种子数)，这些指标均按更大为所观察方向；覆盖越大、距离越大不是同一业务含义。此数为探索性尾部统计，不作未经校正的确认性显著结论；多指标无多重比较校正，未用Validation/Test。A1对C2的检验力有限：Profile订单≥5的385人中383人原属C2。','## 文件','各层protocol.json记录预先固定的方案；manifest.json记录完成状态与校验；mined/保留每范围原生候选；counts/为共同池精确计数；scope_audit.csv为订单量和客户量；screening_counts.csv为筛选数量；selected_rules.csv为实际预算规则；system_metrics.csv及similarity_seed_metrics.csv保留逐种子结果。S_vs_A1_coverage.csv与all_system_metrics.csv提供可复核比较。']
(O/'A1独立重跑报告.md').write_text('\n\n'.join(lines),encoding='utf-8');print(comp.to_string(index=False));print(pd.DataFrame(sim).to_string(index=False))


