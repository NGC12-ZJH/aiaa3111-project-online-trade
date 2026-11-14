"""Discovery L2 G/L/R baseline; frozen taxonomy, no validation tuning."""
import argparse,json,hashlib,time
from pathlib import Path
import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import fpgrowth
from mlxtend.frequent_patterns import fpcommon
from importlib import import_module
import math
def mine_bool(data,threshold):
    assert data.dtypes.eq(bool).all()
    tree,disabled,_=fpcommon.setup_fptree(data,threshold)
    generator=import_module('mlxtend.frequent_patterns.fpgrowth').fpg_step(tree,math.ceil(threshold*len(data)),None,3,0)
    rows=[]
    for count,items in generator:
        assert int(data.values[:,items].all(1).sum())==count
        if count/len(data)>=threshold:rows.append(frozenset(items))
    return pd.DataFrame({'itemsets':rows})
p=argparse.ArgumentParser();p.add_argument('--root',required=True);R=Path(p.parse_args().root);O=R/'category_patterns';O.mkdir(exist_ok=True);start=time.perf_counter()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
b=pd.read_csv(R/'discovery_baskets.csv',dtype=str,keep_default_na=False)
t=pd.read_csv(R/'taxonomy_analysis/item_taxonomy_v1.csv',dtype=str,keep_default_na=False)
assert t.stock_code.is_unique
mapping=t.set_index('stock_code').l2_id.to_dict()
original=b['items'].map(json.loads)
assert all(c in mapping for items in original for c in items)
mapped=original.map(lambda items:sorted({mapping[c] for c in items if mapping[c] not in ('other','')}))
cols=sorted({c for items in mapped for c in items});idx={c:i for i,c in enumerate(cols)}
x=np.zeros((len(b),len(cols)),dtype=bool)
for i,items in enumerate(mapped):x[i,[idx[c] for c in items]]=True
assert len(b)==7521 and b.basket_id.is_unique
bb=b.copy();bb['items']=mapped.map(json.dumps);bb['n_l2']=mapped.map(len);bb.to_csv(O/'discovery_l2_baskets.csv',index=False)
np.save(O/'discovery_l2.npy',x);(O/'l2_items.json').write_text(json.dumps(cols),encoding='utf-8')
labels=pd.read_csv(R/'labels/customer_clusters.csv',dtype=str);rand=pd.read_csv(R/'labels/random_groups.csv',dtype=str)
assert labels.customer_id.is_unique
real=b.customer_id.map(labels.set_index('customer_id').cluster_id);assert real.notna().all()
groups=sorted(real.unique());scopes=[('G','','GLOBAL',np.ones(len(b),bool))]+[('L','',g,real.eq(g).to_numpy()) for g in groups]
for seed,z in rand.groupby('seed',sort=True):
    assert z.customer_id.is_unique and set(z.customer_id)==set(labels.customer_id)
    assert z.random_group_id.value_counts().to_dict()==labels.cluster_id.value_counts().to_dict()
    rr=b.customer_id.map(z.set_index('customer_id').random_group_id);assert rr.notna().all()
    scopes += [('R',seed,g,rr.eq(g).to_numpy()) for g in groups]
assert len(scopes)==64
cfg=dict(config_id='l2_discovery_baseline_v1',status='exploratory_not_validation_selected',granularity='l2',taxonomy_version='taxonomy_v1',min_support=.01,min_joint_count=20,min_antecedent_count=20,min_confidence=.2,min_lift=1,max_itemset_length=3,ranking='joint_count desc, confidence desc, lift desc, rule_id asc',empty_baskets='retained in denominator',other='excluded before within-basket deduplication')
(O/'config.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
generated={};pool=set();audits=[]
for method,seed,g,mask in scopes:
    tick=time.perf_counter();n=int(mask.sum());found=mine_bool(pd.DataFrame(x[mask]),max(.01,20/n))
    keys={(tuple(sorted(items-{c})),c) for items in found.itemsets if len(items)>1 for c in items}
    generated[(method,seed,g)]=keys;pool.update(keys)
    audits.append(dict(method=method,seed=seed,group_id=g,n_baskets=n,n_customers=b.loc[mask,'customer_id'].nunique(),empty_baskets=int((x[mask].sum(1)==0).sum()),single_category_baskets=int((x[mask].sum(1)==1).sum()),generated_rules=len(keys),mining_seconds=time.perf_counter()-tick))
    print('mined',method,seed,g,len(keys),flush=True)
pool=sorted(pool);components=sorted({a for a,c in pool}|{(c,) for a,c in pool}|{tuple(sorted(a+(c,))) for a,c in pool})
ci={s:i for i,s in enumerate(components)}
# Membership stored once, exact integer counts computed for each scope.
hits=np.stack([x[:,list(s)].all(1) for s in components])
ai=np.array([ci[a] for a,c in pool]);bi=np.array([ci[(c,)] for a,c in pool]);ji=np.array([ci[tuple(sorted(a+(c,)))] for a,c in pool])
total=hits.sum(1);names={}
def walk(obj):
    if isinstance(obj,dict):
        if 'id' in obj and 'name_zh' in obj:names[obj['id']]=obj['name_zh']
        for v in obj.values():walk(v)
    elif isinstance(obj,list):
        for v in obj:walk(v)
walk(json.loads((R/'taxonomy_analysis/taxonomy_v1.json').read_text(encoding='utf-8')))
base=pd.DataFrame([dict(rule_id=hashlib.sha256(json.dumps(['l2',[cols[i] for i in a],[cols[c]]]).encode()).hexdigest()[:16],antecedent=json.dumps([cols[i] for i in a]),consequent=json.dumps([cols[c]]),antecedent_name=' + '.join(names.get(cols[i],cols[i]) for i in a),consequent_name=names.get(cols[c],cols[c]),length=len(a)+1,granularity='l2',taxonomy_version='taxonomy_v1',config_id=cfg['config_id']) for a,c in pool])
assert base.rule_id.is_unique
base.to_csv(O/'candidate_rules.csv',index=False,encoding='utf-8-sig')
qualified=[];summary=[];tops=[];global_ranks={};scope_dir=O/'evidence';scope_dir.mkdir(exist_ok=True)
for method,seed,g,mask in scopes:
    n=int(mask.sum());no=len(b)-n;cnt=hits[:,mask].sum(1);j=cnt[ji];ac=cnt[ai];cc=cnt[bi]
    support=j/n;conf=np.divide(j,ac,out=np.full(len(pool),np.nan),where=ac>0);lift=np.divide(conf,cc/n,out=np.full(len(pool),np.nan),where=cc>0)
    jo=total[ji]-j;ao=total[ai]-ac
    e=base.copy();e['method']=method;e['seed']=seed;e['group_id']=g;e['n_baskets']=n;e['joint_count']=j;e['antecedent_count']=ac;e['consequent_count']=cc;e['support']=support;e['confidence']=conf;e['lift']=lift
    e['outside_baskets']=no;e['outside_joint_count']=jo;e['outside_antecedent_count']=ao;e['outside_support']=jo/no if no else np.nan;e['outside_confidence']=np.divide(jo,ao,out=np.full(len(pool),np.nan),where=ao>0);e['support_difference']=e.support-e.outside_support
    e['generated_here']=[key in generated[(method,seed,g)] for key in pool];e['eligible']=(j>=20)&(ac>=20)&(support>=.01)&(conf>=.2)&(lift>=1)
    q=e[e.eligible & e.generated_here].sort_values(['joint_count','confidence','lift','rule_id'],ascending=[False,False,False,True]).copy()
    if method=='G':global_ranks=dict(zip(q.rule_id,range(1,len(q)+1)))
    e['global_rank']=e.rule_id.map(global_ranks);e['global_eligible']=e.rule_id.isin(global_ranks)
    e.to_csv(scope_dir/f'{method}_{seed}_{g}.csv.gz',index=False,compression='gzip')
    qualified.append(q)
    for length in [0,2,3]:
        sub=q if length==0 else q[q.length.eq(length)]
        summary.append(dict(method=method,seed=seed,group_id=g,length=length,qualified_rules=len(sub)))
        sub=sub.head(50).copy();sub['rank']=range(1,len(sub)+1);sub['ranking_length']=length;tops.append(sub)
    # Check a concrete qualifying rule directly against mapped baskets.
    if len(q):
        rr=q.iloc[0];items=json.loads(rr.antecedent)+json.loads(rr.consequent)
        assert int(x[mask][:,[idx[c] for c in items]].all(1).sum())==rr.joint_count
    print('evidence',method,seed,g,len(q),flush=True)
pd.concat(qualified).to_csv(O/'qualified_rules.csv.gz',index=False,compression='gzip')
top=pd.concat(tops);top.to_csv(O/'top50_by_scope_length.csv',index=False,encoding='utf-8-sig')
summary=pd.DataFrame(summary);summary.to_csv(O/'rule_counts.csv',index=False);pd.DataFrame(audits).to_csv(O/'scope_audit.csv',index=False)
def table(df):
    return '| '+' | '.join(df.columns)+' |\n|'+'|'.join(['---']*len(df.columns))+'|\n'+'\n'.join('| '+' | '.join(str(v).replace('|',' / ') for v in row)+' |' for row in df.itertuples(index=False,name=None))
lines=['# 品类层 Discovery 探索基线','SKU 映射为冻结 taxonomy_v1 的 l2_id；排除 other，订单内去重。保留原始全部7521张订单，包括映射后空篮，保持G/L/R分母与客户分组。二品类 A→B；三品类 {A,B}→C。','门槛沿用商品层仅作为探索基线：support≥1%，联合与前件计数≥20，confidence≥20%，lift≥1，最长3品类。不是最终选定参数。后续由Validation选择门槛或排序，Test未使用。跨粒度命中率及规则数量不能直接作为优劣证据。','排名：联合次数↓、confidence↓、lift↓、rule_id↑；每个范围独立Top50，不是部署预算。共同候选池来自64个范围，在每个范围重算群内外证据；随机组逐seed保留。',f'实际观察到{len(cols)}个非other子类；映射后空篮{int((x.sum(1)==0).sum())}张，单品类篮{int((x.sum(1)==1).sum())}张；共同候选池{len(pool)}条方向规则。','## G/L 合格规则数',table(summary[summary.method.ne('R')])]
for (method,g,length),z in top[top.method.ne('R') & top.ranking_length.ne(0)].groupby(['method','group_id','ranking_length']):
    z=z.head(10).copy();z['rule']=z.antecedent_name+' → '+z.consequent_name
    for c in ['support','confidence']:z[c]=z[c].map(lambda v:f'{v:.2%}')
    z['lift']=z.lift.round(2);lines.extend([f'## {method}/{g} {length}品类 Top10',table(z[['rank','rule','joint_count','support','confidence','lift']])])
(O/'品类层挖掘报告.md').write_text('\n\n'.join(lines),encoding='utf-8')
manifest=dict(config=cfg,common_pool_rules=len(pool),evidence_rows=len(pool)*64,n_scopes=64,n_baskets=len(b),n_l2=len(cols),empty_baskets=int((x.sum(1)==0).sum()),elapsed_seconds=time.perf_counter()-start,inputs={f:sha(R/f) for f in ['discovery_baskets.csv','labels/customer_clusters.csv','labels/random_groups.csv','taxonomy_analysis/item_taxonomy_v1.csv','taxonomy_analysis/manifest.json']},code_sha256=sha(Path(__file__)),checks=['all SKU mapped','basket IDs unique and denominator unchanged','random customer counts matched','64 scopes','rule IDs unique','top rule exact count checked in each scope'])
(O/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');print(summary[summary.method.ne('R')].to_string(index=False));print(json.dumps(manifest),flush=True)
