import os
os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
import json,hashlib,html
import numpy as np,pandas as pd
from mlxtend.frequent_patterns import fpgrowth
R=Path(__file__).resolve().parent;O=R/'high_value_analysis';O.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
protected=[R/'patterns/manifest.json',R/'patterns/selected_rules.csv',R/'patterns/rule_evidence.csv.gz'];before={str(p):sha(p) for p in protected}
b=pd.read_csv(R/'discovery_baskets.csv',dtype=str);orders=pd.read_csv(R/'processed/orders.csv.gz',dtype={'basket_id':str});labels=pd.read_csv(R/'labels/customer_clusters.csv',dtype=str)
b=b.drop(columns=['gross_purchase_amount','basket_size'],errors='ignore').merge(orders[['basket_id','gross_purchase_amount','basket_size']],on='basket_id',validate='one_to_one').merge(labels[['customer_id','cluster_id']],on='customer_id',validate='many_to_one')
assert len(b)==7521 and b.basket_id.is_unique and b.split.eq('discovery').all()
x=np.load(R/'discovery.npy');codes=json.loads((R/'items.json').read_text());ix={c:i for i,c in enumerate(codes)}
for i,z in enumerate(b['items'].map(json.loads)):assert set(np.array(codes)[x[i]])==set(z)
threshold=float(b.gross_purchase_amount.quantile(.9));high=b.gross_purchase_amount.ge(threshold).to_numpy();low=~high
assert high.sum()==753
b['high_value']=high;b['size_bin']=pd.cut(b.basket_size,[0,1,10,20,50,np.inf],labels=['1','2-10','11-20','21-50','51+'])
b.to_csv(O/'discovery_amount_cohort.csv',index=False)
name=pd.read_csv(R/'pattern_analysis/product_names.csv',dtype=str).set_index('stock_code').description.to_dict()
# Preserve the original algorithm, count thresholds and ranking for the comparison.
pool=set();origin={};timing=[]
for scope,mask in [('high',high),('rest',low)]:
 import time
 t=time.perf_counter();f=fpgrowth(pd.DataFrame(x[mask]),min_support=max(.01,20/int(mask.sum())),max_len=3);rules=set()
 for items in f.itemsets:
  if len(items)>1:
   for c in items:rules.add((tuple(sorted(items-{c})),c))
 origin[scope]=rules;pool|=rules;timing.append({'scope':scope,'seconds':time.perf_counter()-t,'candidates':len(rules)})
# Include original global candidates, including those not passing final confidence/lift.
e=pd.read_csv(R/'patterns/rule_evidence.csv.gz',dtype={'method':str},keep_default_na=False)
g=e[(e.method=='G')&e.generated_here]
for row in g.itertuples():pool.add((tuple(sorted(ix[c] for c in json.loads(row.antecedent))),ix[json.loads(row.consequent)[0]]))
del e
pool=sorted(pool);parts={a for a,c in pool}|{(c,) for a,c in pool}|{tuple(sorted(a+(c,))) for a,c in pool};hit={p:x[:,list(p)].all(axis=1) for p in parts}
rows=[]
for a,c in pool:
 joint=hit[tuple(sorted(a+(c,)))];ant=hit[a];cons=hit[(c,)];an=[codes[i] for i in a];cn=[codes[c]]
 d={'rule_id':hashlib.sha256(json.dumps([an,cn]).encode()).hexdigest()[:16],'antecedent':json.dumps(an),'consequent':json.dumps(cn),'antecedent_name':' + '.join(name.get(z,z).strip() for z in an),'consequent_name':name.get(codes[c],codes[c]).strip(),'itemset_key':json.dumps(sorted(an+cn))}
 for scope,mask in [('high',high),('rest',low),('all',np.ones(len(b),bool))]:
  n=int(mask.sum());j=int((joint&mask).sum());ac=int((ant&mask).sum());cc=int((cons&mask).sum());confidence=j/ac if ac else np.nan;lift=confidence/(cc/n) if cc else np.nan
  d.update({scope+'_joint':j,scope+'_antecedent':ac,scope+'_support':j/n,scope+'_confidence':confidence,scope+'_lift':lift,scope+'_eligible':j>=20 and ac>=20 and j/n>=.01 and confidence>=.2 and lift>=1})
 d['support_gap']=d['high_support']-d['rest_support'];d['confidence_gap']=d['high_confidence']-d['rest_confidence'];d['high_generated']=(a,c) in origin['high'];d['rest_generated']=(a,c) in origin['rest']
 d['matched_high_order_amount']=float(b.loc[joint&high,'gross_purchase_amount'].sum())
 rows.append(d)
rules=pd.DataFrame(rows);globalrank={rid:i+1 for i,rid in enumerate(rules[rules.all_eligible].sort_values(['all_joint','all_confidence','all_lift','rule_id'],ascending=[False,False,False,True]).rule_id)}
rules['global_rank']=rules.rule_id.map(globalrank)
qualified=rules[rules.high_eligible].sort_values(['high_joint','high_confidence','high_lift','rule_id'],ascending=[False,False,False,True]).copy();qualified.insert(0,'high_rank',range(1,len(qualified)+1))
rules.to_csv(O/'common_rule_evidence.csv.gz',index=False,compression='gzip');qualified.to_csv(O/'high_value_qualified_rules.csv',index=False);qualified.head(50).to_csv(O/'high_value_top50.csv',index=False)
# Representative non-reverse cases and basket-size stratification; descriptive, not causal adjustment.
cases=qualified.sort_values(['support_gap','high_joint'],ascending=False).drop_duplicates('itemset_key').head(8);cases.to_csv(O/'differential_cases.csv',index=False)
strata=[];cluster=[]
for row in cases.itertuples():
 aa=json.loads(row.antecedent);cc=json.loads(row.consequent);joint=hit[tuple(sorted(ix[z] for z in aa+cc))];ant=hit[tuple(sorted(ix[z] for z in aa))]
 for size in ['1','2-10','11-20','21-50','51+']:
  for scope,mask in [('high',high),('rest',low)]:
   sel=mask&b.size_bin.eq(size).to_numpy();n=int(sel.sum());j=int((joint&sel).sum());ac=int((ant&sel).sum());strata.append({'rule_id':row.rule_id,'size_bin':size,'scope':scope,'n_baskets':n,'joint_count':j,'antecedent_count':ac,'support':j/n if n else None,'confidence':j/ac if ac else None})
 for group in ['0','1','2']:
  sel=high&b.cluster_id.eq(group).to_numpy();n=int(sel.sum());j=int((joint&sel).sum());cluster.append({'rule_id':row.rule_id,'cluster':group,'n_high_baskets':n,'joint_count':j,'support':j/n if n else None})
pd.DataFrame(strata).to_csv(O/'case_basket_size_strata.csv',index=False);pd.DataFrame(cluster).to_csv(O/'case_cluster_counts.csv',index=False)
profile=b.groupby('high_value').agg(orders=('basket_id','size'),customers=('customer_id','nunique'),amount=('gross_purchase_amount','sum'),median_amount=('gross_purchase_amount','median'),median_basket_size=('basket_size','median'));profile.to_csv(O/'cohort_summary.csv')
groups=b.groupby('cluster_id').agg(orders=('basket_id','size'),high_orders=('high_value','sum'));groups['high_rate']=groups.high_orders/groups.orders;groups.to_csv(O/'cluster_summary.csv')
# Independent Python-set counts for top 50, separate from numpy membership calculation.
raw=b['items'].map(lambda z:set(json.loads(z))).tolist()
for row in qualified.head(50).itertuples():
 aa=set(json.loads(row.antecedent));both=aa|set(json.loads(row.consequent))
 assert sum(both<=z for z,h in zip(raw,high) if h)==row.high_joint
 assert sum(aa<=z for z,h in zip(raw,high) if h)==row.high_antecedent
assert before=={str(p):sha(p) for p in protected}
manifest={'status':'exploratory_discovery_only','definition':'global Discovery amount 90th percentile, >= threshold, include ties','amount_field':'gross_purchase_amount','threshold_gbp':threshold,'high_orders':int(high.sum()),'high_customers':int(b.loc[high,'customer_id'].nunique()),'high_amount_share':float(b.loc[high,'gross_purchase_amount'].sum()/b.gross_purchase_amount.sum()),'min_joint':20,'min_antecedent':20,'min_support':.01,'effective_high_min_support':20/int(high.sum()),'confidence':.2,'lift':1,'max_len':3,'qualified_high_rules':len(qualified),'mining':timing,'checks':['matrix alignment every basket','top50 independently recounted','original experiment hashes unchanged'],'inputs':{str(p.relative_to(R)):sha(p) for p in [R/'discovery_baskets.csv',R/'processed/orders.csv.gz',R/'labels/customer_clusters.csv']}}
(O/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(manifest,indent=2));print(cases[['antecedent_name','consequent_name','high_joint','high_support','rest_support','high_confidence','rest_confidence','global_rank']].to_string(index=False))
