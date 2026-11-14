from pathlib import Path
import argparse,json,hashlib
import numpy as np
import pandas as pd
p=argparse.ArgumentParser();p.add_argument('--root',required=True);R=Path(p.parse_args().root);O=R/'category_fixed_budget';O.mkdir(exist_ok=True)
x=np.load(R/'category_patterns/discovery_l2.npy');cols=json.loads((R/'category_patterns/l2_items.json').read_text());ix={c:i for i,c in enumerate(cols)}
b=pd.read_csv(R/'category_patterns/discovery_l2_baskets.csv',dtype=str);labels=pd.read_csv(R/'labels/customer_clusters.csv',dtype=str);random=pd.read_csv(R/'labels/random_groups.csv',dtype=str)
groups={('G',''):pd.Series('GLOBAL',index=b.index),('L',''):b.customer_id.map(labels.set_index('customer_id').cluster_id)}
for seed,z in random.groupby('seed'):groups[('R',seed)]=b.customer_id.map(z.set_index('customer_id').random_group_id)
rules={}
for f in sorted((R/'category_screening/scope_rules').glob('*.csv.gz')):
    e=pd.read_csv(f,dtype={'seed':str,'group_id':str},keep_default_na=False,low_memory=False)
    for col in ['joint_count','confidence','lift']:e[col]=pd.to_numeric(e[col])
    key=tuple(e.iloc[0][['method','seed','group_id']]);rules[key]=e[e.passes_strict & e.passes_increment].sort_values(['joint_count','confidence','lift','rule_id'],ascending=[False,False,False,True]).copy()
assert len(rules)==64
def allocate(sizes,B):
    raw={g:B*n/sum(sizes.values()) for g,n in sizes.items()};a={g:int(v) for g,v in raw.items()}
    for g in sorted(raw,key=lambda g:(-(raw[g]-a[g]),g))[:B-sum(a.values())]:a[g]+=1
    return a
cache={}
def hit(items):
    key=tuple(sorted(items))
    if key not in cache:cache[key]=x[:,[ix[c] for c in key]].all(1)
    return cache[key]
results=[];audit=[];selected=[];order_rows=[]
for (method,seed),assignment in groups.items():
    assert assignment.notna().all();sizes=assignment.value_counts().to_dict()
    for B in [20,50,100]:
        quota=allocate(sizes,B);covered=np.zeros(len(b),bool);triggered=covered.copy();allsets=set();allrules=set();actual=0
        for g,n in sorted(sizes.items()):
            z=rules[(method,seed,g)].head(quota[g]).copy();mask=assignment.eq(g).to_numpy();local_cov=np.zeros(len(b),bool);local_ant=local_cov.copy();combos=set()
            for row in z.itertuples():
                a=json.loads(row.antecedent);c=json.loads(row.consequent);combo=tuple(sorted(a+c));combos.add(combo);allsets.add(combo);allrules.add(row.rule_id)
                local_cov |= hit(a+c)&mask;local_ant |= hit(a)&mask
            covered|=local_cov;triggered|=local_ant;actual+=len(z)
            z['budget']=B;z['allocated_budget']=quota[g];z['rank_within_group']=range(1,len(z)+1);selected.append(z)
            audit.append(dict(method=method,seed=seed,group_id=g,budget=B,n_baskets=n,allocated=quota[g],actual=len(z),available=len(rules[(method,seed,g)]),two_category=int(z.length.eq(2).sum()),three_category=int(z.length.eq(3).sum()),unique_combinations=len(combos),covered_orders=int(local_cov.sum()),coverage=local_cov.sum()/n,triggered_orders=int(local_ant.sum())))
        assert actual==B and sum(quota.values())==B and (covered<=triggered).all()
        results.append(dict(method=method,seed=seed,budget=B,actual=actual,unique_rule_ids=len(allrules),unique_combinations=len(allsets),covered_orders=int(covered.sum()),order_coverage=covered.mean(),triggered_orders=int(triggered.sum()),antecedent_coverage=triggered.mean()))
        order_rows.append(pd.DataFrame(dict(basket_id=b.basket_id,method=method,seed=seed,budget=B,assigned_group=assignment,covered=covered,triggered=triggered)))
s=pd.DataFrame(results);s.to_csv(O/'system_metrics.csv',index=False);pd.DataFrame(audit).to_csv(O/'allocation_audit.csv',index=False);pd.concat(selected).to_csv(O/'selected_rules.csv',index=False,encoding='utf-8-sig');pd.concat(order_rows).to_csv(O/'order_coverage.csv.gz',index=False,compression='gzip')
summary=[]
for B in [20,50,100]:
    z=s[s.budget.eq(B)];g=z[z.method.eq('G')].iloc[0];l=z[z.method.eq('L')].iloc[0];r=z[z.method.eq('R')]
    assert len(r)==20
    summary.append(dict(budget=B,G=g.order_coverage,L=l.order_coverage,R_median=r.order_coverage.median(),R_min=r.order_coverage.min(),R_max=r.order_coverage.max(),L_minus_G_pp=100*(l.order_coverage-g.order_coverage),L_greater_random=int((l.order_coverage>r.order_coverage).sum()),L_equal_random=int((l.order_coverage==r.order_coverage).sum())))
v=pd.DataFrame(summary);v.to_csv(O/'comparison.csv',index=False)
def md(d):return '| '+' | '.join(d.columns)+' |\n|'+'|'.join(['---']*len(d.columns))+'|\n'+'\n'.join('| '+' | '.join(str(v) for v in row)+' |' for row in d.itertuples(index=False,name=None))
display=v.copy()
for col in ['G','L','R_median','R_min','R_max']:display[col]=display[col].map(lambda z:f'{z:.2%}')
display.L_minus_G_pp=display.L_minus_G_pp.round(2)
lines=['# 品类层固定系统预算 G/L/R 比较','严格档：support≥3%，联合及前件次数≥20，confidence≥50%，lift≥1.5；三品类额外要求confidence增量≥5个百分点。Discovery开发配置，未经Validation选择。二/三品类混合排序，未设置长度配额。','系统总预算B=20/50/100。G独占B；L及每个随机种子按其组内Discovery订单数用最大余数法分配，平局按group_id，不转移剩余名额。每个组按联合次数↓、confidence↓、lift↓、rule_id↑取规则。不同群同一规则各占一个部署名额；反向规则各占名额，不额外做组合去重。所有系统实际名额均等于B。','群内规则仅用于对应群的订单。系统覆盖率为完整包含至少一条被部署规则的订单并集÷7521；前件触达率另列，不是预测准确率或未来表现。每个随机种子产生一个全系统指标，20次重复，不把60组当独立样本。',md(display),'## 配额及规则长度组成',md(pd.DataFrame(audit).query("method != 'R'")[['method','group_id','budget','allocated','actual','two_category','three_category','unique_combinations','coverage']]),'## 输出','system_metrics.csv：每个系统及随机种子的覆盖、触达与去重数量；allocation_audit.csv：各组配额及命中数；selected_rules.csv：实际部署规则；order_coverage.csv.gz：逐订单命中及分组，可复核比较。','规则用同一Discovery数据选取并评估，属于开发期描述。L超过若干随机种子不是显著性检验。结果仅代表当前配置、预算分配和排序，不能推出其他策略的优劣。']
(O/'固定预算对照报告.md').write_text('\n\n'.join(lines),encoding='utf-8')
assert s.groupby(['method','seed']).order_coverage.apply(lambda z:z.is_monotonic_increasing).all()
(O/'manifest.json').write_text(json.dumps(dict(config='strict_increment5pp',budgets=[20,50,100],n_orders=len(b),n_systems=22,random_seeds=sorted(random.seed.unique(),key=int),source_manifest_sha256=hashlib.sha256((R/'category_screening/manifest.json').read_bytes()).hexdigest(),checks=['64 input scopes','every system actual rules equals budget','coverage union uses assigned-group rules only','coverage is subset of antecedent triggers','coverage monotonic with budget'],script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2),encoding='utf-8')
print(v.to_string(index=False));print(pd.DataFrame(audit).query("method != 'R'").to_string(index=False))
