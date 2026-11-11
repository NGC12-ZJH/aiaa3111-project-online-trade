from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
R=Path(__file__).resolve().parent; A=R/'pattern_analysis'; O=A/'figures';O.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white','axes.titleweight':'bold','savefig.facecolor':'white'})
colors=['#3667AD','#E69532','#318879']; G='#3667AD';L='#E69532';RC='#7A8190'
def finish(fig,name,title,subtitle):
 fig.suptitle(title,fontsize=19,fontweight='bold',x=.06,ha='left',y=.98)
 fig.text(.06,.915,subtitle,fontsize=10,color='#555555')
 fig.text(.06,.025,'Discovery：2010-06-01 至 2010-12-01（右端不含）｜仅发现期描述，不代表未来效果或显著性',fontsize=9,color='#666666')
 fig.tight_layout(rect=[.035,.07,.98,.87]);fig.savefig(O/(name+'.png'),dpi=200);fig.savefig(O/(name+'.svg'));plt.close(fig)
# 1
scope=pd.read_csv(R/'patterns/scope_audit.csv',dtype={'group_id':str}); scope=scope[scope.method.eq('L')].set_index('group_id').loc[['0','1','2']]
summary=pd.read_csv(A/'local_summary.csv',dtype={'group':str}).set_index('group').loc[['0','1','2']]
fig,ax=plt.subplots(1,3,figsize=(14,5.8)); labels=['C0','C1','C2']
for axis,values,title in [(ax[0],scope.n_baskets,'Discovery 有效购物篮'),(ax[1],summary.qualified_rules,'合格方向规则'),(ax[2],np.maximum(np.ceil(scope.n_baskets*.01),20)/scope.n_baskets*100,'实际最低支持度')]:
 bars=axis.bar(labels,values,color=colors,width=.6);axis.set_title(title,pad=15);axis.set_ylim(0,max(values)*1.23)
 for bar,v in zip(bars,values):axis.text(bar.get_x()+bar.get_width()/2,v+max(values)*.035,f'{v:.2f}%' if axis==ax[2] else f'{int(v):,}',ha='center',fontsize=13)
 axis.grid(axis='y',alpha=.15);axis.set_axisbelow(True)
ax[2].axhline(1,color='#777777',ls='--',lw=1);ax[2].set_ylabel('%');ax[0].set_ylabel('篮数');ax[1].set_ylabel('规则数')
finish(fig,'01_groups_thresholds','样本量影响门槛，也影响规则数量','统一要求：support ≥ 1%，联合次数 ≥ 20；C0 的绝对次数门槛主导，不能将规则少直接解释为偏好单一。')
# 2
cov=pd.read_csv(A/'discovery_coverage_NOT_future.csv');fig,axs=plt.subplots(1,2,figsize=(13,6.4))
for ax,metric,title in zip(axs,['complete_coverage','customer_macro_coverage'],['订单完整覆盖率','顾客宏平均完整覆盖率']):
 rr=cov[cov.method.eq('R')].groupby('budget')[metric].agg(['min','median','max']);xx=rr.index.to_numpy()
 ax.fill_between(xx,rr['min'].to_numpy()*100,rr['max'].to_numpy()*100,color=RC,alpha=.2,label='R：20 个种子最小–最大')
 ax.plot(xx,rr['median']*100,'--o',color=RC,label='R：种子中位数')
 for method,color,name in [('G',G,'G：全局'),('L',L,'L：真实分群')]:
  p=cov[cov.method.eq(method)].sort_values('budget');ax.plot(p.budget,p[metric]*100,'-o',color=color,lw=2.3,label=name)
  for row in p.itertuples():ax.annotate(f'{getattr(row,metric)*100:.1f}%',(row.budget,getattr(row,metric)*100),xytext=(0,8 if method=='G' else -17),textcoords='offset points',ha='center',color=color,fontsize=10)
 ax.set_title(title,pad=12);ax.set_xticks([20,50,100]);ax.set_xlabel('系统总规则预算');ax.set_ylabel('覆盖率（%）');ax.set_ylim(0,46);ax.grid(alpha=.18);ax.legend(fontsize=8,loc='upper left')
finish(fig,'02_budget_coverage','同预算下：全局覆盖更高，分群与随机对照的差异有限','每张订单最多计一次覆盖；宏平均对有 Discovery 订单的顾客等权。灰带是随机种子范围，不是置信区间。')
# 3
cases=pd.read_csv(A/'cases.csv',dtype={'group_id':str})
choices=[('0','HAND WARMER OWL DESIGN','HAND WARMER SCOTTY DOG DESIGN','C0｜猫头鹰暖手袋 → 小狗暖手袋'),('1','FELTCRAFT CUSHION BUTTERFLY','FELTCRAFT CUSHION RABBIT','C1｜蝴蝶靠垫 → 兔子靠垫'),('2','JUMBO STORAGE BAG SUKI','JUMBO BAG PINK WITH WHITE SPOTS','C2｜SUKI 收纳袋 → 粉色白点购物袋'),('0',"POPPY'S PLAYHOUSE BEDROOM","POPPY'S PLAYHOUSE KITCHEN",'C0｜玩具屋卧室 → 玩具屋厨房（反例）')]
chosen=[]
for g,a,c,label in choices:
 p=cases[(cases.group_id==g)&cases.antecedent_names.str.strip().eq(a)&cases.consequent_names.str.strip().eq(c)].iloc[0];chosen.append(p)
pd.DataFrame(chosen).to_csv(O/'case_chart_data.csv',index=False)
fig,axs=plt.subplots(1,2,figsize=(14,6.6));ys=np.arange(4)
for ax,inside,outside,title in [(axs[0],'support','outside_support','支持度：该组合在订单中多常见'),(axs[1],'confidence','outside_confidence','置信度：买了前件后，有多少同时买后件')]:
 for y,p in zip(ys,chosen):
  v=float(p[inside])*100;w=float(p[outside])*100
  ax.plot([w,v],[y,y],color='#BFC5CD',lw=3);ax.scatter(w,y,color=RC,s=65,label='群外' if y==0 else None,zorder=3);ax.scatter(v,y,color=L,s=65,label='群内' if y==0 else None,zorder=3)
  ax.annotate(f'{w:.1f}%',(w,y),xytext=(0,-17),textcoords='offset points',ha='center',color=RC,fontsize=10);ax.annotate(f'{v:.1f}%',(v,y),xytext=(0,10),textcoords='offset points',ha='center',color='#B46D10',fontsize=10)
 ax.set_yticks(ys);ax.set_yticklabels([z[3]+'\n联合次数='+str(int(p.joint_count)) for z,p in zip(choices,chosen)] if ax==axs[0] else []);ax.set_ylim(3.5,-.6);ax.set_xlim(0,5.2 if ax==axs[0] else 105);ax.set_title(title,fontsize=12,pad=15);ax.set_xlabel('%');ax.grid(axis='x',alpha=.2);ax.legend(loc='upper right',fontsize=9)
finish(fig,'03_rule_cases','群体差异要同时看普遍程度和条件关联','探索性选择：三个差异案例＋一个反例，非无偏样本。玩具屋组合群内 support 更高，但 confidence 没有更高。')
# 4
red=pd.read_csv(A/'selected_redundancy.csv',dtype={'group_id':str},keep_default_na=False);red=red[(red.budget==50)&red.method.ne('R')]
fig,ax=plt.subplots(figsize=(11,6));xx=np.arange(4);width=.33
ax.bar(xx-width/2,red.rules,width,label='部署的方向规则',color=G);ax.bar(xx+width/2,red.unique_itemsets,width,label='不同商品并集',color=L)
for i,row in enumerate(red.itertuples()):
 ax.text(i-width/2,row.rules+1,str(row.rules),ha='center');ax.text(i+width/2,row.unique_itemsets+1,str(row.unique_itemsets),ha='center')
ax.set_xticks(xx,['G：全局','L：C0','L：C1','L：C2']);ax.set_ylim(0,60);ax.set_ylabel('数量');ax.legend(loc='upper right');ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
finish(fig,'04_rule_redundancy','预算 50：不少方向规则对应同一个完整匹配集合','A→B 与 B→A 的 confidence 不同，但完整覆盖集合相同。这里只衡量同范围内商品并集重复，不包含跨组合的重叠。')
print('Saved four PNG and SVG figures to',O)
