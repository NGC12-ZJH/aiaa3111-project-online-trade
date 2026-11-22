from pathlib import Path
import json,sys,hashlib
import numpy as np
import pandas as pd
R=Path(__import__('os').environ.get('PATTERN_PROJECT_ROOT', str(Path(__file__).resolve().parent)));O=R/'ranking_gap_sensitivity';S=R/'category_P1_P5_handoff';sys.path.insert(0,str(O/'vendor'));from validation import load_period
protocol={'base_D_commit':'4461750','periods':['discovery','validation'],'configs':['P1','P2','P3','P4','P5'],'budgets':[20,50,100],'variants':['original','evidence_frequency','evidence_gap'],'evidence_gate':'Discovery target and rest antecedent orders >=20 and customers >=10; same gate for frequency/gap; missing rest confidence never zero-filled','ranking':'Discovery target-rest confidence DESC, then joint count/confidence/lift DESC, rule_id ASC','budgets_policy':'original per-group Discovery quotas; duplicate rule identities across groups retain slots; no refill between groups; restricted/shared separately','candidate_signal':'D gap >=5pp AND baseline-adjusted association gap >0, descriptive only, not D full quality definition','test_used':False,'status':'post-Test-publication exploratory sensitivity; no change to frozen main experiment'}
(O/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
tax=pd.read_csv(S/'inputs/item_taxonomy_v1.csv',dtype=str);tm=dict(zip(tax.stock_code,tax.l2_id));labels=pd.read_csv(S/'inputs/customer_clusters.csv',dtype=str);true=dict(zip(labels.customer_id,labels.cluster_id));idx={p:load_period(O/'inputs',p,tm,true)[0] for p in protocol['periods']}
systems=[('GL','G','',None),('GL','L','',true)]
for ctrl,file in [('S','random_groups.csv'),('A1','random_groups_A1_profile_frequency.csv'),('A2','random_groups_A2_discovery_baskets.csv')]:
 rr=pd.read_csv(S/'inputs'/file,dtype=str)
 for seed,z in rr.groupby('seed'):systems.append((ctrl,'R',seed,dict(zip(z.customer_id,z.random_group_id))))
base={p:pd.read_csv(O/'inputs'/('discovery_replay.csv' if p=='discovery' else 'system_metrics.csv'),dtype={'seed':str},keep_default_na=False).set_index(['control','method','seed','config','budget','flow']) for p in idx}
selected=[];metrics=[];audits=[];evrows=[];seen=set();globalhits={};checked=0
use=['rule_id','antecedent','consequent','length','n_baskets','joint_count','antecedent_count','confidence','lift','outside_antecedent_count','outside_confidence']+['passes_'+p for p in protocol['configs']]
def ratio(a,b):return a/b if b else np.nan
for control,method,seed,mapping in systems:
 groups=['GLOBAL'] if method=='G' else ['0','1','2'];masks={p:{g:ind.all if mapping is None else ind.scope(mapping,g) for g in groups} for p,ind in idx.items()};sizes={g:masks['discovery'][g].bit_count() for g in groups}
 data={g:pd.read_csv(S/'evidence'/f'{control}_{method}_{seed}_{g}.csv.gz',usecols=use) for g in groups};gatecache={};evidencecache={};customer_masks={p:{g:[bits for customer,bits in ind.by_customer.items() if mapping is None or mapping[customer]==g] for g in groups} for p,ind in idx.items()}
 def gate(g,row):
  if method=='G':return True
  if row.antecedent_count<20 or row.outside_antecedent_count<20:return False
  key=g,row.antecedent
  if key not in gatecache:
   am=idx['discovery'].mask(json.loads(row.antecedent));target=sum(bool(am&bits) for bits in customer_masks['discovery'][g]);total=sum(bool(am&bits) for bits in idx['discovery'].by_customer.values());gatecache[key]=target>=10 and total-target>=10
  return gatecache[key]
 def evidence(g,row):
  key=g,row.rule_id
  if key not in evidencecache:
   out={}
   for period,ind in idx.items():
    am=ind.mask(json.loads(row.antecedent));cm=ind.mask(json.loads(row.consequent));sc=masks[period][g];rest=ind.all^sc;n=sc.bit_count();nr=rest.bit_count();a=(am&sc).bit_count();ar=(am&rest).bit_count();j=(am&cm&sc).bit_count();jr=(am&cm&rest).bit_count();ct=ratio(j,a);cr=ratio(jr,ar);bt=ratio((cm&sc).bit_count(),n);br=ratio((cm&rest).bit_count(),nr)
    out.update({period+'_'+k:v for k,v in dict(target_a=a,rest_a=ar,target_joint=j,rest_joint=jr,target_confidence=ct,rest_confidence=cr,confidence_gap_pp=100*(ct-cr),association_gap_pp=100*(ct-bt-cr+br),target_antecedent_customers=sum(bool(am&bits) for bits in customer_masks[period][g]),rest_antecedent_customers=sum(bool(am&bits) for bits in ind.by_customer.values())-sum(bool(am&bits) for bits in customer_masks[period][g])).items()})
   evidencecache[key]=out
  return evidencecache[key]
 for config in protocol['configs']:
  lists={v:{} for v in protocol['variants']}
  for g,d in data.items():
   q=d[d['passes_'+config]].copy();q['gap']=q.confidence-q.outside_confidence;q=q.sort_values(['joint_count','confidence','lift','rule_id'],ascending=[False,False,False,True]);lists['original'][g]=q.head(100)
   for variant in ['evidence_frequency','evidence_gap']:
    z=q if variant=='evidence_frequency' or method=='G' else q.sort_values(['gap','joint_count','confidence','lift','rule_id'],ascending=[False,False,False,False,True]);chosen=[]
    for row in z.itertuples():
     if gate(g,row):chosen.append(row.Index)
     if len(chosen)==100:break
    lists[variant][g]=z.loc[chosen]
  for B in protocol['budgets']:
   raw={g:B*sizes[g]/sum(sizes.values()) for g in groups};quota={g:int(v) for g,v in raw.items()}
   for g in sorted(groups,key=lambda g:(-(raw[g]-quota[g]),g))[:B-sum(quota.values())]:quota[g]+=1
   for variant in protocol['variants']:
    selections=[]
    for g in groups:
     z=lists[variant][g].head(quota[g]);audits.append(dict(control=control,method=method,seed=seed,config=config,budget=B,variant=variant,group=g,allocated=quota[g],actual=len(z),shortfall=quota[g]-len(z)))
     for rank,row in enumerate(z.itertuples(),1):
      e=evidence(g,row);v=dict(control=control,method=method,seed=seed,config=config,budget=B,variant=variant,group=g,rank=rank,rule_id=row.rule_id,antecedent=row.antecedent,consequent=row.consequent,**e);selected.append(v);selections.append((g,row,e))
    signals=[e for g,row,e in selections if e['discovery_confidence_gap_pp']>=5 and e['discovery_association_gap_pp']>0];kept=sum(e['validation_confidence_gap_pp']>0 and e['validation_association_gap_pp']>0 for e in signals)
    for period,ind in idx.items():
     restricted=shared=0
     for g,row,e in selections:
      h=ind.mask(json.loads(row.antecedent))&ind.mask(json.loads(row.consequent));shared|=h;restricted|=h&masks[period][g]
     for flow,h in [('restricted',restricted),('shared',shared)]:
      if method=='G':globalhits[period,config,B,flow]=h
      gh=globalhits[period,config,B,flow]
      if variant=='original':assert h.bit_count()==base[period].loc[(control,method,seed,config,B,flow)].covered_orders;checked+=1
      metrics.append(dict(period=period,control=control,method=method,seed=seed,config=config,budget=B,variant=variant,flow=flow,actual=len(selections),shortfall=B-len(selections),unique_rules=len(set(row.rule_id for g,row,e in selections)),covered_orders=h.bit_count(),coverage=h.bit_count()/ind.n,new_orders=(h&~gh).bit_count(),lost_orders=(gh&~h).bit_count(),common_orders=(h&gh).bit_count(),net_orders=h.bit_count()-gh.bit_count(),D_signal_slots=len(signals),V_kept_signal_slots=kept,direction_retention=ratio(kept,len(signals)),median_confidence_gap_pp=float(np.nanmedian([e[period+'_confidence_gap_pp'] for g,row,e in selections])) if method!='G' else np.nan))
 print('DONE',control,method,seed,flush=True)
m=pd.DataFrame(metrics);m.to_csv(O/'system_metrics.csv',index=False);pd.DataFrame(audits).to_csv(O/'allocation_audit.csv',index=False);pd.DataFrame(selected).to_csv(O/'selected_rules_evidence.csv.gz',index=False,compression='gzip')
rows=[]
for (period,config,B,variant,flow),z in m.groupby(['period','config','budget','variant','flow']):
 g=z[z.method.eq('G')].iloc[0];l=z[z.method.eq('L')].iloc[0]
 for c in ['S','A1','A2']:
  rr=z[z.control.eq(c)];v=rr.coverage;rows.append(dict(period=period,config=config,budget=B,variant=variant,flow=flow,control=c,G=g.coverage,L=l.coverage,R_median=v.median(),R_min=v.min(),R_max=v.max(),random_ge_L=int((v>=l.coverage-1e-12).sum()),upper_tail=(1+(v>=l.coverage-1e-12).sum())/(1+len(v)),L_new_orders=l.new_orders,L_lost_orders=l.lost_orders,L_D_signals=l.D_signal_slots,L_V_signals_kept=l.V_kept_signal_slots,L_direction_retention=l.direction_retention,R_direction_retention_median=rr.direction_retention.median(),L_median_confidence_gap_pp=l.median_confidence_gap_pp))
pd.DataFrame(rows).to_csv(O/'comparison.csv',index=False);(O/'verification.json').write_text(json.dumps(dict(original_period_systems_reproduced=checked,system_rows=len(m),test_used=False,new_BY_tests_computed=False,code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2),encoding='utf-8');print('COMPLETE',checked,len(m))
