"""Cluster/global content, one-vs-rest effects and future advantage retention."""
from pathlib import Path
from functools import reduce
from operator import or_
import csv
import gzip
import json
import time
import numpy as np
import pandas as pd
from scipy.stats import t, false_discovery_control
from .validation import load_inputs, load_period, sha, rate
from .quality import ratio_contrast, adjust_fdr


def diff_test(value_a, se_a, m_a, value_b, se_b, m_b):
    delta=value_a-value_b;df=min(m_a,m_b)-1
    if not np.isfinite(delta) or not np.isfinite(se_a+se_b) or df<1:
        return delta,float('nan'),float('nan'),1.
    se=float(np.hypot(se_a,se_b))
    if se<1e-14:return delta,float('nan'),float('nan'),1.
    critical=t.ppf(.975,df)
    return float(delta),float(delta-critical*se),float(delta+critical*se),float(t.sf(delta/se,df))


def point_quality(s,thresholds):
    evidence=(s['a']>=thresholds['min_antecedent_orders'] and s['j']>=thresholds['min_joint_orders']
              and s['a_customers']>=thresholds['min_antecedent_customers'] and s['j_customers']>=thresholds['min_joint_customers']
              and s['max_joint_share']<=thresholds['max_customer_joint_share']+1e-12)
    effect=(s['lift']+1e-12>=thresholds['min_lift'] and s['assoc']+1e-12>=thresholds['min_confidence_uplift'])
    increment=(s['length']==2 or s['increment_pp']+1e-10>=thresholds['min_triple_increment_pp'])
    return evidence, bool(evidence and effect and increment)


class PeriodVectors:
    def __init__(self,index):
        self.index=index;self.customers=list(index.by_customer);self.orders=index.customer_counts(index.all);self.cache={}

    def vec(self,items):
        key=tuple(sorted(items))
        if key not in self.cache:self.cache[key]=self.index.customer_counts(self.index.mask(key))
        return self.cache[key]


class FamilyStats:
    def __init__(self,vectors,mapping,definitions):
        self.v=vectors;self.definitions=definitions;self.cache={}
        labels=np.array([mapping[c] for c in vectors.customers]);self.ids={'GLOBAL':np.arange(len(labels))}
        for group in ['0','1','2']:
            self.ids[group]=np.flatnonzero(labels==group);self.ids['rest'+group]=np.flatnonzero(labels!=group)
        self.masks={key:reduce(or_,(vectors.index.by_customer[vectors.customers[i]] for i in indices),0) for key,indices in self.ids.items()}

    def get(self,scope,rid,quality=False):
        key=scope,rid
        if key not in self.cache:
            ant,con=self.definitions[rid];ix=self.ids[scope]
            nvec=self.v.orders[ix];av=self.v.vec(ant)[ix];cv=self.v.vec(con)[ix];jv=self.v.vec(tuple(set(ant)|set(con)))[ix]
            n,a,c,j=map(lambda x:int(x.sum()),[nvec,av,cv,jv]);m=len(ix);conf=rate(j,a);baseline=rate(c,n)
            if a and m>1:
                influence=(jv-conf*av)/a;conf_se=float(np.sqrt(m/(m-1)*np.dot(influence,influence)))
            else:conf_se=float('nan')
            assoc,se,_,_,p=ratio_contrast(jv,av,cv,nvec)
            self.cache[key]=dict(n=n,m=m,a=a,c=c,j=j,confidence=conf,baseline=baseline,lift=rate(conf,baseline) if baseline else float('nan'),
                                 assoc=assoc,conf_se=conf_se,assoc_se=se,p_assoc=p,length=len(ant)+len(con),
                                 a_customers=int(np.sum(av>0)),j_customers=int(np.sum(jv>0)),max_joint_share=rate(float(jv.max()),j) if m and j else float('nan'))
        s=self.cache[key]
        if quality and 'p_quality' not in s:
            ant,con=self.definitions[rid];increment=float('nan');pinc=0.
            if len(ant)==2:
                ix=self.ids[scope];av=self.v.vec(ant)[ix];jv=self.v.vec(tuple(set(ant)|set(con)))[ix]
                deltas=[];ps=[]
                for item in ant:
                    single=self.v.vec([item])[ix];single_joint=self.v.vec(tuple(set([item])|set(con)))[ix]
                    delta,_,_,_,pv=ratio_contrast(jv,av,single_joint,single);deltas.append(delta*100);ps.append(pv)
                increment=min(deltas);pinc=max(ps)
            s.update(increment_pp=increment,p_quality=max(s['p_assoc'],pinc))
        return s


def measure(engine,group,rid,thresholds):
    target=engine.get(group,rid,quality=True);rest=engine.get('rest'+group,rid);glob=engine.get('GLOBAL',rid)
    assert all(target[k]+rest[k]==glob[k] for k in ['n','a','c','j'])
    delta,lo,hi,pconf=diff_test(target['confidence'],target['conf_se'],target['m'],rest['confidence'],rest['conf_se'],rest['m'])
    association,alo,ahi,passoc=diff_test(target['assoc'],target['assoc_se'],target['m'],rest['assoc'],rest['assoc_se'],rest['m'])
    other_confs=[];other_assocs=[];strict_ps=[];other_opportunity=True
    output={}
    for other in ['0','1','2']:
        if other==group:continue
        os=engine.get(other,rid)
        od,ol,oh,op=diff_test(target['confidence'],target['conf_se'],target['m'],os['confidence'],os['conf_se'],os['m'])
        oa,oal,oah,oap=diff_test(target['assoc'],target['assoc_se'],target['m'],os['assoc'],os['assoc_se'],os['m'])
        other_confs.append(od);other_assocs.append(oa);strict_ps.extend([op,oap])
        other_opportunity &= os['a']>=20 and os['a_customers']>=10
        output.update({f'C{other}_antecedent_count':os['a'],f'C{other}_joint_count':os['j'],f'C{other}_confidence':os['confidence'],f'C{other}_lift':os['lift'],
                       f'confidence_gap_vs_C{other}_pp':od*100,f'association_gap_vs_C{other}_pp':oa*100})
    sufficient,qualified=point_quality(target,thresholds)
    rest_opportunity=rest['a']>=20 and rest['a_customers']>=10
    minconf=float(np.min(other_confs));minassoc=float(np.min(other_assocs))
    pjoint=max(target['p_quality'],pconf,passoc)
    output.update(target_orders=target['n'],target_customers=target['m'],target_antecedent_count=target['a'],target_joint_count=target['j'],
                  target_antecedent_customers=target['a_customers'],target_joint_customers=target['j_customers'],target_max_customer_joint_share=target['max_joint_share'],
                  target_confidence=target['confidence'],target_baseline=target['baseline'],target_lift=target['lift'],target_uplift=target['assoc'],target_increment_pp=target['increment_pp'],
                  rest_orders=rest['n'],rest_customers=rest['m'],rest_antecedent_count=rest['a'],rest_joint_count=rest['j'],
                  rest_antecedent_customers=rest['a_customers'],rest_confidence=rest['confidence'],rest_baseline=rest['baseline'],rest_lift=rest['lift'],rest_uplift=rest['assoc'],
                  global_confidence=glob['confidence'],global_lift=glob['lift'],confidence_gap_vs_global_pp=100*(target['confidence']-glob['confidence']),
                  confidence_gap_vs_rest_pp=delta*100,confidence_gap_ci95_low_pp=lo*100,confidence_gap_ci95_high_pp=hi*100,
                  association_gap_vs_rest_pp=association*100,association_gap_ci95_low_pp=alo*100,association_gap_ci95_high_pp=ahi*100,
                  lift_ratio_vs_global=rate(target['lift'],glob['lift']) if glob['lift'] else float('nan'),
                  lift_ratio_vs_rest=rate(target['lift'],rest['lift']) if rest['lift'] else float('nan'),
                  specificity_confidence_pp=minconf*100,specificity_association_pp=minassoc*100,
                  target_evidence_sufficient=bool(sufficient),target_point_quality_pass=bool(qualified),rest_opportunity_sufficient=bool(rest_opportunity),
                  other_groups_opportunity_sufficient=bool(other_opportunity),p_confidence_gap=pconf,p_association_gap=passoc,
                  p_one_vs_rest=pjoint,p_strict=max([pjoint]+strict_ps))
    output['advantage_candidate']=bool(qualified and rest_opportunity and delta>=.05-1e-12 and association>1e-12)
    output['strict_point_candidate']=bool(output['advantage_candidate'] and other_opportunity and minconf>=.05-1e-12 and minassoc>1e-12)
    return output


def content_row(local_rows,global_rows,top100,level):
    ls=set(local_rows.rule_id);gs=set(global_rows.rule_id)
    lc=set(local_rows.combination_id);gc=set(global_rows.combination_id)
    return dict(level=level,local_slots=len(local_rows),local_unique_rules=len(ls),global_slots=len(global_rows),global_unique_rules=len(gs),
                overlap_rules=len(ls&gs),union_rules=len(ls|gs),jaccard_rules=len(ls&gs)/len(ls|gs),
                local_novel_rules=len(ls-gs),local_novel_share=len(ls-gs)/len(ls),global_only_rules=len(gs-ls),
                local_rules_absent_G100=len(ls-top100),local_unique_combinations=len(lc),global_unique_combinations=len(gc),
                overlap_combinations=len(lc&gc),jaccard_combinations=len(lc&gc)/len(lc|gc))


def summarize(pairs,novel,scope_rows):
    selected=[pairs[r.scope_id,r.rule_id] for r in scope_rows.itertuples(index=False)];d=[x[0] for x in selected];v=[x[1] for x in selected]
    candidates=np.array([x['advantage_candidate'] for x in d],bool)
    supported=np.array([x['advantage_supported'] for x in v],bool)
    directions=np.array([x['confidence_gap_vs_rest_pp']>0 and x['association_gap_vs_rest_pp']>0 for x in v],bool)
    confdir=np.array([x['confidence_gap_vs_rest_pp']>0 for x in v],bool)
    novel_flags=np.array([rid in novel for rid in scope_rows.rule_id],bool)
    ratios=[vv['confidence_gap_vs_rest_pp']/dd['confidence_gap_vs_rest_pp'] for dd,vv in zip(d,v) if dd['advantage_candidate'] and np.isfinite(vv['confidence_gap_vs_rest_pp'])]
    failures={k:sum(x['validation_status']==k for x in v) for k in ['not_triggered','insufficient_evidence','point_effect_or_increment_below_minimum','uncertainty_unresolved','supported']}
    return dict(selected_slots=len(selected),discovery_advantage_candidates=int(candidates.sum()),validation_supported_slots=int(supported.sum()),
                validation_supported_share=float(np.mean(supported)),strict_supported_slots=sum(x['strict_supported'] for x in v),
                surviving_advantage_slots=int(np.sum(candidates&supported)),advantage_survival_rate=rate(int(np.sum(candidates&supported)),int(candidates.sum())),
                candidate_both_directions_kept=int(np.sum(candidates&directions)),both_directions_kept_rate=rate(int(np.sum(candidates&directions)),int(candidates.sum())),
                candidate_confidence_direction_kept_rate=rate(int(np.sum(candidates&confdir)),int(candidates.sum())),
                effect_retention_ratio_median=float(np.median(ratios)) if ratios else float('nan'),effect_retention_estimable_candidates=len(ratios),
                novel_to_global_slots=int(novel_flags.sum()),supported_novel_slots=int(np.sum(novel_flags&supported)),
                surviving_novel_slots=int(np.sum(novel_flags&candidates&supported)),
                validation_confidence_gap_pp_median=float(np.nanmedian([x['confidence_gap_vs_rest_pp'] for x in v])),
                validation_association_gap_pp_median=float(np.nanmedian([x['association_gap_vs_rest_pp'] for x in v])),**failures)


def main(root):
    started=time.time();pp=root/'configs/validation_specificity.json';protocol=json.loads(pp.read_text(encoding='utf-8'));phash=sha(pp)
    assert not protocol['test_evaluation'] and not protocol['parameter_selection']
    original=json.loads((root/'configs/validation.json').read_text(encoding='utf-8'))
    thresholds=json.loads((root/'configs/validation_quality.json').read_text(encoding='utf-8'))['primary']
    local=root/'data/processed/local/D_validation';out=root/'results/tables/validation_specificity';out.mkdir(parents=True,exist_ok=True)
    core,taxmap,true,mappings,rows,_=load_inputs(local,root,original)
    periods={p:PeriodVectors(load_period(local,p,taxmap,true)[0]) for p in ['discovery','validation']}
    val=periods['validation'].index
    definitions={r.rule_id:(r.ant,r.con) for r in rows.drop_duplicates('rule_id').itertuples()}
    old=pd.read_csv(local/'validation_rule_evidence.csv.gz',dtype={'rule_id':str}).drop_duplicates(['scope_id','rule_id'])
    old={(r.scope_id,r.rule_id):(r.n_baskets,r.antecedent_count,r.joint_count) for r in old.itertuples() if r.method!='G'}
    globals={(config,budget):d for (config,budget),d in rows.loc[rows.method.eq('G')].groupby(['config','budget'],sort=False)}
    system_rows=[];group_rows=[];contents=[];coverage_rows=[];gl_detail=[];family_audits=[];checked=0;raw_rows=[]
    full_path=local/'specificity_rule_evidence.csv.gz';handle=gzip.open(full_path,'wt',encoding='utf-8',newline='');writer=None
    families=list(rows.loc[rows.method.ne('G')].groupby(['control','method','seed'],sort=False))
    try:
        for number,(family,fr) in enumerate(families,1):
            mapping=mappings[family];engines={p:FamilyStats(v,mapping,definitions) for p,v in periods.items()}
            unique=fr.drop_duplicates(['scope_id','rule_id']);pairs={}
            for rule in unique.itertuples(index=False):
                disc=measure(engines['discovery'],rule.group_id,rule.rule_id,thresholds)
                future=measure(engines['validation'],rule.group_id,rule.rule_id,thresholds)
                assert (disc['target_orders'],disc['target_antecedent_count'],disc['target_joint_count'])==(int(rule.n_baskets),rule.antecedent_count,rule.joint_count)
                assert (future['target_orders'],future['target_antecedent_count'],future['target_joint_count'])==old[rule.scope_id,rule.rule_id]
                checked+=1;pairs[rule.scope_id,rule.rule_id]=(disc,future)
            # Correct both types of hypothesis in one shared within-system family.
            keys=list(pairs);ps=[pairs[k][1][name] for name in ['p_one_vs_rest','p_strict'] for k in keys]
            qb=adjust_fdr(ps,'BY');qh=adjust_fdr(ps,'BH')
            np.testing.assert_allclose(qb,false_discovery_control(np.array(ps),method='by'),atol=1e-14,rtol=1e-12)
            family_audits.append(dict(control=family[0],method=family[1],seed=family[2],native_rule_scopes=len(keys),hypotheses=len(ps)))
            for i,key in enumerate(keys):
                disc,future=pairs[key];future.update(q_one_vs_rest_BY=float(qb[i]),q_strict_BY=float(qb[i+len(keys)]),q_one_vs_rest_BH=float(qh[i]),q_strict_BH=float(qh[i+len(keys)]))
                future['advantage_supported']=bool(future['advantage_candidate'] and future['q_one_vs_rest_BY']<=.05)
                future['strict_supported']=bool(future['strict_point_candidate'] and future['q_strict_BY']<=.05)
                future['advantage_supported_BH']=bool(future['advantage_candidate'] and future['q_one_vs_rest_BH']<=.05)
                future['validation_status']=('not_triggered' if future['target_antecedent_count']==0 else 'insufficient_evidence' if not(future['target_evidence_sufficient'] and future['rest_opportunity_sufficient']) else
                                             'point_effect_or_increment_below_minimum' if not future['advantage_candidate'] else 'uncertainty_unresolved' if not future['advantage_supported'] else 'supported')
            for rule in unique.itertuples(index=False):
                for period,evidence in zip(['discovery','validation'],pairs[rule.scope_id,rule.rule_id]):
                    record=dict(period=period,control=family[0],method=family[1],seed=family[2],group_id=rule.group_id,scope_id=rule.scope_id,rule_id=rule.rule_id,
                                antecedent=rule.antecedent,consequent=rule.consequent,**evidence)
                    # Other-group columns differ by target group; explicitly fix all columns.
                    for other in ['0','1','2']:
                        for suffix in ['antecedent_count','joint_count','confidence','lift']:record.setdefault(f'C{other}_{suffix}','')
                        record.setdefault(f'confidence_gap_vs_C{other}_pp','');record.setdefault(f'association_gap_vs_C{other}_pp','')
                    for field in ['q_one_vs_rest_BY','q_strict_BY','q_one_vs_rest_BH','q_strict_BH','advantage_supported','strict_supported','advantage_supported_BH','validation_status']:record.setdefault(field,'')
                    if writer is None:writer=csv.DictWriter(handle,list(record),lineterminator='\n');writer.writeheader()
                    writer.writerow(record)
                    if family[0]=='GL':gl_detail.append(record)
            for (config,budget),selected in fr.groupby(['config','budget'],sort=False):
                glob=globals[config,budget];gs=set(glob.rule_id);top100=set(globals[config,100].rule_id)
                overall=content_row(selected,glob,top100,'system');overall.update(control=family[0],method=family[1],seed=family[2],config=config,budget=budget);contents.append(overall)
                summary=summarize(pairs,set(selected.rule_id)-gs,selected);summary.update(control=family[0],method=family[1],seed=family[2],config=config,budget=budget);system_rows.append(summary)
                for group,part in selected.groupby('group_id',sort=False):
                    diagnostic=summarize(pairs,set(part.rule_id)-gs,part);diagnostic.update(control=family[0],method=family[1],seed=family[2],config=config,budget=budget,group_id=group);group_rows.append(diagnostic)
                    cc=content_row(part,glob,top100,'group'+group);cc.update(control=family[0],method=family[1],seed=family[2],config=config,budget=budget);contents.append(cc)
                for period,engine in engines.items():
                    index=engine.v.index;g_hit=reduce(or_,(index.mask(r.ant)&index.mask(r.con) for r in glob.itertuples(index=False)),0)
                    g_trigger=reduce(or_,(index.mask(r.ant) for r in glob.itertuples(index=False)),0)
                    for flow in ['restricted','shared']:
                        local_hit=0;local_trigger=0
                        for r in selected.itertuples(index=False):
                            scope=engine.masks[r.group_id] if flow=='restricted' else index.all
                            am=index.mask(r.ant);local_hit|=am&index.mask(r.con)&scope;local_trigger|=am&scope
                        row=dict(period=period,config=config,budget=budget,control=family[0],method=family[1],seed=family[2],flow=flow,n_baskets=index.n,
                                 global_covered_orders=g_hit.bit_count(),local_covered_orders=local_hit.bit_count(),
                                 local_only_complete_orders=(local_hit&~g_hit).bit_count(),global_only_complete_orders=(g_hit&~local_hit).bit_count(),
                                 shared_complete_orders=(g_hit&local_hit).bit_count(),union_complete_orders=(g_hit|local_hit).bit_count(),
                                 local_only_antecedent_orders=(local_trigger&~g_trigger).bit_count(),
                                 net_order_difference=local_hit.bit_count()-g_hit.bit_count(),union_unique_directed_rules=len(set(selected.rule_id)|gs))
                        for col in ['local_only_complete','global_only_complete','local_only_antecedent','union_complete']:row[col+'_coverage']=row[col+'_orders']/index.n
                        row['net_coverage_difference']=row['net_order_difference']/index.n;coverage_rows.append(row)
                        if period=='validation':raw_rows.append(dict(config=config,budget=budget,control=family[0],method=family[1],seed=family[2],flow=flow,covered_orders=row['local_covered_orders']))
            if number%20==0 or family[0]=='GL':print(f'Completed {number}/{len(families)} systems: {family}; native-rule checks {checked:,}',flush=True)
    finally:handle.close()
    systems=pd.DataFrame(system_rows);groups=pd.DataFrame(group_rows);content=pd.DataFrame(contents);coverage=pd.DataFrame(coverage_rows);detail=pd.DataFrame(gl_detail)
    systems.to_csv(out/'advantage_system_summary.csv',index=False);systems.loc[systems.control.eq('GL')].to_csv(out/'GL_advantage_summary.csv',index=False)
    groups.loc[groups.control.eq('GL')].to_csv(out/'GL_group_advantage_summary.csv',index=False);groups.to_csv(local/'specificity_group_summaries.csv.gz',index=False)
    content.loc[content.control.eq('GL')].to_csv(out/'GL_rule_set_difference.csv',index=False);content.to_csv(local/'specificity_rule_set_difference.csv.gz',index=False)
    coverage.to_csv(out/'complementarity_systems.csv',index=False);coverage.loc[coverage.control.eq('GL')].to_csv(out/'GL_complementarity.csv',index=False)
    detail.to_csv(out/'GL_rule_strength.csv',index=False);pd.DataFrame(family_audits).to_csv(out/'family_audit.csv',index=False)
    # Pair the same frozen identity across periods for direct meeting/report examples.
    ids=['control','method','seed','group_id','scope_id','rule_id','antecedent','consequent']
    paired=detail.loc[detail.period.eq('discovery')].merge(detail.loc[detail.period.eq('validation')],on=ids,suffixes=('_D','_V'),validate='one_to_one')
    paired['confidence_gap_retention_ratio']=np.where(paired.advantage_candidate_D.astype(bool),paired.confidence_gap_vs_rest_pp_V/paired.confidence_gap_vs_rest_pp_D,np.nan)
    paired.to_csv(out/'GL_rule_advantage_retention.csv',index=False)
    examples=paired.loc[paired.advantage_candidate_D.astype(bool)&paired.advantage_supported_V.astype(bool)].sort_values('confidence_gap_vs_rest_pp_V',ascending=False)
    examples.to_csv(out/'GL_supported_survivor_examples.csv',index=False)
    # Compare real-group metrics against one whole-system statistic per seed.
    random=[]
    for (config,budget),ss in systems.groupby(['config','budget'],sort=False):
        real=ss.loc[ss.control.eq('GL')].iloc[0]
        for control in ['S','A1','A2']:
            rs=ss.loc[ss.control.eq(control)]
            for metric in ['validation_supported_share','advantage_survival_rate','both_directions_kept_rate','supported_novel_slots']:
                vals=rs[metric].dropna().to_numpy();value=real[metric]
                random.append(dict(config=config,budget=budget,control=control,metric=metric,real=value,random_total_seeds=len(rs),random_estimable_seeds=len(vals),
                                   random_median=float(np.median(vals)) if len(vals) else np.nan,random_min=float(np.min(vals)) if len(vals) else np.nan,random_max=float(np.max(vals)) if len(vals) else np.nan,
                                   random_ge_real=int(np.sum(vals>=value-1e-12)) if np.isfinite(value) else np.nan,
                                   descriptive_upper_tail=(1+np.sum(vals>=value-1e-12))/(1+len(vals)) if np.isfinite(value) and len(vals) else np.nan))
    pd.DataFrame(random).to_csv(out/'random_advantage_comparisons.csv',index=False)
    # Validate every reconstructed future L/R system against the original output.
    oldsys=pd.read_csv(root/'results/tables/validation/system_metrics.csv',dtype={'seed':str},keep_default_na=False)
    oldsys=oldsys.loc[oldsys.method.ne('G')]
    re=pd.DataFrame(raw_rows).merge(oldsys,on=['config','budget','control','method','seed','flow'],validate='one_to_one',suffixes=('_new','_old'))
    assert len(re)==6630 and (re.covered_orders_new==re.covered_orders_old).all()
    assert sha(pp)==phash
    manifest=dict(status='passed',protocol_sha256=phash,recorded_date=protocol['recorded_date'],test_evaluated=False,parameters_selected=False,
                  systems=len(families),native_discovery_validation_rule_checks=checked,raw_validation_system_checks=len(re),BY_families_checked_against_scipy=len(families),
                  true_rule_identities=len(paired),supported_discovery_candidates=len(examples),elapsed_seconds=round(time.time()-started,2),implementation_sha256=sha(Path(__file__)),
                  input_hashes={str(p.relative_to(root)):sha(p) for p in [pp,root/'configs/validation_quality.json',local/'discovery_baskets.csv',local/'validation_baskets.csv',local/'validation_rule_evidence.csv.gz']},
                  output_hashes={str(p.relative_to(root)):sha(p) for p in out.glob('*.csv')})
    (out/'run_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(systems.loc[systems.control.eq('GL')][['config','budget','discovery_advantage_candidates','validation_supported_slots','surviving_advantage_slots','advantage_survival_rate','strict_supported_slots']].to_string(index=False))
    print('Specificity extension completed:',manifest['elapsed_seconds'],'seconds.',flush=True)


if __name__=='__main__':main(Path(__file__).resolve().parents[3])
