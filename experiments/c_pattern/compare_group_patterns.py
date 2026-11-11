from pathlib import Path
import json,hashlib,html
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.spatial.distance import pdist,squareform
R=Path(__file__).resolve().parent;O=R/'pattern_similarity';O.mkdir(exist_ok=True)
source=R/'patterns/rule_evidence.csv.gz'
parts=[]
for chunk in pd.read_csv(source,dtype={'group_id':str,'seed':str},keep_default_na=False,low_memory=False,chunksize=100000):parts.append(chunk[chunk.method.isin(['G','L'])])
e=pd.concat(parts,ignore_index=True)
for col in ['support','confidence','lift','outside_support','outside_confidence','support_difference','global_rank']:e[col]=pd.to_numeric(e[col],errors='coerce')
e['scope']=np.where(e.method.eq('G'),'G','C'+e.group_id)
e['itemset']=e.apply(lambda r:json.dumps(sorted(set(json.loads(r.antecedent)+json.loads(r.consequent)))),axis=1)
e['length']=e.itemset.map(lambda z:len(json.loads(z)))
scopes=['C0','C1','C2','G'];names=pd.read_csv(R/'pattern_analysis/product_names.csv',dtype=str).set_index('stock_code').description.to_dict()
# Group identical unions before selecting Top K; highest-ranked eligible direction represents the union.
ranked={};toprows=[]
for scope in scopes:
 p=e[(e.scope==scope)&e.eligible&e.generated_here].sort_values(['joint_count','confidence','lift','rule_id'],ascending=[False,False,False,True]).drop_duplicates('itemset').copy()
 p['combination_rank']=range(1,len(p)+1);ranked[scope]=p
 q=p.head(20).copy();q['products']=q.itemset.map(lambda z:' + '.join(names.get(c,c).strip() for c in json.loads(z)));toprows.append(q)
pd.concat(toprows).to_csv(O/'top20_unique_combinations.csv',index=False)
jacc={};overlap=[]
for k in [10,20]:
 matrix=np.eye(4)
 for i,a in enumerate(scopes):
  for j,b in enumerate(scopes):
   A=set(ranked[a].itemset.head(k));B=set(ranked[b].itemset.head(k));assert len(A)==k and len(B)==k
   matrix[i,j]=len(A&B)/len(A|B)
   if i<j:overlap.append({'k':k,'a':a,'b':b,'intersection':len(A&B),'union':len(A|B),'jaccard':matrix[i,j]})
 assert np.allclose(matrix,matrix.T);jacc[k]=matrix;pd.DataFrame(matrix,index=scopes,columns=scopes).to_csv(O/f'jaccard_top{k}.csv')
pd.DataFrame(overlap).to_csv(O/'topk_overlap_counts.csv',index=False)
# All shared-pool unions, including rules not eligible in the target group.
assert e.groupby(['scope','itemset']).support.nunique().max()==1
unique=e.drop_duplicates(['scope','itemset']);vectors=unique.pivot(index='itemset',columns='scope',values='support')[scopes];assert vectors.notna().all().all()
weights=np.array([801,2173,4547])/7521
assert np.allclose(vectors[['C0','C1','C2']].to_numpy()@weights,vectors.G)
distances={};means={}
for length in [2,3]:
 v=vectors.loc[vectors.index.map(lambda z:len(json.loads(z))==length)]
 d=squareform(pdist(v.T.to_numpy(),metric='braycurtis'));distances[length]=(d,len(v));pd.DataFrame(d,index=scopes,columns=scopes).to_csv(O/f'support_braycurtis_length{length}.csv')
 md=np.abs(v.to_numpy().T[:,None,:]-v.to_numpy().T[None,:,:]).mean(axis=2)*100;means[length]=md;pd.DataFrame(md,index=scopes,columns=scopes).to_csv(O/f'support_mean_gap_pp_length{length}.csv')
# Predeclared representative policy: three largest positive support gaps + strongest negative example per group; distinct unions.
examples=[]
for scope in scopes[:3]:
 p=e[(e.scope==scope)&e.eligible].copy();p['confidence_gap_pp']=(p.confidence-p.outside_confidence)*100
 for typ,q in [('positive',p[p.support_difference>0].sort_values(['support_difference','joint_count','rule_id'],ascending=[False,False,True]).drop_duplicates('itemset').head(3)),('counterexample',p[p.support_difference<0].sort_values(['support_difference','joint_count','rule_id'],ascending=[True,False,True]).drop_duplicates('itemset').head(1))]:
  q=q.copy();q['case_type']=typ;examples.append(q)
cases=pd.concat(examples);cases['antecedent_name']=cases.antecedent.map(lambda z:' + '.join(names.get(c,c).strip() for c in json.loads(z)));cases['consequent_name']=cases.consequent.map(lambda z:' + '.join(names.get(c,c).strip() for c in json.loads(z)))
assert np.allclose(cases.joint_count/cases.n_baskets,cases.support)
assert np.allclose(cases.outside_joint_count/cases.outside_baskets,cases.outside_support)
assert np.allclose(cases.antecedent_count*cases.confidence,cases.joint_count)
cases.to_csv(O/'representative_rules.csv',index=False)
plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':11})
def plot(matrices,titles,cmap,filename,title,note):
 fig,axs=plt.subplots(1,2,figsize=(11,6))
 for ax,m,t in zip(axs,matrices,titles):
  im=ax.imshow(m,cmap=cmap,vmin=0,vmax=1);ax.set_xticks(range(4),scopes);ax.set_yticks(range(4),scopes);ax.set_title(t,pad=15)
  for i in range(4):
   for j in range(4):ax.text(j,i,f'{m[i,j]:.3f}',ha='center',va='center',color='white' if m[i,j]>.55 else '#14283c',fontsize=13)
 fig.colorbar(im,ax=axs.ravel().tolist(),fraction=.025,pad=.04)
 fig.suptitle(title,fontsize=17,fontweight='bold');fig.text(.06,.035,note,fontsize=9);fig.subplots_adjust(top=.80,bottom=.16,left=.07,right=.86,wspace=.3);fig.savefig(O/(filename+'.png'),dpi=200);fig.savefig(O/(filename+'.svg'));plt.close(fig)
plot([jacc[10],jacc[20]],['Top10 不同商品组合','Top20 不同商品组合'],'Blues','01_jaccard','热门商品组合重合：Jaccard 相似度（越大越相似）','先按商品并集去重，再取Top-K；不是系统预算实验。Discovery描述性结果，非未来效果。')
plot([distances[2][0],distances[3][0]],[f'二商品组合（共同池 {distances[2][1]} 个）',f'三商品组合（共同池 {distances[3][1]} 个）'],'Oranges','02_support_distance','共同池支持度：Bray–Curtis 差异度（越大越不同）','相同商品并集只计一次；未达该群筛选门槛仍使用实际support。G包含自身，尤其受C2影响。')
# Support profile of all representative unions, including negative examples.
keys=list(dict.fromkeys(cases.itemset));v=vectors.loc[keys]*100
fig,ax=plt.subplots(figsize=(11,8));im=ax.imshow(v.to_numpy(),cmap='YlGnBu',aspect='auto');ax.set_xticks(range(4),scopes);ax.set_yticks(range(len(keys)),[' + '.join(json.loads(k)) for k in keys]);ax.set_ylabel('代表组合的商品编码（名称及方向见报告）')
for i in range(len(keys)):
 for j in range(4):ax.text(j,i,f'{v.iloc[i,j]:.2f}%',ha='center',va='center',color='white' if v.iloc[i,j]>v.to_numpy().max()*.6 else '#14283c')
fig.colorbar(im,ax=ax,label='Support（%）');ax.set_title('代表组合在三个群与全局的支持度',fontsize=16,pad=18);fig.text(.04,.025,'每群取支持度正差最大的3个组合及负差最大的1个反例；探索性选例，不能用于显著性结论。',fontsize=9);fig.tight_layout(rect=[0,.07,1,.96]);fig.savefig(O/'03_case_support.png',dpi=200);plt.close(fig)
show=cases[['scope','case_type','antecedent_name','consequent_name','n_baskets','outside_baskets','antecedent_count','outside_antecedent_count','joint_count','outside_joint_count','support','outside_support','confidence','outside_confidence','confidence_gap_pp','global_rank']].copy()
for c in ['support','outside_support','confidence','outside_confidence']:show[c]=show[c].map(lambda v:f'{v:.2%}' if pd.notna(v) else '不可估')
show.columns=['群','类型','前件','后件','群内篮数','群外篮数','群内前件次数','群外前件次数','群内联合次数','群外联合次数','群内support','群外support','群内confidence','群外confidence','confidence差(百分点)','全局排名']
body='''<meta charset="utf-8"><style>body{font:16px Microsoft YaHei;margin:32px;color:#24384f;line-height:1.7}table{border-collapse:collapse;font-size:13px}td,th{padding:9px;border-bottom:1px solid #ccd4df}th{background:#e4edf7}img{max-width:1100px;width:100%}.table{overflow:auto}</style><h1>顾客群购物模式相似度与差异度</h1><p>仅Discovery。Top-K先将商品并集相同的合格方向规则合并，再按该组合排名最高的方向规则排序（联合次数、confidence、lift降序，rule_id升序），取K个不同组合。该规则明确处理同次数的并列，不把相同商品集合重复计算。</p><p>共同池差异使用全部G/L/R候选的不同商品并集，对各群重新计算的真实support，包含未达各群筛选门槛者。二商品和三商品分别比较；Bray–Curtis=Σ|sᵢ−tᵢ|/Σ(sᵢ+tᵢ)，不对向量归一化为概率。池来源仍影响指标，不涵盖所有未入池商品组合。</p><p>Jaccard越大越相似；Bray–Curtis越大越不同。C2占60.5%的Discovery订单，G是群体加权混合；群vsG有自身重叠，不能当独立样本。未做随机距离对照、置信区间或Validation验证，差异大不等于更有用。</p><img src="01_jaccard.png"><img src="02_support_distance.png"><img src="03_case_support.png"><h2>各群 vs 群外：代表规则与计数</h2><p>每群选择support正差最大的3个不同商品集合，以及负差最大的1个反例；均为该群合格规则，保留代表方向。群外为其他两个真实群的合格Discovery订单。全局排名空白表示未通过完整全局筛选。百分比为展示舍入。</p>'''
(O/'群体相似度分析.html').write_text(body+'<div class="table">'+show.to_html(index=False,escape=True,float_format=lambda v:f'{v:.2f}',na_rep='—')+'</div>',encoding='utf-8')
(O/'manifest.json').write_text(json.dumps({'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'unique_common_pool_by_length':{str(k):n for k,(d,n) in distances.items()},'scope_order':scopes,'checks':['exact TopK cardinalities','symmetric matrices','duplicate-union support consistency','global support equals weighted group support','case support and confidence counts checked'],'status':'discovery_descriptive_only'},indent=2),encoding='utf-8')
print('JACCARD',pd.DataFrame(overlap).to_string(index=False));print('DISTANCES');print({k:np.round(d,4).tolist() for k,(d,n) in distances.items()});print('CASES',cases[['scope','case_type','antecedent_name','consequent_name','support_difference']].to_string(index=False))
