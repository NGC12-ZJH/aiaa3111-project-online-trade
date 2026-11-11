from pathlib import Path
import json,gzip,csv,collections
import numpy as np,pandas as pd
r=Path(__file__).resolve().parent; o=r/'pattern_analysis';o.mkdir(exist_ok=True)
e=pd.read_csv(r/'patterns/rule_evidence.csv.gz',dtype={'group_id':str,'seed':str},keep_default_na=False)
s=pd.read_csv(r/'patterns/selected_rules.csv',dtype={'group_id':str,'seed':str},keep_default_na=False);s=s[s.flow.eq('native')]
b=pd.read_csv(r/'discovery_baskets.csv',dtype=str); x=np.load(r/'discovery.npy'); names=json.loads((r/'items.json').read_text()); ix={n:i for i,n in enumerate(names)}
labels=pd.read_csv(r/'labels/customer_clusters.csv',dtype=str).set_index('customer_id').cluster_id; real=b.customer_id.map(labels).to_numpy()
rand=pd.read_csv(r/'labels/random_groups.csv',dtype=str)
desc=collections.defaultdict(collections.Counter);ids=set(b.basket_id)
with gzip.open(r/'processed/clean_transactions.csv.gz','rt',encoding='utf-8') as f:
 for row in csv.DictReader(f):
  if row['split']=='discovery' and row['invoice_id'] in ids and row['is_valid_basket_item']=='1' and row['description'].strip():desc[row['stock_code']][row['description'].strip()]+=1
lookup={k:v.most_common(1)[0][0] for k,v in desc.items()}
pd.DataFrame([{'stock_code':k,'description':v,'description_variants':len(desc[k])} for k,v in lookup.items()]).to_csv(o/'product_names.csv',index=False)
for d in [e,s]:
 for field in ['support_difference','outside_support','outside_confidence','confidence','support','lift']: d[field]=pd.to_numeric(d[field],errors='coerce')
 d['antecedent_names']=d.antecedent.map(lambda z:' + '.join(lookup.get(c,c) for c in json.loads(z)))
 d['consequent_names']=d.consequent.map(lambda z:' + '.join(lookup.get(c,c) for c in json.loads(z)))
 d['itemset_key']=d.apply(lambda row:json.dumps(sorted(set(json.loads(row.antecedent)+json.loads(row.consequent)))),axis=1)
 d['global_rank']=pd.to_numeric(d.global_rank,errors='coerce')
 d['confidence_difference']=pd.to_numeric(d.confidence,errors='coerce')-pd.to_numeric(d.outside_confidence,errors='coerce')
local=e[e.method.eq('L')&e.eligible].copy()
local.to_csv(o/'local_qualified_named.csv',index=False)
summary=[]
for g,part in local.groupby('group_id'):
 summary.append({'group':g,'qualified_rules':len(part),'unique_itemsets':part.itemset_key.nunique(),'positive_support_gap':int((part.support_difference>0).sum()),'not_globally_eligible':int((~part.global_eligible).sum()),'outside_global_top50':int((part.global_rank.isna()|part.global_rank.gt(50)).sum())})
pd.DataFrame(summary).to_csv(o/'local_summary.csv',index=False)
# Show best differential examples per group, excluding duplicate reverse directions.
cases=[]
for g,part in local.groupby('group_id'):
 for typ,p in [('largest_support_gap',part),('outside_global_top50',part[part.global_rank.isna()|part.global_rank.gt(50)])]:
  t=p.sort_values(['support_difference','joint_count'],ascending=False).drop_duplicates('itemset_key').head(5).copy();t['case_type']=typ;cases.append(t)
pd.concat(cases).to_csv(o/'cases.csv',index=False)
cache={}
def hit(z):
 key=tuple(sorted(z))
 if key not in cache:cache[key]=x[:,[ix[c] for c in key]].all(axis=1)
 return cache[key]
coverage=[]; redundancy=[]
for (method,seed,budget),part in s.groupby(['method','seed','budget']):
 assigned=None
 if method=='L':assigned=real
 if method=='R':assigned=b.customer_id.map(rand[rand.seed.eq(seed)].set_index('customer_id').random_group_id).to_numpy()
 complete=np.zeros(len(b),bool);ante=np.zeros(len(b),bool);multiplicity=np.zeros(len(b),int)
 for row in part.itertuples():
  mask=np.ones(len(b),bool) if method=='G' else assigned==row.group_id
  a=json.loads(row.antecedent);c=json.loads(row.consequent)
  j=hit(a+c)&mask;complete|=j;ante|=hit(a)&mask;multiplicity+=j
 per=pd.DataFrame({'customer':b.customer_id,'covered':complete}).groupby('customer').covered.mean()
 coverage.append(dict(method=method,seed=seed,budget=budget,rules=len(part),complete_coverage=complete.mean(),antecedent_coverage=ante.mean(),customer_macro_coverage=per.mean(),covered_baskets=int(complete.sum()),mean_matches_per_covered=float(multiplicity[complete].mean())))
 for g,p in part.groupby('group_id'):
  redundancy.append(dict(method=method,seed=seed,budget=budget,group_id=g,rules=len(p),unique_itemsets=p.itemset_key.nunique()))
pd.DataFrame(coverage).to_csv(o/'discovery_coverage_NOT_future.csv',index=False);pd.DataFrame(redundancy).to_csv(o/'selected_redundancy.csv',index=False)
s[s.method.ne('R')].to_csv(o/'selected_GL_named.csv',index=False)
print('LOCAL SUMMARY');print(pd.DataFrame(summary).to_string(index=False))
print('DISCOVERY COVERAGE');df=pd.DataFrame(coverage);print(df[df.method.ne('R')].to_string(index=False));print(df[df.method.eq('R')].groupby('budget').complete_coverage.agg(['min','median','max']).to_string())
print('CASES');print(pd.concat(cases)[['group_id','case_type','antecedent_names','consequent_names','joint_count','support','outside_support','confidence','outside_confidence','lift','global_rank']].to_string(index=False))
