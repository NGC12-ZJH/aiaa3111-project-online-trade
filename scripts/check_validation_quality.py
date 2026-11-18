"""Independent BY/BH library check and direct-set coverage on all G/L systems."""
from pathlib import Path
import json
import time
import numpy as np
import pandas as pd
from scipy.stats import false_discovery_control

ROOT=Path(__file__).resolve().parents[1]


def main():
    started=time.time();local=ROOT/'data/processed/local/D_validation';core=local/'core'
    out=ROOT/'results/tables/validation_quality'
    detail=pd.read_csv(local/'quality_rule_evidence.csv.gz',dtype={'rule_id':str,'seed':str},keep_default_na=False)
    families=0
    for key,d in detail.groupby(['control','method','seed'],sort=False):
        p=d.p_combined.astype(float).to_numpy()
        for method,col in [('by','q_BY'),('bh','q_BH')]:
            np.testing.assert_allclose(false_discovery_control(p,method=method),d[col].astype(float),rtol=1e-12,atol=1e-14)
        families+=1
    tax=pd.read_csv(core/'inputs/item_taxonomy_v1.csv',dtype=str,keep_default_na=False).set_index('stock_code').l2_id.to_dict()
    data=pd.read_csv(local/'validation_baskets.csv',dtype=str,keep_default_na=False)
    data=data.loc[data.is_eligible_for_main_comparison.eq('1')]
    baskets=[set(tax[x] for x in json.loads(s) if tax[x]!='other') for s in data['items']]
    clusters=pd.read_csv(core/'inputs/customer_clusters.csv',dtype=str).set_index('customer_id').cluster_id.to_dict()
    protocol=json.loads((ROOT/'configs/validation_quality.json').read_text(encoding='utf-8'))['primary']
    lookup={}
    for row in detail.loc[detail.control.eq('GL')].to_dict('records'):
        # Boolean gate evaluated directly, without the implementation's classifier.
        ok=(int(row['antecedent_count'])>=protocol['min_antecedent_orders']
            and int(row['joint_count'])>=protocol['min_joint_orders']
            and int(row['antecedent_customers'])>=protocol['min_antecedent_customers']
            and int(row['joint_customers'])>=protocol['min_joint_customers']
            and float(row['max_customer_joint_share'])<=protocol['max_customer_joint_share']+1e-12
            and float(row['confidence_uplift'])>=protocol['min_confidence_uplift']-1e-12
            and float(row['lift'])>=protocol['min_lift']-1e-12
            and (int(row['length'])==2 or float(row['triple_increment_pp'])>=protocol['min_triple_increment_pp']-1e-10)
            and float(row['q_BY'])<=protocol['alpha'])
        assert ok==(row['primary_status']=='accepted')
        lookup[row['method'],row['evaluation_scope'],row['rule_id']]=ok
    summary=pd.read_csv(out/'GL_quality_summary.csv');checked=0
    for config in ['P1','P2','P3','P4','P5']:
        rules=pd.read_csv(core/f'selected_rules/{config}_GL.csv.gz',dtype=str,keep_default_na=False)
        for (budget,method),group in rules.groupby(['budget','method'],sort=False):
            for flow in ['restricted','shared']:
                accepted=[];slots=0
                for r in group.itertuples(index=False):
                    scope='GLOBAL' if flow=='shared' or method=='G' else r.scope_id
                    if lookup[method,scope,r.rule_id]:
                        accepted.append((r.group_id,set(json.loads(r.antecedent)),set(json.loads(r.consequent))))
                        slots+=1
                hits=[]
                for customer,basket in zip(data.customer_id,baskets):
                    hits.append(any(a<=basket and c<=basket for g,a,c in accepted if method=='G' or flow=='shared' or g==clusters[customer]))
                row=summary.loc[summary.config.eq(config)&summary.budget.eq(int(budget))&summary.method.eq(method)&summary.flow.eq(flow)].iloc[0]
                assert slots==row.accepted_rule_slots
                assert sum(hits)==row.quality_covered_orders
                macro=pd.DataFrame({'customer':data.customer_id.to_numpy(),'hit':hits}).groupby('customer').hit.mean().mean()
                assert abs(macro-row.quality_customer_macro_coverage)<1e-12
                checked+=1
    result=dict(status='passed',fdr_library='scipy.stats.false_discovery_control',fdr_families_checked=families,
                direct_set_GL_systems_checked=checked,all_GL_gate_decisions_match=True,
                checks=['BY/BH adjusted values match independent library','All 60 GL accepted-slot counts match direct gates',
                        'All 60 GL quality coverage and customer macro coverage match direct sets'],elapsed_seconds=round(time.time()-started,2))
    (out/'independent_check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(result)


if __name__=='__main__':main()
