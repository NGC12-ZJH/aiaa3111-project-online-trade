import os
os.environ['OMP_NUM_THREADS']='1'
import json,hashlib,time,sys
from pathlib import Path
import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import fpgrowth
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'patterns'; OUT.mkdir(exist_ok=True)
CFG={'config_id':'discovery_dev_v1','status':'development_not_validation_selected','min_support':.01,'min_joint_count':20,'min_antecedent_count':20,'min_confidence':.2,'min_lift':1.0,'max_itemset_length':3,'budgets':[20,50,100],'ranking':'joint_count desc, confidence desc, lift desc, rule_id asc','budget_policy':'largest remainder by Discovery basket counts; ties group_id; no redistribution','redundancy':'exact duplicate rule only; no additional pruning'}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ruleid(a,c):return hashlib.sha256(json.dumps([a,c]).encode()).hexdigest()[:16]
def allocate(sizes,budget):
 total=sum(sizes.values()); raw={g:budget*n/total for g,n in sizes.items()}; out={g:int(v) for g,v in raw.items()}
 for g in sorted(raw,key=lambda g:(-(raw[g]-out[g]),g))[:budget-sum(out.values())]:out[g]+=1
 return out
def main():
 start=time.perf_counter(); b=pd.read_csv(ROOT/'discovery_baskets.csv',dtype=str,keep_default_na=False)
 labels=pd.read_csv(ROOT/'labels/customer_clusters.csv',dtype=str); random=pd.read_csv(ROOT/'labels/random_groups.csv',dtype=str)
 assert labels.customer_id.is_unique and len(labels)==2684
 assert set(b.customer_id)<=set(labels.customer_id)
 assert labels.fitted_until.str.startswith('2010-06-01').all()
 assert b.basket_id.is_unique and b.split.eq('discovery').all() and b.is_eligible_for_main_comparison.eq('1').all()
 x=np.load(ROOT/'discovery.npy'); columns=json.loads((ROOT/'items.json').read_text()); assert len(x)==len(b)
 for i,items in enumerate(b['items'].map(json.loads)): assert set(np.array(columns)[x[i]])==set(items)
 mapping=labels.set_index('customer_id').cluster_id; groups=sorted(mapping.unique()); seeds=sorted(random.seed.unique(),key=int); assert len(seeds)==20
 scopes=[('G','', 'GLOBAL',np.ones(len(b),dtype=bool))]
 real=b.customer_id.map(mapping)
 scopes += [('L','',g,real.eq(g).to_numpy()) for g in groups]
 for seed in seeds:
  r=random[random.seed.eq(seed)]; assert r.customer_id.is_unique and set(r.customer_id)==set(labels.customer_id)
  assert r.random_group_id.value_counts().to_dict()==labels.cluster_id.value_counts().to_dict()
  assigned=b.customer_id.map(r.set_index('customer_id').random_group_id); assert assigned.notna().all()
  scopes += [('R',seed,g,assigned.eq(g).to_numpy()) for g in groups]
 pool=set(); generated={}; audits=[]; timings=[]
 for method,seed,g,mask in scopes:
  n=int(mask.sum()); assert n>0
  audits.append(dict(method=method,seed=seed,group_id=g,n_baskets=n,n_customers=b.loc[mask,'customer_id'].nunique(),single_item_baskets=int((x[mask].sum(axis=1)==1).sum())))
  t=time.perf_counter(); found=fpgrowth(pd.DataFrame(x[mask]),min_support=max(CFG['min_support'],CFG['min_joint_count']/n),max_len=3)
  keys=set()
  for items in found.itemsets:
   if len(items)<2:continue
   for c in items: keys.add((tuple(sorted(items-{c})),c))
  generated[(method,seed,g)]=keys; pool|=keys
  timings.append(dict(method=method,seed=seed,group_id=g,seconds=time.perf_counter()-t,n_generated_rules=len(keys)))
  print('mined',method,seed,g,n,len(keys),flush=True)
 pool=sorted(pool); pd.DataFrame(audits).to_csv(OUT/'scope_audit.csv',index=False)
 pd.DataFrame(timings).to_csv(OUT/'mining_runtime.csv',index=False)
 # Cache exact basket membership for every component; original baskets retained for evidence.
 sets={tuple([c]) for a,c in pool}|{a for a,c in pool}|{tuple(sorted(a+(c,))) for a,c in pool}
 matches={s:x[:,list(s)].all(axis=1) for s in sets}
 entries=[]
 for method,seed,g,mask in scopes:
  n=int(mask.sum()); outside=~mask; no=int(outside.sum())
  for a,c in pool:
   joint=matches[tuple(sorted(a+(c,)))]; ant=matches[a]; cons=matches[(c,)]
   j=int(np.count_nonzero(joint&mask)); ac=int(np.count_nonzero(ant&mask)); cc=int(np.count_nonzero(cons&mask))
   support=j/n; conf=j/ac if ac else None; lift=conf/(cc/n) if ac and cc else None
   jo=int(np.count_nonzero(joint&outside)); ao=int(np.count_nonzero(ant&outside))
   names=[columns[i] for i in a]; cn=[columns[c]]; rid=ruleid(names,cn)
   eligible=j>=CFG['min_joint_count'] and ac>=CFG['min_antecedent_count'] and support>=CFG['min_support'] and conf is not None and conf>=CFG['min_confidence'] and lift is not None and lift>=CFG['min_lift']
   entries.append(dict(rule_id=rid,method=method,seed=seed,group_id=g,antecedent=json.dumps(names),consequent=json.dumps(cn),n_baskets=n,antecedent_count=ac,consequent_count=cc,joint_count=j,support=support,confidence=conf,lift=lift,outside_baskets=no,outside_joint_count=jo,outside_antecedent_count=ao,outside_support=jo/no if no else None,outside_confidence=jo/ao if ao else None,support_difference=support-jo/no if no else None,generated_here=(a,c) in generated[(method,seed,g)],eligible=eligible,config_id=CFG['config_id']))
 e=pd.DataFrame(entries); rankcols=['joint_count','confidence','lift','rule_id']; asc=[False,False,False,True]
 glob=e[e.method.eq('G')&e.eligible].sort_values(rankcols,ascending=asc); ranks={r:i+1 for i,r in enumerate(glob.rule_id)}
 e['global_rank']=e.rule_id.map(ranks); e['global_eligible']=e.rule_id.isin(ranks)
 e.to_csv(OUT/'rule_evidence.csv.gz',index=False,compression='gzip')
 selected=[]; totals=[]
 for flow in ['native','common_pool']:
  for (method,seed),part in e.groupby(['method','seed'],dropna=False):
   sizes=part.groupby('group_id').n_baskets.first().to_dict()
   for budget in CFG['budgets']:
    quotas=allocate(sizes,budget)
    for g,q in quotas.items():
     subset=part[part.group_id.eq(g)&part.eligible]
     if flow=='native':subset=subset[subset.generated_here]
     top=subset.sort_values(rankcols,ascending=asc).head(q).copy(); top['flow']=flow; top['budget']=budget; top['allocated_budget']=q; top['selection_reason']='qualified then '+CFG['ranking']; selected.append(top)
     totals.append(dict(flow=flow,method=method,seed=seed,group_id=g,budget=budget,allocated=q,actual=len(top),qualified_candidates=len(subset)))
 pd.concat(selected,ignore_index=True).to_csv(OUT/'selected_rules.csv',index=False)
 totals=pd.DataFrame(totals); totals.to_csv(OUT/'budget_audit.csv',index=False)
 assert (totals.groupby(['flow','method','seed','budget'],dropna=False).actual.sum()<=totals.groupby(['flow','method','seed','budget'],dropna=False).allocated.sum()).all()
 # Traceable illustrative cases; no future-performance claims.
 cases=e[e.method.eq('L')&e.eligible].sort_values(['support_difference','joint_count'],ascending=False).head(10).copy()
 lookup={ruleid([columns[i] for i in a],[columns[c]]):(a,c) for a,c in pool}
 evidence=[]
 for row in cases.itertuples():
  a,c=lookup[row.rule_id]; mask=real.eq(row.group_id).to_numpy() & matches[tuple(sorted(a+(c,)))]
  for bid in b.loc[mask,'basket_id'].head(5):evidence.append(dict(rule_id=row.rule_id,group_id=row.group_id,basket_id=bid))
 cases.to_csv(OUT/'discovery_case_candidates.csv',index=False); pd.DataFrame(evidence).to_csv(OUT/'case_order_examples.csv',index=False)
 manifest={'config':CFG,'n_baskets':len(b),'n_scopes':len(scopes),'random_seeds':seeds,'common_pool_rules':len(pool),'evidence_rows':len(e),'elapsed_seconds':time.perf_counter()-start,'inputs':{str(p.relative_to(ROOT)):digest(p) for p in [ROOT/'discovery_baskets.csv',ROOT/'discovery.npy',ROOT/'items.json',ROOT/'labels/customer_clusters.csv',ROOT/'labels/random_groups.csv']},'code_sha256':digest(Path(__file__)),'checks':['label uniqueness and complete coverage','20 size-matched customer permutations','encoded matrix checked against every basket','exact rule membership counts','system budgets checked']}
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8'); (OUT/'config.json').write_text(json.dumps(CFG,indent=2),encoding='utf-8')
 print(json.dumps(manifest,indent=2),flush=True)
if __name__=='__main__':main()
