"""Record a reproducible freeze, then evaluate only the registered Test comparisons."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from online_trade.evaluation.validation import (
    BasketIndex, bootstrap_pairs, evaluate, load_inputs, load_period, random_comparisons, sha,
)
from online_trade.evaluation.quality import QualityEvidence, adjust_fdr, classify, comparisons, quality_summary
from online_trade.evaluation.hybrid import merge_lists, union_mask

LOCAL = ROOT / 'data/processed/local/D_validation'
FREEZE = ROOT / 'configs/test_frozen.json'
OUTPUT = ROOT / 'results/tables/test'
VALIDATION = ROOT / 'configs/validation.json'
QUALITY = ROOT / 'configs/validation_quality.json'
SNAPSHOT_BASKETS = 'data/processed/A_data_preparation/baskets.csv.gz'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    path.write_bytes((json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8'))


def rank_digest(ids):
    return hashlib.sha256('\n'.join(ids).encode('utf-8')).hexdigest()


def freeze():
    if FREEZE.exists() or OUTPUT.exists():
        raise SystemExit('A freeze or Test output already exists.')
    original = read_json(VALIDATION)
    core, _, _, _, rules, configs = load_inputs(LOCAL, ROOT, original)
    paths = [VALIDATION, QUALITY, Path(__file__).resolve(), LOCAL / 'discovery_baskets.csv',
             ROOT / 'configs/experiment.json', ROOT / 'data/taxonomy/item_taxonomy_v1.csv']
    paths += [core / 'configurations.csv', *sorted((core / 'inputs').glob('*.csv'))]
    paths += sorted((core / 'selected_rules').glob('*.csv.gz'))
    paths += [ROOT / f'src/online_trade/evaluation/{m}.py' for m in ['validation', 'quality', 'hybrid']]
    rules = rules.loc[rules.config.eq('P5')]
    quotas = []
    for (budget, control, method, seed, group), selected in rules.groupby(['budget','control','method','seed','group_id']):
        ids = selected.sort_values('rank_within_group').rule_id.tolist()
        quotas.append(dict(budget=int(budget), control=control, method=method, seed=seed, group=group,
                           slots=len(ids), ordered_rule_ids_sha256=rank_digest(ids)))
    ref = original['a_snapshot_commit']
    source = json.loads(git('show', f'{ref}:data/processed/A_data_preparation/run_manifest.json'))
    expected = next(i['sha256'] for i in source['output_metadata'] if i['filename'] == 'baskets.csv.gz')
    spec = dict(status='frozen', recorded_date='2026-11-21', selected_on='Validation only',
                selection_rationale='P5/100 maximized both G and L raw and quality_v1 order coverage in the compared Validation grid; A1 rankings were descriptive, not a selection criterion.',
                config='P5', discovery_thresholds=configs['P5'], primary_budget=100, budgets=[20,50,100],
                primary_flow='restricted', secondary_flow='shared', primary_random_control='A1',
                controls={'S': list(range(42,62)), 'A1': list(range(1000,1100)), 'A2': list(range(1000,1100))},
                test_window=read_json(ROOT/'configs/experiment.json')['test'], primary_metric='order_complete_cooccurrence_coverage',
                primary_contrasts=['L-G (paired customer interval)', 'L versus A1 (descriptive seed distribution)'],
                bootstrap=dict(repeats=2000,seed=3111,unit='active eligible Test customer',interval='pointwise paired percentile 95%'),
                eligibility='valid baskets of identified Profile customers, same baskets across methods; empty/single category baskets retained; Global fallback for all other baskets separately',
                quality=dict(primary=read_json(QUALITY)['primary'], family='Per system, union of P5 only across all three budgets and both flows; deduplicated scope/rule, BY. Validation compared five configs, so adjusted rates are not strictly comparable across periods.',
                             interpretation='Prespecified secondary retrospective Test measure, with definition developed after initial Validation; Test quality labels never adjust deployed lists.'),
                exploratory_hybrid='P3 frozen G50 + frozen L50 dedup directed rule_id, shared, matched G_K; raw coverage only; no random-hybrid comparator.',
                rule_policy='Frozen C lists, original ranks and group quotas; no refit, mining, retuning, replacement, or refill.',
                source_baskets_sha256=expected, a_snapshot_commit=ref, c_handoff_commit=original['c_handoff_commit'],
                input_hashes={p.relative_to(ROOT).as_posix():sha(p) for p in paths}, frozen_ranked_rule_lists=quotas)
    write_json(FREEZE, spec)


def test_index(spec, taxmap, clusters):
    raw = git('show', f"{spec['a_snapshot_commit']}:{SNAPSHOT_BASKETS}")
    assert hashlib.sha256(raw).hexdigest() == spec['source_baskets_sha256']
    frame = pd.read_csv(io.BytesIO(raw), compression='gzip', dtype=str, keep_default_na=False)
    data = frame.loc[frame.split.eq('test')].copy()
    assert data.basket_id.is_unique
    dates = pd.to_datetime(data.invoice_date,format='mixed')
    window = spec['test_window']
    eligible_dates = pd.to_datetime(frame.invoice_date,format='mixed').between(pd.Timestamp(window['start']), pd.Timestamp(window['end_exclusive']), inclusive='left')
    assert dates.between(pd.Timestamp(window['start']), pd.Timestamp(window['end_exclusive']), inclusive='left').all()
    assert eligible_dates.equals(frame.split.eq('test'))
    eligible = data.is_eligible_for_main_comparison.eq('1')
    assert eligible.equals(data.customer_id.isin(clusters))
    baskets = [{taxmap[item] for item in json.loads(s) if taxmap[item] != 'other'} for s in data['items']]
    index = BasketIndex(data.loc[eligible].customer_id.tolist(), [b for b,k in zip(baskets,eligible) if k])
    fallback = BasketIndex(data.loc[~eligible].customer_id.tolist(), [b for b,k in zip(baskets,eligible) if not k])
    return index, fallback, dict(period='test', all_valid_baskets=len(data), eligible_baskets=index.n,
                                eligible_customers=len(index.by_customer), eligible_share=index.n/len(data),
                                anonymous_baskets=int(data.customer_id.eq('').sum()), non_profile_baskets=fallback.n,
                                empty_l2_eligible_baskets=sum(not b for b in index.baskets),
                                single_l2_eligible_baskets=sum(len(b)==1 for b in index.baskets))


def quality_metrics(index, disc, mappings, rows, gates):
    definitions = {r.rule_id:(r.ant,r.con) for r in rows.drop_duplicates('rule_id').itertuples()}
    engine = QualityEvidence(index, disc, mappings, definitions)
    result, rule_details = [], []
    for family, family_rows in rows.groupby(['control','method','seed'],sort=False):
        control, method, seed = family
        identities = set()
        for row in family_rows.drop_duplicates(['scope_id','rule_id']).itertuples():
            scope = 'GLOBAL' if method == 'G' else row.scope_id
            if method != 'G':
                engine.set_scope(scope,mappings[family],row.group_id)
            identities.update([(scope,row.rule_id),('GLOBAL',row.rule_id)])
        identities = sorted(identities)
        evidence = [engine.get(scope,rid) for scope,rid in identities]
        adjusted = adjust_fdr([e['p_combined'] for e in evidence],'BY')
        records = {}
        for (scope,rid), detail, q in zip(identities,evidence,adjusted):
            record = dict(detail, q_BY=float(q), control=control,method=method,seed=seed,family_size=len(identities))
            records[family,scope,rid] = record
            if control == 'GL':
                rule_details.append(dict(record,status=classify(record,gates)))
        for budget, selected in family_rows.groupby('budget'):
            for flow in ['restricted','shared']:
                summary = quality_summary(engine,records,selected,method,flow,family,gates)
                result.append(dict(summary, setting='primary', config='P5',budget=budget,flow=flow,control=control,method=method,seed=seed))
    return pd.DataFrame(result), pd.DataFrame(rule_details)


def weights(index, spec):
    n = len(index.by_customer)
    return np.random.default_rng(spec['seed']).multinomial(n, np.full(n,1/n), size=spec['repeats']).astype(float)


def intervals(index, masks, spec):
    out = []
    draws = weights(index,spec['bootstrap'])
    for budget in spec['budgets']:
        for flow in ['restricted','shared']:
            result = bootstrap_pairs(index,masks['P5',budget,'G',flow],masks['P5',budget,'L',flow],draws)
            for (contrast,metric),(point,low,high) in result.items():
                out.append(dict(budget=budget,flow=flow,contrast=contrast,metric=metric,estimate=point,low95=low,high95=high))
    return pd.DataFrame(out)


def hybrid(index, rules, spec):
    p3 = rules.loc[rules.config.eq('P3') & rules.control.eq('GL')]
    def ids(method,budget):
        return p3.loc[p3.method.eq(method)&p3.budget.eq(budget)].sort_values(['group_id','rank_within_group']).rule_id.tolist()
    merged, matched = merge_lists(ids('G',50),ids('L',50),ids('G',100))
    definitions = {r.rule_id:(r.ant,r.con) for r in p3.drop_duplicates('rule_id').itertuples()}
    left, right = union_mask(index,definitions,merged), union_mask(index,definitions,matched)
    point,low,high = bootstrap_pairs(index,right,left,weights(index,spec['bootstrap']))['L_minus_G','order']
    return pd.DataFrame([dict(config='P3',K=len(merged),hybrid_coverage=left.bit_count()/index.n,
                      global_K_coverage=right.bit_count()/index.n,difference=point,low95=low,high95=high,
                      hybrid_only=(left&~right).bit_count(),global_only=(right&~left).bit_count())])


def run():
    if OUTPUT.exists():
        raise SystemExit('Existing formal Test output found.')
    spec = read_json(FREEZE)
    assert git('show','HEAD:configs/test_frozen.json') == FREEZE.read_bytes()
    assert not git('status','--porcelain'), 'Start from the clean freeze commit.'
    for path,digest in spec['input_hashes'].items():
        assert sha(ROOT/path)==digest,path
    _, taxmap, clusters, mappings, all_rules, configs = load_inputs(LOCAL,ROOT,read_json(VALIDATION))
    rules = all_rules.loc[all_rules.config.eq(spec['config'])]
    keys = ['budget','control','method','seed','group_id']
    ranklists = {key: r.sort_values('rank_within_group').rule_id.tolist() for key,r in rules.groupby(keys)}
    assert len(ranklists)==len(spec['frozen_ranked_rule_lists'])
    for r in spec['frozen_ranked_rule_lists']:
        ids = ranklists[r['budget'],r['control'],r['method'],r['seed'],r['group']]
        assert len(ids)==r['slots'] and rank_digest(ids)==r['ordered_rule_ids_sha256']
    for control,seeds in spec['controls'].items():
        assert sorted(set(map(int,rules.loc[rules.control.eq(control),'seed']))) == seeds
    assert configs[spec['config']] == spec['discovery_thresholds']
    index, fallback, audit = test_index(spec,taxmap,clusters)
    disc,_,_ = load_period(LOCAL,'discovery',taxmap,clusters)
    print('Frozen Test sample:',audit,flush=True)
    with TemporaryDirectory(prefix='.test-',dir=OUTPUT.parent) as temporary:
        folder = Path(temporary)/'tables'
        folder.mkdir()
        raw,masks,_ = evaluate(index,mappings,rules,configs,'test')
        assert len(raw)==222*3*2
        print('Raw coverage complete. Evaluating secondary quality measures.',flush=True)
        quality, detail = quality_metrics(index,disc,mappings,rules,spec['quality']['primary'])
        checks = quality.merge(raw,on=['config','budget','flow','control','method','seed'],validate='one_to_one')
        assert len(checks)==len(raw) and (checks.raw_covered_orders==checks.covered_orders).all()
        assert (checks.quality_covered_orders<=checks.covered_orders).all()
        fallback_rows = []
        definitions = {r.rule_id:(r.ant,r.con) for r in rules.loc[rules.method.eq('G')].drop_duplicates('rule_id').itertuples()}
        for budget, group in rules.loc[rules.method.eq('G')].groupby('budget'):
            masks_by_scope = {'all':fallback.all, 'anonymous':fallback.by_customer.get('',0)}
            masks_by_scope['identified_non_profile'] = fallback.all ^ masks_by_scope['anonymous']
            hit = union_mask(fallback,definitions,group.rule_id)
            for name,scope in masks_by_scope.items():
                count = scope.bit_count()
                fallback_rows.append(dict(budget=budget,scope=name,orders=count,hits=(hit&scope).bit_count(),coverage=(hit&scope).bit_count()/count if count else np.nan))
        tables = dict(system_metrics=raw, random_comparisons=random_comparisons(raw), paired_customer_intervals=intervals(index,masks,spec),
                      system_quality=quality, random_quality_comparisons=comparisons(quality), GL_rule_quality=detail,
                      P3_hybrid_exploratory=hybrid(index,all_rules,spec), non_profile_global_fallback=pd.DataFrame(fallback_rows),sample_audit=pd.DataFrame([audit]))
        for name,table in tables.items():
            table.to_csv(folder/f'{name}.csv',index=False,lineterminator='\n')
        write_json(folder/'run_manifest.json',dict(status='passed', freeze_commit=git('rev-parse','HEAD').decode().strip(),
                   freeze_sha256=sha(FREEZE),test_evaluated=True,sample=audit,systems=len(raw),
                   output_hashes={p.name:sha(p) for p in sorted(folder.glob('*.csv'))}))
        folder.rename(OUTPUT)
    print('Formal Test finished:',OUTPUT,flush=True)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['freeze','run'])
    args = parser.parse_args()
    (freeze if args.action=='freeze' else run)()
