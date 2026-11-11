from pathlib import Path
import json,hashlib,itertools
import numpy as np,pandas as pd
from scipy.spatial.distance import braycurtis
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parent;O=R/'random_similarity';O.mkdir(exist_ok=True)
src=R/'patterns/rule_evidence.csv.gz';e=pd.read_csv(src,dtype={'seed':str,'group_id':str},keep_default_na=False,low_memory=False)
for col in ['support','outside_support','confidence','lift']:e[col]=pd.to_numeric(e[col],errors='coerce')
# Cache union mapping once per direction rule, not once per scope.
base=e[e.method.eq('G')];keys={r.rule_id:json.dumps(sorted(set(json.loads(r.antecedent)+json.loads(r.consequent)))) for r in base.itertuples()};e['itemset']=e.rule_id.map(keys);e['length']=e.itemset.map(lambda z:len(json.loads(z)))
global_support=base.assign(itemset=base.rule_id.map(keys)).drop_duplicates('itemset').set_index('itemset').support.sort_index()
seeds=sorted(e.loc[e.method.eq('R'),'seed'].unique(),key=int);assert len(seeds)==20
details=[];stats=[];sizes=[]
for method,seed in [('L','')]+[('R',s) for s in seeds]:
 p=e[e.method.eq(method)&e.seed.eq(seed)].copy();groups=sorted(p.group_id.unique());assert groups==['0','1','2']
 ranked={};vectors={};outside={};n={}
 for g in groups:
  t=p[p.group_id.eq(g)];assert t.groupby('itemset').support.nunique().max()==1
  unique=t.drop_duplicates('itemset').set_index('itemset').sort_index();assert unique.index.equals(global_support.index)
  vectors[g]=unique.support;outside[g]=unique.outside_support;n[g]=int(unique.n_baskets.iloc[0]);assert unique.outside_baskets.eq(7521-n[g]).all()
  assert np.allclose(vectors[g]*n[g]+outside[g]*(7521-n[g]),global_support*7521)
  q=t[t.eligible&t.generated_here].sort_values(['joint_count','confidence','lift','rule_id'],ascending=[False,False,False,True]).drop_duplicates('itemset')
  ranked[g]=q;assert len(q)>=20
  sizes.append({'method':method,'seed':seed,'group':g,'n_baskets':n[g],'qualified_unions':len(q)})
 assert sum(n.values())==7521
 # One equal-weight aggregate per seed; three dependent group-pairs are not independent replicates.
 for k in [10,20]:
  values=[]
  for a,b in itertools.combinations(groups,2):
   A=set(ranked[a].itemset.head(k));B=set(ranked[b].itemset.head(k));j=len(A&B)/len(A|B);values.append(1-j)
   details.append({'method':method,'seed':seed,'family':'pair_jaccard','setting':k,'group_a':a,'group_b':b,'similarity':j,'difference':1-j,'intersection':len(A&B)})
  stats.append({'method':method,'seed':seed,'metric':f'pair_jaccard_distance_top{k}','value':np.mean(values)})
 for length in [2,3]:
  selected=global_support.index.map(lambda z:len(json.loads(z))==length);pair=[];rest=[];absolute=[]
  for a,b in itertools.combinations(groups,2):
   d=braycurtis(vectors[a].to_numpy()[selected],vectors[b].to_numpy()[selected]);pair.append(d)
   details.append({'method':method,'seed':seed,'family':'pair_braycurtis','setting':length,'group_a':a,'group_b':b,'difference':d})
  for g in groups:
   v=vectors[g].to_numpy()[selected];w=outside[g].to_numpy()[selected];d=braycurtis(v,w);gap=np.mean(np.abs(v-w))*100;rest.append(d);absolute.append(gap)
   details.append({'method':method,'seed':seed,'family':'group_vs_rest','setting':length,'group_a':g,'group_b':'REST','difference':d,'mean_absolute_support_gap_pp':gap,'n_patterns':int(sum(selected))})
  for metric,values in [(f'pair_braycurtis_len{length}',pair),(f'rest_braycurtis_len{length}',rest),(f'rest_mean_abs_support_pp_len{length}',absolute)]:stats.append({'method':method,'seed':seed,'metric':metric,'value':np.mean(values)})
summary=pd.DataFrame(stats);detail=pd.DataFrame(details);summary.to_csv(O/'seed_level_metrics.csv',index=False);detail.to_csv(O/'pair_and_group_details.csv',index=False);pd.DataFrame(sizes).to_csv(O/'scope_sizes.csv',index=False)
comparisons=[]
for metric,frame in summary.groupby('metric',sort=False):
 obs=float(frame.loc[frame.method.eq('L'),'value'].iloc[0]);r=frame.loc[frame.method.eq('R'),'value'].to_numpy();assert len(r)==20
 comparisons.append({'metric':metric,'real':obs,'random_min':min(r),'random_median':np.median(r),'random_max':max(r),'real_minus_random_median':obs-np.median(r),'random_less_than_real':int(sum(r<obs)),'random_equal_real':int(sum(np.isclose(r,obs,rtol=0,atol=1e-12))),'random_greater_equal_real':int(sum(r>=obs))})
comp=pd.DataFrame(comparisons);comp.to_csv(O/'real_vs_random_summary.csv',index=False)
# Confirm the real-group calculations reproduce the previous analysis.
previous=pd.read_csv(R/'pattern_similarity/topk_overlap_counts.csv')
for k in [10,20]:
 expected=1-previous[(previous.k==k)&previous.a.ne('G')&previous.b.ne('G')].jaccard.mean();actual=summary[(summary.method=='L')&(summary.metric==f'pair_jaccard_distance_top{k}')].value.iloc[0];assert np.isclose(expected,actual)
for length in [2,3]:
 m=pd.read_csv(R/f'pattern_similarity/support_braycurtis_length{length}.csv',index_col=0).loc[['C0','C1','C2'],['C0','C1','C2']].to_numpy();expected=m[np.triu_indices(3,1)].mean();actual=summary[(summary.method=='L')&(summary.metric==f'pair_braycurtis_len{length}')].value.iloc[0];assert np.isclose(expected,actual)
plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False})
labels={'pair_jaccard_distance_top10':'Top10：平均 Jaccard 差异度','pair_jaccard_distance_top20':'Top20：平均 Jaccard 差异度','pair_braycurtis_len2':'二商品：组间平均 Bray–Curtis','pair_braycurtis_len3':'三商品：组间平均 Bray–Curtis','rest_braycurtis_len2':'二商品：组与群外平均 Bray–Curtis','rest_braycurtis_len3':'三商品：组与群外平均 Bray–Curtis','rest_mean_abs_support_pp_len2':'二商品：组与群外平均支持度绝对差','rest_mean_abs_support_pp_len3':'三商品：组与群外平均支持度绝对差'}
for page,metrics in [('01_between_groups',list(labels)[:4]),('02_group_vs_rest',list(labels)[4:])]:
 fig,axs=plt.subplots(2,2,figsize=(12,7.5))
 for ax,metric in zip(axs.flat,metrics):
  c=comp[comp.metric.eq(metric)].iloc[0];v=summary[(summary.metric==metric)&summary.method.eq('R')].value.to_numpy();ax.scatter(v,np.linspace(-.13,.13,20),s=38,color='#527ba9',label='随机：每点1个种子');ax.plot([min(v),max(v)],[0,0],color='#527ba9',alpha=.25);ax.axvline(c.random_median,color='#527ba9',ls='--',label=f'随机中位 {c.random_median:.3f}');ax.axvline(c.real,color='#d38b20',lw=2,label=f'真实分群 {c.real:.3f}');ax.set_ylim(-.22,.35);ax.set_yticks([]);ax.set_title(labels[metric],fontsize=11);ax.set_xlabel('百分点（越大差异越大）' if '_pp_' in metric else '差异度（越大差异越大）');ax.legend(fontsize=8,loc='upper left');ax.grid(axis='x',alpha=.15)
 fig.suptitle('真实分群与20次随机顾客分组的差异对照',fontsize=17,fontweight='bold');fig.text(.04,.025,'Discovery探索性分析｜每个种子内等权平均3个组对或3个组｜共同池固定｜散点范围不是置信区间',fontsize=9);fig.tight_layout(rect=[0,.06,1,.94]);fig.savefig(O/(page+'.png'),dpi=200);fig.savefig(O/(page+'.svg'));plt.close(fig)
view=comp.copy();view.metric=view.metric.map(labels)
body='''<meta charset="utf-8"><style>body{font:16px Microsoft YaHei;max-width:1250px;margin:32px auto;color:#24384f;line-height:1.7}table{border-collapse:collapse;font-size:13px}td,th{padding:10px;border-bottom:1px solid #ccd4df}img{width:100%}</style><h1>随机分组：群体差异对照</h1><p>沿用既有20个seed（42–61），顾客级置换保持Profile组人数，所有方法使用同一7521个Discovery购物篮。Top-K先合并商品并集，再按最佳合格方向规则排序；K=10/20。共同池包含2134个二商品组合、2326个三商品组合，使用实际support，不把未过门槛者置零。</p><p>每个种子先对3个组对等权平均：Jaccard差异=1-J，Bray–Curtis为支持度向量距离；组vs群外先分别计算，再对3组等权平均。平均绝对支持度差以百分点表示。20个种子构成20个随机汇总值，不把60个组对当作独立样本。明细保留，未按结果挑种子。</p><h2>解释边界</h2><ul><li>共同池由真实及这些随机组共同产生并固定，比较是条件于该候选池的探索性诊断，不是完整重抽样的正式置换检验。多个指标无多重检验处理，因此不报告显著性p值。</li><li>随机标签匹配Profile顾客组人数，不匹配Discovery各组订单数、活跃度、篮子大小及商品边际频率。真实差异较大仍可能反映这些因素，不能直接归因于独特商品偏好。</li><li>随机样本只有20个：真实值高于全部20个，也不能据此宣称极小p值或稳定优势。范围不是置信区间。</li><li>本结果不证明规则更有用、更高覆盖或未来保持；下一步须冻结候选与政策后在Validation重复检查。若需稳健性，可预先规定按历史活跃度分层置换，但不按Test结果修改。</li></ul>'''
(O/'随机差异对照报告.html').write_text(body+view.to_html(index=False,float_format=lambda x:f'{x:.4f}')+'<img src="01_between_groups.png"><img src="02_group_vs_rest.png">',encoding='utf-8')
(O/'manifest.json').write_text(json.dumps({'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'seeds':seeds,'aggregation':'equal mean of 3 pairs or 3 groups within seed','status':'exploratory_conditional_on_fixed_pool_no_formal_p_values','checks':['20 seeds each metric','exact Top-K cardinalities','three groups sum to 7521','group plus outside reconstruct global support','real statistics reproduce previous analysis']},indent=2),encoding='utf-8')
print(comp.to_string(index=False))
