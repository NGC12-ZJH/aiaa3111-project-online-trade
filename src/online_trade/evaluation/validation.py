"""Validate C's frozen category rules, without fitting, selection or Test access."""
from functools import reduce
from operator import and_, or_
from pathlib import Path
import csv
import hashlib
import json
import platform
import subprocess
import sys
import time

import numpy as np
import pandas as pd


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rate(a, b):
    return a / b if b else float('nan')


class BasketIndex:
    """An integer bit per order; exact intersections preserve order denominators."""
    def __init__(self, customers, baskets):
        self.customers = list(customers)
        self.baskets = list(map(frozenset, baskets))
        self.n = len(baskets)
        self.all = (1 << self.n) - 1
        self.items = {}
        self.by_customer = {}
        for i, (customer, basket) in enumerate(zip(customers, baskets)):
            bit = 1 << i
            self.by_customer[customer] = self.by_customer.get(customer, 0) | bit
            for item in basket:
                self.items[item] = self.items.get(item, 0) | bit
        self.cache = {}

    def mask(self, items):
        key = tuple(sorted(items))
        if key not in self.cache:
            self.cache[key] = reduce(and_, (self.items.get(x, 0) for x in key), self.all)
        return self.cache[key]

    def scope(self, mapping, group):
        return reduce(or_, (mask for customer, mask in self.by_customer.items() if mapping[customer] == group), 0)

    def customer_counts(self, mask):
        return np.array([(mask & bits).bit_count() for bits in self.by_customer.values()], dtype=float)


def rule_evidence(index, scope, antecedent, consequent, thresholds):
    n = scope.bit_count()
    am, cm = index.mask(antecedent), index.mask(consequent)
    a, c, j = (am & scope).bit_count(), (cm & scope).bit_count(), (am & cm & scope).bit_count()
    confidence = rate(j, a)
    lift = rate(confidence, rate(c, n)) if a and c and n else float('nan')
    increment = float('nan')
    if len(antecedent) == 2:
        single = []
        for item in antecedent:
            sm = index.mask([item]) & scope
            single.append(rate((sm & cm).bit_count(), sm.bit_count()))
        if all(np.isfinite(single)):
            increment = 100 * (confidence - max(single))
    passes = (n > 0 and a >= thresholds['min_antecedent_count'] and j >= thresholds['min_joint_count']
              and rate(j, n) + 1e-12 >= thresholds['support'] and confidence + 1e-12 >= thresholds['confidence']
              and lift + 1e-12 >= thresholds['lift'])
    threshold = thresholds['triple_increment_pp']
    if len(antecedent) == 2 and pd.notna(threshold):
        passes = passes and np.isfinite(increment) and increment + 1e-10 >= threshold
    fate = ('not_triggered' if not a else 'triggered_no_joint' if not j else
            'meets_frozen_threshold' if passes else 'observed_below_threshold')
    return dict(n_baskets=n, antecedent_count=a, consequent_count=c, joint_count=j, support=rate(j, n),
                confidence=confidence, lift=lift, confidence_increment_pp=increment, fate=fate)


def bootstrap_pairs(index, gmask, lmask, weights):
    totals = index.customer_counts(index.all)
    g, l = index.customer_counts(gmask), index.customer_counts(lmask)
    result = {}
    for name, values in [('G', g), ('L', l), ('L_minus_G', l - g)]:
        for metric in ['order', 'customer_macro']:
            samples = (weights @ values) / (weights @ totals) if metric == 'order' else (weights @ (values / totals)) / len(totals)
            estimate = values.sum() / totals.sum() if metric == 'order' else np.mean(values / totals)
            lo, hi = np.quantile(samples, [0.025, 0.975])
            result[name, metric] = (float(estimate), float(lo), float(hi))
    return result


def load_inputs(local, root, protocol):
    core = local / 'core'
    taxonomy = pd.read_csv(core / 'inputs/item_taxonomy_v1.csv', dtype=str, keep_default_na=False)
    assert len(taxonomy) == 4724 and taxonomy.stock_code.is_unique
    assert set(taxonomy.taxonomy_version) == {'taxonomy_v1'}
    assert sha(core / 'inputs/item_taxonomy_v1.csv') == sha(root / 'data/taxonomy/item_taxonomy_v1.csv')
    taxmap = dict(zip(taxonomy.stock_code, taxonomy.l2_id))
    clusters = pd.read_csv(core / 'inputs/customer_clusters.csv', dtype=str, keep_default_na=False)
    assert len(clusters) == 2684 and clusters.customer_id.is_unique
    true = dict(zip(clusters.customer_id, clusters.cluster_id))
    mappings = {('GL', 'G', ''): None, ('GL', 'L', ''): true}
    for control, name, seeds in [('S', 'random_groups.csv', range(42, 62)),
                                  ('A1', 'random_groups_A1_profile_frequency.csv', range(1000, 1100)),
                                  ('A2', 'random_groups_A2_discovery_baskets.csv', range(1000, 1100))]:
        data = pd.read_csv(core / 'inputs' / name, dtype=str, keep_default_na=False)
        assert set(data.seed) == set(map(str, seeds))
        for seed, group in data.groupby('seed', sort=False):
            assert group.customer_id.is_unique and set(group.customer_id) == set(true)
            assert group.random_group_id.value_counts().sort_index().tolist() == [700, 1263, 721]
            mappings[control, 'R', seed] = dict(zip(group.customer_id, group.random_group_id))
    rules = pd.concat([pd.read_csv(p, dtype=str, keep_default_na=False) for p in sorted((core / 'selected_rules').glob('*.csv.gz'))], ignore_index=True)
    assert len(rules) == 188700
    assert set(rules.config) == set(protocol['configs'])
    rules['budget'] = rules.budget.astype(int)
    for name in ['joint_count', 'antecedent_count', 'consequent_count', 'allocated_budget', 'rank_within_group']:
        rules[name] = rules[name].astype(int)
    rules['ant'] = rules.antecedent.map(lambda x: tuple(json.loads(x)))
    rules['con'] = rules.consequent.map(lambda x: tuple(json.loads(x)))
    assert all(len(a) in (1, 2) and len(c) == 1 and not set(a) & set(c) for a, c in zip(rules.ant, rules.con))
    assert not rules.duplicated(['config', 'budget', 'scope_id', 'rule_id']).any()
    assert rules.groupby('rule_id')[['antecedent', 'consequent']].nunique().to_numpy().max() == 1
    configs = pd.read_csv(core / 'configurations.csv').set_index('config').to_dict('index')
    return core, taxmap, true, mappings, rules, configs


def load_period(local, period, taxmap, true):
    data = pd.read_csv(local / f'{period}_baskets.csv', dtype=str, keep_default_na=False)
    assert set(data.split) == {period} and data.basket_id.is_unique
    lo, hi = {'discovery': ('2010-06-01', '2010-12-01'), 'validation': ('2010-12-01', '2011-06-01')}[period]
    assert ((data.invoice_date >= lo) & (data.invoice_date < hi)).all()
    categories = []
    unknown = set()
    for items in data['items']:
        raw = json.loads(items)
        unknown.update(x for x in raw if x not in taxmap)
        categories.append({taxmap[x] for x in raw if x in taxmap and taxmap[x] != 'other'})
    assert not unknown, f'Unmapped product codes: {unknown}'
    eligible = data.is_eligible_for_main_comparison.eq('1')
    assert eligible.equals(data.customer_id.isin(true))
    primary = data.loc[eligible]
    assert len(primary) == {'discovery': 7521, 'validation': 4862}[period]
    idx = BasketIndex(primary.customer_id.tolist(), [b for b, keep in zip(categories, eligible) if keep])
    fallback = BasketIndex(data.loc[~eligible].customer_id.tolist(), [b for b, keep in zip(categories, eligible) if not keep])
    audit = {'period': period, 'all_valid_baskets': len(data), 'eligible_baskets': idx.n,
             'eligible_customers': len(idx.by_customer), 'eligible_order_share': idx.n / len(data),
             'non_profile_baskets': fallback.n, 'anonymous_baskets': int(data.customer_id.eq('').sum()),
             'identified_non_profile_baskets': int((~eligible & data.customer_id.ne('')).sum()),
             'empty_l2_eligible_baskets': sum(not b for b in idx.baskets),
             'single_l2_eligible_baskets': sum(len(b) == 1 for b in idx.baskets), 'unmapped_codes': 0}
    return idx, fallback, audit


def evaluate(index, mappings, rules, configs, period, evidence_path=None):
    scopes, scope_info = {}, {}
    for (control, method, seed, group), rows in rules.groupby(['control', 'method', 'seed', 'group_id'], sort=False):
        scope_id = rows.scope_id.iloc[0]
        mapping = mappings[control, method, seed]
        scopes[scope_id] = index.all if mapping is None else index.scope(mapping, group)
        scope_info[scope_id] = (control, method, seed, group)
    systems, masks, evidence_cache = [], {}, {}
    sink = None
    if evidence_path:
        import gzip
        sink = gzip.open(evidence_path, 'wt', encoding='utf-8', newline='')
        fields = ['period', 'config', 'scope_id', 'control', 'method', 'seed', 'group_id', 'rule_id', 'antecedent', 'consequent',
                  'n_baskets', 'antecedent_count', 'consequent_count', 'joint_count', 'support', 'confidence', 'lift', 'confidence_increment_pp', 'fate']
        writer = csv.DictWriter(sink, fields, lineterminator='\n')
        writer.writeheader()
    system_keys = ['config', 'budget', 'control', 'method', 'seed']
    try:
        for key, rows in rules.groupby(system_keys, sort=False):
            config, budget, control, method, seed = key
            assert len(rows) == budget
            assert rows.groupby('group_id').allocated_budget.nunique().max() == 1
            assert rows.groupby('group_id').size().equals(rows.groupby('group_id').allocated_budget.first())
            full, triggered, shared_full, shared_triggered = 0, 0, 0, 0
            fates = {x: 0 for x in ['not_triggered', 'triggered_no_joint', 'observed_below_threshold', 'meets_frozen_threshold']}
            confidences, lifts = [], []
            for row in rows.itertuples(index=False):
                scope = scopes[row.scope_id]
                am, cm = index.mask(row.ant), index.mask(row.con)
                full |= am & cm & scope
                triggered |= am & scope
                shared_full |= am & cm
                shared_triggered |= am
                cache_key = config, row.scope_id, row.rule_id
                if cache_key not in evidence_cache:
                    evidence = rule_evidence(index, scope, row.ant, row.con, configs[config])
                    evidence_cache[cache_key] = evidence
                    if sink:
                        writer.writerow(dict(period=period, config=config, scope_id=row.scope_id, control=control,
                                              method=method, seed=seed, group_id=row.group_id, rule_id=row.rule_id,
                                              antecedent=row.antecedent, consequent=row.consequent, **evidence))
                evidence = evidence_cache[cache_key]
                if period == 'discovery':
                    for field in ['joint_count', 'antecedent_count', 'consequent_count']:
                        assert evidence[field] == getattr(row, field), (cache_key, field)
                fates[evidence['fate']] += 1
                if np.isfinite(evidence['confidence']): confidences.append(evidence['confidence'])
                if np.isfinite(evidence['lift']): lifts.append(evidence['lift'])
            assert not full & ~triggered and not full & ~shared_full
            availability = []
            mapping = mappings[control, method, seed]
            quotas = rows.groupby('group_id').size().to_dict()
            for customer in index.by_customer:
                availability.append(budget if method == 'G' else quotas[mapping[customer]])
            for flow, hit, trigger in [('restricted', full, triggered), ('shared', shared_full, shared_triggered)]:
                customer_totals = index.customer_counts(index.all)
                customer_hits = index.customer_counts(hit)
                metrics = dict(zip(system_keys, key))
                metrics.update(period=period, flow=flow, n_baskets=index.n, n_customers=len(customer_totals), actual_rule_count=len(rows),
                               unique_rules=rows.rule_id.nunique(), unique_combinations=rows.combination_id.nunique(),
                               covered_orders=hit.bit_count(), coverage=rate(hit.bit_count(), index.n),
                               triggered_orders=trigger.bit_count(), antecedent_coverage=rate(trigger.bit_count(), index.n),
                               customer_macro_coverage=float(np.mean(customer_hits / customer_totals)),
                               customer_any_coverage=float(np.mean(customer_hits > 0)),
                               mean_available_rule_slots=float(np.mean(availability)) if flow == 'restricted' else budget,
                               min_available_rule_slots=min(availability) if flow == 'restricted' else budget,
                               max_available_rule_slots=max(availability) if flow == 'restricted' else budget,
                               native_scope_mean_confidence=float(np.mean(confidences)) if confidences else float('nan'),
                               native_scope_mean_lift=float(np.mean(lifts)) if lifts else float('nan'),
                               native_scope_threshold_retention=fates['meets_frozen_threshold'] / len(rows), **fates)
                systems.append(metrics)
                if control == 'GL': masks[config, budget, method, flow] = hit
    finally:
        if sink: sink.close()
    return pd.DataFrame(systems), masks, len(evidence_cache)


def random_comparisons(metrics):
    records = []
    for (config, budget, flow), data in metrics.groupby(['config', 'budget', 'flow'], sort=False):
        l = data.loc[data.method.eq('L')].iloc[0]
        g = data.loc[data.method.eq('G')].iloc[0]
        for control in ['S', 'A1', 'A2']:
            random = data.loc[data.control.eq(control)]
            assert len(random) == (20 if control == 'S' else 100)
            for metric in ['coverage', 'customer_macro_coverage', 'antecedent_coverage']:
                vals = random[metric].to_numpy()
                ge = int(np.sum(vals >= l[metric] - 1e-12))
                records.append(dict(config=config, budget=budget, flow=flow, control=control, metric=metric,
                                    G=g[metric], L=l[metric], L_minus_G=l[metric] - g[metric], random_n=len(vals),
                                    random_median=float(np.median(vals)), random_min=float(vals.min()), random_max=float(vals.max()),
                                    random_ge_L=ge, empirical_upper_tail=(1 + ge) / (1 + len(vals))))
    return pd.DataFrame(records)


def main(root):
    started = time.time()
    local = root / 'data/processed/local/D_validation'
    out = root / 'results/tables/validation'
    out.mkdir(parents=True, exist_ok=True)
    protocol_path = root / 'configs/validation.json'
    protocol = json.loads(protocol_path.read_text(encoding='utf-8'))
    assert protocol['selection_or_recommendation'] is False and protocol['test_evaluation'] is False
    core, taxmap, true, mappings, rules, configs = load_inputs(local, root, protocol)
    discovery, _, discovery_audit = load_period(local, 'discovery', taxmap, true)
    print('Replaying all 6660 Discovery system metrics...', flush=True)
    replay, _, _ = evaluate(discovery, mappings, rules, configs, 'discovery')
    expected = pd.read_csv(core / 'system_metrics.csv', keep_default_na=False)
    keys = ['config', 'budget', 'control', 'method', 'seed', 'flow']
    expected['seed'] = expected.seed.astype(str)
    merged = replay.merge(expected, on=keys, suffixes=('_new', '_C'), validate='one_to_one')
    assert len(merged) == 6660
    for metric in ['covered_orders', 'triggered_orders', 'unique_rules', 'unique_combinations']:
        assert (merged[f'{metric}_new'] == merged[f'{metric}_C']).all(), metric
    assert (merged.actual_rule_count == merged.actual).all()
    print('Discovery replay passed, including every selected rule count.', flush=True)
    replay.to_csv(out / 'discovery_replay.csv', index=False)
    validation, fallback, audit = load_period(local, 'validation', taxmap, true)
    print(f"Evaluating Validation: {validation.n} eligible baskets, {len(validation.by_customer)} customers...", flush=True)
    # Detailed rule evidence stays local: no need to commit a large redundant table.
    metrics, masks, evidence_n = evaluate(validation, mappings, rules, configs, 'validation', local / 'validation_rule_evidence.csv.gz')
    assert len(metrics) == 6660
    metrics.to_csv(out / 'system_metrics.csv', index=False)
    comparisons = random_comparisons(metrics)
    comparisons.to_csv(out / 'random_comparisons.csv', index=False)
    rng = np.random.default_rng(protocol['bootstrap']['seed'])
    n_customers = len(validation.by_customer)
    weights = rng.multinomial(n_customers, np.full(n_customers, 1 / n_customers), size=protocol['bootstrap']['repeats']).astype(float)
    intervals = []
    for config in protocol['configs']:
        for budget in protocol['budgets']:
            for flow in ['restricted', 'shared']:
                result = bootstrap_pairs(validation, masks[config, budget, 'G', flow], masks[config, budget, 'L', flow], weights)
                for (contrast, metric), (estimate, low, high) in result.items():
                    intervals.append(dict(config=config, budget=budget, flow=flow, contrast=contrast, metric=metric,
                                          estimate=estimate, ci95_low=low, ci95_high=high, bootstrap_repeats=len(weights)))
    pd.DataFrame(intervals).to_csv(out / 'paired_customer_bootstrap.csv', index=False)
    fallback_rows = []
    for (config, budget), group in rules.loc[rules.method.eq('G')].groupby(['config', 'budget'], sort=False):
        hit = reduce(or_, (fallback.mask(a) & fallback.mask(c) for a, c in zip(group.ant, group.con)), 0)
        fallback_rows.append(dict(config=config, budget=budget, n_baskets=fallback.n,
                                  n_identified_customers=sum(bool(c) for c in fallback.by_customer),
                                  anonymous_baskets=sum(not c for c in fallback.customers),
                                  covered_orders=hit.bit_count(), coverage=rate(hit.bit_count(), fallback.n)))
    pd.DataFrame(fallback_rows).to_csv(out / 'non_profile_global_fallback.csv', index=False)
    pd.DataFrame([discovery_audit, audit]).to_csv(out / 'sample_audit.csv', index=False)
    base = metrics.loc[metrics.control.eq('GL')].copy()
    base.to_csv(out / 'GL_summary.csv', index=False)
    # Save customer/order indicators only in the ignored local output directory.
    detail = pd.DataFrame({'customer_id': validation.customers})
    for (config, budget, method, flow), mask in masks.items():
        detail[f'{config}_{budget}_{method}_{flow}'] = [(mask >> i) & 1 for i in range(validation.n)]
    detail.to_csv(local / 'GL_order_indicators.csv.gz', index=False)
    inputs = [protocol_path, local / 'input_provenance.json', local / 'discovery_baskets.csv', local / 'validation_baskets.csv']
    inputs += sorted((core / 'selected_rules').glob('*.csv.gz')) + sorted((core / 'inputs').glob('*'))
    manifest = dict(status='passed', protocol_sha256=sha(protocol_path), test_evaluated=False, configurations_selected=False,
                    c_handoff_commit=protocol['c_handoff_commit'], a_snapshot_commit=protocol['a_snapshot_commit'],
                    sample=audit, discovery_replayed_systems=len(replay), validation_systems=len(metrics),
                    validation_rule_evidence_rows=evidence_n, bootstrap_repeats=len(weights),
                    python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__,
                    elapsed_seconds=round(time.time() - started, 2),
                    input_hashes={str(p.relative_to(root)): sha(p) for p in inputs},
                    implementation_sha256=sha(Path(__file__)),
                    git_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
                    checks=['All Discovery system integer counts match C', 'All selected Discovery rule evidence counts match C',
                            'Frozen quota sums equal system budget', 'Shared coverage contains restricted coverage',
                            'Joint hits are subset of antecedent hits', 'Empty and single-category baskets retained',
                            'All random seeds retain 2684 customers with groups 700/1263/721', 'No Test inputs exported or evaluated'],
                    output_hashes={str(p.relative_to(root)): sha(p) for p in out.glob('*.csv')})
    (out / 'run_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Validation finished in {manifest["elapsed_seconds"]}s. No configuration selected; no Test evaluation.', flush=True)


if __name__ == '__main__':
    main(Path(__file__).resolve().parents[3])
