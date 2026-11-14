"""Restore full scope evidence from row-aligned exact counts and the candidate dictionary."""
from pathlib import Path
import argparse,json
import numpy as np
import pandas as pd
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);a=p.parse_args();S=a.root/'category_patterns'
base=pd.read_csv(S/'candidate_rules.csv',keep_default_na=False);audit=pd.read_csv(S/'scope_audit.csv',dtype={'seed':str,'group_id':str},keep_default_na=False);(S/'evidence').mkdir(exist_ok=True)
global_ids={}
for row in audit.itertuples():
    f=f'{row.method}_{row.seed}_{row.group_id}.csv.gz';d=pd.read_csv(S/'compact_evidence'/f)
    assert len(d)==len(base) and np.array_equal(d.candidate_index,np.arange(len(base)))
    e=base.copy()
    for c in ['joint_count','antecedent_count','consequent_count','outside_joint_count','outside_antecedent_count','generated_here','eligible']:e[c]=d[c].to_numpy()
    n=int(row.n_baskets);no=7521-n;e['method']=row.method;e['seed']=row.seed;e['group_id']=row.group_id;e['n_baskets']=n;e['support']=e.joint_count/n;e['confidence']=e.joint_count/e.antecedent_count.replace(0,np.nan);e['lift']=e.confidence/(e.consequent_count/n).replace(0,np.nan)
    e['outside_baskets']=no;e['outside_support']=e.outside_joint_count/no if no else np.nan;e['outside_confidence']=e.outside_joint_count/e.outside_antecedent_count.replace(0,np.nan);e['support_difference']=e.support-e.outside_support
    if row.method=='G':
        q=e[e.eligible].sort_values(['joint_count','confidence','lift','rule_id'],ascending=[False,False,False,True]);global_ids=dict(zip(q.rule_id,range(1,len(q)+1)))
    e['global_rank']=e.rule_id.map(global_ids);e['global_eligible']=e.rule_id.isin(global_ids);e.to_csv(S/'evidence'/f,index=False,compression='gzip')
    print('restored',f,flush=True)
