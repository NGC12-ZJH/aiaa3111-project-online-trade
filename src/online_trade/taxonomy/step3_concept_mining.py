"""Concept-level (L2) rule mining for G / L / R on Discovery, with C's thresholds; exploratory Validation check."""
import itertools
import numpy as np
import pandas as pd
from .paths import INPUT, TAXONOMY, RESULTS, CACHE, THRESHOLDS, BUDGET50_ALLOCATION
OUT = RESULTS
TH = THRESHOLDS
tax = pd.read_csv(TAXONOMY / 'item_taxonomy_v0.csv', dtype={'stock_code': str}).set_index('stock_code')
b = pd.read_csv(INPUT / 'baskets_long.csv.gz', dtype=str)
cl = pd.read_csv(INPUT / 'customer_clusters.csv', dtype=str).set_index('customer_id').cluster_id
rg = pd.read_csv(INPUT / 'random_groups.csv', dtype=str)
b = b[(b.is_eligible_for_main_comparison == '1') & b.customer_id.isin(cl.index) & b.split.isin(['discovery', 'validation'])]
b['l2'] = b.stock_code.map(tax.l2_id)
b = b[b.l2 != 'other']
C = sorted(b.l2.unique()); idx = {c: i for i, c in enumerate(C)}
def matrix(split):
    d = b[b.split == split]
    bk = d.groupby('basket_id').agg(cust=('customer_id', 'first'))
    pos = {k: i for i, k in enumerate(bk.index)}
    X = np.zeros((len(bk), len(C)), dtype=bool)
    X[d.basket_id.map(pos).values, d.l2.map(idx).values] = True
    return X, bk.cust.values
XD, custD = matrix('discovery'); XV, custV = matrix('validation')
print('Discovery baskets', len(XD), 'Validation baskets', len(XV), 'concepts', len(C), 'median concepts/basket', np.median(XD.sum(1)))
def mine(X):
    n = len(X); Xi = X.astype(np.int32)
    single = Xi.sum(0); pair = Xi.T @ Xi
    rules = []
    for a in range(len(C)):
        for c in range(len(C)):
            if a != c:
                rules.append(((a,), c, single[a], pair[a, c]))
    for a, bb in itertools.combinations(range(len(C)), 2):
        if pair[a, bb] < TH['min_ante']: continue
        m = X[:, a] & X[:, bb]; tri = Xi[m].sum(0)
        for c in range(len(C)):
            if c not in (a, bb): rules.append(((a, bb), c, pair[a, bb], tri[c]))
    df = pd.DataFrame(rules, columns=['ante', 'cons', 'ante_count', 'joint'])
    df['n'] = n; df['cons_count'] = single[df.cons.values]
    df['support'] = df.joint / n; df['confidence'] = df.joint / df.ante_count.clip(lower=1)
    df['lift'] = df.confidence / (df.cons_count / n)
    df['eligible'] = (df.support >= TH['min_support']) & (df.joint >= TH['min_joint']) & (df.ante_count >= TH['min_ante']) & (df.confidence >= TH['min_conf']) & (df.lift >= TH['min_lift'])
    df['key'] = df.ante.map(lambda a: '+'.join(C[i] for i in a)) + '->' + df.cons.map(lambda c: C[c])
    df['itemset'] = [frozenset(a + (c,)) for a, c in zip(df.ante, df.cons)]
    return df.set_index('key')
scopes = {('G', '', 'ALL'): np.ones(len(XD), bool)}
for g in '012': scopes[('L', '', g)] = np.array([cl.get(c) == g for c in custD])
seeds = sorted(rg.seed.unique(), key=int)
rmap = {s: rg[rg.seed == s].set_index('customer_id').random_group_id for s in seeds}
for s in seeds:
    for g in '012': scopes[('R', s, g)] = np.array([rmap[s].get(c) == g for c in custD])
res = {k: mine(XD[m]) for k, m in scopes.items()}
# 1) qualified counts
rows = [dict(method=k[0], seed=k[1], group=k[2], baskets=len(XD[m]), qualified=int(res[k].eligible.sum()),
             qualified_2item=int((res[k].eligible & (res[k].ante.map(len) == 1)).sum()),
             qualified_3item=int((res[k].eligible & (res[k].ante.map(len) == 2)).sum())) for k, m in scopes.items()]
cnt = pd.DataFrame(rows); cnt.to_csv(f'{OUT}/concept_qualified_counts.csv', index=False)
print('\n[1] qualified concept rules'); print(cnt[cnt.method != 'R'].to_string(index=False))
print(cnt[cnt.method == 'R'].groupby('group')[['baskets', 'qualified']].agg(['median', 'min', 'max']).to_string())
# 2) distinctiveness: support vectors over common pool of 2-item concept sets (union of eligible in any scope)
pool = set()
for k, d in res.items(): pool |= set(d[d.eligible & (d.ante.map(len) == 1)].itemset)
pool = sorted(pool, key=lambda s: sorted(s))
def supvec(d):
    s = d[d.ante.map(len) == 1].drop_duplicates('itemset').set_index('itemset').support
    return np.array([s.get(p, 0.0) for p in pool])
def outside(mask):
    return mine(XD[~mask])
def bc(u, v): return np.abs(u - v).sum() / (u + v).sum()
def metrics(method, seed):
    ks = [(method, seed, g) for g in '012']
    V = [supvec(res[k]) for k in ks]
    between = np.mean([bc(V[i], V[j]) for i, j in itertools.combinations(range(3), 2)])
    vs_out = np.mean([bc(V[i], supvec(outside(scopes[k]))) for i, k in enumerate(ks)])
    def top10(k):
        d = res[k][res[k].eligible & (res[k].ante.map(len) == 1)].sort_values(['joint', 'confidence', 'lift'], ascending=False)
        return set(d.drop_duplicates('itemset').itemset.head(10))
    T = [top10(k) for k in ks]
    jd = np.mean([1 - len(T[i] & T[j]) / max(1, len(T[i] | T[j])) for i, j in itertools.combinations(range(3), 2)])
    return dict(method=method, seed=seed, between_BC=between, group_vs_rest_BC=vs_out, top10_jaccard_distance=jd)
dist = pd.DataFrame([metrics('L', '')] + [metrics('R', s) for s in seeds]); dist.to_csv(f'{OUT}/concept_distinctiveness.csv', index=False)
print('\n[2] concept-level distinctiveness, pool of %d 2-concept sets' % len(pool))
L = dist.iloc[0]; R = dist.iloc[1:]
for m in ['between_BC', 'group_vs_rest_BC', 'top10_jaccard_distance']:
    print(f'  {m}: L={L[m]:.4f}  R median={R[m].median():.4f} [{R[m].min():.4f}-{R[m].max():.4f}]  L > R in {(L[m] > R[m]).sum()}/20  empirical p={(1 + (R[m] >= L[m]).sum()) / 21:.3f}')
# 3) representative group-specific concept rules (largest support gap vs rest, 2-item, eligible in group)
reps = []
for g in '012':
    k = ('L', '', g); d = res[k][res[k].eligible].copy(); o = outside(scopes[k])
    d['out_support'] = o.support.reindex(d.index).values; d['out_conf'] = o.confidence.reindex(d.index).values
    d['gap_pp'] = 100 * (d.support - d.out_support)
    d = d.sort_values('gap_pp', ascending=False).drop_duplicates('itemset')
    for key, r in d.head(5).iterrows():
        reps.append(dict(group=g, rule=key, joint=r.joint, support=round(r.support, 4), out_support=round(r.out_support, 4), conf=round(r.confidence, 3), out_conf=round(r.out_conf, 3), lift=round(r.lift, 2)))
reps = pd.DataFrame(reps); reps.to_csv(f'{OUT}/concept_group_representative_rules.csv', index=False)
print('\n[3] top group-vs-rest concept rules'); print(reps.to_string(index=False))
# 4) exploratory Validation check at budget 50 (C's policy: proportional allocation, joint/conf/lift ranking)
alloc = BUDGET50_ALLOCATION
def select(k, K):
    d = res[k][res[k].eligible].sort_values(['joint', 'confidence', 'lift'], ascending=False)
    return d.head(K)
def val_eval(rule_sets, groups_of_cust):
    hit = np.zeros(len(XV), bool); trig = np.zeros(len(XV), bool); confs = []; lifts = []
    for g, sel in rule_sets.items():
        m = np.array([groups_of_cust(c) == g for c in custV])
        Xg = XV[m]; base = XV[m].mean(0)
        h = np.zeros(m.sum(), bool); t = np.zeros(m.sum(), bool)
        for _, r in sel.iterrows():
            a = Xg[:, list(r.ante)].all(1); j = a & Xg[:, r.cons]
            t |= a; h |= j
            if a.sum() >= 20:
                cf = j.sum() / a.sum(); confs.append(cf); lifts.append(cf / max(base[r.cons], 1e-9))
        hit[m] = h; trig[m] = t
    return dict(trigger_rate=trig.mean(), hit_rate=hit.mean(), median_val_conf=np.median(confs), median_val_lift=np.median(lifts), rules=sum(len(v) for v in rule_sets.values()))
ev = [dict(method='G', seed='', **val_eval({'ALL': select(('G', '', 'ALL'), 50)}, lambda c: 'ALL'))]
ev.append(dict(method='L', seed='', **val_eval({g: select(('L', '', g), alloc[g]) for g in '012'}, lambda c: cl.get(c))))
for s in seeds:
    ev.append(dict(method='R', seed=s, **val_eval({g: select(('R', s, g), alloc[g]) for g in '012'}, lambda c, s=s: rmap[s].get(c))))
ev = pd.DataFrame(ev); ev.to_csv(f'{OUT}/concept_validation_budget50.csv', index=False)
print('\n[4] exploratory Validation, budget 50 (concept level)')
print(ev[ev.method != 'R'].round(4).to_string(index=False))
print('R median:', ev[ev.method == 'R'][['trigger_rate', 'hit_rate', 'median_val_conf', 'median_val_lift']].median().round(4).to_dict())
print('L hit_rate > R in %d/20' % (ev.iloc[1].hit_rate > ev[ev.method == 'R'].hit_rate).sum())
print('\nG top-15 concept rules (budget order):')
print(select(('G', '', 'ALL'), 15)[['joint', 'support', 'confidence', 'lift']].round(3).to_string())
pd.to_pickle(res, CACHE / 'concept_rules_all_scopes.pkl')
