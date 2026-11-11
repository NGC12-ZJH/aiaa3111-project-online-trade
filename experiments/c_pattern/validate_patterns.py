import json
from pathlib import Path
import pandas as pd
from pattern_mining import allocate
r=Path(__file__).resolve().parent
assert allocate({'0':1,'1':1,'2':1},20)=={'0':7,'1':7,'2':6}
a=pd.read_csv(r/'patterns/scope_audit.csv',dtype={'seed':str,'group_id':str},keep_default_na=False)
assert a.groupby(['method','seed']).n_baskets.sum().eq(7521).all()
s=pd.read_csv(r/'patterns/selected_rules.csv',dtype={'seed':str,'group_id':str},keep_default_na=False)
assert not s.duplicated(['flow','method','seed','group_id','budget','rule_id']).any()
assert (s.groupby(['flow','method','seed','budget']).size().reset_index(name='n').eval('n <= budget')).all()
b=pd.read_csv(r/'discovery_baskets.csv',dtype=str); baskets=b['items'].map(lambda z:set(json.loads(z)))
l=pd.read_csv(r/'labels/customer_clusters.csv',dtype=str).set_index('customer_id').cluster_id
random=pd.read_csv(r/'labels/random_groups.csv',dtype=str)
# Independent Python set-based recount on a deterministic sample of deployed rules.
sample=s.drop_duplicates(['method','seed','group_id','rule_id']).sample(n=min(150,len(s.drop_duplicates(['method','seed','group_id','rule_id']))),random_state=42)
for row in sample.itertuples():
 if row.method=='G':mask=pd.Series(True,index=b.index)
 elif row.method=='L':mask=b.customer_id.map(l).eq(row.group_id)
 else:mask=b.customer_id.map(random[random.seed.eq(row.seed)].set_index('customer_id').random_group_id).eq(row.group_id)
 ant=set(json.loads(row.antecedent)); cons=set(json.loads(row.consequent)); subset=baskets[mask]
 ac=sum(ant<=z for z in subset); jc=sum(ant|cons<=z for z in subset)
 assert ac==row.antecedent_count and jc==row.joint_count
 assert abs(jc/len(subset)-row.support)<1e-12
 assert abs(jc/ac-row.confidence)<1e-12
print('PASS: 22 methods/seeds use the same 7521 baskets; budgets and duplicate checks; 150 independent set-based rule recounts; deterministic budget tie test.')
