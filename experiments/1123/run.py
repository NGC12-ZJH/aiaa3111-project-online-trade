"""Run the shared-rule experiment with three Profile feature sets."""

import argparse
from datetime import datetime
from fractions import Fraction
from itertools import combinations
import json
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits


HERE = Path(__file__).resolve().parent
VARIANTS = ("rfm", "rfm_form", "form")
RFM = ("recency", "frequency", "monetary")
FORM = ("qty", "skus", "concentration", "price", "low", "high")
GROUPS = ("0", "1", "2")
FEATURES = {"rfm": RFM, "rfm_form": RFM + FORM, "form": FORM}
SOURCE = "data/processed/A_data_preparation"
COST = Fraction(1, 2)
SEEDS = tuple(range(1000, 1100))


def snapshot_profile(repo, ref, name, columns):
    obj = f"{ref}:{SOURCE}/{name}.csv.gz"
    with subprocess.Popen(["git", "-C", str(repo), "show", obj], stdout=subprocess.PIPE) as proc:
        blocks = [chunk.loc[chunk.split.eq("profile")] for chunk in pd.read_csv(
            proc.stdout, compression="gzip", chunksize=125000, usecols=columns, dtype=str,
            keep_default_na=False)]
        assert proc.wait() == 0
    return pd.concat(blocks, ignore_index=True)


def profile_features(repo, common, inputs):
    from online_trade.clustering.features import build_rfm

    retail = common.module("historical_form_features", repo.parent / "1122/retail_data.py")
    ref = common.read_json(repo / "configs/test_frozen.json")["a_snapshot_commit"]
    fields = ["split", "is_identified_customer", "invoice_datetime", "gross_purchase_amount", "net_amount",
              "basket_size", "is_valid_rfm_order", "is_eligible_for_main_comparison", "is_profile_customer",
              "is_valid_order", "customer_id", "basket_id"]
    orders = snapshot_profile(repo, ref, "orders", fields)
    assert orders.invoice_datetime.lt("2010-06-01").all()
    known = orders.loc[orders.is_identified_customer.eq("1")].copy()
    known["invoice_datetime"] = pd.to_datetime(known.invoice_datetime, format="mixed")
    for name in ("gross_purchase_amount", "net_amount", "basket_size"):
        known[name] = known[name].astype(float)
    rfm = build_rfm(known, "2010-06-01")
    valid = orders.loc[orders.is_valid_order.eq("1")].set_index("basket_id")
    fields = ["split", "invoice_datetime", "invoice_id", "stock_code", "quantity", "unit_price",
              "is_valid_basket_item"]
    lines = snapshot_profile(repo, ref, "clean_transactions", fields)
    assert lines.invoice_datetime.lt("2010-06-01").all()
    lines = lines.loc[lines.is_valid_basket_item.eq("1") & lines.invoice_id.isin(valid.index)].copy()
    lines["unit_price"] = lines.unit_price.astype(float)
    lines["quantity"] = lines.quantity.astype(float)
    assert lines.unit_price.gt(0).all() and lines.quantity.gt(0).all()
    bands = tuple(np.quantile(lines.unit_price, [.33, .67]))
    forms = []
    for invoice, block in lines.groupby("invoice_id", sort=False):
        cid = valid.loc[invoice, "customer_id"]
        if cid:
            payload = [(sku, "", qty, price, "") for sku, qty, price in
                       block[["stock_code", "quantity", "unit_price"]].itertuples(index=False, name=None)]
            forms.append((cid, *retail.features(payload, *bands)[:6]))
    form = pd.DataFrame(forms, columns=["customer_id", *FORM]).groupby("customer_id").median()
    assert list(rfm.index) == list(form.index) and set(inputs.profile) == set(rfm.index)
    return rfm.join(form), bands


def cluster_and_shuffle(repo, common, inputs, out):
    from online_trade.clustering.features import feature_matrix
    from online_trade.clustering.methods import order_by_value

    profile, bands = profile_features(repo, common, inputs)
    transformed = profile.loc[:, list(RFM + FORM)].copy()
    for col in ("frequency", "monetary", "qty", "skus", "price"):
        transformed[col] = np.log1p(transformed[col])
    scaled = pd.DataFrame(StandardScaler().fit_transform(transformed), index=profile.index,
                          columns=transformed.columns)
    original_scale = feature_matrix(profile)
    np.testing.assert_allclose(scaled.loc[:, list(RFM)], original_scale, atol=1e-12)
    old_true = np.array([inputs.profile[c] for c in profile.index])
    strata = pd.cut(profile.frequency, [0, 1, 2, 4, 9, np.inf], labels=["1", "2", "3-4", "5-9", "10+"])
    layers = {layer: np.flatnonzero(strata.eq(layer)) for layer in sorted(strata.unique())}
    mappings = {("GL", "G", ""): None}
    real_labels, rows, checks = {}, [], {}
    for variant, columns in FEATURES.items():
        with threadpool_limits(limits=1):
            raw = KMeans(n_clusters=3, n_init=10, random_state=42).fit_predict(scaled.loc[:, list(columns)].to_numpy())
        labels = order_by_value(original_scale, raw).astype(str)
        real_labels[variant] = labels
        true = dict(zip(profile.index, labels))
        mappings["GL", variant, ""] = true
        if variant == "rfm":
            assert np.array_equal(labels, old_true)
        for group in GROUPS:
            medians = profile.loc[labels == group, list(RFM + FORM)].median().to_dict()
            rows.append(dict(variant=variant, group=group, customers=int((labels == group).sum()),
                             discovery_orders=inputs.discovery.scope(true, group).bit_count(), **medians))
        for seed in SEEDS:
            noisy = labels.copy()
            rng = np.random.default_rng(seed)
            for indices in layers.values():
                noisy[indices] = rng.permutation(labels[indices])
                assert sorted(noisy[indices]) == sorted(labels[indices])
            mapping = dict(zip(profile.index, noisy))
            if variant == "rfm":
                assert mapping == inputs.mappings["A1", "R", str(seed)]
            mappings["A1", variant, str(seed)] = mapping
        checks[variant] = common.hashlib.sha256("|".join(labels).encode()).hexdigest()
    common.csv(pd.DataFrame(rows), out / "profile_clusters.csv")
    common.write_json(out / "profile_audit.json", {
        "profile_customers": len(profile), "price_bands": list(bands), "features": FEATURES,
        "profile_rfm_labels_reproduced": True, "original_rfm_A1_seeds_reproduced": len(SEEDS),
        "matched_random_systems": len(VARIANTS) * len(SEEDS), "label_sequence_sha256": checks,
        "pairwise_ari": {f"{a}_vs_{b}": float(adjusted_rand_score(real_labels[a], real_labels[b]))
                         for a, b in combinations(VARIANTS, 2)},
    })
    return mappings


def discovery(repo, common, inputs, out):
    mappings = cluster_and_shuffle(repo, common, inputs, out)
    print("Profile and 300 A1 lists verified.", flush=True)
    dense = common.module("old_dense_builder", repo / "experiments/validation_budget_redesign/run.py")
    disc = inputs.discovery
    index, definitions = dense.prepare_index(repo, disc)
    pools, capacities = {}, []
    for i, (key, mapping) in enumerate(mappings.items(), 1):
        scopes = {"GLOBAL": disc.all} if mapping is None else {g: disc.scope(mapping, g) for g in GROUPS}
        sizes = {g: mask.bit_count() for g, mask in scopes.items()}
        assert sum(sizes.values()) == 7521
        ranked = {g: {p: order for p, order, _ in index.ranks(mask, sizes[g], inputs.configs)}
                  for g, mask in scopes.items()}
        for config in common.CONFIGS:
            ranks = {g: p[config] for g, p in ranked.items()}
            capacity = len({index.joint[r] for choices in ranks.values() for r in choices})
            pools[key, config] = common.nested(index, ranks, sizes, min(capacity, common.SCAN_CAP))
            capacities.append((*key, config, capacity))
        if i % 50 == 0:
            print(f"Discovery lists built for {i}/{len(mappings)} systems.", flush=True)
    dc = pd.DataFrame(capacities, columns=common.KEY + ["config", "available_combinations"])
    limits = dc.groupby("config").available_combinations.min().floordiv(10).mul(10).clip(upper=300).to_dict()
    assert min(limits.values()) >= 10
    scores = {}
    data = []
    for (key, config), pool in pools.items():
        for position, (direction, owner, local_rank) in enumerate(pool[:limits[config]], 1):
            a, c = definitions[str(direction)]
            if direction not in scores:
                joint = disc.mask(a + c).bit_count()
                conf = joint / disc.mask(a).bit_count()
                scores[direction] = (conf, joint, conf / (disc.mask(c).bit_count() / disc.n))
            data.append((*key, config, position, owner, index.ids[direction], local_rank,
                         " + ".join(a), c[0], *scores[direction]))
    frame = pd.DataFrame(data, columns=common.KEY + ["config", "position", "owner", "rule_id", "rank_in_cluster",
                                                    "antecedent", "consequent", "disc_conf", "disc_joint", "disc_lift"])
    verify_rosters(common, frame, limits)
    baseline = common.read_csv(repo / "experiments/shared_full_store/results/discovery_paths.csv.gz")
    old = baseline.rename(columns={"method": "old_method"}).assign(
        method=lambda x: x.old_method.replace({"L": "rfm", "R": "rfm"}))
    old = old.loc[old.position.le(old.config.map(limits)), frame.columns]
    rfm = frame.loc[frame.method.isin(["G", "rfm"])]
    cols = common.KEY + ["config", "position"]
    pd.testing.assert_frame_equal(rfm.sort_values(cols).reset_index(drop=True),
                                  old.sort_values(cols).reset_index(drop=True))
    popular = sorted(((c, mask.bit_count()) for c, mask in disc.items.items()), key=lambda x: (-x[1], x[0]))
    common.csv(pd.DataFrame(popular, columns=["l2_id", "discovery_orders"]), out / "discovery_popularity.csv")
    common.csv(dc, out / "discovery_capacities.csv")
    common.csv(frame, out / "discovery_paths.csv.gz")
    common.write_json(out / "discovery_audit.json", {
        "sample": inputs.audit, "systems": len(mappings), "limits": limits, "paths": len(frame),
        "original_rfm_and_global_paths_reproduced": len(rfm), "protocol_sha256": common.sha(HERE / "README.md"),
    })
    print("Discovery finished:", limits, flush=True)


def verify_rosters(common, frame, limits):
    assert len(frame[common.KEY].drop_duplicates()) == 304
    assert set(map(tuple, frame[common.KEY].drop_duplicates().to_numpy())) == (
        {("GL", "G", "")} | {("GL", variant, "") for variant in VARIANTS} |
        {("A1", variant, str(seed)) for variant in VARIANTS for seed in SEEDS})
    combo = {rid: tuple(sorted(ant + con)) for rid, (ant, con) in common.parts(frame).items()}
    for (*_, config), rows in frame.groupby(common.KEY + ["config"], sort=False):
        assert sorted(rows.position) == list(range(1, limits[config] + 1))
        assert len({combo[rid] for rid in rows.rule_id}) == limits[config]


def summary(common, data, keys, metrics):
    rows = []
    for _, block in data.groupby(keys, sort=False):
        meta = {k: block.iloc[0][k] for k in keys}
        real = block.loc[block.control.eq("GL")].set_index("method")
        for variant in VARIANTS:
            rand = block.loc[block.control.eq("A1") & block.method.eq(variant)]
            assert len(rand) == 100
            for metric in metrics:
                g, l = real.loc["G", metric], real.loc[variant, metric]
                vals = rand[metric]
                ge = int(vals.ge(l - 1e-12).sum())
                rows.append(meta | dict(variant=variant, metric=metric, G=g, L=l, L_minus_G=l-g,
                    A1_min=vals.min(), A1_median=vals.median(), A1_max=vals.max(), A1_ge_L=ge,
                    descriptive_upper_tail=(1 + ge) / 101))
    return pd.DataFrame(rows)


def selections(data):
    grid = data.loc[data.control.eq("GL")].pivot(
        index=["config", "budget"], columns="method", values="reliable_coverage_count")
    records = []
    for name in ("common", *VARIANTS):
        ranking = []
        for (p, b), count in grid.iterrows():
            choice = VARIANTS if name == "common" else (name,)
            local = Fraction(sum(int(count[v]) for v in choice), len(choice))
            gain = Fraction(int(count.G) + local, 2) * 100 / 7364
            score = gain - COST * b / 10
            ranking.append((p, b, gain, score))
        ranking.sort(key=lambda x: (-x[3], x[1], x[0]))
        records.extend((name, i, p, b, float(gain), float(score))
                       for i, (p, b, gain, score) in enumerate(ranking, 1))
    return pd.DataFrame(records, columns=["selection", "rank", "config", "budget", "coverage_pp", "score_pp"])


def input_hashes(repo, common, inputs):
    hashes = inputs.hashes()
    added = ["experiments/shared_full_store/run.py", "experiments/shared_full_store/results/discovery_paths.csv.gz",
             "src/online_trade/clustering/features.py", "src/online_trade/clustering/methods.py",
             "../1122/retail_data.py"]
    return hashes | {name: common.sha(repo / name) for name in added}


def validation(repo, common, inputs, out):
    assert common.sha(HERE / "README.md") == common.read_json(out / "discovery_audit.json")["protocol_sha256"]
    data = pd.read_csv(inputs.local / "validation_baskets.csv", dtype=str, keep_default_na=False)
    validation_window = common.read_json(repo / "configs/experiment.json")["validation"]
    period = common.Period(data, inputs.taxonomy, inputs.profile, validation_window)
    assert [period.audit[k] for k in common.STRATA] == [8067, 4862, 2502, 703]
    frame = common.read_csv(out / "discovery_paths.csv.gz")
    systems, rules, _ = common.coverage_systems(inputs, period, frame, 10)
    metrics = [*common.MEASURES, "quality_pass_share", "strict_quality_pass_share",
               "raw_coverage_gain_pp", "reliable_coverage_gain_pp"]
    ranking = selections(systems)
    choice = ranking.loc[ranking.selection.eq("common")].iloc[0]
    picked = frame.loc[frame.config.eq(choice.config) & frame.position.le(choice.budget)]
    popular = common.read_csv(out / "discovery_popularity.csv").l2_id.tolist()
    top, _, _ = common.recommend(repo, period, picked, popular)
    for name, table in {"validation_systems": systems, "validation_GL_quality": rules, "validation_ranking": ranking,
        "validation_A1": summary(common, systems, ["config", "budget"], metrics), "validation_recommendation": top}.items():
        common.csv(table, out / f"{name}.csv")
    common.write_json(out / "validation_audit.json", {
        "sample": period.audit, "rows": len(systems), "test_accessed_for_evaluation": False,
        "common_selection": {"config": choice.config, "budget": int(choice.budget), "score_pp": float(choice.score_pp)},
        "runner_sha256": common.sha(Path(__file__)), "input_hashes": input_hashes(repo, common, inputs),
        "path_sha256": common.sha(out / "discovery_paths.csv.gz"),
    })
    print("Validation choice:", choice.config, int(choice.budget), flush=True)


def freeze(repo, common, inputs, out):
    assert not (out / "freeze.json").exists()
    audit = common.read_json(out / "validation_audit.json")
    assert audit["runner_sha256"] == common.sha(Path(__file__))
    assert audit["input_hashes"] == input_hashes(repo, common, inputs)
    assert audit["path_sha256"] == common.sha(out / "discovery_paths.csv.gz")
    assert not audit["test_accessed_for_evaluation"]
    rank = common.read_csv(out / "validation_ranking.csv")
    row = rank.loc[rank.selection.eq("common") & rank["rank"].eq(1)].iloc[0]
    p, b = row.config, int(row.budget)
    roster = common.read_csv(out / "discovery_paths.csv.gz").query("config == @p and position <= @b")
    verify_rosters(common, roster, {p: b})
    common.csv(roster, out / "frozen_rule_lists.csv")
    original = common.read_json(repo / "configs/test_frozen.json")
    filenames = ["profile_audit.json", "discovery_audit.json", "discovery_popularity.csv", "validation_audit.json",
                 "validation_ranking.csv", "frozen_rule_lists.csv"]
    common.write_json(out / "freeze.json", {
        "recorded_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "evidence": "historical Test supplementary evaluation",
        "selection": {"config": p, "budget": b, "score_pp": float(row.score_pp), "cost_pp_per_10": .5},
        "test_window": original["test_window"], "a_snapshot_commit": original["a_snapshot_commit"],
        "source_baskets_sha256": original["source_baskets_sha256"], "quality": common.QUALITY,
        "strict_quality": common.STRICT_QUALITY, "bootstrap": common.BOOTSTRAP,
        "runner_sha256": audit["runner_sha256"], "protocol_sha256": common.sha(HERE / "README.md"),
        "input_hashes": audit["input_hashes"], "artifact_hashes": {name: common.sha(out / name) for name in filenames},
    })
    print(f"Frozen {p}/{b} for 304 rule lists.", flush=True)


def test(repo, common, inputs, out):
    spec = common.read_json(out / "freeze.json")
    assert spec["runner_sha256"] == common.sha(Path(__file__))
    assert spec["protocol_sha256"] == common.sha(HERE / "README.md")
    assert spec["input_hashes"] == input_hashes(repo, common, inputs)
    assert all(common.sha(out / name) == digest for name, digest in spec["artifact_hashes"].items())
    dest = out / "test"
    assert not dest.exists()
    frame = common.read_csv(out / "frozen_rule_lists.csv")
    p, b = spec["selection"]["config"], spec["selection"]["budget"]
    verify_rosters(common, frame, {p: b})
    period = common.test_period(inputs, spec)
    assert [period.audit[k] for k in common.STRATA] == [10890, 5730, 4532, 628]
    systems, rules, masks = common.coverage_systems(inputs, period, frame, b)
    popular = common.read_csv(out / "discovery_popularity.csv").l2_id.tolist()
    top, hits, eligible = common.recommend(repo, period, frame, popular)
    top_all = top.loc[top["sample"].eq("all")]
    metrics = [*common.MEASURES, "quality_pass_share", "strict_quality_pass_share", "accepted_store_coverage"]
    cover_summary = summary(common, systems, ["config", "budget"], metrics)
    top_summary = summary(common, top, ["sample", "top_orders"], ["hit_at_5", "ndcg_at_5"])
    runs, index_map = [], {}
    references = [("G", v) for v in VARIANTS] + list(combinations(VARIANTS, 2))
    for left, right in references:
        for i, measure in enumerate(common.MEASURES):
            label = f"{right}_minus_{left}:{measure}"
            index = period.store if i == 0 else period.identified
            runs.append((label, masks[left, p, b][i], masks[right, p, b][i], index.all))
            index_map[label] = index
    for left, right in references + [("popular", method) for method in ("G", *VARIANTS)]:
        label = f"{right}_minus_{left}:hit_at_5"
        a = ("BASE", "popular", "") if left == "popular" else ("GL", left, "")
        runs.append((label, hits[a], hits["GL", right, ""], eligible))
        index_map[label] = period.store
    intervals = common.intervals(period, runs, index_map).rename(columns={"L_minus_G": "difference"})
    dest.mkdir()
    tables = {"systems": systems, "GL_quality": rules, "coverage_comparisons": cover_summary,
              "recommendation": top, "recommendation_comparisons": top_summary, "paired_intervals": intervals}
    for name, table in tables.items():
        common.csv(table, dest / f"{name}.csv")
    common.write_json(dest / "audit.json", {"sample": period.audit, "systems": len(systems),
        "unable_to_fill_five": int((top_all.top_orders - top_all.five_recommendation_orders).max()),
        "freeze_sha256": common.sha(out / "freeze.json")})
    print("Test finished for all three partitions.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("discovery", "validation", "freeze", "test"))
    parser.add_argument("--repo", type=Path, default=HERE.parent / "repository")
    parser.add_argument("--out", type=Path, default=HERE / "results")
    args = parser.parse_args()
    repo, out = args.repo.resolve(), args.out.resolve()
    sys.path.insert(0, str(repo / "src"))
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("shared_d", repo / "experiments/shared_full_store/run.py")
    common = module_from_spec(spec)
    spec.loader.exec_module(common)
    out.mkdir(parents=True, exist_ok=True)
    globals()[args.action](repo, common, common.Inputs(repo), out)


if __name__ == "__main__":
    main()
