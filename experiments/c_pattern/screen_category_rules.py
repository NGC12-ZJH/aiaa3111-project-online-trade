from pathlib import Path
import argparse,json,hashlib
import numpy as np
import pandas as pd
p=argparse.ArgumentParser();p.add_argument('--root',required=True);R=Path(p.parse_args().root);S=R/'category_patterns';O=R/'category_screening';O.mkdir(exist_ok=True);(O/'scope_rules').mkdir(exist_ok=True)
configs={'baseline':(.01,.2,1.),'moderate':(.02,.4,1.3),'strict':(.03,.5,1.5)}
x=np.load(S/'discovery_l2.npy');cols=json.loads((S/'l2_items.json').read_text());ix={c:i for i,c in enumerate(cols)}
b=pd.read_csv(S/'discovery_l2_baskets.csv',dtype=str);labels=pd.read_csv(R/'labels/customer_clusters.csv',dtype=str);random=pd.read_csv(R/'labels/random_groups.csv',dtype=str)
real=b.customer_id.map(labels.set_index('customer_id').cluster_id)
candidate=pd.read_csv(S/'candidate_rules.csv');ants=candidate.antecedent.map(json.loads).tolist();cons=candidate.consequent.map(json.loads).tolist()
sets=[tuple(sorted(a+c)) for a,c in zip(ants,cons)];unique=sorted(set(sets));ui={s:i for i,s in enumerate(unique)}
hits=np.stack([x[:,[ix[c] for c in s]].all(1) for s in unique]);indices=np.array([ui[s] for s in sets]);ante_sets=sorted({tuple(a) for a in ants});amap={s:i for i,s in enumerate(ante_sets)};ahits=np.stack([x[:,[ix[c] for c in s]].all(1) for s in ante_sets]);aindices=np.array([amap[tuple(a)] for a in ants])
key_index={(tuple(a),c[0]):i for i,(a,c) in enumerate(zip(ants,cons))}
trip=np.array([i for i,a in enumerate(ants) if len(a)==2]);s1=np.array([key_index.get(((ants[i][0],),cons[i][0]),-1) for i in trip]);s2=np.array([key_index.get(((ants[i][1],),cons[i][0]),-1) for i in trip]);assert (s1>=0).all() and (s2>=0).all()
summary=[];tops=[];concentration=[];base_reconciled=0
rankcols=['joint_count','confidence','lift','rule_id'];rankasc=[False,False,False,True]
for f in sorted((S/'evidence').glob('*.csv.gz')):
    e=pd.read_csv(f,dtype={'seed':str,'group_id':str},keep_default_na=False,low_memory=False)
    assert e.rule_id.tolist()==candidate.rule_id.tolist()
    for c in ['support','confidence','lift','joint_count','antecedent_count']:e[c]=pd.to_numeric(e[c],errors='coerce')
    method=e.method.iloc[0];seed=e.seed.iloc[0];g=e.group_id.iloc[0]
    if method=='G':mask=np.ones(len(b),bool)
    elif method=='L':mask=real.eq(g).to_numpy()
    else:mask=b.customer_id.map(random[random.seed.eq(seed)].set_index('customer_id').random_group_id).eq(g).to_numpy()
    n=int(mask.sum());assert n==e.n_baskets.iloc[0]
    conf=e.confidence.to_numpy();inc=np.full(len(e),np.nan);inc[trip]=conf[trip]-np.maximum(conf[s1],conf[s2]);e['confidence_increment_pp']=inc*100
    e['single1_confidence']=np.nan;e['single2_confidence']=np.nan;e.loc[trip,'single1_confidence']=conf[s1];e.loc[trip,'single2_confidence']=conf[s2]
    e['single1_rule_id']='';e['single2_rule_id']='';e.loc[trip,'single1_rule_id']=candidate.rule_id.iloc[s1].to_numpy();e.loc[trip,'single2_rule_id']=candidate.rule_id.iloc[s2].to_numpy()
    e['passes_increment']=e.length.eq(2) | (e.confidence_increment_pp>=5-1e-10)
    popularity=pd.Series(x[mask].mean(0),index=cols).sort_values(ascending=False,kind='stable');popular=set(popularity.head(10).index)
    h=hits[:,mask];ah=ahits[:,mask]
    for config,(sup,confidence,lift) in configs.items():
        passed=e.generated_here & e.support.ge(sup) & e.joint_count.ge(20) & e.antecedent_count.ge(20) & e.confidence.ge(confidence) & e.lift.ge(lift)
        e['passes_'+config]=passed
        if config=='baseline':assert np.array_equal(passed.to_numpy(),(e.generated_here & e.eligible).to_numpy());base_reconciled+=1
        for incremental in [False,True]:
            take=passed & (e.passes_increment if incremental else True)
            variant='increment5pp' if incremental else 'no_increment'
            for length in [0,2,3]:
                selected=take & (e.length.eq(length) if length else True);pos=np.flatnonzero(selected);z=e.loc[selected].sort_values(rankcols,ascending=rankasc)
                js=np.unique(indices[pos]);aas=np.unique(aindices[pos]);covered=h[js].any(0) if len(js) else np.zeros(n,bool);trigger=ah[aas].any(0) if len(aas) else np.zeros(n,bool)
                combos=[unique[i] for i in js];topcombos=[sets[i] for i in z.drop_duplicates(['antecedent','consequent']).head(50).index]
                # Concentration uses unique itemsets, so directions do not multiply frequencies.
                freq=pd.Series([c for s in combos for c in s],dtype=str).value_counts()
                if len(freq):
                    for c,count in freq.head(10).items():concentration.append(dict(method=method,seed=seed,group_id=g,config=config,increment=variant,length=length,l2=c,itemset_count=int(count),itemset_share=count/len(combos),basket_prevalence=popularity[c],is_top10_popular=c in popular))
                allhot=sum(set(s)<=popular for s in combos)
                row=dict(method=method,seed=seed,group_id=g,config=config,increment=variant,length=length,n_baskets=n,rules=len(z),unique_combinations=len(js),covered_orders=int(covered.sum()),order_coverage=float(covered.mean()),triggered_orders=int(trigger.sum()),antecedent_coverage=float(trigger.mean()),empty=len(z)==0,distinct_l2=len(freq),all_items_top10_popular_share=allhot/len(combos) if combos else np.nan,most_common_l2=freq.index[0] if len(freq) else '',most_common_l2_itemset_share=float(freq.iloc[0]/len(combos)) if len(freq) else np.nan)
                summary.append(row)
                top=z.head(50).copy();top['screening_config']=config;top['increment_policy']=variant;top['ranking_length']=length;top['rank']=range(1,len(top)+1);tops.append(top)
    e[e.passes_baseline].to_csv(O/'scope_rules'/f.name,index=False,compression='gzip')
    print('screened',method,seed,g,flush=True)
summary=pd.DataFrame(summary);summary.to_csv(O/'scope_summary.csv',index=False,encoding='utf-8-sig');pd.DataFrame(concentration).to_csv(O/'category_concentration.csv',index=False,encoding='utf-8-sig');pd.concat(tops).to_csv(O/'top50.csv',index=False,encoding='utf-8-sig')
# Each seed is one replicate: average its three groups before summarizing the 20 seeds.
metrics=['rules','unique_combinations','order_coverage','antecedent_coverage','distinct_l2','all_items_top10_popular_share','most_common_l2_itemset_share']
seedlevel=summary[summary.method.eq('R')].groupby(['seed','config','increment','length'])[metrics].mean().reset_index();seedlevel.to_csv(O/'random_seed_means.csv',index=False)
seedlevel.groupby(['config','increment','length'])[metrics].agg(['median','min','max']).to_csv(O/'random_seed_summary.csv')
def md(df):return '| '+' | '.join(df.columns)+' |\n|'+'|'.join(['---']*len(df.columns))+'|\n'+'\n'.join('| '+' | '.join(str(v).replace('|',' / ') for v in row)+' |' for row in df.itertuples(index=False,name=None))
lines=['# 品类层三档筛选与三品类增量检查','仅筛选已有Discovery证据，不重新挖掘，不使用Validation/Test。三档support/confidence/lift依次为：基线1%/20%/1；中等2%/40%/1.3；严格3%/50%/1.5；联合及前件次数均≥20。','每档分别报告不检查增量、三品类增量≥5个百分点。增量为confidence(AB→C)−max(confidence(A→C),confidence(B→C))，直接使用共同池中单前件证据，即使单前件规则未合格也参与比较。二品类不做该增量筛选。它不是统计显著性检验。','订单覆盖率＝至少完整包含一条保留规则全部品类的订单数÷本范围全部订单数；另列前件触达率。使用全部保留规则，不是TopK或系统预算。不同组合数对前后件并集去重。三品类指3个不同l2。','热门品类按各范围订单出现率取Top10（同率按类别代码排序）。报告保留组合中全部商品均属于热门Top10的比例、覆盖子类数和最集中子类占组合的比例；以不同组合计数避免正反规则重复影响。不设任意阈值把结果判为仅剩热门。','随机结果先在每个seed内对3组取等权均值，再汇总20个seed，不将60组当独立样本。零规则时覆盖率为0，集中度未定义留空。']
for incname in ['no_increment','increment5pp']:
    d=summary[summary.method.ne('R') & summary.length.ne(0) & summary.increment.eq(incname)].copy()
    for col in ['order_coverage','all_items_top10_popular_share']:d[col]=d[col].map(lambda v:f'{v:.2%}' if pd.notna(v) else '—')
    lines += [f'## {incname}',md(d[['method','group_id','config','length','rules','unique_combinations','order_coverage','distinct_l2','all_items_top10_popular_share']])]
empty=summary[summary.empty & summary.length.ne(0)];lines += ['## 空范围',md(empty[['method','seed','group_id','config','increment','length']]) if len(empty) else '所有范围及两种长度均有保留规则。','## 文件说明','scope_rules/：原基线合格规则及三档通过标记、增量值及两个单前件置信度和ID。scope_summary.csv：全部64范围×3档×2增量方案×3长度口径。top50.csv：各配置独立Top50。category_concentration.csv：各范围保留组合的高频子类。random_seed_means.csv：按种子聚合；随机均值不代表合并订单覆盖率。','这些结果用于Discovery敏感性分析。规则数量和覆盖率不能独自决定最终参数，下一步需Validation验证；未据此作显著性或业务增益结论。']
(O/'品类层筛选对照报告.md').write_text('\n\n'.join(lines),encoding='utf-8')
manifest=dict(configs=configs,increment_pp=5,n_scopes=base_reconciled,summary_rows=len(summary),source_manifest_sha256=hashlib.sha256((S/'manifest.json').read_bytes()).hexdigest(),checks=['64 baseline counts reconcile','all triple single antecedent rules found','scope basket denominators match','coverage computed as union of exact basket membership'],script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
assert base_reconciled==64 and len(summary)==1152
(O/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(summary[summary.method.ne('R') & summary.length.eq(0)][['method','group_id','config','increment','rules','unique_combinations','order_coverage','distinct_l2','all_items_top10_popular_share']].to_string(index=False));print('EMPTY',len(empty),flush=True)
