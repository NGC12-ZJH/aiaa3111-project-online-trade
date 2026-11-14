from pathlib import Path
import argparse
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser();p.add_argument('--root',required=True);R=Path(p.parse_args().root);O=R/'category_visualizations';O.mkdir(exist_ok=True)
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False,'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':180})
s=pd.read_csv(R/'category_screening/scope_summary.csv',keep_default_na=False);m=pd.read_csv(R/'category_fixed_budget/system_metrics.csv',keep_default_na=False)
s['scope']=np.where(s.method.eq('G'),'G','C'+s.group_id.astype(str));gl=s[s.method.ne('R')];order=['G','C0','C1','C2'];colors=['#264c70','#d88725','#31a088','#945cab'];configs=['baseline','moderate','strict'];cn=['基线','中等','严格'];paths=[]
def save(fig,name,note):
    fig.text(.02,.015,note,fontsize=9,color='#555');fig.tight_layout(rect=[0,.07,1,.97]);fig.savefig(O/(name+'.png'));fig.savefig(O/(name+'.svg'));plt.close(fig);paths.append(name)
fig,ax=plt.subplots(figsize=(11,6));xx=np.arange(4);width=.24
for j,(config,label) in enumerate(zip(configs,cn)):
    a=gl[(gl.config==config)&(gl.increment=='increment5pp')&(gl.length==0)].set_index('scope').loc[order]
    bars=ax.bar(xx+(j-1)*width,a.rules,width,label=label)
    ax.bar_label(bars,labels=[f'{v:,}' for v in a.rules],fontsize=9,padding=3)
ax.set_xticks(xx,order);ax.set_ylabel('合格方向规则数');ax.set_title('提高门槛后，品类层候选规则明显减少');ax.legend();ax.set_ylim(0,37000)
save(fig,'01_threshold_rule_counts','三档均加三品类增量≥5个百分点；二品类不受增量筛选影响。不是固定预算结果。')
fig,axes=plt.subplots(1,2,figsize=(12,6));a=gl[(gl.config=='strict')&(gl.increment=='increment5pp')&(gl.length!=0)].pivot(index='scope',columns='length',values='rules').loc[order]
for ax,percent in zip(axes,[False,True]):
    vals=a.div(a.sum(1),axis=0)*100 if percent else a;bottom=np.zeros(4)
    for length,col in [(2,'#2c7f96'),(3,'#d99235')]:
        ax.bar(order,vals[length],bottom=bottom,label=f'{length}品类规则',color=col)
        for i,v in enumerate(vals[length]):
            if not percent:ax.text(i,bottom[i]+v/2,f'{a[length].iloc[i]:,}',ha='center',va='center',fontsize=9)
            elif length==3:ax.text(i,bottom[i]+v/2,f'{v:.1f}%',ha='center',va='center')
        bottom+=vals[length].to_numpy()
    ax.set_ylabel('占比（%）' if percent else '方向规则数');ax.set_title('规则构成占比' if percent else '规则构成数量');ax.legend(loc='upper left')
fig.suptitle('严格档＋增量检查后，三品类仍占绝大多数')
save(fig,'02_rule_length_composition','三品类为 {A,B}→C；方向分别计数。增量是相对两个单前件中较强者的confidence差。')
fig,ax=plt.subplots(figsize=(10,6))
for scope,color in zip(order,colors):
    z=gl[(gl.scope==scope)&(gl.length==0)&(gl.increment=='increment5pp')].set_index('config').loc[configs]
    ax.plot(z.rules,z.order_coverage*100,'o-',label=scope,color=color)
    for label,(_,r) in zip(cn,z.iterrows()):ax.annotate(label,(r.rules,r.order_coverage*100),xytext=(5,5),textcoords='offset points',fontsize=9,color=color)
ax.set_xscale('log');ax.set_xlabel('全部保留方向规则数（对数轴）');ax.set_ylabel('订单覆盖率（%）');ax.set_title('规则大幅减少时，完整订单覆盖率下降相对较小');ax.legend();ax.grid(alpha=.2)
save(fig,'03_rules_vs_coverage','覆盖＝至少完整包含一条保留规则的订单并集／该范围全部订单。使用全部规则，未固定预算。')
fig,ax=plt.subplots(figsize=(10,6));budgets=[20,50,100];rng=np.random.default_rng(2026)
for B in budgets:
    vals=m[(m.method=='R')&(m.budget==B)].order_coverage*100
    ax.scatter(np.full(20,B)+rng.uniform(-1.4,1.4,20),vals,color='#969ba3',alpha=.65,s=22)
    ax.plot([B,B],[vals.min(),vals.max()],color='#969ba3',lw=3)
med=m[m.method=='R'].groupby('budget').order_coverage.median().loc[budgets]*100
ax.plot(budgets,med,'s--',color='#777',label='R：20个种子的中位数与范围')
for method,color,label in [('G',colors[0],'G：全局'),('L',colors[2],'L：真实分群')]:
    z=m[m.method==method].set_index('budget').loc[budgets];ax.plot(budgets,z.order_coverage*100,'o-',color=color,lw=2,label=label)
    for B,v in zip(budgets,z.order_coverage*100):ax.annotate(f'{v:.2f}%',(B,v),xytext=(0,8),textcoords='offset points',ha='center',color=color)
ax.set_xticks(budgets);ax.set_ylim(30,72);ax.set_xlabel('系统总规则预算 B');ax.set_ylabel('系统订单覆盖率（%）');ax.set_title('固定相同预算后：G覆盖率最高，L处于随机分组范围内');ax.legend();ax.grid(alpha=.2)
save(fig,'04_fixed_budget_GLR','严格档＋增量检查；L/R按订单数分配总预算，规则仅用于所属群。灰点为一个随机种子的系统结果；范围不是置信区间。')
fig,axes=plt.subplots(1,2,figsize=(12,5));z=gl[(gl.config=='strict')&(gl.increment=='increment5pp')&(gl.length==0)].set_index('scope').loc[order]
for ax,column,mult,title in [(axes[0],'distinct_l2',1,'剩余规则涉及的子类数（共76类）'),(axes[1],'all_items_top10_popular_share',100,'全部品类均属热门Top10的组合占比')]:
    bars=ax.bar(order,z[column]*mult,color=colors);ax.bar_label(bars,fmt='%.1f' if mult==100 else '%d',padding=3);ax.set_title(title);ax.set_ylim(0,85 if mult==1 else 12);ax.set_ylabel('子类数' if mult==1 else '不同组合占比（%）')
save(fig,'05_popularity_concentration','严格档＋增量检查；热门Top10按各范围订单出现率确定。低占比不代表不存在单个热门品类主导。')
table=gl[(gl.increment=='increment5pp')&(gl.length==0)][['scope','config','rules','unique_combinations','order_coverage','distinct_l2','all_items_top10_popular_share']].copy();table.to_csv(O/'筛选汇总表.csv',index=False,encoding='utf-8-sig')
a.rename(columns={2:'二品类规则',3:'三品类规则'}).to_csv(O/'严格档规则构成.csv',encoding='utf-8-sig')
comp=pd.read_csv(R/'category_fixed_budget/comparison.csv');comp.to_csv(O/'固定预算对照表.csv',index=False,encoding='utf-8-sig')
def md(df):return '| '+' | '.join(df.columns)+' |\n|'+'|'.join(['---']*len(df.columns))+'|\n'+'\n'.join('| '+' | '.join(map(str,row))+' |' for row in df.itertuples(index=False,name=None))
table['order_coverage']=table.order_coverage.map(lambda v:f'{v:.2%}');table['all_items_top10_popular_share']=table.all_items_top10_popular_share.map(lambda v:f'{v:.2%}');table.config=table.config.replace(dict(zip(configs,cn)))
table.columns=['范围','配置','方向规则数','不同组合数','订单覆盖率','涉及子类数','全热门组合占比']
for c in ['G','L','R_median','R_min','R_max']:comp[c]=comp[c].map(lambda v:f'{v:.2%}')
comp.L_minus_G_pp=comp.L_minus_G_pp.round(2)
lines=['# 品类层结果图表','所有结果为Discovery开发期描述；严格档未经Validation选择。图1–3和5使用全部合格规则；图4为固定系统预算，不可混淆。','## 筛选汇总',md(table),'## 严格档二／三品类数量',md(a.reset_index().rename(columns={'scope':'范围',2:'二品类',3:'三品类'})),'## 固定预算对照',md(comp)]
for name in paths:lines.extend([f'## {name}',f'![{name}]({name}.png)'])
lines+=['## 汇报要点','提高门槛和三品类增量检查压缩了规则，但三品类仍占多数。严格档仍涉及61–68个子类，不能简单说只剩热门类别。固定预算后G覆盖率高于L；L处于20个随机种子的结果范围内。规则覆盖不是推荐准确率，也不能证明未来或因果收益。']
(O/'品类层图表汇总.md').write_text('\n\n'.join(lines),encoding='utf-8');print('Created',len(paths),'PNG + SVG figures, 3 CSV tables and report')
