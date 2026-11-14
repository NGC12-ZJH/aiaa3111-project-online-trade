from pathlib import Path
import json, subprocess, hashlib, argparse
import pandas as pd

p=argparse.ArgumentParser();p.add_argument('--root',required=True);args=p.parse_args()
R=Path(args.root); O=R/'taxonomy_analysis';O.mkdir(exist_ok=True)
commit='c89430d4cb894154d6084b3eae7f70ba18a04069'
repo=R/'publish-pattern-mining'
def gitfile(path):
    return (R/'taxonomy_analysis'/Path(path).name).read_bytes()
raw=gitfile('data/taxonomy/item_taxonomy_v1.csv');(O/'item_taxonomy_v1.csv').write_bytes(raw)
config=gitfile('configs/taxonomy/taxonomy_v1.json');(O/'taxonomy_v1.json').write_bytes(config)
tax=pd.read_csv(O/'item_taxonomy_v1.csv',dtype=str,keep_default_na=False)
assert not tax.stock_code.duplicated().any()
assert set(tax.taxonomy_version)=={'taxonomy_v1'}
t=tax.set_index('stock_code').to_dict('index')
names={}
def walk(x):
    if isinstance(x,dict):
        if 'id' in x and 'name_zh' in x:names[x['id']]=x['name_zh']
        for v in x.values():walk(v)
    elif isinstance(x,list):
        for v in x:walk(v)
walk(json.loads(config))
e=pd.read_csv(R/'patterns/rule_evidence.csv.gz',dtype={'seed':str,'group_id':str},keep_default_na=False,low_memory=False)
for col in ['joint_count','antecedent_count','support','confidence','lift']:
    e[col]=pd.to_numeric(e[col],errors='coerce')
u=e[['rule_id','antecedent','consequent']].drop_duplicates('rule_id'); rows=[]
for r in u.itertuples():
    a=json.loads(r.antecedent);b=json.loads(r.consequent);codes=a+b
    assert all(c in t for c in codes),codes
    cats=[t[c]['l2_id'] for c in codes];design=[t[c]['design_line'] for c in codes]
    unknown=any(c in ('','other') for c in cats)
    typ=('未分类（含other）' if unknown else '同类换款' if len(set(cats))==1 else '同系列配套' if len(set(design))==1 and design[0] not in ('','none') else '真正跨类搭配')
    d=dict(rule_id=r.rule_id,length=len(codes),granularity='sku',taxonomy_version='taxonomy_v1',rule_type=typ,taxonomy_unknown=unknown,is_cross_category=(not unknown and len(set(cats))>1),itemset=json.dumps(sorted(codes)))
    for side,items in [('antecedent',a),('consequent',b)]:
        for field in ['l2_id','l1_id','design_line','season']:
            d[side+'_'+field]=json.dumps([t[c][field] for c in items],ensure_ascii=False)
        d[side+'_name']=' + '.join(t[c]['canonical_description'] for c in items)
        d[side+'_category']=' + '.join(names.get(t[c]['l2_id'],t[c]['l2_id']) for c in items)
    rows.append(d)
ann=pd.DataFrame(rows);ann.to_csv(O/'candidate_taxonomy.csv',index=False,encoding='utf-8-sig')
e=e.merge(ann,on='rule_id',validate='many_to_one');assert len(e)==719744
e.to_csv(O/'rule_evidence_taxonomy.csv.gz',index=False,compression='gzip')
q=e[e.eligible & e.generated_here].copy();q.to_csv(O/'qualified_rules_taxonomy.csv.gz',index=False,compression='gzip')
types=['同类换款','同系列配套','真正跨类搭配','未分类（含other）'];counts=[];tops=[]
keys=['method','seed','group_id']
for scope,scope_e in e.groupby(keys):
    z=q[(q[keys]==pd.Series(scope,index=keys)).all(axis=1)]
    for length in [2,3]:
        zlen=z[z.length.eq(length)]
        for typ in types:
            n=int(zlen.rule_type.eq(typ).sum())
            counts.append(dict(zip(keys,scope),length=length,rule_type=typ,count=n,total=len(zlen),share=n/len(zlen) if len(zlen) else None))
    for length in [0,2,3]:
        cross=z[z.is_cross_category & (z.length.eq(length) if length else True)].sort_values(['joint_count','confidence','lift','rule_id'],ascending=[False,False,False,True]).copy()
        cross['ranking_length']=length;cross['rank']=range(1,len(cross)+1);tops.append(cross.head(50))
counts=pd.DataFrame(counts);top=pd.concat(tops)
counts.to_csv(O/'classification_counts.csv',index=False,encoding='utf-8-sig')
top.to_csv(O/'cross_category_top50.csv',index=False,encoding='utf-8-sig')
assert counts.groupby(keys+['length'])['count'].sum().sum()==len(q)
assert top.is_cross_category.all()
def md(df):
    return '| '+' | '.join(df.columns)+' |\n|'+'|'.join(['---']*len(df.columns))+'|\n'+'\n'.join('| '+' | '.join(str(v).replace('|',' / ').replace('\n',' ') for v in row)+' |' for row in df.itertuples(index=False,name=None))
intro='''# 现有规则 taxonomy 分析

仅标注原有 Discovery 规则；未重新挖掘、未改变筛选或排序，未使用 Validation/Test。
范围包括 G、C0/C1/C2，以及 20 个随机种子各三个组（64 个范围）。统计对象为 generated_here 且 eligible 的方向规则，A→B 与 B→A 分别计数。

三商品规则按前后件的全部商品统一判定：全部同一 l2 为同类换款；否则全部属于同一个非 none design_line 为同系列配套；其余为真正跨类搭配。三商品中只有部分商品共享系列仍归第三类。含 other 单列为未分类，不强行解释为跨类。该分类描述标签关系，不证明款式替代、功能互补或业务价值。

占比以该范围、该长度的全部合格方向规则为分母。跨类榜包括同系列配套和真正跨类搭配；先筛选跨类，再按 joint_count↓、confidence↓、lift↓、rule_id↑ 排序。各范围独立 Top50，前10/20即对应榜单，不是系统预算。0表示二/三商品混合榜；不足50不补齐。
'''
lines=[intro,'## G/L 分类数量与占比']
display=counts[counts.method.ne('R')].copy();display['share']=display.share.map(lambda v:f'{v:.2%}' if pd.notna(v) else '无规则')
lines.append(md(display))
for (method,seed,g,length),part in top[top.method.ne('R') & top.ranking_length.ne(0)].groupby(keys+['ranking_length']):
    part=part.head(10).copy();part['规则']=part.antecedent_name+' → '+part.consequent_name;part['子类']=part.antecedent_category+' → '+part.consequent_category
    for c in ['support','confidence']:part[c]=part[c].map(lambda x:f'{x:.2%}')
    part['lift']=part.lift.round(2)
    lines.extend([f'## {method}/{g} {length}商品跨类 Top10',md(part[['rank','规则','子类','rule_type','joint_count','support','confidence','lift']])])
lines.append('## 完整输出\nclassification_counts.csv：所有64范围的分类占比（含零计数）；cross_category_top50.csv：混合、二商品、三商品完整Top50；candidate_taxonomy.csv：共同候选池标签；rule_evidence_taxonomy.csv.gz：全部证据附标签。随机组保持每个seed分开，不当成独立的60次重复。')
(O/'taxonomy规则分析.md').write_text('\n\n'.join(lines),encoding='utf-8')
manifest=dict(taxonomy_commit=commit,taxonomy_sha256=hashlib.sha256(raw).hexdigest(),evidence_sha256=hashlib.sha256((R/'patterns/rule_evidence.csv.gz').read_bytes()).hexdigest(),candidate_rules=len(ann),evidence_rows=len(e),qualified_rows=len(q),scopes=64,unknown_qualified=int(q.taxonomy_unknown.sum()),checks='mapping complete; evidence rows preserved; counts reconcile; all top rules cross-category')
(O/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(display.to_string(index=False));print(json.dumps(manifest,ensure_ascii=False))
