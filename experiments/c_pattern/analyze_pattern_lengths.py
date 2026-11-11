from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
R=Path(__file__).resolve().parent;O=R/'pattern_length_analysis';O.mkdir(exist_ok=True)
e=pd.read_csv(R/'patterns/rule_evidence.csv.gz',dtype={'seed':str,'group_id':str},keep_default_na=False,low_memory=False)
for c in ['support','confidence','lift','outside_support','outside_confidence','support_difference']:e[c]=pd.to_numeric(e[c],errors='coerce')
e['length']=e.antecedent.map(lambda x:len(json.loads(x))+1);e['itemset']=e.apply(lambda r:json.dumps(sorted(json.loads(r.antecedent)+json.loads(r.consequent))),axis=1)
names=pd.read_csv(R/'pattern_analysis/product_names.csv',dtype=str).set_index('stock_code').description.to_dict()
for c in ['antecedent','consequent']:e[c+'_name']=e[c].map(lambda x:' + '.join(names.get(i,i).strip() for i in json.loads(x)))
q=e[e.eligible&e.generated_here].copy();counts=[];tops=[]
for (method,seed,g),p in e.groupby(['method','seed','group_id']):
 for length in [2,3]:
  z=q[(q.method==method)&(q.seed==seed)&(q.group_id==g)&(q.length==length)].sort_values(['joint_count','confidence','lift','rule_id'],ascending=[False,False,False,True]).copy()
  counts.append(dict(method=method,seed=seed,group_id=g,length=length,qualified_rules=len(z),unique_combinations=z.itemset.nunique()))
  z['rank_within_length']=range(1,len(z)+1);tops.append(z.head(50))
counts=pd.DataFrame(counts);top=pd.concat(tops);counts.to_csv(O/'counts_by_scope_length.csv',index=False);top.to_csv(O/'top50_by_scope_length.csv',index=False)
# Exact comparisons to both single-antecedent rules, even when they fail mining filters.
b=pd.read_csv(R/'discovery_baskets.csv',dtype=str);x=np.load(R/'discovery.npy');codes=json.loads((R/'items.json').read_text());ix={c:i for i,c in enumerate(codes)};labels=pd.read_csv(R/'labels/customer_clusters.csv',dtype=str).set_index('customer_id').cluster_id;groups=b.customer_id.map(labels)
cache={}
def hit(items):
 key=tuple(sorted(items))
 if key not in cache:cache[key]=x[:,[ix[c] for c in key]].all(axis=1)
 return cache[key]
rows=[]
for row in q[(q.length==3)&q.method.isin(['G','L'])].itertuples():
 mask=np.ones(len(b),bool) if row.method=='G' else groups.eq(row.group_id).to_numpy();a=json.loads(row.antecedent);c=json.loads(row.consequent);d=row._asdict()
 for i,ant in enumerate(a,1):
  ac=int((hit([ant])&mask).sum());j=int((hit([ant]+c)&mask).sum());d[f'single{i}_antecedent']=ant;d[f'single{i}_antecedent_count']=ac;d[f'single{i}_joint_count']=j;d[f'single{i}_confidence']=j/ac if ac else np.nan
 assert int((hit(a+c)&mask).sum())==row.joint_count
 assert int((hit(a)&mask).sum())==row.antecedent_count
 d['best_single_confidence']=max(d['single1_confidence'],d['single2_confidence']);d['confidence_increment_pp']=(row.confidence-d['best_single_confidence'])*100;rows.append(d)
triples=pd.DataFrame(rows);triples.to_csv(O/'triple_vs_single_all_GL.csv',index=False)
cases=[]
for g in ['0','1','2']:
 p=triples[(triples.method=='L')&(triples.group_id==g)]
 for typ,z in [('largest_support_gap',p.sort_values(['support_difference','joint_count'],ascending=False).drop_duplicates('itemset').head(2)),('no_confidence_gain',p[p.confidence_increment_pp<=0].sort_values(['joint_count','rule_id'],ascending=[False,True]).head(1))]:
  z=z.copy();z['case_type']=typ;cases.append(z)
cases=pd.concat(cases);cases.to_csv(O/'triple_cases.csv',index=False)
def md(df):
 def text(v):return str(v).replace('|',' / ').replace('\n',' ')
 return '| '+' | '.join(map(text,df.columns))+' |\n|'+'|'.join(['---']*len(df.columns))+'|\n'+'\n'.join('| '+' | '.join(text(v) for v in row)+' |' for row in df.itertuples(index=False,name=None))+'\n'
lines=['# 按商品数拆分的规则排行榜','每个范围独立按联合次数、confidence、lift降序及rule_id升序排序；二商品A→B，三商品{A,B}→C。保留方向规则，不是去重商品组合，也不是系统总预算。合格条件沿用开发配置。','## G/L 合格规则数',md(counts[counts.method.ne('R')])]
for (method,g,length),p in top[top.method.ne('R')].groupby(['method','group_id','length']):
 t=p.head(10).copy();t['rule']=t.antecedent_name+' → '+t.consequent_name;t['support']=t.support.map(lambda v:f'{v:.2%}');t['confidence']=t.confidence.map(lambda v:f'{v:.2%}');t['lift']=t.lift.round(2)
 lines += [f'## {method}/{g}：{length}商品 Top10（实际{len(t)}条）',md(t[['rank_within_length','rule','joint_count','antecedent_count','support','confidence','lift']])]
lines += ['## 三商品群内外案例及单前件对照','选择每群support差最大的两个不同三商品集合，并额外展示最多一个无confidence增益案例。若该群无合格三商品规则则留空，不降低门槛补齐。增益定义为confidence(AB→C)−max(confidence(A→C),confidence(B→C))，是发现期描述，非因果或显著性判断。']
for row in cases.itertuples():
 lines += [f'### C{row.group_id} / {row.case_type}: {row.antecedent_name} → {row.consequent_name}',f'- 群内：联合{row.joint_count} / 前件{row.antecedent_count} / 全部篮{row.n_baskets}；群外：联合{row.outside_joint_count} / 前件{row.outside_antecedent_count} / 全部篮{row.outside_baskets}。',f'- support群内{row.support:.2%}、群外{row.outside_support:.2%}；confidence群内{row.confidence:.2%}、群外{row.outside_confidence:.2%}。',f'- 单前件1 {row.single1_antecedent}→{row.consequent}：{row.single1_joint_count}/{row.single1_antecedent_count}，confidence={row.single1_confidence:.2%}。',f'- 单前件2 {row.single2_antecedent}→{row.consequent}：{row.single2_joint_count}/{row.single2_antecedent_count}，confidence={row.single2_confidence:.2%}。',f'- 相对较强单前件的confidence增量：**{row.confidence_increment_pp:+.2f}个百分点**。']
(O/'按长度规则榜单与三商品案例.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
print(counts[counts.method.ne('R')].to_string(index=False));print(cases[['group_id','case_type','antecedent_name','consequent_name','joint_count','confidence','best_single_confidence','confidence_increment_pp']].to_string(index=False))
