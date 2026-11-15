from pathlib import Path
import argparse,json,itertools
import pandas as pd
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--root',required=True);R=Path(p.parse_args().root);O=R/'activity_controls_A1';rows=[]
def bc(a,b):return abs(a-b).sum()/(a+b).sum()
for method,seed in [('L','')]+[('R',str(s)) for s in range(42,62)]:
 vec={};out={};rank={};lengths=None
 for g in ['0','1','2']:
  key=f'{method}_{seed}_{g}'
  e=pd.read_csv(R/f'category_patterns/evidence/{key}.csv.gz',usecols=['antecedent','consequent','support','outside_support','length'])
  e['combo']=[tuple(sorted(json.loads(a)+json.loads(c))) for a,c in zip(e.antecedent,e.consequent)];u=e.drop_duplicates('combo').sort_values('combo');vec[g]=u.support.to_numpy();out[g]=u.outside_support.to_numpy();lengths=u.length.to_numpy()
  q=pd.read_csv(R/f'category_screening/scope_rules/{key}.csv.gz',low_memory=False);q=q[q.passes_strict & q.passes_increment].sort_values(['joint_count','confidence','lift','rule_id'],ascending=[False,False,False,True]);rank[g]=list(dict.fromkeys(tuple(sorted(json.loads(a)+json.loads(c))) for a,c in zip(q.antecedent,q.consequent)))
 for k in [10,20]:
  vals=[]
  for a,b in itertools.combinations(vec,2):
   aa=set(rank[a][:k]);bb=set(rank[b][:k]);vals.append(1-len(aa&bb)/len(aa|bb))
  rows.append(dict(method=method,seed=seed,metric=f'pair_jaccard_distance_top{k}',value=np.mean(vals)))
 for le in [2,3]:
  mask=lengths==le
  vals=[bc(vec[a][mask],vec[b][mask]) for a,b in itertools.combinations(vec,2)];rest=[bc(vec[g][mask],out[g][mask]) for g in vec];gap=[np.abs(vec[g][mask]-out[g][mask]).mean()*100 for g in vec]
  for name,v in [(f'pair_braycurtis_len{le}',vals),(f'rest_braycurtis_len{le}',rest),(f'rest_mean_abs_support_pp_len{le}',gap)]:rows.append(dict(method=method,seed=seed,metric=name,value=np.mean(v)))
 print('S similarity',method,seed,flush=True)
pd.DataFrame(rows).to_csv(O/'S_l2_similarity_seed_metrics.csv',index=False)
