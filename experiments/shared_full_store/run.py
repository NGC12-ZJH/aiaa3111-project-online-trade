"""Build shared rule lists, select on Validation, freeze, then replay Test."""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
CONFIGS = ("P1", "P2", "P3", "P4", "P5")
KEY = ["control", "method", "seed"]
SYSTEMS = [("GL", "G", ""), ("GL", "L", "")] + [
    ("A1", "R", str(seed)) for seed in range(1000, 1100)
]
QUALITY = dict(min_antecedent_orders=20, min_joint_orders=10, min_antecedent_customers=10,
               min_joint_customers=5, max_customer_joint_share=.5, min_confidence_uplift=.05,
               min_lift=1.2, min_triple_increment_pp=5, adjustment="BY", alpha=.05)
STRICT_QUALITY = {**QUALITY, "min_confidence_uplift": .10}
MEASURES = ("raw_coverage", "reliable_coverage", "strict_reliable_coverage")
STRATA = ("all", "profile", "identified_non_profile", "anonymous")
TEXT_FIELDS = dict(seed=str, owner=str, rule_id=str)
SOURCE_PATH = "data/processed/A_data_preparation/baskets.csv.gz"
BOOTSTRAP = dict(repeats=2000, seed=3111)
SCAN_CAP = 300


def module(name, path):
    spec = spec_from_file_location(name, path)
    result = module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def csv(frame, path):
    frame.to_csv(path, index=False, lineterminator="\n")


def read_csv(path):
    return pd.read_csv(path, keep_default_na=False, dtype=TEXT_FIELDS, float_precision="round_trip")


def parts(frame):
    return {
        row.rule_id: (tuple(row.antecedent.split(" + ")), (row.consequent,))
        for row in frame.itertuples(index=False)
    }


def nested(index, ranks, sizes, limit):
    """Reuse the cumulative proportional deficit rule at every position."""
    shares = sum(sizes.values())
    seen, sequence = set(), []
    contributed, pointers = Counter(), Counter()
    for position in range(1, limit + 1):
        available = []
        for group, candidates in ranks.items():
            while pointers[group] < len(candidates) and index.joint[candidates[pointers[group]]] in seen:
                pointers[group] += 1
            if pointers[group] < len(candidates):
                available.append(group)
        if not available:
            return sequence
        group = min(available, key=lambda g: (contributed[g] * shares - position * sizes[g], g))
        rank = pointers[group]
        direction = ranks[group][rank]
        sequence.append((direction, group, rank + 1))
        seen.add(index.joint[direction])
        pointers[group] += 1
        contributed[group] += 1
    return sequence


class Inputs:
    def __init__(self, repo):
        from online_trade.evaluation.validation import load_inputs, load_period

        self.repo = repo
        self.local = repo / "data/processed/local/D_validation"
        self.core, self.taxonomy, self.profile, self.mappings, _, self.configs = load_inputs(
            self.local, repo, {"configs": CONFIGS})
        self.discovery, _, self.audit = load_period(
            self.local, "discovery", self.taxonomy, self.profile)

    def hashes(self):
        repo_files = [
            "configs/test_frozen.json",
            "configs/experiment.json",
            "src/online_trade/evaluation/validation.py",
            "src/online_trade/evaluation/quality.py",
            "experiments/discovery_residual_refill/run.py",
            "experiments/validation_budget_redesign/run.py",
            "experiments/validation_four_metrics/run.py",
            "experiments/validation_hybrid_residual/run.py",
            "experiments/validation_budget_redesign/results/global_local_A1_rule_paths.csv.gz",
            "data/taxonomy/item_taxonomy_v1.csv",
        ]
        local_files = ["discovery_baskets.csv", "validation_baskets.csv", "core/configurations.csv",
                       "core/inputs/customer_clusters.csv", "core/inputs/item_taxonomy_v1.csv",
                       "core/inputs/random_groups_A1_profile_frequency.csv"]
        paths = [self.repo / path for path in repo_files] + [self.local / path for path in local_files]
        return {p.relative_to(self.repo).as_posix(): sha(p) for p in paths}


def discovery(inputs, out):
    previous = inputs.repo / "experiments/validation_budget_redesign"
    dense = module("dense_budget", previous / "run.py")
    disc = inputs.discovery
    index, definitions = dense.prepare_index(inputs.repo, disc)
    pools = {}
    sizes_rows = []
    for key in SYSTEMS:
        mapping = inputs.mappings[key]
        masks = {"GLOBAL": disc.all} if mapping is None else {g: disc.scope(mapping, g) for g in ("0", "1", "2")}
        sizes = {g: mask.bit_count() for g, mask in masks.items()}
        assert sum(sizes.values()) == disc.n
        ranked = {g: {p: ranks for p, ranks, _ in index.ranks(mask, sizes[g], inputs.configs)}
                  for g, mask in masks.items()}
        for config in CONFIGS:
            ranks = {g: choices[config] for g, choices in ranked.items()}
            capacity = len({index.joint[r] for choices in ranks.values() for r in choices})
            pool = nested(index, ranks, sizes, min(capacity, SCAN_CAP))
            assert len(pool) == min(capacity, SCAN_CAP)
            pools[key, config] = pool
            sizes_rows.append((*key, config, capacity))
    capacities = pd.DataFrame(sizes_rows, columns=KEY + ["config", "available_combinations"])
    maximum = capacities.groupby("config").available_combinations.min().floordiv(10).mul(10)
    limits = maximum.clip(upper=SCAN_CAP).to_dict()
    new_rows = []
    for (key, config), pool in pools.items():
        assert limits[config] >= 100
        for position, (direction, owner, original_rank) in enumerate(pool[:limits[config]], 1):
            ant, con = definitions[str(direction)]
            n_a = disc.mask(ant).bit_count()
            n_b = disc.mask(con).bit_count()
            joint = disc.mask(ant + con).bit_count()
            conf = joint / n_a
            new_rows.append((*key, config, position, owner, index.ids[direction], original_rank,
                             " + ".join(ant), con[0], conf, joint, conf / (n_b / disc.n)))
    frame = pd.DataFrame(new_rows, columns=KEY + ["config", "position", "owner", "rule_id", "rank_in_cluster",
                                                "antecedent", "consequent", "disc_conf", "disc_joint", "disc_lift"])
    original = read_csv(previous / "results/global_local_A1_rule_paths.csv.gz")
    original = original.loc[original.unit.eq("combination"), KEY + ["config", "position", "owner", "rule_id", "rank_in_cluster"]]
    first = frame.loc[frame.position.le(100), original.columns]
    order = KEY + ["config", "position"]
    pd.testing.assert_frame_equal(first.sort_values(order).reset_index(drop=True),
                                  original.sort_values(order).reset_index(drop=True))
    verify_rosters(frame, limits)
    popular = sorted(((c, mask.bit_count()) for c, mask in disc.items.items()), key=lambda x: (-x[1], x[0]))
    csv(pd.DataFrame(popular, columns=["l2_id", "discovery_orders"]), out / "discovery_popularity.csv")
    csv(capacities, out / "discovery_capacities.csv")
    csv(frame, out / "discovery_paths.csv.gz")
    write_json(out / "discovery_audit.json", {
        "sample": inputs.audit, "systems": len(SYSTEMS), "capacity_limits": limits,
        "available_common_limits": maximum.to_dict(),
        "prefixes_verified_against_existing_100": len(original),
        "paths": len(frame), "protocol_sha256": sha(HERE / "README.md"),
    })
    print("Discovery verified. Equal-capacity limits:", limits, flush=True)


def verify_rosters(frame, limits):
    directions = parts(frame)
    assert set(map(tuple, frame[KEY].drop_duplicates().to_numpy())) == set(SYSTEMS)
    assert len(frame.groupby(KEY + ["config"])) == len(SYSTEMS) * len(limits)
    for (_, _, _, config), block in frame.groupby(KEY + ["config"], sort=False):
        budget = limits[config]
        assert sorted(block.position.tolist()) == list(range(1, budget + 1))
        assert len({tuple(sorted(a + c)) for a, c in map(directions.__getitem__, block.rule_id)}) == budget


class Period:
    def __init__(self, data, taxonomy, profiles, window):
        from online_trade.evaluation.validation import BasketIndex

        dates = pd.to_datetime(data.invoice_date, format="mixed")
        assert dates.between(window["start"], window["end_exclusive"], inclusive="left").all()
        assert data.basket_id.is_unique
        self.ids = data.basket_id.tolist()
        customers = data.customer_id.tolist()
        eligible = data.customer_id.isin(profiles)
        assert eligible.equals(data.is_eligible_for_main_comparison.eq("1"))
        known = data.customer_id.ne("")
        baskets = [{taxonomy[item] for item in json.loads(items) if taxonomy[item] != "other"}
                   for items in data["items"]]
        self.store = BasketIndex(customers, baskets)
        self.identified = BasketIndex(data.loc[known, "customer_id"].tolist(),
                                      [basket for basket, ok in zip(baskets, known) if ok])
        profile_mask = self.store.scope({c: c in profiles for c in self.store.by_customer}, True)
        anonymous_mask = self.store.by_customer.get("", 0)
        other_mask = self.store.all & ~(profile_mask | anonymous_mask)
        self.strata = dict(all=self.store.all, profile=profile_mask,
                           identified_non_profile=other_mask, anonymous=anonymous_mask)
        self.audit = {name: mask.bit_count() for name, mask in self.strata.items()}
        self.audit.update(identified=self.identified.n, identified_customers=len(self.identified.by_customer),
                          maskable=sum(len(b) >= 2 for b in baskets))


def accepted(engine, rule_ids):
    from online_trade.evaluation.quality import adjust_fdr, classify

    facts = [engine.get("GLOBAL", rid) for rid in rule_ids]
    qvalues = adjust_fdr([fact["p_combined"] for fact in facts])
    return {
        rid: {**fact, "q_BY": float(q), "family_size": len(rule_ids),
              "status": classify({**fact, "q_BY": q}, QUALITY),
              "strict_status": classify({**fact, "q_BY": q}, STRICT_QUALITY)}
        for rid, fact, q in zip(rule_ids, facts, qvalues)
    }


def coverage_systems(inputs, period, frame, step):
    from online_trade.evaluation.quality import QualityEvidence

    definitions = parts(frame)
    engine = QualityEvidence(period.identified, inputs.discovery, {}, definitions)
    full = {rid: period.store.mask(ant + con) for rid, (ant, con) in definitions.items()}
    known = {rid: period.identified.mask(ant + con) for rid, (ant, con) in definitions.items()}
    results, details, gl = [], [], {}
    for key, system in frame.groupby(KEY, sort=False):
        states = accepted(engine, sorted(set(system.rule_id)))
        if key[0] == "GL":
            details.extend({**dict(zip(KEY, key)), **evidence} for evidence in states.values())
        for config, pool in system.groupby("config", sort=False):
            raw = reliable = strict = portable = strict_portable = 0
            passed = strict_passed = 0
            before = np.zeros(7, dtype=int)
            for entry in pool.sort_values("position").itertuples(index=False):
                rid = entry.rule_id
                raw |= full[rid]
                if states[rid]["status"] == "accepted":
                    passed += 1
                    reliable |= known[rid]
                    portable |= full[rid]
                if states[rid]["strict_status"] == "accepted":
                    strict_passed += 1
                    strict |= known[rid]
                    strict_portable |= full[rid]
                if entry.position % step:
                    continue
                assert not strict & ~reliable and not portable & ~raw and not strict_portable & ~portable
                counts = np.array([x.bit_count() for x in (raw, reliable, strict, portable, strict_portable)]
                                  + [passed, strict_passed])
                assert np.all(counts >= before)
                row = dict(zip(KEY, key)) | dict(config=config, budget=entry.position,
                                                identified_orders=period.identified.n,
                                                quality_family=len(states))
                names = (*MEASURES, "accepted_store_coverage", "strict_accepted_store_coverage",
                         "quality_pass_share", "strict_quality_pass_share")
                den = (period.store.n, period.identified.n, period.identified.n,
                       period.store.n, period.store.n, entry.position, entry.position)
                for i, name in enumerate(names):
                    row[name] = counts[i] / den[i]
                    row[name + "_count"] = counts[i]
                    row[name + "_gain_count"] = counts[i] - before[i]
                    if i < 5:
                        row[name + "_gain_pp"] = (counts[i] - before[i]) * 100 / den[i]
                for label, mask in period.strata.items():
                    n = mask.bit_count()
                    hits = (raw & mask).bit_count()
                    row[f"{label}_orders"] = n
                    row[f"{label}_raw_hits"] = hits
                    row[f"{label}_raw_coverage"] = hits / n
                assert sum(row[f"{s}_raw_hits"] for s in STRATA[1:]) == counts[0]
                results.append(row)
                if key[0] == "GL":
                    gl[key[1], config, entry.position] = (raw, reliable, strict)
                before = counts
    return pd.DataFrame(results), pd.DataFrame(details), gl


def compare(frame, keys, measures):
    comparisons = []
    for values, group in frame.groupby(keys, sort=False):
        gl = group.loc[group.control.eq("GL")].set_index("method")
        random = group.loc[group.control.eq("A1")]
        assert len(random) == 100 and set(gl.index) == {"G", "L"}
        for measure in measures:
            g, l = gl.loc["G", measure], gl.loc["L", measure]
            draws = random[measure]
            ge = int(draws.ge(l - 1e-12).sum())
            comparisons.append(dict(zip(keys, values)) | dict(metric=measure, G=g, L=l, L_minus_G=l-g,
                A1_min=draws.min(), A1_median=draws.median(), A1_max=draws.max(), A1_ge_L=ge,
                descriptive_upper_tail=(1 + ge) / 101))
    return pd.DataFrame(comparisons)


def selection(frame, quality_measure, tolerance):
    metrics = ["raw_coverage", quality_measure]
    fields = metrics + [m + "_gain_pp" for m in metrics]
    grid = frame.loc[frame.control.eq("GL")].pivot(index=["config", "budget"], columns="method", values=fields)
    primary = grid.loc[:, metrics]
    gaps = (primary.max() - primary) * 100
    gains = grid.drop(columns=metrics, level=0)
    next_gains = gains.groupby(level="config").shift(-1)
    later_gains = gains.groupby(level="config").shift(-2)
    both_small = next_gains.lt(.5).all(axis=1) & later_gains.lt(.5).all(axis=1)
    grid.columns = ["_".join(key) for key in grid.columns]
    grid["max_shortfall_pp"] = gaps.max(axis=1)
    grid["mean_raw"] = primary.raw_coverage.mean(axis=1)
    grid["mean_quality"] = primary[quality_measure].mean(axis=1)
    grid["next_two_small"] = both_small
    grid["next_step_max_gain_pp"] = next_gains.max(axis=1)
    grid["second_step_max_gain_pp"] = later_gains.max(axis=1)
    for key in gaps:
        grid["_".join(key) + "_gap_pp"] = gaps[key]
    grid = grid.reset_index()
    eligible = grid.loc[grid.max_shortfall_pp.le(tolerance + 1e-10)]
    plateau = eligible.loc[eligible.next_two_small]
    if len(plateau):
        candidates, status = plateau, "two_low_gain_steps"
    elif len(eligible):
        candidates, status = eligible, "within_tolerance_plateau_unconfirmed"
    else:
        candidates, status = grid, "best_available_shortfall"
    order = ["budget", "max_shortfall_pp"]
    if not len(eligible):
        order.reverse()
    choice = candidates.sort_values(order + ["mean_raw", "mean_quality", "config"],
                                    ascending=[True, True, False, False, True]).iloc[0]
    return grid, dict(choice, quality_metric=quality_measure, tolerance_pp=tolerance, selection_status=status)


def validation(inputs, out):
    assert sha(HERE / "README.md") == read_json(out / "discovery_audit.json")["protocol_sha256"]
    frame = read_csv(out / "discovery_paths.csv.gz")
    original = read_json(inputs.repo / "configs/experiment.json")
    data = pd.read_csv(inputs.local / "validation_baskets.csv", dtype=str, keep_default_na=False)
    assert set(data.split) == {"validation"}
    period = Period(data, inputs.taxonomy, inputs.profile, original["validation"])
    assert [period.audit[k] for k in STRATA] == [8067, 4862, 2502, 703]
    systems, rules, _ = coverage_systems(inputs, period, frame, 10)
    csv(systems, out / "validation_systems.csv")
    csv(rules, out / "validation_GL_quality.csv")
    csv(compare(systems, ["config", "budget"], [*MEASURES, "quality_pass_share",
                "raw_coverage_gain_pp", "reliable_coverage_gain_pp"]), out / "validation_A1.csv")
    choices = []
    for quality in ("reliable_coverage", "strict_reliable_coverage"):
        for tolerance in (.5, 1.0, 2.0):
            grid, choice = selection(systems, quality, tolerance)
            choices.append(choice)
            if tolerance == 1.0 and quality == "reliable_coverage":
                csv(grid, out / "validation_selection_grid.csv")
                print("Validation main choice:", choice["config"], choice["budget"],
                      choice["selection_status"], flush=True)
    csv(pd.DataFrame(choices), out / "validation_choices.csv")
    write_json(out / "validation_audit.json", {
        "sample": period.audit, "rows": len(systems), "test_accessed": False,
        "runner_sha256": sha(Path(__file__)), "protocol_sha256": sha(HERE / "README.md"),
        "input_hashes": inputs.hashes(), "discovery_paths_sha256": sha(out / "discovery_paths.csv.gz"),
    })


def freeze(inputs, out):
    assert not (out / "freeze.json").exists(), "Freeze already exists."
    audit = read_json(out / "validation_audit.json")
    assert not audit["test_accessed"] and audit["runner_sha256"] == sha(Path(__file__))
    assert audit["protocol_sha256"] == sha(HERE / "README.md")
    assert audit["input_hashes"] == inputs.hashes()
    assert sha(out / "discovery_paths.csv.gz") == audit["discovery_paths_sha256"]
    chosen = read_csv(out / "validation_choices.csv").query(
        "quality_metric == 'reliable_coverage' and tolerance_pp == 1.0").iloc[0]
    config, budget = chosen.config, int(chosen.budget)
    paths = read_csv(out / "discovery_paths.csv.gz")
    roster = paths.loc[paths.config.eq(config) & paths.position.le(budget)]
    verify_rosters(roster, {config: budget})
    csv(roster, out / "frozen_rule_lists.csv")
    original = read_json(inputs.repo / "configs/test_frozen.json")
    write_json(out / "freeze.json", {
        "recorded_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "evidence": "supplementary evaluation on a previously reported historical Test period",
        "selection": dict(config=config, budget=budget, criterion=chosen.selection_status),
        "test_window": original["test_window"], "a_snapshot_commit": original["a_snapshot_commit"],
        "source_baskets_sha256": original["source_baskets_sha256"], "quality": QUALITY,
        "strict_quality": STRICT_QUALITY, "bootstrap": BOOTSTRAP,
        "runner_sha256": sha(Path(__file__)), "protocol_sha256": sha(HERE / "README.md"),
        "input_hashes": audit["input_hashes"], "artifact_hashes": {
            name: sha(out / name) for name in ["discovery_popularity.csv", "validation_choices.csv",
            "validation_selection_grid.csv", "validation_audit.json", "frozen_rule_lists.csv"]
        },
    })
    print(f"Frozen {config}/{budget}, {len(SYSTEMS)} rule lists.", flush=True)


def test_period(inputs, spec):
    ref = spec["a_snapshot_commit"]
    raw = subprocess.check_output(["git", "show", f"{ref}:{SOURCE_PATH}"], cwd=inputs.repo)
    assert hashlib.sha256(raw).hexdigest() == spec["source_baskets_sha256"]
    frame = pd.read_csv(BytesIO(raw), compression="gzip", dtype=str, keep_default_na=False)
    window = spec["test_window"]
    dates = pd.to_datetime(frame.invoice_date, format="mixed")
    in_window = dates.between(window["start"], window["end_exclusive"], inclusive="left")
    assert in_window.equals(frame.split.eq("test"))
    return Period(frame.loc[in_window], inputs.taxonomy, inputs.profile, window)


def recommend(repo, period, roster, popular):
    top = module("masked_baskets", repo / "experiments/validation_four_metrics/run.py")
    hybrid = module("recommendation_replay", repo / "experiments/validation_hybrid_residual/run.py")
    masked = top.MaskedBaskets(period.store, period.ids)
    assert masked.n == period.audit["maskable"]
    fallback = [(cat, masked.all & ~masked.observed[cat]) for cat in popular]
    definitions = parts(roster)
    props = {rid: (con[0], masked.trigger(ant) & ~masked.observed[con[0]])
             for rid, (ant, con) in definitions.items()}
    assert all(cat in popular for cat, _ in props.values())
    _, available = hybrid.replay(fallback, masked)
    groups = [(("BASE", "popular", ""), roster.iloc[:0]), *roster.groupby(KEY, sort=False)]
    rows, hits = [], {}
    for key, block in groups:
        order = block.sort_values(["disc_conf", "disc_joint", "disc_lift", "rule_id"],
                                  ascending=[False, False, False, True])
        ranks, occupied = hybrid.replay([props[rid] for rid in order.rule_id] + fallback, masked)
        assert occupied[5] == available[5]
        hits[key] = hybrid.union(ranks)
        for label, scope in period.strata.items():
            subset = scope & masked.all
            stats = hybrid.top_metrics(ranks, occupied, subset)
            rows.append(dict(zip(KEY, key)) | dict(sample=label, **stats))
    result = pd.DataFrame(rows)
    for i, row in result.iterrows():
        subset = period.strata[row["sample"]] & masked.all
        hit = hits[tuple(row[k] for k in KEY)] & subset
        for label, ref in (("popular", ("BASE", "popular", "")), ("G", SYSTEMS[0])):
            baseline = hits[ref] & subset
            result.loc[i, f"new_hits_vs_{label}"] = (hit & ~baseline).bit_count()
            result.loc[i, f"lost_hits_vs_{label}"] = (baseline & ~hit).bit_count()
            result.loc[i, f"net_hits_vs_{label}"] = hit.bit_count() - baseline.bit_count()
    return result, hits, masked.all


def intervals(period, runs, samples):
    rng = np.random.default_rng(BOOTSTRAP["seed"])
    output = []
    for measure, g, l, eligible in runs:
        index = samples[measure]
        strata = [
            [mask for cid, mask in index.by_customer.items() if cid and mask & eligible],
            [1 << i for i, cid in enumerate(index.customers) if not cid and (1 << i) & eligible],
        ]
        numer = np.zeros(BOOTSTRAP["repeats"])
        denom = np.zeros(BOOTSTRAP["repeats"])
        for clusters in strata:
            if not clusters:
                continue
            n = len(clusters)
            weights = rng.multinomial(n, np.full(n, 1 / n), size=BOOTSTRAP["repeats"]).astype(float)
            numer += weights @ np.array([(l & mask).bit_count() - (g & mask).bit_count() for mask in clusters])
            denom += weights @ np.array([(eligible & mask).bit_count() for mask in clusters])
        lo, hi = np.quantile(numer / denom, [.025, .975])
        output.append(dict(metric=measure, L_minus_G=(l.bit_count()-g.bit_count())/eligible.bit_count(),
                           low95=lo, high95=hi))
    return pd.DataFrame(output)


def test(inputs, out):
    spec = read_json(out / "freeze.json")
    runner_digest = sha(Path(__file__))
    if spec["runner_sha256"] != runner_digest:
        recovery = read_json(out / "runner_recovery.json")
        assert recovery["freeze_sha256"] == sha(out / "freeze.json")
        assert recovery["original_runner_sha256"] == sha(out / "frozen_runner_original.py") == spec["runner_sha256"]
        assert recovery["corrected_runner_sha256"] == runner_digest
    assert spec["protocol_sha256"] == sha(HERE / "README.md")
    assert spec["input_hashes"] == inputs.hashes()
    assert all(sha(out / name) == digest for name, digest in spec["artifact_hashes"].items())
    assert not (out / "test").exists(), "Test result directory already exists."
    roster = read_csv(out / "frozen_rule_lists.csv")
    config, budget = spec["selection"]["config"], spec["selection"]["budget"]
    verify_rosters(roster, {config: budget})
    period = test_period(inputs, spec)
    assert [period.audit[k] for k in STRATA] == [10890, 5730, 4532, 628]
    systems, rules, masks = coverage_systems(inputs, period, roster, budget)
    popularity = read_csv(out / "discovery_popularity.csv").l2_id.tolist()
    top, hits, eligible = recommend(inputs.repo, period, roster, popularity)
    gl_g, gl_l = (masks[m, config, budget] for m in ("G", "L"))
    runs = [(measure, gh, lh, idx.all) for measure, gh, lh, idx in
            zip(MEASURES, gl_g, gl_l, [period.store, period.identified, period.identified])]
    runs += [("hit_at_5", hits[SYSTEMS[0]], hits[SYSTEMS[1]], eligible),
             ("G_hit_at_5_vs_popular", hits["BASE", "popular", ""], hits[SYSTEMS[0]], eligible),
             ("L_hit_at_5_vs_popular", hits["BASE", "popular", ""], hits[SYSTEMS[1]], eligible)]
    index_map = {name: period.identified if name in MEASURES[1:] else period.store for name, *_ in runs}
    ci = intervals(period, runs, index_map)
    metrics = [*MEASURES, "quality_pass_share", "strict_quality_pass_share", "accepted_store_coverage"]
    coverage_compare = compare(systems, ["config", "budget"], metrics)
    top_compare = compare(top.loc[top.control.ne("BASE")], ["sample", "top_orders"], ["hit_at_5", "ndcg_at_5"])
    dest = out / "test"
    dest.mkdir()
    for name, table in {"systems": systems, "GL_quality": rules, "coverage_comparisons": coverage_compare,
                        "recommendation": top, "recommendation_comparisons": top_compare,
                        "paired_intervals": ci}.items():
        csv(table, dest / f"{name}.csv")
    baseline = top.loc[top.control.eq("BASE") & top["sample"].eq("all")].iloc[0]
    write_json(dest / "audit.json", {"sample": period.audit, "systems": len(systems),
        "test_runner_sha256": runner_digest, "freeze_sha256": sha(out / "freeze.json"),
        "unable_to_fill_five": int(baseline.top_orders - baseline.five_recommendation_orders)})
    print(coverage_compare.to_string(index=False), flush=True)
    print(top_compare.loc[top_compare["sample"].eq("all")].to_string(index=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("discovery", "validation", "freeze", "test"))
    parser.add_argument("--repo", type=Path, default=HERE.parents[1])
    parser.add_argument("--out", type=Path, default=HERE / "results")
    args = parser.parse_args()
    repo, out = args.repo.resolve(), args.out.resolve()
    sys.path.insert(0, str(repo / "src"))
    out.mkdir(parents=True, exist_ok=True)
    globals()[args.action](Inputs(repo), out)


if __name__ == "__main__":
    main()
