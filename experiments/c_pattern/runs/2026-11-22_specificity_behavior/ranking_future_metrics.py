from pathlib import Path
import pandas as pd,numpy as np,json
R=Path(__import__('os').environ.get('PATTERN_PROJECT_ROOT', str(Path(__file__).resolve().parent)));O=R/'ranking_gap_sensitivity/future_specificity';O.mkdir(exist_ok=True)
d=pd.read_csv(R/'ranking_gap_sensitivity/selected_rules_evidence.csv.gz',dtype={'seed':str,'group':str},keep_default_na=False,low_memory=False)
d=d[d.method!='G'].copy()
for c in ['validation_confidence_gap_pp','validation_association_gap_pp','discovery_confidence_gap_pp','discovery_association_gap_pp']:d[c]=pd.to_numeric(d[c],errors='coerce')
d['fixed_effect_kept']=(d.validation_confidence_gap_pp>=5-1e-10)&(d.validation_association_gap_pp>0)
keys=['control','method','seed','config','budget','variant']
def stats(z):
 out={'selected_slots':len(z),'estimable_slots':int(z.validation_confidence_gap_pp.notna().sum()),'fixed_effect_kept':int(z.fixed_effect_kept.sum()),'fixed_effect_retention':z.fixed_effect_kept.mean()}
 for col,prefix in [('validation_confidence_gap_pp','confidence_gap'),('validation_association_gap_pp','adjusted_gap')]:
  for q,name in [(.25,'q25'),(.5,'median'),(.75,'q75')]:out[prefix+'_'+name+'_pp']=z[col].quantile(q)
 return out
rows=[];groups=[]
for k,z in d.groupby(keys,dropna=False,sort=False):
 rows.append(dict(zip(keys,k))|stats(z))
 for g,a in z.groupby('group'):groups.append(dict(zip(keys,k))|{'group':g}|stats(a))
m=pd.DataFrame(rows);m.to_csv(O/'system_metrics.csv',index=False);pd.DataFrame(groups).to_csv(O/'group_metrics.csv',index=False)
real=m[m.method=='L'];real.to_csv(O/'L_metrics.csv',index=False)
comparisons=[]
for _,l in real.iterrows():
 for ctrl in ['S','A1','A2']:
  z=m[(m.control==ctrl)&(m.config==l.config)&(m.budget==l.budget)&(m.variant==l.variant)]
  for metric in ['confidence_gap_median_pp','adjusted_gap_median_pp','fixed_effect_retention']:
   v=z[metric];ge=int((v>=l[metric]-1e-12).sum())
   comparisons.append(dict(config=l.config,budget=l.budget,variant=l.variant,control=ctrl,metric=metric,L=l[metric],random_median=v.median(),random_q25=v.quantile(.25),random_q75=v.quantile(.75),random_min=v.min(),random_max=v.max(),random_ge_L=ge,seeds=len(v),descriptive_upper_tail=(ge+1)/(len(v)+1)))
c=pd.DataFrame(comparisons);c.to_csv(O/'random_comparison.csv',index=False)
assert len(m)==9945 and len(real)==45
assert (m.selected_slots==m.budget).all()
assert (m.fixed_effect_kept<=m.estimable_slots).all()
protocol={'source':'Frozen ranking_gap_sensitivity/selected_rules_evidence.csv.gz; unchanged candidates and ranks','period':'Validation','fixed_effect':'Validation confidence target-minus-rest >=5pp AND adjusted association gap >0','denominator':'ALL selected slots, not Discovery signal subset; nonestimable slots count as not retained','quartiles':'pandas linear quantiles across estimable selected group-rule slots; missing excluded and reported','duplicates':'Original allocation retained; same direction in different groups is a separate group-rule slot, not an independent statistical replicate','random':'One complete three-group system per seed; compare system median/gap/retention with real L; no pooling seed-rule observations','G':'No target/rest contrast for global scope; G not assigned artificial zero','flow':'These are target-group rule evidence measures, not coverage; identical under restricted/shared selection','scope':'P1-P5 x20/50/100 x3variants; S20,A1/A2 each100','limitations':['Posthoc descriptive analysis, not confirmatory significance','No new BY/BH or customer-bootstrap intervals; quartiles describe rule heterogeneity, not uncertainty','No added Validation count gate; low counts can yield unstable differences','Unchanged Test; no remine or rerank'], 'checks':{'systems':len(m),'all_budgets_filled':True,'nonestimable_slots':int((m.selected_slots-m.estimable_slots).sum())}}
(O/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
def table(z):return '| '+' | '.join(z.columns)+' |\n|'+'|'.join(['---']*len(z.columns))+'|\n'+'\n'.join('| '+' | '.join(map(str,r))+' |' for r in z.itertuples(index=False,name=None))
view=real[real.budget==100][['config','variant','confidence_gap_q25_pp','confidence_gap_median_pp','confidence_gap_q75_pp','adjusted_gap_q25_pp','adjusted_gap_median_pp','adjusted_gap_q75_pp','fixed_effect_kept','selected_slots']].round(3)
report='# 群体特色排序：未来差异与固定效应保持率\n\n保持冻结候选及排序不变。所有数值来自Validation，未使用Test。本次为事后探索性补充。\n\n## 指标口径\n\nconfidence差为群内减群外；调整差为(conf群内−后件基础率群内)−(conf群外−后件基础率群外)。两者报告规则名额层面的中位数、25%和75%分位数，单位pp。四分位数不是置信区间。\n\n固定效应保持率=Validation confidence差≥5pp且调整差>0的名额数/全部选中名额数。与旧“Discovery信号中未来两项差为正”的指标不同，不能直接混比。缺失不计为保持。未增加Validation样本数过滤，小样本需谨慎解释。跨群重复规则仍保留各自群内外证据；没有将名额当独立样本进行显著性检验。\n\nG没有目标群与群外，故此指标不适用；Restricted/Shared不改变冻结规则的目标群证据，因此无需重复两份。这不是最新组合去重预算实验。\n\n## 预算100的真实分群\n\n'+table(view)+'\n\n## 随机对照\n\nrandom_comparison.csv每行以一个种子的完整系统为单位，汇总系统差值中位数及保持率；S20种子、A1/A2各100种子。上尾比例为(1+达到或超过L的次数)/(1+种子数)，未经多重比较校正。\n\n## 文件\n\nL_metrics.csv含全部45套真实群结果；group_metrics.csv分群结果；system_metrics.csv含9945套系统结果；random_comparison.csv随机比较；protocol.json记录定义及核验。\n'
(O/'未来群体特色指标补充.md').write_text(report,encoding='utf-8')
print(view.to_string(index=False));print(c[(c.config=='P5')&(c.budget==100)&(c.variant=='evidence_gap')].to_string(index=False));print(protocol['checks'])
