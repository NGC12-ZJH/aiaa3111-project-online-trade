"""Do local rules supplement global rules at the same unique directed-rule budget?"""
from pathlib import Path
from functools import reduce
from operator import or_
import json
import time
import numpy as np
import pandas as pd
from .validation import BasketIndex, bootstrap_pairs, sha
from .quality import adjust_fdr, classify


def merge_lists(global50, local50, global100):
    assert len(global50)==50 and len(set(global50))==50
    assert len(local50)==50
    assert len(global100)==100 and len(set(global100))==100
    assert global100[:50]==global50
    hybrid=list(dict.fromkeys(global50+local50))
    return hybrid,global100[:len(hybrid)]


def union_mask(index,definitions,rule_ids):
    return reduce(or_,(index.mask(definitions[r][0])&index.mask(definitions[r][1]) for r in rule_ids),0)


def main(root):
    started=time.time();pp=root/'configs/validation_hybrid.json';protocol=json.loads(pp.read_text(encoding='utf-8'));phash=sha(pp)
    assert not protocol['test_evaluation'] and not protocol['parameter_selection']
    local=root/'data/processed/local/D_validation';core=local/'core'
    out=root/'results/tables/validation_hybrid';out.mkdir(parents=True,exist_ok=True)
    tx=pd.read_csv(core/'inputs/item_taxonomy_v1.csv',dtype=str,keep_default_na=False).set_index('stock_code').l2_id.to_dict()
    data=pd.read_csv(local/'validation_baskets.csv',dtype=str,keep_default_na=False)
    assert set(data.split)=={'validation'}
    data=data.loc[data.is_eligible_for_main_comparison.eq('1')]
    assert len(data)==4862 and data.customer_id.nunique()==1458
    baskets=[{tx[x] for x in json.loads(s) if tx[x]!='other'} for s in data['items']]
    index=BasketIndex(data.customer_id.tolist(),baskets)
    lists={};definitions={};composition=[];sources=[]
    for config in protocol['configs']:
        source=core/f'selected_rules/{config}_GL.csv.gz';sources.append(source)
        d=pd.read_csv(source,dtype=str,keep_default_na=False)
        for r in d.drop_duplicates('rule_id').itertuples():definitions[r.rule_id]=(tuple(json.loads(r.antecedent)),tuple(json.loads(r.consequent)))
        def ids(method,budget):
            r=d.loc[d.method.eq(method)&d.budget.eq(str(budget))].copy();r['rank']=r.rank_within_group.astype(int)
            return r.sort_values(['group_id','rank']).rule_id.tolist()
        g50,l50,g100=ids('G',50),ids('L',50),ids('G',100)
        hybrid,matched=merge_lists(g50,l50,g100)
        lists[config]={'G50':g50,'HYBRID':hybrid,'G_K':matched}
        composition.append(dict(config=config,K=len(hybrid),global50_unique=len(g50),local50_slots=len(l50),
                                local50_unique=len(set(l50)),overlap_G50_L50=len(set(g50)&set(l50)),
                                local_new_vs_G50=len(set(l50)-set(g50)),same_rules_H_GK=len(set(hybrid)&set(matched)),
                                hybrid_rules_outside_GK=len(set(hybrid)-set(matched)),global_K_rules_outside_H=len(set(matched)-set(hybrid))))
    universe=sorted(set(r for configs in lists.values() for ids in configs.values() for r in ids))
    evidence_path=local/'quality_rule_evidence.csv.gz'
    evidence=pd.read_csv(evidence_path,dtype={'rule_id':str})
    evidence=evidence.loc[evidence.evaluation_scope.eq('GLOBAL')&evidence.rule_id.isin(universe)].copy()
    # Global point estimates are independent of their original system's correction family.
    for field in ['p_combined','confidence_uplift','lift','antecedent_count','joint_count']:
        assert evidence.groupby('rule_id')[field].nunique(dropna=False).max()==1,field
    evidence=evidence.drop_duplicates('rule_id').set_index('rule_id').loc[universe].reset_index()
    evidence['q_BY']=adjust_fdr(evidence.p_combined.to_numpy(),'BY');evidence['q_BH']=adjust_fdr(evidence.p_combined.to_numpy(),'BH')
    thresholds=json.loads((root/'configs/validation_quality.json').read_text(encoding='utf-8'))['primary']
    evidence['hybrid_primary_status']=[classify(r,thresholds) for r in evidence.to_dict('records')]
    quality={r.rule_id:r.hybrid_primary_status=='accepted' for r in evidence.itertuples()}
    evidence.to_csv(out/'shared_rule_quality.csv',index=False)
    summary=[];contrasts=[];memberships=[];order_rows=pd.DataFrame({'customer_id':data.customer_id.to_numpy(),'basket_id':data.basket_id.to_numpy()})
    rng=np.random.default_rng(protocol['bootstrap']['seed']);m=len(index.by_customer)
    weights=rng.multinomial(m,np.full(m,1/m),size=protocol['bootstrap']['repeats']).astype(float)
    for config,systems in lists.items():
        raw={};good={};k=len(systems['HYBRID']);customer_totals=index.customer_counts(index.all)
        for name,ids in systems.items():
            raw[name]=union_mask(index,definitions,ids)
            accepted=[r for r in ids if quality[r]];good[name]=union_mask(index,definitions,accepted)
            assert not good[name]&~raw[name]
            for rid in ids:
                memberships.append(dict(config=config,system=name,rule_id=rid,accepted=quality[rid],
                                        in_G50=rid in systems['G50'],in_hybrid=rid in systems['HYBRID'],in_G_K=rid in systems['G_K'],
                                        antecedent=json.dumps(definitions[rid][0]),consequent=json.dumps(definitions[rid][1])))
            summary.append(dict(config=config,system=name,K=k,actual_unique_rules=len(ids),accepted_unique_rules=len(accepted),
                                accepted_share=len(accepted)/len(ids),covered_orders=raw[name].bit_count(),coverage=raw[name].bit_count()/index.n,
                                customer_macro_coverage=float(np.mean(index.customer_counts(raw[name])/customer_totals)),
                                quality_covered_orders=good[name].bit_count(),quality_coverage=good[name].bit_count()/index.n,
                                quality_customer_macro_coverage=float(np.mean(index.customer_counts(good[name])/customer_totals)),
                                n_baskets=index.n,n_customers=m))
            order_rows[f'{config}_{name}']=[(raw[name]>>i)&1 for i in range(index.n)]
        assert not raw['G50']&~raw['HYBRID'] and not raw['G50']&~raw['G_K']
        for left,right in [('HYBRID','G_K'),('HYBRID','G50'),('G_K','G50')]:
            stats=bootstrap_pairs(index,raw[right],raw[left],weights)
            only_left=(raw[left]&~raw[right]).bit_count();only_right=(raw[right]&~raw[left]).bit_count()
            for metric in ['order','customer_macro']:
                estimate,lo,hi=stats['L_minus_G',metric]
                contrasts.append(dict(config=config,K=k,comparison=f'{left}_minus_{right}',metric=metric,estimate=estimate,
                                      ci95_low=lo,ci95_high=hi,left_only_orders=only_left,right_only_orders=only_right,
                                      net_orders=only_left-only_right,quality_difference=(good[left].bit_count()-good[right].bit_count())/index.n,
                                      bootstrap_repeats=len(weights)))
    pd.DataFrame(composition).to_csv(out/'rule_composition.csv',index=False)
    pd.DataFrame(summary).to_csv(out/'system_comparison.csv',index=False)
    pd.DataFrame(contrasts).to_csv(out/'paired_comparisons.csv',index=False)
    pd.DataFrame(memberships).to_csv(out/'rule_membership.csv',index=False)
    order_rows.to_csv(local/'hybrid_order_indicators.csv.gz',index=False)
    # A direct set implementation independently checks all fifteen raw and quality coverages.
    independent=0
    for config,systems in lists.items():
        for name,ids in systems.items():
            exact=sum(any(set(definitions[r][0])<=b and set(definitions[r][1])<=b for r in ids) for b in baskets)
            qexact=sum(any(set(definitions[r][0])<=b and set(definitions[r][1])<=b for r in ids if quality[r]) for b in baskets)
            row=next(r for r in summary if r['config']==config and r['system']==name)
            assert exact==row['covered_orders'] and qexact==row['quality_covered_orders'];independent+=1
    assert sha(pp)==phash
    manifest=dict(status='passed',protocol_sha256=phash,quality_protocol_sha256=sha(root/'configs/validation_quality.json'),
                  c_handoff_commit='ac2b8a3338198c24c7cf6203aa623be11a02d2f8',sample_orders=index.n,sample_customers=m,
                  unique_GLOBAL_quality_hypotheses=len(universe),quality_family='common across five hybrid/matched lists; reused raw GLOBAL p-values, BY recalculated',
                  independent_direct_set_systems=independent,test_evaluated=False,parameters_selected=False,
                  elapsed_seconds=round(time.time()-started,2),implementation_sha256=sha(Path(__file__)),
                  input_hashes={str(p.relative_to(root)):sha(p) for p in sources+[local/'validation_baskets.csv',evidence_path,pp]},
                  output_hashes={str(p.relative_to(root)):sha(p) for p in out.glob('*.csv')})
    (out/'run_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(pd.DataFrame(composition).to_string(index=False));print(pd.DataFrame(summary)[['config','system','actual_unique_rules','coverage','quality_coverage']].to_string(index=False))
    print('Direct-set check passed for',independent,'systems; no Test evaluation.')


if __name__=='__main__':main(Path(__file__).resolve().parents[3])
