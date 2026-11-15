"""Independent 100-seed A2 rerun; original S outputs remain read-only."""
from pathlib import Path
import argparse,json,hashlib,time,itertools,math
from importlib import import_module
import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import fpcommon
def bounded_fpg(tree,minsup):
 depth=len(tree.cond_items);items=list(tree.nodes)
 if tree.is_path():
  for size in range(1,min(len(items),3-depth)+1):
   for combination in itertools.combinations(items,size):yield min(tree.nodes[i][0].count for i in combination),tree.cond_items+list(combination)
 else:
  if depth<3:
   for item in items:yield sum(node.count for node in tree.nodes[item]),tree.cond_items+[item]
  if depth+1<3:
   for item in items:yield from bounded_fpg(tree.conditional_tree(item,minsup),minsup)
p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--random-file',required=True);p.add_argument('--layer',choices=['sku','l2'],required=True);p.add_argument('--mine-shard',type=int,choices=range(4));a=p.parse_args();R=Path(a.root);O=R/'activity_controls_A2'/a.layer;O.mkdir(parents=True,exist_ok=True);(O/'mined').mkdir(exist_ok=True);(O/'counts').mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
start=time.time();b=pd.read_csv(R/'discovery_baskets.csv',dtype=str);lab=pd.read_csv(R/'labels/customer_clusters.csv',dtype={'customer_id':str,'cluster_id':str});rand=pd.read_csv(a.random_file,dtype=str)
assert sha(Path(a.random_file))=='cea8ee0b237ccfd568f5fdc6cb6cff191a085e3554f626e277515dbab3691f40'
assert len(rand)==268400 and sorted(rand.seed.unique(),key=int)==list(map(str,range(1000,1100)))
discovery_frequency=lab.customer_id.map(b.customer_id.value_counts()).fillna(0);lab['stratum']=pd.cut(discovery_frequency,[-1,0,1,2,4,9,np.inf],labels=['0','1','2','3-4','5-9','10+']).astype(str)
expected=lab.groupby(['stratum','cluster_id']).size().to_dict();lookup=lab.set_index('customer_id');real=b.customer_id.map(lookup.cluster_id);scopes=[('G','','GLOBAL',np.ones(len(b),bool))]+[('L','',g,real.eq(g).to_numpy()) for g in ['0','1','2']]
for seed,z in rand.groupby('seed',sort=True):
 assert z.customer_id.is_unique and set(z.customer_id)==set(lab.customer_id)
 assert (z.stratum.to_numpy()==z.customer_id.map(lookup.stratum).to_numpy()).all()
 assert z.groupby(['stratum','random_group_id']).size().to_dict()==expected
 assigned=b.customer_id.map(z.set_index('customer_id').random_group_id);assert assigned.notna().all()
 scopes.extend(('R',seed,g,assigned.eq(g).to_numpy()) for g in ['0','1','2'])
assert len(scopes)==304
if a.layer=='sku':x=np.load(R/'discovery.npy');cols=json.loads((R/'items.json').read_text())
else:x=np.load(R/'category_patterns/discovery_l2.npy');cols=json.loads((R/'category_patterns/l2_items.json').read_text())
ix={c:i for i,c in enumerate(cols)};audit=[];found_by={};pool=set()
protocol=dict(control='A2',seeds=list(range(1000,1100)),layer=a.layer,random_sha256=sha(Path(a.random_file)),baskets_sha256=sha(R/'discovery_baskets.csv'),code_sha256=sha(Path(__file__)),similarity_pool='fixed original S union for comparable S/A2 support distances; native TopK recomputed',thresholds='SKU original 1%/.2/1; L2 primary strict 3%/.5/1.5 plus 5pp; no Validation/Test',planned_seed_count=100)
if a.mine_shard is None:(O/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
for method,seed,g,mask in scopes:
 if a.mine_shard is not None and (method!='R' or int(seed)%4!=a.mine_shard):continue
 key=f'{method}_{seed}_{g}';f=O/'mined'/f'{key}.json';n=int(mask.sum());tick=time.time()
 if f.exists():found=[(tuple(z[0]),z[1]) for z in json.loads(f.read_text())]
 else:
  data=pd.DataFrame(x[mask]);threshold=max(.01,20/n);tree,_,_=fpcommon.setup_fptree(data,threshold);found=[]
  bitcols=[int.from_bytes(np.packbits(data.values[:,i],bitorder='little').tobytes(),'little') for i in range(len(cols))]
  for count,items in bounded_fpg(tree,math.ceil(threshold*n)):
   joint_bits=bitcols[items[0]]
   for item in items[1:]:joint_bits &= bitcols[item]
   assert count==joint_bits.bit_count()
   if len(items)>1 and count/n>=threshold:
    found.extend((tuple(sorted(int(v) for v in set(items)-{c})),int(c)) for c in items)
  f.write_text(json.dumps(sorted(set(found))),encoding='utf-8')
 found=set(found)
 if a.mine_shard is None:found_by[key]=found;pool|=found
 audit.append(dict(method=method,seed=seed,group_id=g,n_baskets=n,n_customers=b.loc[mask,'customer_id'].nunique(),generated=len(found),seconds=time.time()-tick));print('MINED',a.layer,key,len(found),flush=True)
if a.mine_shard is not None:
 print('SHARD COMPLETE',a.mine_shard,flush=True);raise SystemExit(0)
# Retain original S pool for exactly comparable distances, without treating it as native A2 output.
if a.layer=='sku':old=pd.read_csv(R/'patterns/rule_evidence.csv.gz',usecols=['rule_id','antecedent','consequent','method'],low_memory=False);old=old[old.method.eq('G')]
else:old=pd.read_csv(R/'category_patterns/candidate_rules.csv')
reference={tuple(sorted(ix[c] for c in json.loads(r.antecedent)+json.loads(r.consequent))) for r in old.itertuples()}
for r in old.itertuples():pool.add((tuple(ix[c] for c in json.loads(r.antecedent)),ix[json.loads(r.consequent)[0]]))
pool=sorted(pool);components=sorted({aa for aa,c in pool}|{(c,) for aa,c in pool}|{tuple(sorted(aa+(c,))) for aa,c in pool});ci={s:i for i,s in enumerate(components)}
hits=np.stack([x[:,list(s)].all(1) for s in components]);total=hits.sum(1);ai=np.array([ci[aa] for aa,c in pool]);bi=np.array([ci[(c,)] for aa,c in pool]);ji=np.array([ci[tuple(sorted(aa+(c,)))] for aa,c in pool]);length=np.array([len(aa)+1 for aa,c in pool])
def rid(aa,c):
 payload=[[cols[i] for i in aa],[cols[c]]]
 if a.layer=='l2':payload=['l2']+payload
 return hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:16]
base=pd.DataFrame([dict(rule_id=rid(aa,c),antecedent=json.dumps([cols[i] for i in aa]),consequent=json.dumps([cols[c]]),length=len(aa)+1) for aa,c in pool]);base.to_csv(O/'candidate_rules.csv',index=False)
keyidx={key:i for i,key in enumerate(pool)};trip=np.flatnonzero(length==3);s1=np.array([keyidx[((pool[i][0][0],),pool[i][1])] for i in trip]);s2=np.array([keyidx[((pool[i][0][1],),pool[i][1])] for i in trip]);native_qualified={};supports={};selected=[];counts=[];metrics=[]
ref={le:np.array([ci[s] for s in sorted(reference) if len(s)==le]) for le in [2,3]}
for method,seed,g,mask in scopes:
 key=f'{method}_{seed}_{g}';n=int(mask.sum());c=hits[:,mask].sum(1);j=c[ji];ant=c[ai];con=c[bi];conf=np.divide(j,ant,out=np.full(len(pool),np.nan),where=ant>0);lift=np.divide(conf,con/n,out=np.full(len(pool),np.nan),where=con>0);generated=np.array([key2 in found_by[key] for key2 in pool]);inc=np.full(len(pool),np.nan);inc[trip]=conf[trip]-np.maximum(conf[s1],conf[s2]);support=j/n
 np.savez_compressed(O/'counts'/f'{key}.npz',joint=j,antecedent=ant,consequent=con,generated=generated,n_baskets=n,outside_joint=total[ji]-j,outside_antecedent=total[ai]-ant)
 passing={}
 for config,(sup,co,li) in {'baseline':(.01,.2,1),'moderate':(.02,.4,1.3),'strict':(.03,.5,1.5)}.items():
  eligible=generated&(j>=20)&(ant>=20)&(support>=sup)&(conf>=co)&(lift>=li)
  for useinc in [False,True]:
   ok=eligible&((length==2)|(inc>=.05-1e-12) if useinc else True);passing[(config,useinc)]=ok
   for le in [2,3]:counts.append(dict(method=method,seed=seed,group_id=g,config=config,increment=useinc,length=le,rules=int((ok&(length==le)).sum()),unique_combinations=len(set(ji[ok&(length==le)]))))
 ok=passing[('baseline',False)] if a.layer=='sku' else passing[('strict',True)]
 q=base.loc[ok].copy();q['joint_count']=j[ok];q['antecedent_count']=ant[ok];q['support']=support[ok];q['confidence']=conf[ok];q['lift']=lift[ok];q['increment_pp']=inc[ok]*100;q=q.sort_values(['joint_count','confidence','lift','rule_id'],ascending=[False,False,False,True]);native_qualified[key]=q
 supports[key]=(c,n);print('COUNTED',a.layer,key,len(q),flush=True)
pd.DataFrame(audit).to_csv(O/'scope_audit.csv',index=False);pd.DataFrame(counts).to_csv(O/'screening_counts.csv',index=False)
# Confirm original real and global native rules, not just aggregate counts.
for method,g in [('G','GLOBAL'),('L','0'),('L','1'),('L','2')]:
 q=native_qualified[f'{method}__{g}']
 if a.layer=='l2':z=pd.read_csv(R/f'category_screening/scope_rules/{method}__{g}.csv.gz',low_memory=False);ids=set(z.loc[z.passes_strict&z.passes_increment,'rule_id'])
 else:
  if method=='G':orig=pd.read_csv(R/'patterns/rule_evidence.csv.gz',dtype={'group_id':str},keep_default_na=False,low_memory=False);orig=orig[orig.method.isin(['G','L'])]
  ids=set(orig.loc[orig.method.eq(method)&orig.group_id.eq(g)&orig.eligible&orig.generated_here,'rule_id'])
 assert set(q.rule_id)==ids,(a.layer,method,g,len(q),len(ids))
def alloc(sizes,B):
 raw={g:B*n/sum(sizes.values()) for g,n in sizes.items()};out={g:int(v) for g,v in raw.items()}
 for g in sorted(raw,key=lambda g:(-(raw[g]-out[g]),g))[:B-sum(out.values())]:out[g]+=1
 return out
systems=[('G','')]+[('L','')]+[('R',str(seed)) for seed in range(1000,1100)];seedstats=[]
def bc(u,v):return np.abs(u-v).sum()/(u+v).sum() if (u+v).sum() else 0
for method,seed in systems:
 ss=[s for s in scopes if s[0]==method and s[1]==seed];sizes={g:int(mask.sum()) for _,_,g,mask in ss}
 for B in [20,50,100]:
  quotas=alloc(sizes,B);local=np.zeros(len(b),bool);shared=local.copy();trigger=local.copy();trigger_shared=local.copy();actual=0;ids=set();unions=set()
  for _,_,g,mask in ss:
   q=native_qualified[f'{method}_{seed}_{g}'].head(quotas[g]);actual+=len(q);ids.update(q.rule_id)
   for i in q.index:local|=hits[ji[i]]&mask;shared|=hits[ji[i]];trigger|=hits[ai[i]]&mask;trigger_shared|=hits[ai[i]];unions.add(ji[i])
   z=q.copy();z['method']=method;z['seed']=seed;z['group_id']=g;z['budget']=B;z['allocated']=quotas[g];selected.append(z)
  assert actual<=B and (local<=shared).all()
  for flow,cov,tr in [('restricted',local,trigger),('shared',shared,trigger_shared)]:metrics.append(dict(control='A2',method=method,seed=seed,budget=B,flow=flow,actual=actual,unique_rules=len(ids),unique_combinations=len(unions),covered_orders=int(cov.sum()),coverage=cov.mean(),antecedent_coverage=tr.mean()))
 if method=='G':continue
 for k in [10,20]:
  ranks={g:list(dict.fromkeys(ji[native_qualified[f'{method}_{seed}_{g}'].index]))[:k] for g in sizes};values=[]
  for ga,gb in itertools.combinations(sizes,2):
   aa=set(ranks[ga]);bb=set(ranks[gb]);values.append(1-len(aa&bb)/len(aa|bb) if aa|bb else 0)
  seedstats.append(dict(method=method,seed=seed,metric=f'pair_jaccard_distance_top{k}',value=np.mean(values)))
 for le in [2,3]:
  vec={g:supports[f'{method}_{seed}_{g}'][0][ref[le]]/sizes[g] for g in sizes};pv=[bc(vec[ga],vec[gb]) for ga,gb in itertools.combinations(sizes,2)];rv=[];av=[]
  for g in sizes:
   cnt,n=supports[f'{method}_{seed}_{g}'];outside=(total[ref[le]]-cnt[ref[le]])/(len(b)-n);rv.append(bc(vec[g],outside));av.append(np.abs(vec[g]-outside).mean()*100)
  for metric,value in [(f'pair_braycurtis_len{le}',np.mean(pv)),(f'rest_braycurtis_len{le}',np.mean(rv)),(f'rest_mean_abs_support_pp_len{le}',np.mean(av))]:seedstats.append(dict(method=method,seed=seed,metric=metric,value=value))
pd.concat(selected).to_csv(O/'selected_rules.csv',index=False);m=pd.DataFrame(metrics);m.to_csv(O/'system_metrics.csv',index=False);st=pd.DataFrame(seedstats);st.to_csv(O/'similarity_seed_metrics.csv',index=False)
summary=[]
for (B,flow),z in m.groupby(['budget','flow']):
 l=z[z.method.eq('L')].coverage.iloc[0];gv=z[z.method.eq('G')].coverage.iloc[0];rr=z[z.method.eq('R')].coverage;assert len(rr)==100
 summary.append(dict(budget=B,flow=flow,G=gv,L=l,A2_median=rr.median(),A2_min=rr.min(),A2_max=rr.max(),random_ge_real=int((rr>=l-1e-12).sum()),empirical_upper_tail=(1+(rr>=l-1e-12).sum())/101))
pd.DataFrame(summary).to_csv(O/'coverage_comparison.csv',index=False)
sim=[]
for metric,z in st.groupby('metric'):
 l=z[z.method.eq('L')].value.iloc[0];rr=z[z.method.eq('R')].value;assert len(rr)==100;sim.append(dict(metric=metric,real=l,A2_median=rr.median(),A2_min=rr.min(),A2_max=rr.max(),random_ge_real=int((rr>=l-1e-12).sum()),empirical_upper_tail=(1+(rr>=l-1e-12).sum())/101))
pd.DataFrame(sim).to_csv(O/'similarity_comparison.csv',index=False)
(O/'manifest.json').write_text(json.dumps(dict(**protocol,candidate_rules=len(pool),n_scopes=304,evidence_rows=len(pool)*304,elapsed_seconds=time.time()-start,reference_combinations={str(k):len(v) for k,v in ref.items()},checks=['all100 seeds and exact strata counts verified','all mined counts verified directly','G and L exact rule ID sets reproduce original','seed level aggregation','budget and shared-superset checks']),indent=2),encoding='utf-8')
print('COMPLETE',a.layer);print(pd.DataFrame(summary).to_string(index=False));print(pd.DataFrame(sim).to_string(index=False))
