"""Load one scope's full qualified rules and evidence; paths relative to handoff."""
from pathlib import Path
import argparse
import pandas as pd
p=argparse.ArgumentParser();p.add_argument('--config',required=True,choices=['P1','P2','P3','P4','P5']);p.add_argument('--scope',required=True,help='e.g. GL_G__GLOBAL, GL_L__0, A1_R_1000_0');p.add_argument('--output');a=p.parse_args()
root=Path(__file__).resolve().parent
if Path(a.scope).name!=a.scope:raise ValueError('scope must be an identifier')
df=pd.read_csv(root/'evidence'/f'{a.scope}.csv.gz',dtype={'seed':str,'group_id':str},keep_default_na=False)
df=df[df['passes_'+a.config]].copy();df['config']=a.config;df['rank_within_group']=range(1,len(df)+1)
if a.output:df.to_csv(a.output,index=False)
else:print(df.to_string(index=False))
