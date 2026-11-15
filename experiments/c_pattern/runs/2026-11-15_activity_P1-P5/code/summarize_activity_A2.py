from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path('C:/Users/83946/Desktop/intro2datamining/project');O=R/'activity_controls_A2';A=R/'activity_controls_A1'
frames=[pd.read_csv(A/'all_system_metrics.csv',dtype={'seed':str},keep_default_na=False)]
sims=[pd.read_csv(A/'similarity_summary.csv')]
audits=[]
for layer in ['sku','l2']:
 d=pd.read_csv(O/layer/'system_metrics.csv',dtype={'seed':str},keep_default_na=False);d['layer']=layer
 assert len(d)==612 and (d.actual==d.budget).all()
 assert d[d.method.eq('R')].seed.nunique()==100
 pivot=d.pivot(index=['method','seed','budget'],columns='flow',values='coverage');assert (pivot.shared>=pivot.restricted).all()
 old=frames[0];old=old[old.layer.eq(layer)&old.control.eq('A1')&old.method.ne('R')]
 real=d[d.method.ne('R')].merge(old,on=['method','seed','budget','flow'],suffixes=('_new','_old'));assert len(real)==12 and np.allclose(real.coverage_new,real.coverage_old,atol=1e-12)
 audit=pd.read_csv(O/layer/'scope_audit.csv',dtype={'seed':str},keep_default_na=False);assert len(audit)==304
 assert (audit[audit.method.eq('R')].groupby('seed').n_baskets.sum()==7521).all()
 assert len(list((O/layer/'counts').glob('*.npz')))==304
 audits.append(audit[audit.method.eq('R')].groupby('group_id').n_baskets.agg(['min','median','max']).assign(layer=layer).reset_index())
 frames.append(d)
 sim=pd.read_csv(O/layer/'similarity_comparison.csv').rename(columns={'A2_median':'median','A2_min':'minimum','A2_max':'maximum','empirical_upper_tail':'upper_tail'});sim['layer']=layer;sim['control']='A2';sims.append(sim)
allm=pd.concat(frames,ignore_index=True);allm.to_csv(O/'all_system_metrics.csv',index=False)
sim=pd.concat(sims,ignore_index=True)
assert sim.groupby(['layer','metric']).real.agg(lambda x:x.max()-x.min()).max()<1e-10
sim.to_csv(O/'S_A1_A2_similarity.csv',index=False)
rows=[]
for (layer,flow,budget),z in allm.groupby(['layer','flow','budget']):
 g=z[z.method.eq('G')].coverage.iloc[0];l=z[z.method.eq('L')].coverage.iloc[0]
 for control,n in [('S',20),('A1',100),('A2',100)]:
  v=z[z.method.eq('R')&z.control.eq(control)].coverage;assert len(v)==n
  rows.append(dict(layer=layer,flow=flow,budget=budget,control=control,G=g,L=l,median=v.median(),minimum=v.min(),maximum=v.max(),ge_real=int((v>=l-1e-12).sum()),upper_tail=(1+(v>=l-1e-12).sum())/(n+1)))
comp=pd.DataFrame(rows);comp.to_csv(O/'S_A1_A2_coverage.csv',index=False)
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False})
fig,axes=plt.subplots(2,2,figsize=(14,9))
for i,layer in enumerate(['sku','l2']):
 for j,flow in enumerate(['restricted','shared']):
  ax=axes[i,j];z=comp[comp.layer.eq(layer)&comp.flow.eq(flow)];t=z[z.control.eq('A2')]
  ax.plot(t.budget,t.G*100,'o-',label='G');ax.plot(t.budget,t.L*100,'o-',label='L')
  for control,off,col in [('S',-2,'#999999'),('A1',0,'#248e84'),('A2',2,'#9855a4')]:
   t=z[z.control.eq(control)];med=t['median'].to_numpy()*100
   ax.errorbar(t.budget+off,med,yerr=[med-t.minimum.to_numpy()*100,t.maximum.to_numpy()*100-med],fmt='s--',capsize=3,label=control,color=col)
  ax.set_title(('商品层' if layer=='sku' else '品类层')+' / '+('限本群' if flow=='restricted' else '全订单共享'));ax.set_xticks([20,50,100]);ax.set_xlabel('系统总规则预算');ax.set_ylabel('完整订单覆盖率 (%)');ax.grid(alpha=.2);ax.legend()
fig.text(.03,.015,'随机点为中位数，线段为最小—最大值（不是置信区间）；S 20种子，A1/A2 各100种子。',fontsize=10)
fig.tight_layout(rect=[0,.04,1,1]);fig.savefig(O/'S_A1_A2_coverage.png',dpi=180);fig.savefig(O/'S_A1_A2_coverage.svg');plt.close(fig)
def md(d):return '| '+' | '.join(d.columns)+' |\n|'+'|'.join(['---']*len(d.columns))+'|\n'+'\n'.join('| '+' | '.join(map(str,row))+' |' for row in d.itertuples(index=False,name=None))
t=comp[comp.control.eq('A2')].copy()
for c in ['G','L','median','minimum','maximum']:t[c]=t[c].map(lambda v:f'{v*100:.2f}%')
t.upper_tail=t.upper_tail.round(4)
report='''# A2 完整100种子敏感性分析

A1仍为主对照，A2仅作敏感性分析。使用 B 分支 b/activity-random-groups 的提交 13d83b7677dbf12099ab6bb1ad7018609a3b7b99，独立重跑，未读取 B 的结果。

## 方法与冻结口径

- A2按Discovery合格篮子数0/1/2/3–4/5–9/10+分层，只在层内打乱真实客户群标签；每层每组人数保持不变。100个种子1000–1099全部使用。
- 随机文件SHA256：cea8ee0b237ccfd568f5fdc6cb6cff191a085e3554f626e277515dbab3691f40。
- 商品层和品类层各304个范围（G+3个L+300个R）。G/L沿用已核验的挖掘缓存，A2随机范围全部重新挖掘。原S和A1结果不覆盖。
- 商品层原门槛support≥1%、联合及前件≥20、confidence≥20%、lift≥1；品类层严格档support≥3%、confidence≥50%、lift≥1.5，联合及前件≥20，三品类增量confidence≥5个百分点。品类层使用冻结l2映射，订单内去重并排除other。
- 按联合次数、confidence、lift降序和rule_id升序选择；系统预算20/50/100按Discovery群内订单数最大余数法分配，不回收重复规则预算。限群和共享模式使用同一批规则。
- 覆盖率为同时包含前件和后件的订单并集占7521个订单的比例，不是预测准确率。
- 相似度沿用S固定共同池，避免候选空间变化影响support距离；Top-K使用各范围原生合格规则的去重组合。
- 每种子先汇总三个组对/三个群外对比，再与真实系统比较；不能把300个组当独立样本。经验上尾比例=(1+随机≥真实次数)/101，比较包含浮点容差1e-12。

## A2覆盖率

'''+md(t)+'\n\n## S / A1 / A2对照图\n\n![覆盖率](S_A1_A2_coverage.png)\n\n完整数字见 [三对照覆盖率](S_A1_A2_coverage.csv) 和 [三对照相似度](S_A1_A2_similarity.csv)。\n\n## A2相似度\n\n'+md(sim[sim.control.eq('A2')].round(6))+'\n\n## A2群内订单规模\n\n'+md(pd.concat(audits,ignore_index=True))+'\n\n## 解释边界与D交接\n\nA2使用Discovery期活跃度，是更直接控制当期交易量的条件随机对照，不能替代只用Profile信息的A1主对照。它按区间匹配，并不保证每组订单总数或篮子大小完全一致。覆盖更好、support结构差异更大和规则更有预测价值是三个不同结论。所有结果仅为Discovery探索，多个指标未作多重比较校正，最小经验上尾比例为1/101≈0.0099，不报告p=0。Validation/Test尚未运行；交给D前需固定规则、排序、预算和评价口径，不能利用验证结果反向调整本次选择。\n'
(O/'A2敏感性分析报告.md').write_text(report,encoding='utf-8')
(O/'verification.json').write_text(json.dumps(dict(status='passed',seeds=100,scopes_per_layer=304,layers=['sku','l2'],checks=['exact strata and customer labels in mining runner','G/L eligible rule IDs unchanged','G/L coverage identical to A1','all system budgets filled','shared coverage superset','all seed order totals 7521','304 count files each layer','real similarity identical across controls'],B_results_read=False,Validation_run=False),indent=2),encoding='utf-8')
print(comp[comp.control.eq('A2')].to_string(index=False));print(sim[sim.control.eq('A2')].to_string(index=False))
