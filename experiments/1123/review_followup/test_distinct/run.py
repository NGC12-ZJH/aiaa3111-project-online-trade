"""Reproduce poster Fig. 4 using the 1123 frozen inputs and B2 seeds."""

import argparse
from copy import copy
from importlib.util import module_from_spec, spec_from_file_location
from itertools import combinations
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits


def load_common(repo):
    sys.path.insert(0, str(repo / 'src'))
    spec = spec_from_file_location('fig4_common', repo / 'experiments/shared_full_store/run.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate(index, family, maps, original, review, phase):
    pair_masks = [index.mask(pair) for pair in family]
    totals = np.array([mask.bit_count() for mask in pair_masks])

    def mean_distance(mapping):
        groups = [index.scope(mapping, group) for group in original.GROUPS]
        n = np.array([mask.bit_count() for mask in groups])
        assert sum(n) == index.n and min(n) > 0
        counts = np.array([[(mask & group).bit_count() for mask in pair_masks] for group in groups])
        support = counts / n[:, None]
        rest = (totals - counts) / (index.n - n[:, None])
        return np.mean([review.bc(a, b) for a, b in zip(support, rest)])

    summary, details = [], []
    for variant in original.VARIANTS:
        real = mean_distance(maps['GL', variant, ''])
        draws = np.array([mean_distance(maps['B2', variant, str(seed)]) for seed in original.SEEDS])
        median = np.median(draws)
        reaches_real = draws >= real - 1e-12
        summary.append(dict(period=phase, variant=variant, orders=index.n, real=real,
                            B2_median=median, gap=real-median, B2_ge=int(reaches_real.sum())))
        for seed, distance, reaches in zip(original.SEEDS, draws, reaches_real):
            details.append(dict(period=phase, variant=variant, seed=seed,
                                B2_distance=distance, B2_ge_real=bool(reaches)))
    return summary, details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True, help='1123 directory next to repository')
    parser.add_argument('--snapshot-repo', type=Path, required=True, help='Git checkout containing the data snapshot')
    parser.add_argument('--out', type=Path, required=True, help='New output directory')
    args = parser.parse_args()
    project, snapshot_repo, out = (path.resolve() for path in (args.project, args.snapshot_repo, args.out))
    repo = project.parent / 'repository'
    common = load_common(repo)
    from online_trade.evaluation.validation import BasketIndex, load_period

    original = common.module('fig4_main1123', project / 'run.py')
    review = common.module('fig4_review1123', project / 'review_followup/run.py')
    # The prepared evaluation inputs and the Git snapshot can be in different checkouts.
    snapshot_profile = original.snapshot_profile
    original.snapshot_profile = lambda _repo, *parameters: snapshot_profile(snapshot_repo, *parameters)
    spec_file = project / 'results/freeze.json'
    validation_file = project / 'review_followup/results/distinct_summary.csv'
    spec = common.read_json(spec_file)
    out.mkdir(parents=True, exist_ok=False)
    with threadpool_limits(limits=2), TemporaryDirectory(dir=out) as scratch:
        inputs = common.Inputs(repo)
        maps = review.partitions(original, repo, common, inputs, Path(scratch))
        validation, _, _ = load_period(inputs.local, 'validation', inputs.taxonomy, inputs.profile)
        test_inputs = copy(inputs)
        test_inputs.repo = snapshot_repo
        test_period = common.test_period(test_inputs, spec)
        customers, baskets = zip(*((customer, basket) for customer, basket in
            zip(test_period.store.customers, test_period.store.baskets) if customer in inputs.profile))
        test = BasketIndex(customers, baskets)
        assert (validation.n, test.n) == (4862, 5730)
        family = [pair for pair in combinations(sorted(inputs.discovery.items), 2)
                  if inputs.discovery.mask(pair).bit_count() >= 20]
        assert len(family) == 2786
        summaries, all_draws = [], []
        for phase, index in [('validation', validation), ('test', test)]:
            summary, draws = evaluate(index, family, maps, original, review, phase)
            summaries.extend(summary)
            all_draws.extend(draws)

    summary = pd.DataFrame(summaries)
    saved = common.read_csv(validation_file).query(
        "period == 'validation' and control == 'B2' and metric == 'rest_bc' and length == 2").set_index('variant')
    actual = summary.query("period == 'validation'").set_index('variant').loc[saved.index]
    for column, existing in [('real', 'real'), ('B2_median', 'median'), ('gap', 'gap'), ('B2_ge', 'random_ge')]:
        np.testing.assert_allclose(actual[column], saved[existing], rtol=1e-12, atol=1e-12)

    draws = pd.DataFrame(all_draws)
    assert len(draws) == 600 and draws.groupby(['period', 'variant']).size().eq(100).all()
    common.csv(summary, out / 'fig4_values.csv')
    common.csv(draws, out / 'b2_draws.csv')
    common.write_json(out / 'audit.json', dict(
        baseline_validation_reproduced=True, discovery_pair_count=len(family),
        evaluation_orders=dict(validation=validation.n, test=test.n),
        b2_seeds_per_period_and_variant=100, snapshot_commit=spec['a_snapshot_commit'],
        source_baskets_sha256=spec['source_baskets_sha256'],
        main_freeze_sha256=common.sha(spec_file), published_validation_sha256=common.sha(validation_file),
        runner_sha256=common.sha(Path(__file__)),
        values_sha256=common.sha(out / 'fig4_values.csv'), b2_draws_sha256=common.sha(out / 'b2_draws.csv'),
    ))
    print(summary.to_string(index=False), flush=True)


if __name__ == '__main__':
    main()
