"""Independent set-based check; intentionally does not import D's evaluator."""
from pathlib import Path
import json
import time
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def main():
    started=time.time();local=ROOT/'data/processed/local/D_validation';core=local/'core'
    baskets=pd.read_csv(local/'validation_baskets.csv',dtype=str,keep_default_na=False)
    baskets=baskets.loc[baskets.is_eligible_for_main_comparison.eq('1')]
    tax=pd.read_csv(core/'inputs/item_taxonomy_v1.csv',dtype=str,keep_default_na=False).set_index('stock_code').l2_id.to_dict()
    category_baskets=[set(tax[x] for x in json.loads(s) if tax[x]!='other') for s in baskets['items']]
    customers=baskets.customer_id.to_numpy()
    clusters=pd.read_csv(core/'inputs/customer_clusters.csv',dtype=str).set_index('customer_id').cluster_id.to_dict()
    systems=pd.read_csv(ROOT/'results/tables/validation/system_metrics.csv',dtype={'seed':str},keep_default_na=False)
    checked=0
    for config in ['P1','P2','P3','P4','P5']:
        for control in ['GL','A1','A2','S']:
            data=pd.read_csv(core/f'selected_rules/{config}_{control}.csv.gz',dtype=str,keep_default_na=False)
            # All G/L; one explicitly fixed seed for each random family.
            seed='' if control=='GL' else '42' if control=='S' else '1000'
            if control!='GL':data=data.loc[data.seed.eq(seed)]
            mapping=clusters
            if control!='GL':
                name={'S':'random_groups.csv','A1':'random_groups_A1_profile_frequency.csv','A2':'random_groups_A2_discovery_baskets.csv'}[control]
                labels=pd.read_csv(core/'inputs'/name,dtype=str,keep_default_na=False)
                mapping=labels.loc[labels.seed.eq(seed)].set_index('customer_id').random_group_id.to_dict()
            for (budget,method),selected in data.groupby(['budget','method']):
                rules=[(r.group_id,set(json.loads(r.antecedent)),set(json.loads(r.consequent))) for r in selected.itertuples()]
                for flow in ['restricted','shared']:
                    hit=[];trigger=[]
                    for customer,basket in zip(customers,category_baskets):
                        applicable=[(a,c) for group,a,c in rules if method=='G' or flow=='shared' or group==mapping[customer]]
                        hit.append(any(a<=basket and c<=basket for a,c in applicable))
                        trigger.append(any(a<=basket for a,c in applicable))
                    expected=systems.loc[systems.config.eq(config)&systems.budget.eq(int(budget))&systems.control.eq(control)&systems.method.eq(method)&systems.seed.eq(seed)&systems.flow.eq(flow)]
                    assert len(expected)==1
                    row=expected.iloc[0]
                    assert sum(hit)==int(row.covered_orders),(config,budget,control,method,flow,'joint')
                    assert sum(trigger)==int(row.triggered_orders),(config,budget,control,method,flow,'antecedent')
                    independent=pd.DataFrame({'customer':customers,'hit':hit}).groupby('customer').hit.mean().mean()
                    assert abs(independent-float(row.customer_macro_coverage))<1e-12
                    checked+=1
    record={'status':'passed','implementation':'direct Python set inclusion; no evaluator imports',
            'checked_systems':checked,'covers':'all GL; S seed 42, A1 seed 1000, A2 seed 1000; all five configs, budgets, flows',
            'checks':['covered_orders','triggered_orders','customer_macro_coverage'],
            'elapsed_seconds':round(time.time()-started,2)}
    (ROOT/'results/tables/validation/independent_check.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(record)


if __name__=='__main__':main()
