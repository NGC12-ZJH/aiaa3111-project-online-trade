from pathlib import Path
import argparse,json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser();p.add_argument('--root',required=True);R=Path(p.parse_args().root);O=R/'category_similarity';O.mkdir(exist_ok=True)
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False,'font.size':11,'savefig.dpi':180})
names=['G','C0','C1','C2'];frames={};evidence={};keys={};rows=[];sizes=[];members=[]
def combo(a,c):return tuple(sorted(json.loads(a)+json.loads(c)))
for scope,file in zip(names,['G__GLOBAL','L__0','L__1','L__2']):
    d=pd.read_csv(R/'category_screening/scope_rules'/f'{file}.csv.gz',low_memory=False)
    q=d[d.passes_strict & d.passes_increment].copy();q['combo']=[combo(a,c) for a,c in zip(q.antecedent,q.consequent)]
    frames[scope]=q.sort_values(['joint_count','confidence','lift','rule_id'],ascending=[False,False,False,True]).drop_duplicates('combo')
    e=pd.read_csv(R/'category_patterns/evidence'/f'{file}.csv.gz',usecols=['antecedent','consequent','support','length'])
    e['combo']=[combo(a,c) for a,c in zip(e.antecedent,e.consequent)];evidence[scope]=e.drop_duplicates('combo').set_index('combo')
def heat(ax,m,title,cmap='YlGnBu',maxval=1):
    im=ax.imshow(m,vmin=0,vmax=maxval,cmap=cmap);ax.set_xticks(range(4),names);ax.set_yticks(range(4),names);ax.set_title(title,pad=12)
    for i in range(4):
        for j in range(4):ax.text(j,i,f'{m[i,j]:.3f}',ha='center',va='center',color='white' if m[i,j]>maxval*.62 else '#152a3a')
    return im
for length in [0,2,3]:
    fig,axes=plt.subplots(1,3,figsize=(14,5));label='二／三品类混合' if length==0 else f'{length}品类'
    for ax,k in zip(axes,[0,20,50]):
        sets={}
        for scope in names:
            q=frames[scope];q=q if length==0 else q[q.length.eq(length)];q=q if k==0 else q.head(k);sets[scope]=set(q.combo)
            sizes.append(dict(scope=scope,length=length,top_k=k,n_combinations=len(q)))
            for rank,r in enumerate(q.itertuples(),1):members.append(dict(scope=scope,length=length,top_k=k,rank=rank,itemset=json.dumps(r.combo),representative_rule_id=r.rule_id))
        m=np.eye(4)
        for i,a in enumerate(names):
            for j,b in enumerate(names):
                union=len(sets[a]|sets[b]);inter=len(sets[a]&sets[b]);m[i,j]=inter/union if union else np.nan
                if i<j:rows.append(dict(metric='jaccard',length=length,top_k=k,scope_a=a,scope_b=b,n_a=len(sets[a]),n_b=len(sets[b]),intersection=inter,union=union,value=m[i,j]))
        heat(ax,m,'全部合格组合' if k==0 else f'Top{k} 不同组合')
    fig.suptitle(f'{label}：组合 Jaccard 相似度（越高越相似）',fontsize=16)
    fig.text(.02,.02,'严格档＋三品类增量≥5pp；先按原有排序取代表方向，再对组合去重、取Top-K。每群独立排名，不是系统预算。',fontsize=10)
    fig.tight_layout(rect=[0,.08,1,.91]);fig.savefig(O/f'jaccard_length_{length}.png');fig.savefig(O/f'jaccard_length_{length}.svg');plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(10,5))
for length,ax in zip([2,3],axes):
    base=evidence['G'];index=base[base.length.eq(length)].index
    vectors={scope:evidence[scope].loc[index,'support'].to_numpy() for scope in names};m=np.zeros((4,4))
    assert all(np.isfinite(v).all() for v in vectors.values())
    for i,a in enumerate(names):
        for j,b in enumerate(names):
            denom=(vectors[a]+vectors[b]).sum();m[i,j]=np.abs(vectors[a]-vectors[b]).sum()/denom if denom else 0
            if i<j:rows.append(dict(metric='bray_curtis_support',length=length,top_k=0,scope_a=a,scope_b=b,n_a=len(index),n_b=len(index),intersection=None,union=None,value=m[i,j]))
    im=heat(ax,m,f'{length}品类：{len(index):,}个共同组合',cmap='YlOrRd',maxval=1)
fig.suptitle('共同候选池 support 的 Bray–Curtis 距离（越低越相似）',fontsize=14)
fig.text(.02,.02,'使用原始64范围共同候选池的全部去重组合；未按严格门槛截断support。G包含各群，不是独立对照。',fontsize=9)
fig.tight_layout(rect=[0,.09,1,.9]);fig.savefig(O/'support_bray_curtis.png');fig.savefig(O/'support_bray_curtis.svg');plt.close(fig)
pd.DataFrame(rows).to_csv(O/'pairwise_metrics.csv',index=False);pd.DataFrame(sizes).to_csv(O/'scope_sizes.csv',index=False);pd.DataFrame(members).to_csv(O/'jaccard_membership.csv.gz',index=False,compression='gzip')
def md(d):return '| '+' | '.join(d.columns)+' |\n|'+'|'.join(['---']*len(d.columns))+'|\n'+'\n'.join('| '+' | '.join(str(v) for v in row)+' |' for row in d.itertuples(index=False,name=None))
report=['# 品类层群体相似度','对象为G/C0/C1/C2。主分析使用严格档加三品类增量≥5个百分点。方向规则先按联合次数、confidence、lift降序及rule_id升序排序，再对前后件品类并集去重，每个组合保留最靠前方向。组合相似不代表规则方向或confidence相同。','Jaccard=交集组合数/并集组合数，越高越相似。全部集合大小不同会影响数值，所以同时展示Top20/50；小数不是显著性指标。每组TopK不是系统总预算；本次不重跑随机相似度检验。','Bray–Curtis=Σ|support_a−support_b|/Σ(support_a+support_b)，越低越相似。使用原64范围共同候选池的去重组合，含未过严格门槛的组合；二三品类分开计算，不把support再归一化为概率分布。','G包含C0/C1/C2，且各群订单占比不同；群与G的接近程度受权重影响。与群外对照的业务解释、Validation稳定性仍需另行判断。']
for length in [0,2,3]:report += [f'## 长度{length}（0为混合）',f'![Jaccard](jaccard_length_{length}.png)']
report+=['## Support强度差异','![Bray–Curtis](support_bray_curtis.png)','## 全部数值',md(pd.DataFrame(rows).round({'value':4}))]
(O/'品类层群体相似度报告.md').write_text('\n\n'.join(report),encoding='utf-8');print(pd.DataFrame(rows).to_string(index=False))
