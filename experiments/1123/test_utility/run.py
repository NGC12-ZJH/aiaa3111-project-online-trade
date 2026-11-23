"""Freeze and evaluate three isolated recommendation choices on 1123 Test."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
from itertools import groupby
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
HISTORY_CUTOFF = "2010-12-01"
WEIGHTS = (.25, .25)
SOURCE = "data/processed/A_data_preparation"
MASK_PREFIX_DISCOVERY = "retail1122-v1"
COMPARISONS = (
    ("l1", "G120_global", "G120_l1"),
    ("pool", "fusion_G100", "fusion_G200"),
    ("ranking_diagnostic", "G100_l1", "fusion_G100"),
    ("sku_asof", "sku_pop", "sku_asof"),
    ("sku_frozen", "sku_pop", "sku_frozen"),
    ("sku_update_diagnostic", "sku_frozen", "sku_asof"),
)


def module(name, path):
    spec = spec_from_file_location(name, path)
    result = module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def github_object(repo, ref, path):
    return subprocess.check_output(["git", "show", f"{ref}:{SOURCE}/{path}"], cwd=repo)


def context(visible, parents):
    counts = Counter(parents[c] for c in visible)
    return min(counts, key=lambda c: (-counts[c], c)) if counts else "UNKNOWN"


def hide(basket_id, categories):
    ordered = sorted(categories)
    digest = sha256(f"{MASK_PREFIX_DISCOVERY}|{basket_id}".encode()).digest()
    hidden = ordered[int.from_bytes(digest[:8], "big") % len(ordered)]
    return frozenset(categories) - {hidden}, hidden


class Inputs:
    def __init__(self, project, common, repo):
        self.project, self.common, self.repo = project, common, repo
        self.old = project.parent / "1122"
        self.shared = common.Inputs(repo)
        self.frozen_1123 = project / "results/freeze.json"
        self.original = common.read_json(self.frozen_1123)
        assert (self.original["selection"]["config"], self.original["selection"]["budget"]) == ("P5", 120)
        self.baseline_list = project / "results/frozen_rule_lists.csv"
        self.labels_path = repo / "data/taxonomy/item_taxonomy_v1.csv"
        tax = pd.read_csv(self.labels_path, usecols=["l1_id", "l2_id"], dtype=str).drop_duplicates()
        tax = tax.loc[tax.l2_id.ne("other")]
        assert tax.l2_id.is_unique
        self.parents = dict(zip(tax.l2_id, tax.l1_id))
        self.disc_orders = self.shared.local / "discovery_baskets.csv"

    def hashes(self):
        paths = [self.frozen_1123, self.baseline_list, self.disc_orders, self.labels_path,
                 self.project / "results/test/recommendation.csv",
                 self.repo / "experiments/shared_full_store/run.py",
                 self.repo / "experiments/validation_four_metrics/run.py",
                 self.repo / "experiments/validation_hybrid_residual/run.py",
                 self.repo / "experiments/discovery_residual_refill/run.py",
                 self.repo / "src/online_trade/evaluation/validation.py",
                 self.old / "retail_rules.py", self.old / "followup_fusion_time/run.py",
                 self.old / "followup_fusion_time/results/fusion_late.csv"]
        return {p.relative_to(self.project.parent).as_posix(): self.common.sha(p) for p in paths}


def freeze(inputs, out):
    common = inputs.common
    assert not (out / "freeze.json").exists()
    assert common.sha(inputs.baseline_list) == inputs.original["artifact_hashes"]["frozen_rule_lists.csv"]
    baseline = common.read_csv(inputs.baseline_list).query("control == 'GL' and method == 'G'").copy()
    assert sorted(baseline.position) == list(range(1, 121))
    common.csv(baseline, out / "G120_frozen.csv")
    disc_rows = pd.read_csv(inputs.disc_orders, dtype=str, keep_default_na=False)
    select = disc_rows.loc[disc_rows.is_eligible_for_main_comparison.eq("1")]
    disc = inputs.shared.discovery
    assert len(select) == disc.n == 7521 and select.customer_id.tolist() == disc.customers
    train = pd.DataFrame({"customer_id": disc.customers, "basket": disc.baskets})
    old = module("retail_rules", inputs.old / "retail_rules.py")
    book = old.Book(train, old.runtime(inputs.repo))
    assert len(book.global_ranks) >= 200
    rows = []
    for i, rank in enumerate(book.global_ranks[:200], 1):
        rule = book.rules[rank.key]
        rows.append((i, rule.identifier, " + ".join(rule.antecedent), rule.consequent,
                     rank.joint, rank.total, rank.confidence, rank.lift))
    common.csv(pd.DataFrame(rows, columns=["position", "rule_id", "antecedent", "consequent",
        "joint", "antecedent_orders", "disc_conf", "disc_lift"]), out / "fusion_G200_frozen.csv")
    histogram = defaultdict(Counter)
    for bid, basket in zip(select.basket_id, disc.baskets):
        if len(basket) >= 2:
            visible, hidden = hide(bid, basket)
            histogram[context(visible, inputs.parents)][hidden] += 1
    popular = {c: n.bit_count() for c, n in disc.items.items()}
    common.csv(pd.DataFrame([(key, cat, hist.get(cat, 0), popular[cat])
                            for key, hist in sorted(histogram.items()) for cat in sorted(popular)],
                            columns=["l1", "l2", "masked_targets", "global_orders"]), out / "L1_discovery_counts.csv")
    ref = inputs.original["a_snapshot_commit"]
    import json
    manifest = json.loads(github_object(inputs.repo, ref, "run_manifest.json"))
    source_hash = {r["filename"]: r["sha256"] for r in manifest["output_metadata"]}
    known = pd.read_csv(inputs.old / "followup_fusion_time/results/fusion_late.csv")
    method = known.loc[known.arm.eq("G200") & known.aggregation_selected_on_early].iloc[0]
    assert method.aggregation == "discounted" and (method.w_G, method.w_extra, method.w_pop) == (1., *WEIGHTS)
    common.write_json(out / "freeze.json", {
        "recorded_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "evidence": "Historical Test supplementary evaluation",
        "a_snapshot_commit": ref, "source_baskets_sha256": source_hash["baskets.csv.gz"],
        "orders_sha256": source_hash["orders.csv.gz"],
        "transaction_sha256": source_hash["clean_transactions.csv.gz"],
        "test_window": inputs.original["test_window"], "fusion_weights": [1., *WEIGHTS],
        "proto_sha256": common.sha(HERE / "README.md"), "runner_sha256": common.sha(Path(__file__)),
        "input_hashes": inputs.hashes(), "artifacts": {
            name: common.sha(out / name) for name in ("G120_frozen.csv", "fusion_G200_frozen.csv", "L1_discovery_counts.csv")
        },
    })
    print("Frozen three Test comparisons, G lists and Discovery context.", flush=True)


def prior_tables(out, common):
    frame = common.read_csv(out / "L1_discovery_counts.csv")
    global_orders = frame.drop_duplicates("l2").set_index("l2").global_orders.sort_index()
    categories = global_orders.index.to_list()
    prior = global_orders.to_numpy(dtype=float) / global_orders.sum()
    by_l1 = {}
    for key, block in frame.groupby("l1"):
        freq = block.set_index("l2").masked_targets.reindex(categories).to_numpy(dtype=float)
        by_l1[key] = (freq + 30 * prior) / (freq.sum() + 30)
    return categories, prior, by_l1


def rule_priority(common, replay, masked, rule_list, fallback):
    rules = rule_list.sort_values(["disc_conf", "disc_joint", "disc_lift", "rule_id"],
                                  ascending=[False, False, False, True])
    props = [(r.consequent, masked.trigger(tuple(r.antecedent.split(" + "))) & ~masked.observed[r.consequent])
             for r in rules.itertuples()]
    ranks, _ = replay.replay(props + fallback, masked)
    return replay.union(ranks)


def fused(common, inputs, masked, frame, cats, priors):
    old = module("old_fusion", inputs.old / "followup_fusion_time/run.py")
    old.union = lambda masks: _union(masks)
    rules = [SimpleNamespace(identifier=r.rule_id, antecedent=tuple(r.antecedent.split(" + ")),
                             consequent=r.consequent) for r in frame.itertuples(index=False)]
    picks = [SimpleNamespace(stats=SimpleNamespace(key=i, joint=r.joint, total=r.antecedent_orders))
             for i, r in enumerate(frame.itertuples(index=False))]
    book = SimpleNamespace(rules=rules, prior=lambda k: (picks[k].stats.joint + .5) / (picks[k].stats.total + 1))
    arena = SimpleNamespace(n=len(priors), observed=masked.observed, antecedent=masked.trigger)
    positions = {cat: i for i, cat in enumerate(cats)}
    head = old.feature_blocks(arena, book, picks[:100], positions)["discounted"]
    tail = old.feature_blocks(arena, book, picks[100:], positions)["discounted"]
    # Reuse the same scores for the two nested lists. Negative infinity excludes visible items.
    seen = np.stack([old.array(masked.observed[c], arena.n) for c in cats], axis=1)
    result = {}
    for label, score in (("fusion_G100", head + WEIGHTS[1] * priors),
                         ("fusion_G200", head + WEIGHTS[0] * tail + WEIGHTS[1] * priors)):
        score[seen] = -np.inf
        top = np.argsort(-score, axis=1, kind="stable")[:, :5]
        indices = (bit.bit_length() - 1 for bit, _, _ in masked.examples)
        result[label] = {i: tuple(cats[c] for c in top[i] if np.isfinite(score[i, c])) for i in indices}
    return result


def _union(masks):
    result = 0
    for mask in masks:
        result |= mask
    return result


def sku_inputs(inputs, spec, test_ids):
    raw = github_object(inputs.repo, spec["a_snapshot_commit"], "clean_transactions.csv.gz")
    assert sha256(raw).hexdigest() == spec["transaction_sha256"]
    order_raw = github_object(inputs.repo, spec["a_snapshot_commit"], "orders.csv.gz")
    assert sha256(order_raw).hexdigest() == spec["orders_sha256"]
    data = pd.read_csv(BytesIO(order_raw), compression="gzip", dtype=str, keep_default_na=False,
                       usecols=["basket_id", "invoice_datetime", "customer_id", "split", "is_valid_order"])
    known = data.loc[data.is_valid_order.eq("1") & data.split.isin(["profile", "discovery", "validation", "test"])]
    assert known.basket_id.is_unique
    by_id = known[["basket_id", "invoice_datetime", "customer_id"]].itertuples(index=False, name=None)
    orders = {bid: (time, cid, set()) for bid, time, cid in by_id}
    columns = ["invoice_id", "stock_code", "split", "is_valid_basket_item"]
    reader = pd.read_csv(BytesIO(raw), compression="gzip", dtype=str, keep_default_na=False,
                         usecols=columns, chunksize=125_000)
    for chunk in reader:
        use = chunk.is_valid_basket_item.eq("1") & chunk.invoice_id.isin(orders)
        block = chunk.loc[use, ["invoice_id", "stock_code"]].drop_duplicates()
        for bid, sku in block.itertuples(index=False, name=None):
            cat = inputs.shared.taxonomy[sku]
            if cat != "other":
                orders[bid][2].add((cat, sku))
    assert set(test_ids) <= set(orders)
    select = pd.read_csv(inputs.disc_orders, dtype=str, keep_default_na=False,
                         usecols=["basket_id", "is_eligible_for_main_comparison"])
    train_ids = select.loc[select.is_eligible_for_main_comparison.eq("1"), "basket_id"]
    popular = defaultdict(Counter)
    for bid in train_ids:
        for category, sku in orders[bid][2]:
            popular[category][sku] += 1
    ranking = {c: sorted(values, key=lambda s: (-values[s], s)) for c, values in popular.items()}
    return orders, ranking


def sku_replay(inputs, spec, period, masked, recommendations):
    orders, ranking = sku_inputs(inputs, spec, period.ids)
    rank = {c: {s: i for i, s in enumerate(skus)} for c, skus in ranking.items()}
    fallback = {c: skus[0] for c, skus in ranking.items()}
    live, frozen = defaultdict(dict), defaultdict(dict)
    by_id = {period.ids[bit.bit_length() - 1]: (bit.bit_length() - 1, hidden)
             for bit, _, hidden in masked.examples}
    scores = {"sku_pop": 0, "sku_asof": 0, "sku_frozen": 0}
    availability = Counter()

    def select(books, cid, cat):
        data = books.get((cid, cat)) if cid else None
        if not data:
            return fallback[cat]
        return min(data, key=lambda s: (-data[s][0], -data[s][1], rank[cat].get(s, 10**6), s))

    for tick, (_, group) in enumerate(groupby(sorted(orders, key=lambda bid: orders[bid][0]),
                                             key=lambda bid: orders[bid][0])):
        bids = list(group)
        time = orders[bids[0]][0]
        for bid in bids:
            if bid not in by_id:
                continue
            i, hidden = by_id[bid]
            _, cid, contents = orders[bid]
            assert cid == period.store.customers[i] and {c for c, _ in contents} == period.store.baskets[i]
            actual = {s for c, s in contents if c == hidden}
            assert actual
            predicted = recommendations[i]
            availability["skus_tested"] += 1
            if cid:
                availability["identified_orders"] += 1
                if any((cid, cat) in live for cat in predicted):
                    availability["identified_orders_using_history"] += 1
                else:
                    availability["identified_orders_all_popular_fallback"] += 1
            predictions = {
                "sku_pop": {fallback[cat] for cat in predicted},
                "sku_asof": {select(live, cid, cat) for cat in predicted},
                "sku_frozen": {select(frozen, cid, cat) for cat in predicted},
            }
            for method, suggestion in predictions.items():
                if actual & suggestion:
                    scores[method] |= 1 << i
        # Update only after every evaluation sharing this timestamp is complete.
        for bid in bids:
            _, cid, contents = orders[bid]
            if not cid:
                continue
            for cat, sku in contents:
                last = live[cid, cat].get(sku, (0, -1))
                live[cid, cat][sku] = (last[0] + 1, tick)
                if time < HISTORY_CUTOFF:
                    frozen[cid, cat][sku] = live[cid, cat][sku]
    assert availability["skus_tested"] == masked.n
    assert scores["sku_asof"] & period.strata["anonymous"] == scores["sku_pop"] & period.strata["anonymous"]
    return scores, availability


def test(inputs, out):
    common, repo = inputs.common, inputs.repo
    spec = common.read_json(out / "freeze.json")
    assert common.sha(HERE / "README.md") == spec["proto_sha256"]
    runner = common.sha(Path(__file__))
    if runner != spec["runner_sha256"]:
        correction = common.read_json(out / "runner_recovery.json")
        assert correction["original_runner_sha256"] == spec["runner_sha256"]
        assert common.sha(out / "frozen_runner_original.py") == spec["runner_sha256"]
        assert correction["corrected_runner_sha256"] == runner
        assert correction["freeze_sha256"] == common.sha(out / "freeze.json")
    assert spec["input_hashes"] == inputs.hashes()
    assert all(common.sha(out / name) == digest for name, digest in spec["artifacts"].items())
    assert not (out / "comparisons.csv").exists()
    period = common.test_period(inputs.shared, spec)
    top = module("mask_replay", repo / "experiments/validation_four_metrics/run.py")
    replay = module("recommendation_replay", repo / "experiments/validation_hybrid_residual/run.py")
    masked = top.MaskedBaskets(period.store, period.ids)
    assert masked.n == 9728
    cats, prior, by_l1 = prior_tables(out, common)
    ctx_masks = defaultdict(int)
    priors = np.broadcast_to(prior, (period.store.n, len(prior))).copy()
    for bit, visible, _ in masked.examples:
        i = bit.bit_length() - 1
        ctx = context(visible, inputs.parents)
        ctx_masks[ctx] |= bit
        priors[i] = by_l1.get(ctx, prior)
    pop_global = [(c, masked.all & ~masked.observed[c])
                  for i in np.argsort(-prior, kind="stable") for c in (cats[i],)]
    pop_l1 = [(cats[i], scope & ~masked.observed[cats[i]]) for ctx, scope in ctx_masks.items()
              for i in np.argsort(-by_l1.get(ctx, prior), kind="stable")]
    roster = common.read_csv(out / "G120_frozen.csv")
    global_score = rule_priority(common, replay, masked, roster, pop_global)
    l1_score = rule_priority(common, replay, masked, roster, pop_l1)
    old = common.read_csv(inputs.project / "results/test/recommendation.csv")
    expected = int(old.loc[old.method.eq("G") & old["sample"].eq("all"), "top5_hit_orders"].iloc[0])
    assert global_score.bit_count() == expected == 2907
    frame = common.read_csv(out / "fusion_G200_frozen.csv")
    assert frame.position.tolist() == list(range(1, 201)) and frame.rule_id.nunique() == 200
    g100 = frame.iloc[:100].rename(columns={"joint": "disc_joint"})
    hits = {"G120_global": global_score, "G120_l1": l1_score,
            "G100_l1": rule_priority(common, replay, masked, g100, pop_l1)}
    predictions = fused(common, inputs, masked, frame, cats, priors)
    for label, recs in predictions.items():
        hits[label] = _union(bit for bit, _, target in masked.examples if target in recs[bit.bit_length() - 1])
    print("Category-context and rule-pool replays complete.", flush=True)
    sku, availability = sku_replay(inputs, spec, period, masked, predictions["fusion_G200"])
    assert all((s & ~hits["fusion_G200"]) == 0 for s in sku.values())
    hits |= sku
    all_samples = {**period.strata, "identified": period.store.all & ~period.strata["anonymous"]}
    comparisons, boot, index = [], [], {}
    for metric, left, right in COMPARISONS:
        main = "identified" if metric.startswith("sku") else "all"
        for sample, strata in all_samples.items():
            scope = strata & masked.all
            a, b = hits[left] & scope, hits[right] & scope
            n = scope.bit_count()
            comparisons.append(dict(metric=metric, sample=sample, primary_sample=sample == main,
                baseline=left, treatment=right, orders=n, baseline_hits=a.bit_count(), treatment_hits=b.bit_count(),
                baseline_hit5=a.bit_count()/n, treatment_hit5=b.bit_count()/n,
                new_hits=(b & ~a).bit_count(), lost_hits=(a & ~b).bit_count(),
                net_hits=b.bit_count()-a.bit_count(), delta_pp=100*(b.bit_count()-a.bit_count())/n))
            if sample == main:
                boot.append((metric, a, b, scope))
                index[metric] = period.store
    results = pd.DataFrame(comparisons)
    bands = common.intervals(period, boot, index).drop(columns="L_minus_G")
    bands[["low95_pp", "high95_pp"]] = 100 * bands[["low95", "high95"]]
    outcomes = results.merge(bands[["metric", "low95_pp", "high95_pp"]], on="metric", suffixes=("", "_main"))
    outcomes.loc[~outcomes.primary_sample, ["low95_pp", "high95_pp"]] = np.nan
    common.csv(outcomes, out / "comparisons.csv")
    common.write_json(out / "audit.json", dict(sample=period.audit, sku_history=availability,
        original_G120_hit_count_reproduced=expected, runner_sha256=runner,
        freeze_sha256=common.sha(out / "freeze.json")))
    print(outcomes.loc[outcomes.primary_sample, ["metric", "orders", "baseline_hit5", "treatment_hit5",
                                                 "net_hits", "delta_pp", "low95_pp", "high95_pp"]].to_string(index=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "test"))
    parser.add_argument("--project", type=Path, default=HERE.parent)
    parser.add_argument("--out", type=Path, default=HERE / "results")
    args = parser.parse_args()
    project, out = args.project.resolve(), args.out.resolve()
    repo = project.parent / "repository"
    sys.path.insert(0, str(repo / "src"))
    common = module("existing_shared_evaluation", repo / "experiments/shared_full_store/run.py")
    out.mkdir(parents=True, exist_ok=True)
    globals()[args.action](Inputs(project, common, repo), out)


if __name__ == "__main__":
    main()
