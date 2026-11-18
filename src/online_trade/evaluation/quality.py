"""Uniform, comparison-only future association quality on fixed Discovery lists."""
from pathlib import Path
from functools import reduce
from operator import or_
import hashlib
import json
import platform
import time

import numpy as np
import pandas as pd
from scipy.stats import t

from .validation import load_inputs, load_period, sha, rate


def adjust_fdr(pvalues, method='BY'):
    p = np.asarray(pvalues, dtype=float)
    if not len(p): return p
    assert np.isfinite(p).all() and ((p >= 0) & (p <= 1)).all()
    order = np.argsort(p, kind='stable')
    n = len(p)
    factor = np.sum(1 / np.arange(1, n + 1)) if method == 'BY' else 1.
    ranked = p[order] * n * factor / np.arange(1, n + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1].clip(0, 1)
    result = np.empty(n)
    result[order] = ranked
    return result


def ratio_contrast(x, d, y, e):
    """Ratio difference, with independent customers and dependent within-customer orders."""
    m = len(x)
    dx, dy = float(np.sum(d)), float(np.sum(e))
    if dx <= 0 or dy <= 0 or m < 2:
        return (float('nan'), float('nan'), float('nan'), float('nan'), 1.)
    rx, ry = np.sum(x) / dx, np.sum(y) / dy
    difference = float(rx - ry)
    influence = (x - rx * d) / dx - (y - ry * e) / dy
    se = float(np.sqrt(m / (m - 1) * np.dot(influence, influence)))
    # Degenerate customer variation is not treated as infinite certainty.
    if se < 1e-14:
        return difference, se, float('nan'), float('nan'), 1.
    critical = t.ppf(.975, m - 1)
    return difference, se, float(difference - critical * se), float(difference + critical * se), float(t.sf(difference / se, m - 1))


class QualityEvidence:
    def __init__(self, validation, discovery, mappings, definitions):
        self.index = validation
        self.discovery = discovery
        self.mappings = mappings
        self.definitions = definitions
        self.customers = list(validation.by_customer)
        self.orders = validation.customer_counts(validation.all)
        self.vector_cache = {}
        self.scope_customers = {'GLOBAL': np.arange(len(self.customers))}
        self.scope_masks = {'GLOBAL': validation.all}
        self.disc_scope_masks = {'GLOBAL': discovery.all}
        self.cache = {}

    def set_scope(self, scope_id, mapping, group):
        if scope_id in self.scope_customers: return
        self.scope_customers[scope_id] = np.array([i for i, c in enumerate(self.customers) if mapping[c] == group], dtype=int)
        self.scope_masks[scope_id] = self.index.scope(mapping, group)
        self.disc_scope_masks[scope_id] = self.discovery.scope(mapping, group)

    def vector(self, items):
        key = tuple(sorted(items))
        if key not in self.vector_cache:
            self.vector_cache[key] = self.index.customer_counts(self.index.mask(key))
        return self.vector_cache[key]

    def get(self, scope, rule_id):
        key = scope, rule_id
        if key in self.cache: return self.cache[key]
        ant, con = self.definitions[rule_id]
        joint_items = tuple(sorted(set(ant) | set(con)))
        indices = self.scope_customers[scope]
        nvec = self.orders[indices]
        av, cv, jv = self.vector(ant)[indices], self.vector(con)[indices], self.vector(joint_items)[indices]
        n, a, c, j = map(lambda x: int(np.sum(x)), [nvec, av, cv, jv])
        confidence, baseline = rate(j, a), rate(c, n)
        uplift, se, low, high, p_assoc = ratio_contrast(jv, av, cv, nvec)
        increment, inc_low, inc_high = float('nan'), float('nan'), float('nan')
        p_increment = 0.
        if len(ant) == 2:
            increments, lows, highs, ps = [], [], [], []
            for item in ant:
                single = self.vector([item])[indices]
                single_joint = self.vector(tuple(sorted(set([item]) | set(con))))[indices]
                delta, _, lo, hi, pv = ratio_contrast(jv, av, single_joint, single)
                increments.append(delta * 100); lows.append(lo * 100); highs.append(hi * 100); ps.append(pv)
            increment = min(increments)
            inc_low, inc_high = min(lows), min(highs)
            p_increment = max(ps)
        ds = self.disc_scope_masks[scope]
        dm = self.discovery
        da = (dm.mask(ant) & ds).bit_count()
        dc = (dm.mask(con) & ds).bit_count()
        dj = (dm.mask(joint_items) & ds).bit_count()
        dn = ds.bit_count()
        dconf, dbase = rate(dj, da), rate(dc, dn)
        dlift = rate(dconf, dbase) if dbase else float('nan')
        lift = rate(confidence, baseline) if baseline else float('nan')
        record = dict(evaluation_scope=scope, rule_id=rule_id, antecedent=json.dumps(ant), consequent=json.dumps(con),
                      length=len(ant) + len(con), n_baskets=n, n_customers=len(indices),
                      antecedent_count=a, consequent_count=c, joint_count=j,
                      antecedent_customers=int(np.sum(av > 0)), joint_customers=int(np.sum(jv > 0)),
                      max_customer_joint_share=rate(np.max(jv), j) if len(jv) and j else float('nan'),
                      support=rate(j, n), confidence=confidence, consequent_baseline=baseline, lift=lift,
                      confidence_uplift=uplift, uplift_cluster_se=se, uplift_ci95_low=low, uplift_ci95_high=high,
                      triple_increment_pp=increment, increment_ci95_low_pp=inc_low, increment_ci95_high_pp=inc_high,
                      p_association=p_assoc, p_increment=p_increment, p_combined=max(p_assoc, p_increment),
                      discovery_confidence=dconf, discovery_lift=dlift,
                      confidence_change_pp=100 * (confidence - dconf), confidence_ratio=rate(confidence, dconf) if dconf else float('nan'),
                      lift_ratio=rate(lift, dlift) if dlift else float('nan'))
        self.cache[key] = record
        return record


def classify(evidence, thresholds):
    if evidence['antecedent_count'] == 0: return 'not_triggered'
    enough = (evidence['antecedent_count'] >= thresholds['min_antecedent_orders']
              and evidence['joint_count'] >= thresholds['min_joint_orders']
              and evidence['antecedent_customers'] >= thresholds['min_antecedent_customers']
              and evidence['joint_customers'] >= thresholds['min_joint_customers']
              and evidence['max_customer_joint_share'] <= thresholds['max_customer_joint_share'] + 1e-12)
    if not enough: return 'insufficient_evidence'
    if not (evidence['confidence_uplift'] + 1e-12 >= thresholds['min_confidence_uplift']
            and evidence['lift'] + 1e-12 >= thresholds['min_lift']): return 'effect_below_minimum'
    if evidence['length'] == 3 and not evidence['triple_increment_pp'] + 1e-10 >= thresholds['min_triple_increment_pp']:
        return 'increment_below_minimum'
    if evidence['q_' + thresholds['adjustment']] > thresholds['alpha']: return 'uncertainty_unresolved'
    return 'accepted'


def quality_summary(q, records, rows, method, flow, family, setting):
    states = {}; full = 0; raw = 0; accepted_keys = set(); selected_keys = set(); accepted_slots = 0
    evidence_list = []
    for r in rows.itertuples(index=False):
        scope = 'GLOBAL' if flow == 'shared' or method == 'G' else r.scope_id
        key = scope, r.rule_id
        e = records[family, scope, r.rule_id]
        state = classify(e, setting)
        states[state] = states.get(state, 0) + 1
        selected_keys.add(key)
        hit = q.index.mask(r.ant) & q.index.mask(r.con) & q.scope_masks[scope]
        raw |= hit
        if state == 'accepted':
            full |= hit; accepted_slots += 1; accepted_keys.add(key)
        evidence_list.append(e)
    assert not full & ~raw
    counts = q.index.customer_counts(full)
    total = q.orders
    possible = len(rows) - states.get('not_triggered', 0) - states.get('insufficient_evidence', 0)
    return dict(actual_rule_slots=len(rows), unique_evaluation_rules=len(selected_keys), accepted_rule_slots=accepted_slots,
                accepted_unique_rules=len(accepted_keys), accepted_slot_share=accepted_slots / len(rows),
                accepted_unique_rule_share=len(accepted_keys) / len(selected_keys), evaluable_slot_share=possible / len(rows),
                raw_covered_orders=raw.bit_count(), raw_coverage=raw.bit_count() / q.index.n,
                quality_covered_orders=full.bit_count(), quality_coverage=full.bit_count() / q.index.n,
                quality_customer_macro_coverage=float(np.mean(counts / total)),
                max_customer_joint_share_mean=float(np.nanmean([e['max_customer_joint_share'] for e in evidence_list])),
                confidence_change_pp_median=float(np.nanmedian([e['confidence_change_pp'] for e in evidence_list])),
                **{state: states.get(state, 0) for state in ['not_triggered', 'insufficient_evidence', 'effect_below_minimum',
                                                          'increment_below_minimum', 'uncertainty_unresolved', 'accepted']})


def comparisons(summary):
    output = []
    for (setting, config, budget, flow), data in summary.groupby(['setting', 'config', 'budget', 'flow'], sort=False):
        l, g = data.loc[data.method.eq('L')].iloc[0], data.loc[data.method.eq('G')].iloc[0]
        for control in ['S', 'A1', 'A2']:
            random = data.loc[data.control.eq(control)]
            for metric in ['quality_coverage', 'accepted_slot_share', 'quality_customer_macro_coverage']:
                vals = random[metric].to_numpy(); ge = int(np.sum(vals >= l[metric] - 1e-12))
                output.append(dict(setting=setting, config=config, budget=budget, flow=flow, control=control, metric=metric,
                                   G=g[metric], L=l[metric], L_minus_G=l[metric] - g[metric], random_n=len(vals),
                                   random_median=float(np.median(vals)), random_min=float(vals.min()), random_max=float(vals.max()),
                                   random_ge_L=ge, descriptive_upper_tail=(1 + ge) / (1 + len(vals))))
    return pd.DataFrame(output)


def main(root):
    started = time.time()
    ppath = root / 'configs/validation_quality.json'; phash = sha(ppath)
    protocol = json.loads(ppath.read_text(encoding='utf-8'))
    assert not protocol['selection_or_recommendation'] and not protocol['test_evaluation']
    original = json.loads((root / 'configs/validation.json').read_text(encoding='utf-8'))
    local = root / 'data/processed/local/D_validation'
    core, taxmap, true, mappings, rows, _ = load_inputs(local, root, original)
    val, _, audit = load_period(local, 'validation', taxmap, true)
    disc, _, _ = load_period(local, 'discovery', taxmap, true)
    definitions = {r.rule_id: (r.ant, r.con) for r in rows.drop_duplicates('rule_id').itertuples()}
    q = QualityEvidence(val, disc, mappings, definitions)
    print('Protocol locked:', phash, flush=True)
    out = root / 'results/tables/validation_quality'; out.mkdir(parents=True, exist_ok=True)
    source_unique = rows.drop_duplicates(['scope_id','rule_id'])
    for r in source_unique.itertuples(index=False):
        if r.method != 'G': q.set_scope(r.scope_id, mappings[r.control, r.method, r.seed], r.group_id)
    print('Computing customer-aware evidence for 50,161 native rule scopes and shared rules...', flush=True)
    records = {}; family_audits = []
    for family, system_rows in rows.groupby(['control', 'method', 'seed'], sort=False):
        identities = set()
        for r in system_rows.drop_duplicates(['scope_id','rule_id']).itertuples(index=False):
            identities.add(('GLOBAL' if r.method == 'G' else r.scope_id, r.rule_id))
            identities.add(('GLOBAL', r.rule_id))
        identities = sorted(identities)
        evidence = [q.get(scope, rid) for scope, rid in identities]
        ps = [e['p_combined'] for e in evidence]
        by, bh = adjust_fdr(ps, 'BY'), adjust_fdr(ps, 'BH')
        for (scope, rid), e, qby, qbh in zip(identities, evidence, by, bh):
            records[family, scope, rid] = dict(e, control=family[0], method=family[1], seed=family[2],
                                              q_BY=float(qby), q_BH=float(qbh), family_hypotheses=len(identities))
        family_audits.append(dict(control=family[0], method=family[1], seed=family[2], hypotheses=len(identities)))
    pd.DataFrame(family_audits).to_csv(out / 'family_audit.csv', index=False)
    detail = pd.DataFrame(records.values())
    detail['primary_status'] = [classify(r, protocol['primary']) for r in records.values()]
    detail.to_csv(local / 'quality_rule_evidence.csv.gz', index=False)
    detail.loc[detail.control.eq('GL')].to_csv(out / 'GL_rule_quality.csv', index=False)
    # Verify every existing native point estimate against the previously saved evidence.
    old = pd.read_csv(local / 'validation_rule_evidence.csv.gz', dtype={'rule_id': str, 'scope_id': str})
    old = old.drop_duplicates(['scope_id','rule_id'])
    checks = 0
    for r in old.itertuples(index=False):
        scope = 'GLOBAL' if r.method == 'G' else r.scope_id
        e = q.get(scope, r.rule_id)
        for col in ['n_baskets', 'antecedent_count','consequent_count','joint_count']:
            assert e[col] == getattr(r, col), (scope, r.rule_id, col)
        for col in ['confidence','lift']:
            assert np.isclose(e[col], getattr(r, col), equal_nan=True, atol=1e-12), (scope,r.rule_id,col)
        if e['length'] == 3:
            assert np.isclose(e['triple_increment_pp'], r.confidence_increment_pp, equal_nan=True, atol=1e-9)
        checks += 1
    print(f'Existing {checks:,} native rule-scope point estimates all match. Summarizing fixed lists...', flush=True)
    results = []
    groups = list(rows.groupby(['config','budget','control','method','seed'], sort=False))
    for variant in protocol['sensitivity']:
        setting = dict(protocol['primary'], **variant['overrides'])
        for (config,budget,control,method,seed), selected in groups:
            for flow in ['restricted','shared']:
                result = quality_summary(q, records, selected, method, flow, (control,method,seed), setting)
                result.update(setting=variant['id'],config=config,budget=budget,control=control,method=method,seed=seed,flow=flow,
                              n_baskets=val.n,n_customers=len(val.by_customer))
                results.append(result)
        print('Completed', variant['id'], flush=True)
    results = pd.DataFrame(results)
    primary = results.loc[results.setting.eq('primary')]
    primary.to_csv(out / 'system_quality.csv', index=False)
    primary.loc[primary.control.eq('GL')].to_csv(out / 'GL_quality_summary.csv', index=False)
    results.loc[results.control.eq('GL')].to_csv(out / 'GL_sensitivity.csv', index=False)
    # Full random sensitivity rows stay local; share all three random summaries instead.
    results.to_csv(local / 'quality_sensitivity_systems.csv.gz', index=False)
    compare = comparisons(results)
    compare.loc[compare.setting.eq('primary')].to_csv(out / 'random_quality_comparisons.csv', index=False)
    compare.to_csv(out / 'sensitivity_random_comparisons.csv', index=False)
    original_metrics = pd.read_csv(root/'results/tables/validation/system_metrics.csv', dtype={'seed':str}, keep_default_na=False)
    original_metrics['seed'] = original_metrics.seed.astype(str)
    merged = primary.merge(original_metrics,on=['config','budget','control','method','seed','flow'],validate='one_to_one')
    assert len(merged)==6660
    assert (merged.raw_covered_orders==merged.covered_orders).all()
    assert (primary.quality_covered_orders<=primary.raw_covered_orders).all()
    assert (primary.accepted_rule_slots<=primary.actual_rule_slots).all()
    assert np.isfinite(primary.quality_coverage).all()
    assert sha(ppath) == phash, 'Quality protocol changed during calculation'
    manifest = dict(status='passed', version=protocol['version'], recorded_date=protocol['recorded_date'],
                    protocol_sha256=phash,prior_results_seen=True, test_evaluated=False,configurations_selected=False,
                    native_rule_scope_checks=checks,unique_statistical_evidence=len(q.cache),family_count=len(family_audits),
                    primary_system_rows=len(primary), sensitivity_settings=len(protocol['sensitivity']),
                    customer_cluster_uncertainty='ratio delta method, one-sided t; BY within-system',
                    sample=audit,python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,
                    elapsed_seconds=round(time.time()-started,2),implementation_sha256=sha(Path(__file__)),
                    source_validation_manifest_sha256=sha(root/'results/tables/validation/run_manifest.json'),
                    input_hashes={str(p.relative_to(root)):sha(p) for p in [ppath,local/'validation_baskets.csv',local/'discovery_baskets.csv',local/'input_provenance.json']},
                    checks=['All 50,161 unique native scope-rule counts and point estimates match existing evidence',
                            'Every 6,660 primary raw system coverage matches original output',
                            'Quality coverage is subset of raw coverage; no replacement or refill',
                            'Shared rules re-evaluated globally; exact duplicate hypotheses collapsed',
                            'Protocol hash unchanged during calculation'],
                    output_hashes={str(p.relative_to(root)):sha(p) for p in out.glob('*.csv')})
    (out/'run_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('Quality comparison complete:',manifest['elapsed_seconds'],'seconds; no parameters selected.',flush=True)


if __name__=='__main__':main(Path(__file__).resolve().parents[3])
