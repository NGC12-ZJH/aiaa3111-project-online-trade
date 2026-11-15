"""Freeze category-level P1-P5 Discovery handoff, without mining or Validation."""
from pathlib import Path
import argparse, json, hashlib, gzip, shutil, time
import numpy as np
import pandas as pd

p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--control',choices=['GL','S','A1','A2'],required=True);a=p.parse_args()
R=Path(a.root);O=R/'category_P1_P5_handoff';C=a.control
for sub in ['evidence','eligible_rules','selected_rules','summaries','inputs']:(O/sub).mkdir(parents=True,exist_ok=True)
cfg={'P1':(.01,.2,1.,None),'P2':(.02,.4,1.3,None),'P3':(.03,.5,1.5,None),'P4':(.02,.4,1.3,5.),'P5':(.02,.4,1.3,10.)}
x=np.load(R/'category_patterns/discovery_l2.npy');cols=json.loads((R/'category_patterns/l2_items.json').read_text());ix={c:i for i,c in enumerate(cols)}
b=pd.read_csv(R/'discovery_baskets.csv',dtype=str);lab=pd.read_csv(R/'labels/customer_clusters.csv',dtype=str);N=len(b);ALL=(1<<N)-1
def bits(v):return int.from_bytes(np.packbits(v,bitorder='little').tobytes(),'little')
cb={c:bits(x[:,i]) for c,i in ix.items()};cache={}
def hit(items):
 k=tuple(sorted(items))
 if k not in cache:
  h=ALL
  for c in k:h &= cb[c]
  cache[k]=h
 return cache[k]
def union(keys):
 h=0
 for k in set(keys):h |= hit(k)
 return h
def div(u,v):return np.divide(u,v,out=np.full(len(u),np.nan),where=v>0)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
basepath=R/'category_patterns/candidate_rules.csv' if C in ['GL','S'] else R/f'activity_controls_{C}/l2/candidate_rules.csv'
base=pd.read_csv(basepath);ants=base.antecedent.map(json.loads).map(tuple).tolist();cons=base.consequent.map(json.loads).map(tuple).tolist();combos=[tuple(sorted(aa+cc)) for aa,cc in zip(ants,cons)]
ki={(aa,cc):i for i,(aa,cc) in enumerate(zip(ants,cons))};trip=np.flatnonzero(base.length.to_numpy()==3);s1=np.array([ki[((ants[i][0],),cons[i])] for i in trip]);s2=np.array([ki[((ants[i][1],),cons[i])] for i in trip])
names=pd.read_csv(R/'category_patterns/evidence/G__GLOBAL.csv.gz',nrows=0).columns
tax=pd.read_csv(R/'taxonomy_analysis/item_taxonomy_v1.csv',dtype=str).fillna('');namecol=next((c for c in ['l2_name','l2_name_en','l2_label'] if c in tax),None);nm=tax.drop_duplicates('l2_id').set_index('l2_id')[namecol].to_dict() if namecol else {c:c for c in cols}
base=base[['rule_id','antecedent','consequent','length']].copy();base['antecedent_name']=[' + '.join(nm.get(c,c) for c in aa) for aa in ants];base['consequent_name']=[' + '.join(nm.get(c,c) for c in cc) for cc in cons]
base['combination_id']=[hashlib.sha256(json.dumps(k).encode()).hexdigest()[:16] for k in combos]
if C=='GL':systems=[('G','',pd.Series('GLOBAL',index=b.index)),('L','',b.customer_id.map(lab.set_index('customer_id').cluster_id))]
else:
 rp=R/'labels/random_groups.csv' if C=='S' else R/f'activity_controls_{C}/random_groups_{C}_{"profile_frequency" if C=="A1" else "discovery_baskets"}.csv'
 rr=pd.read_csv(rp,dtype=str);systems=[('R',seed,b.customer_id.map(z.set_index('customer_id').random_group_id)) for seed,z in rr.groupby('seed',sort=True)]
 assert len(systems)==(20 if C=='S' else 100)
streams={p:gzip.open(O/'eligible_rules'/f'{p}_{C}.csv.gz','wt',encoding='utf-8',compresslevel=1) for p in cfg};headers={p:True for p in cfg}
scope_rows=[];allocation=[];metrics=[];selected=[];sources=[];reconciled=0;scope_count=0
for method,seed,assignment in systems:
 assert assignment.notna().all();groups=['GLOBAL'] if method=='G' else ['0','1','2'];qsets={p:{} for p in cfg};masks={g:bits(assignment.eq(g).to_numpy()) for g in groups};sizes={g:masks[g].bit_count() for g in groups};assert sum(sizes.values())==N
 for g in groups:
  key=f'{method}_{seed}_{g}';scope=f'{C}_{key}';mask=masks[g];n=sizes[g]
  if C in ['GL','S']:
   src=R/'category_patterns/evidence'/f'{key}.csv.gz';e=pd.read_csv(src,dtype={'seed':str,'group_id':str},keep_default_na=False,low_memory=False);assert e.rule_id.tolist()==base.rule_id.tolist()
   j=e.joint_count.to_numpy();ant=e.antecedent_count.to_numpy();con=e.consequent_count.to_numpy();gen=e.generated_here.to_numpy(dtype=bool);oj=e.outside_joint_count.to_numpy();oa=e.outside_antecedent_count.to_numpy()
  else:
   src=R/f'activity_controls_{C}/l2/counts/{key}.npz';z=np.load(src);assert int(z['n_baskets'])==n;j=z['joint'];ant=z['antecedent'];con=z['consequent'];gen=z['generated'];oj=z['outside_joint'];oa=z['outside_antecedent']
  sources.append(dict(path=str(src.relative_to(R)),sha256=sha(src)));co=div(j,ant);su=j/n;li=div(co,con/n);inc=np.full(len(base),np.nan);inc[trip]=(co[trip]-np.maximum(co[s1],co[s2]))*100
  passes={p:gen&(j>=20)&(ant>=20)&(su>=sp)&(co>=cp)&(li>=lp)&((base.length.to_numpy()==2)|(inc>=ip-1e-10) if ip is not None else True) for p,(sp,cp,lp,ip) in cfg.items()}
  assert np.array_equal(passes['P2']&(base.length.to_numpy()==2),passes['P4']&(base.length.to_numpy()==2));assert np.array_equal(passes['P2']&(base.length.to_numpy()==2),passes['P5']&(base.length.to_numpy()==2))
  assert not (passes['P5']&~passes['P4']).any() and not(passes['P4']&~passes['P2']).any() and not(passes['P3']&~passes['P2']).any()
  take=np.flatnonzero(passes['P1']);ev=base.iloc[take].copy();ev['scope_id']=scope;ev['control']=C;ev['method']=method;ev['seed']=seed;ev['group_id']=g;ev['n_baskets']=n
  for col,v in [('joint_count',j),('antecedent_count',ant),('consequent_count',con),('support',su),('confidence',co),('lift',li),('confidence_increment_pp',inc),('outside_joint_count',oj),('outside_antecedent_count',oa)]:ev[col]=v[take]
  ev['outside_baskets']=N-n;ev['outside_support']=oj[take]/(N-n) if N>n else np.nan;ev['outside_confidence']=div(oj[take],oa[take]);ev['generated_here']=True
  one=np.full(len(base),np.nan);two=one.copy();one[trip]=co[s1];two[trip]=co[s2];ev['single1_confidence']=one[take];ev['single2_confidence']=two[take]
  ev['single1_rule_id']='';ev['single2_rule_id']='';present=np.intersect1d(take,trip);trmap={v:i for i,v in enumerate(trip)};ev.loc[present,'single1_rule_id']=base.rule_id.iloc[[s1[trmap[v]] for v in present]].to_numpy();ev.loc[present,'single2_rule_id']=base.rule_id.iloc[[s2[trmap[v]] for v in present]].to_numpy()
  for p in cfg:ev['passes_'+p]=passes[p][take]
  ev=ev.sort_values(['joint_count','confidence','lift','rule_id'],ascending=[False,False,False,True]);ev.to_csv(O/'evidence'/f'{scope}.csv.gz',index=False,compression={'method':'gzip','compresslevel':1})
  for p in cfg:
   q=ev[ev['passes_'+p]].copy();q['config']=p;q['rank_within_group']=np.arange(1,len(q)+1);qsets[p][g]=q
   q[['scope_id','rule_id','rank_within_group']].to_csv(streams[p],index=False,header=headers[p]);headers[p]=False
   for le in [0,2,3]:
    ids=q.index if le==0 else q.index[q.length.eq(le)];ck=[combos[i] for i in ids];ak=[ants[i] for i in ids];cov=union(ck)&mask;tr=union(ak)&mask
    scope_rows.append(dict(control=C,method=method,seed=seed,group_id=g,scope_id=scope,config=p,length=le,n_baskets=n,rules=len(ids),unique_combinations=len(set(ck)),covered_orders=cov.bit_count(),coverage=cov.bit_count()/n,antecedent_coverage=tr.bit_count()/n,empty=len(ids)==0))
  # Independently recount source orders for deterministic sample, including P5 triples.
  samples=list(take[np.linspace(0,len(take)-1,min(5,len(take)),dtype=int)]) if len(take) else []
  for i in samples:
   assert (hit(combos[i])&mask).bit_count()==j[i] and (hit(ants[i])&mask).bit_count()==ant[i]
  scope_count+=1;print('EXPORTED',C,key,len(ev),flush=True)
 for p in cfg:
  previous={}
  for B in [20,50,100]:
   raw={g:B*sizes[g]/N for g in groups};quota={g:int(raw[g]) for g in groups}
   for g in sorted(groups,key=lambda g:(-(raw[g]-quota[g]),g))[:B-sum(quota.values())]:quota[g]+=1
   cv=sh=tr=ts=0;actual=0;ruleids=set();sets=set()
   for g in groups:
    q=qsets[p][g].head(quota[g]).copy();ids=q.index;h=union([combos[i] for i in ids]);ah=union([ants[i] for i in ids]);cv|=h&masks[g];sh|=h;tr|=ah&masks[g];ts|=ah;actual+=len(q);ruleids.update(q.rule_id);sets.update(combos[i] for i in ids)
    q['budget']=B;q['allocated_budget']=quota[g];selected.append(q)
    allocation.append(dict(control=C,method=method,seed=seed,group_id=g,config=p,budget=B,n_baskets=sizes[g],available=len(qsets[p][g]),allocated=quota[g],actual=len(q),shortfall=quota[g]-len(q),empty=len(qsets[p][g])==0,two_category=int(q.length.eq(2).sum()),three_category=int(q.length.eq(3).sum())))
   assert cv&~sh==0 and cv&~tr==0 and sh&~ts==0 and sum(quota.values())==B
   for flow,v,t in [('restricted',cv,tr),('shared',sh,ts)]:
    metrics.append(dict(control=C,method=method,seed=seed,config=p,budget=B,flow=flow,actual=actual,shortfall=B-actual,unique_rules=len(ruleids),unique_combinations=len(sets),covered_orders=v.bit_count(),coverage=v.bit_count()/N,triggered_orders=t.bit_count(),antecedent_coverage=t.bit_count()/N))
for f in streams.values():f.close()
pd.DataFrame(scope_rows).to_csv(O/'summaries'/f'scope_summary_{C}.csv',index=False)
pd.DataFrame(allocation).to_csv(O/'summaries'/f'allocation_audit_{C}.csv',index=False)
pd.DataFrame(metrics).to_csv(O/'summaries'/f'system_metrics_{C}.csv',index=False)
sel=pd.concat(selected,ignore_index=True)
for p in cfg:sel[sel.config.eq(p)].to_csv(O/'selected_rules'/f'{p}_{C}.csv.gz',index=False,compression={'method':'gzip','compresslevel':1})
(O/f'manifest_{C}.json').write_text(json.dumps(dict(control=C,scopes=scope_count,systems=len(systems),configs=cfg,source_candidate_sha256=sha(basepath),script_sha256=sha(Path(__file__)),sources=sources,checks=['P2 P4 P5 pair rules identical','P5 subset P4 subset P2 subset P1; P3 subset P2','sample joint and antecedent counts from source orders','shared coverage superset; full match subset antecedent match','all quota sums equal system budget'],validation_used=False),indent=2),encoding='utf-8')
print('DONE',C,scope_count,len(sel),flush=True)
