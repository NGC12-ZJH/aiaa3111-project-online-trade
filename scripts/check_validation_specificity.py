"""Independent direct-order checks for all real group-rule contrasts and CIs."""
from pathlib import Path
import json
import time
import numpy as np
import pandas as pd
from scipy.stats import t

ROOT=Path(__file__).resolve().parents[1]


def main():
    started=time.time();local=ROOT/'data/processed/local/D_validation';core=local/'core';out=ROOT/'results/tables/validation_specificity'
    detail=pd.read_csv(out/'GL_rule_strength.csv',dtype={'rule_id':str})
    tax=pd.read_csv(core/'inputs/item_taxonomy_v1.csv',dtype=str,keep_default_na=False).set_index('stock_code').l2_id.to_dict()
    labels=pd.read_csv(core/'inputs/customer_clusters.csv',dtype=str).set_index('customer_id').cluster_id.to_dict();checked=0
    for period in ['discovery','validation']:
        d=pd.read_csv(local/f'{period}_baskets.csv',dtype=str,keep_default_na=False);d=d.loc[d.is_eligible_for_main_comparison.eq('1')]
        baskets=[set(tax[x] for x in json.loads(s) if tax[x]!='other') for s in d['items']]
        customers,inverse=np.unique(d.customer_id.to_numpy(),return_inverse=True);groups=np.array([labels[c] for c in customers])
        nvec=np.bincount(inverse).astype(float);vector_cache={}
        def vector(items):
            key=tuple(sorted(items))
            if key not in vector_cache:
                indicators=np.array([set(items)<=b for b in baskets],float)
                vector_cache[key]=np.bincount(inverse,weights=indicators,minlength=len(customers))
            return vector_cache[key]
        for row in detail.loc[detail.period.eq(period)].itertuples():
            ant=json.loads(row.antecedent);con=json.loads(row.consequent)
            av=vector(ant);cv=vector(con);jv=vector(list(set(ant)|set(con)));gmask=groups==str(row.group_id)
            values=[]
            for mask,prefix in [(gmask,'target'),(~gmask,'rest')]:
                n,a,c,j=(z[mask] for z in [nvec,av,cv,jv]);N,A,C,J=n.sum(),a.sum(),c.sum(),j.sum();m=len(n)
                assert int(A)==getattr(row,prefix+'_antecedent_count');assert int(J)==getattr(row,prefix+'_joint_count')
                confidence=J/A if A else np.nan;baseline=C/N
                if A and m>1:
                    conf_if=(j-confidence*a)/A;assoc_if=conf_if-(c-baseline*n)/N
                    vc=m/(m-1)*sum(conf_if**2);va=m/(m-1)*sum(assoc_if**2)
                else:vc=va=np.nan
                values.append((confidence,confidence-baseline,vc,va,m))
            target,rest=values
            for i,var_idx,column in [(0,2,'confidence'),(1,3,'association')]:
                delta=target[i]-rest[i];np.testing.assert_allclose(delta*100,getattr(row,column+'_gap_vs_rest_pp'),equal_nan=True,atol=1e-10)
                se=np.sqrt(target[var_idx]+rest[var_idx]);df=min(target[4],rest[4])-1
                if np.isfinite(se) and se>=1e-14 and df>0:
                    low=(delta-t.ppf(.975,df)*se)*100;high=(delta+t.ppf(.975,df)*se)*100;pv=t.sf(delta/se,df)
                    np.testing.assert_allclose([low,high],[getattr(row,column+'_gap_ci95_low_pp'),getattr(row,column+'_gap_ci95_high_pp')],atol=1e-9,rtol=1e-10)
                    np.testing.assert_allclose(pv,getattr(row,'p_'+column+'_gap'),atol=1e-12,rtol=1e-9)
            checked+=1
    result=dict(status='passed',direct_order_real_rule_period_checks=checked,
                checks=['target/rest counts','confidence and baseline-adjusted gaps','customer-cluster contrast intervals and p values'],
                elapsed_seconds=round(time.time()-started,2))
    (out/'independent_check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(result)


if __name__=='__main__':main()
