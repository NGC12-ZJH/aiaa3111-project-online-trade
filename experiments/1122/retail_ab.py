"""Routes A and B. Static customer groups, seasonal diagnostics, and fixed Slot-5."""
from collections import Counter
from io import BytesIO
import subprocess
import json
from pathlib import Path

import numpy as np
import pandas as pd

from retail_data import CUTOFF, DISCOVERY_END, PROFILE_END, SNAPSHOT, FormCluster, asof_profile, build_view, \
    frequency_groups, group_random, price_bands
from retail_rules import GROUPS, Arena, Book, Paired, SharedQuality, direct_pool, full_hits, greedy, \
    portion, quotas, report_hits, scored, select, split_masks, union

RFM = ["recency", "frequency", "monetary"]
FORM = ["qty", "skus", "concentration", "price", "low", "high"]
BUDGETS = (20, 50, 100)


def labels_for(frame, mapping):
    return frame.customer_id.map(mapping).fillna("").to_numpy()


def make_groups(profile):
    freq, frequency_cuts = frequency_groups(profile)
    result = {"frequency": freq}
    for name, columns in (
        ("rfm", RFM), ("rfm_form", RFM + FORM), ("rfm_form_country", RFM + FORM + ["nonuk", "country_missing"]),
        ("rfm_form_cancel", RFM + FORM + ["cancel_share"]),
    ):
        log = [i for i, c in enumerate(columns) if c in ("frequency", "monetary", "qty", "skus", "price")]
        result[name] = FormCluster(profile[columns], log).labels
    return result, frequency_cuts


def choose(book, ranked, sizes, budget, identity, mode="native", blocked=(), m=0):
    return select(book, {g: scored(book, ranks, mode, blocked, m) for g, ranks in ranked.items()},
                  sizes, budget, identity)


def count_groups(scopes):
    return {g: mask.bit_count() for g, mask in scopes.items()}


def coverage_strata(val_index, view):
    flags = {
        "all": np.ones(len(view), dtype=bool), "winter": view.date.lt("2011-03-01"),
        "spring": view.date.ge("2011-03-01"),
        "seasonal_order": view.seasonal_order, "evergreen_order": ~view.seasonal_order,
    }
    return {name: split_masks(np.where(f, name, ""), [name])[name] for name, f in flags.items()}


def global_quality_rows(book, val, pool, quality, scopes, base, row):
    accepted, passes = quality.evaluate(pool)
    raw = full_hits(book, pool, val)
    baseraw, basegood = base
    masks = val.by_customer.values()
    covered = np.array([(raw & m).bit_count() / m.bit_count() for m in masks])
    reliable = np.array([(accepted & m).bit_count() / m.bit_count() for m in masks])
    records = []
    for partition, scope in scopes.items():
        a = report_hits({**row, "partition": partition, "metric": "raw"}, raw, baseraw, scope)
        b = report_hits({**row, "partition": partition, "metric": "quality_v1"}, accepted, basegood, scope)
        if partition == "all":
            a["customer_macro"] = covered.mean()
            b["customer_macro"] = reliable.mean()
        records.extend(
            {**r, "selected_rules": len(pool), "accepted_rules_all_validation": passes,
             "accepted_share_all_validation": portion(passes, len(pool))}
            for r in (a, b)
        )
    return records, (raw, accepted)


def quality_family_diagnostic(book, validation, pool, seasonal, view):
    records = []
    for month in sorted(view.date.str[:7].unique()):
        monthmask = split_masks(view.date.str[:7], [month])[month]
        for pick in pool:
            r = book.rules[pick.stats.key]
            ant = validation.mask(r.antecedent) & monthmask
            outcome = validation.items.get(r.consequent, 0) & monthmask
            hits = (ant & outcome).bit_count()
            n = monthmask.bit_count()
            confidence = portion(hits, ant.bit_count())
            baseline = portion(outcome.bit_count(), n)
            records.append({
                "month": month, "orders": n, "rule_id": r.identifier,
                "seasonal_exposed": any(x in seasonal for x in r.combination),
                "antecedent_orders": ant.bit_count(), "joint_orders": hits, "confidence": confidence,
                "background": baseline, "added_value": confidence - baseline,
                "discovery_confidence": pick.stats.confidence, "confidence_change": confidence - pick.stats.confidence,
            })
    return records


def purchase_season(retail, train):
    totals, seasonal = Counter(), Counter()
    for invoice in train.id:
        for _, category, _, _, tag in retail.items[invoice]:
            if category == "other":
                continue
            totals[category] += 1
            if tag not in ("", "none", "unknown"):
                seasonal[category] += 1
    return pd.DataFrame([
        {"category": category, "discovery_lines": count, "seasonal_discovery_lines": seasonal[category],
         "seasonal_share": seasonal[category] / count, "seasonal_exposed": seasonal[category] / count >= .2}
        for category, count in sorted(totals.items())
    ])


def original_replay(repo, book, val, disc, view):
    source = f"{SNAPSHOT}:data/processed/B_customer_clustering/customer_clusters.csv"
    raw = subprocess.check_output(["git", "-C", str(repo), "show", source])
    labels = pd.read_csv(BytesIO(raw), dtype=str)
    mapping = dict(zip(labels.customer_id, labels.cluster_id))
    sizes, local = book.local(labels_for(disc, mapping))
    scopes = book.scopes(labels_for(view, mapping))
    allocation = quotas(count_groups(sizes), 100)
    lpicks = [p for g, ranks in local.items() for p in direct_pool(scored(book, ranks[:allocation[g]], "native"), g)]
    gpicks = direct_pool(scored(book, book.global_ranks[:100], "native"))
    actual = {"G": full_hits(book, gpicks, val).bit_count(),
              "L_restricted": full_hits(book, lpicks, val, scopes).bit_count(),
              "L_shared": full_hits(book, lpicks, val).bit_count()}
    official = pd.read_csv(repo / "results/tables/validation/GL_summary.csv").query("config == 'P5' and budget == 100")
    expected = {"G": int(official.query("method == 'G' and flow == 'restricted'").covered_orders.iloc[0]),
                "L_restricted": int(official.query("method == 'L' and flow == 'restricted'").covered_orders.iloc[0]),
                "L_shared": int(official.query("method == 'L' and flow == 'shared'").covered_orders.iloc[0])}
    assert actual == expected, (actual, expected)
    return actual


def compare_random(frame, prefix, primary_metric, index):
    method_col = "system"
    rows = []
    for key, group in frame.groupby(index):
        for name in sorted(group.loc[group[method_col].str.startswith(prefix), method_col].unique()):
            family = name.removeprefix(prefix)
            r = group.loc[group[method_col].eq(name), primary_metric].dropna()
            ref = group.loc[group[method_col].eq(family), primary_metric]
            if len(ref) != 1 or r.empty:
                continue
            val = float(ref.iloc[0])
            rows.append({"metric": primary_metric, **dict(zip(index, key)), "real": family, "L": val,
                         "random_n": len(r), "A1_min": r.min(), "A1_median": r.median(), "A1_max": r.max(),
                         "A1_ge_L": int(r.ge(val).sum())})
    return pd.DataFrame(rows)


def route_ab(repo, out, retail, modules, seed_count):
    BasketIndex = modules[0]
    output = out / "route_ab"
    output.mkdir(exist_ok=True, parents=True)
    profile_orders = retail.between("2009-12-01", PROFILE_END)
    price = price_bands(retail, profile_orders)
    profile = asof_profile(retail, PROFILE_END, price)
    disc = build_view(retail, retail.between(PROFILE_END, DISCOVERY_END, set(profile.index)), price)
    view = build_view(retail, retail.between(DISCOVERY_END, CUTOFF, set(profile.index)), price)
    assert len(profile) == 2684 and len(disc) == 7521 and len(view) == 4862
    book = Book(disc, modules)
    val = BasketIndex(view.customer_id, view.basket)
    quality = SharedQuality(book, val, modules)
    original = original_replay(repo, book, val, disc, view)
    print("A: frozen G and L baseline reconciled", original, flush=True)
    groupings, freq_cuts = make_groups(profile)
    summaries, sizes_rows, all_pools, mask_cache = [], [], {}, {}
    coverage_scopes = coverage_strata(val, view)
    bases = {}
    for b in BUDGETS:
        for mode in ("direction", "combination"):
            pool = choose(book, {"GLOBAL": book.global_ranks}, {"GLOBAL": len(disc)}, b, mode)
            bases[b, mode] = full_hits(book, pool, val), quality.evaluate(pool)[0]
            rows, masks = global_quality_rows(book, val, pool, quality, coverage_scopes, bases[b, mode],
                                              {"system": "global", "seed": "", "budget": b, "identity": mode})
            summaries.extend(rows)
            mask_cache["global", b, mode] = masks
            all_pools["global", b, mode] = pool

    arena = Arena(view)
    full_pop = arena.popular(book)
    g_native = direct_pool(scored(book, book.global_ranks[:100], "native"))
    g_proposals = arena.proposals(book, g_native)
    g_base = arena.replay(g_proposals + full_pop)
    assert g_base[1][5] == arena.all
    g_hits = union(g_base[0])
    blocked = {p.stats.key for p in g_native}
    slot_rows, slot_masks, policy_rows = [], {}, []
    rec_scopes = {"all": arena.all, **{k: v & arena.all for k, v in coverage_scopes.items() if k != "all"}}

    def policy(name, proposals, seed="", report=True):
        result = arena.replay(proposals)
        assert result[1][5] == arena.all, name
        if report:
            for label, scope in rec_scopes.items():
                row = report_hits({"system": name, "seed": seed, "partition": label}, union(result[0]), g_hits, scope)
                row["ndcg5"] = portion(sum((x & scope).bit_count() / np.log2(i + 2)
                                           for i, x in enumerate(result[0])), scope.bit_count())
                policy_rows.append(row)
        return result

    def add_slot(name, proposals, seed="", m="", assign=None):
        result, changed, eligible = arena.slot5(g_base, proposals)
        masks = rec_scopes if assign is None else {**rec_scopes, **{
            f"C{i}": (scope & arena.all) for i, scope in assign.items()}}
        for label, mask in masks.items():
            row = report_hits({"system": name, "seed": seed, "partition": label, "shrink_m": m}, result, g_hits, mask)
            row["eligible_for_takeover"] = (eligible & mask).bit_count()
            row["replaced_fifth"] = (changed & mask).bit_count()
            slot_rows.append(row)
        if seed == "":
            slot_masks[name] = result

    policy("global_popularity", full_pop)
    policy("global_rules_plus_global_pop", g_proposals + full_pop)
    for name, ranks in [("global_tail", scored(book, book.global_ranks[100:200], "native")),
                        ("global_added", scored(book, book.global_ranks, "added", blocked)[:100])]:
        add_slot(name, arena.proposals(book, direct_pool(ranks)))

    def add_system(name, mapping, seed=""):
        d_scope, ranks = book.local(labels_for(disc, mapping))
        v_scope = book.scopes(labels_for(view, mapping))
        sizes = count_groups(d_scope)
        if seed == "":
            for group, n in sizes.items():
                sizes_rows.append({"system": name, "group": group, "profile_customers": sum(v == group for v in mapping.values()),
                                   "discovery_orders": n, "validation_orders": v_scope[group].bit_count()})
        for b in BUDGETS:
            for mode in ("direction", "combination"):
                pool = choose(book, ranks, sizes, b, mode)
                rows, masks = global_quality_rows(
                    book, val, pool, quality, coverage_scopes, bases[b, mode],
                    {"system": name, "seed": seed, "budget": b, "identity": mode},
                )
                summaries.extend(rows)
                if seed == "":
                    mask_cache[name, b, mode] = masks
                    all_pools[name, b, mode] = pool
                if b == 100 and mode == "direction" and seed == "":
                    restricted = full_hits(book, pool, val, v_scope)
                    summaries.append(report_hits(
                        {"system": name, "seed": seed, "budget": b, "identity": mode, "partition": "all",
                         "metric": "raw_restricted", "selected_rules": len(pool)}, restricted, bases[b, mode][0], val.all
                    ))

        if name in ("rfm_form", "A1_rfm_form"):
            shared_pool = choose(book, ranks, sizes, 100, "direction")
            local_pop = arena.popular(book, d_scope, v_scope)
            limited = arena.proposals(book, shared_pool, v_scope)
            policy(name + "_group_pop", local_pop, seed)
            policy(name + "_rules_plus_global_pop", limited + full_pop, seed)
            policy(name + "_rules_plus_group_pop", limited + local_pop, seed)
            for mode in ("added", "gap"):
                pool = choose(book, ranks, sizes, 100, "direction", mode, blocked)
                add_slot(name + "_" + mode + "_shared", arena.proposals(book, pool), seed,
                         assign=v_scope if seed == "" else None)
                add_slot(name + "_" + mode + "_restricted", arena.proposals(book, pool, v_scope), seed,
                         assign=v_scope if seed == "" else None)
            if seed == "":
                pool = choose(book, ranks, sizes, 100, "direction", "added", blocked)
                calibration = []
                for m in (0, 20, 50, 100):
                    shrunk = []
                    err, trials = 0., 0
                    for pick in pool:
                        r = book.rules[pick.stats.key]
                        confidence = (pick.stats.joint + m * book.prior(pick.stats.key)) / (pick.stats.total + m)
                        scoped = v_scope[pick.group]
                        triggered = val.mask(r.antecedent) & scoped
                        matched = triggered & val.items.get(r.consequent, 0)
                        a, j = triggered.bit_count(), matched.bit_count()
                        err += j * (1 - confidence) ** 2 + (a - j) * confidence ** 2
                        trials += a
                        shift = confidence - (pick.stats.confidence - pick.stats.added)
                        shrunk.append(type(pick)(pick.group, pick.stats, float(shift)))
                    calibration.append({"m": m, "brier": portion(err, trials), "rule_order_trials": trials,
                                        "selection_pool": "fixed_local_added", "flow": "restricted"})
                    add_slot(f"rfm_form_shrunk_m{m}", arena.proposals(book, shrunk, v_scope), m=m)
                    add_slot(f"rfm_form_shrunk_shared_m{m}", arena.proposals(book, shrunk), m=m)
                pd.DataFrame(calibration).to_csv(output / "shrinkage_calibration.csv", index=False)

    for name, labels in groupings.items():
        add_system(name, dict(zip(profile.index, map(str, labels))))
    print("A/B: actual frequency, RFM, form, country and cancellation arms completed", flush=True)

    for seed in range(1000, 1000 + seed_count):
        for version in ("rfm_form", "rfm"):
            add_system("A1_" + version, group_random(profile, groupings[version], seed), seed)
        if (seed - 999) % 20 == 0:
            print(f"A/B: {seed - 999}/{seed_count} A1 seeds per RFM variant", flush=True)

    # Match the early candidate window for both budget selectors; maximize only on later Discovery.
    early = disc.loc[disc.date.lt("2010-10-01")].reset_index(drop=True)
    objective_view = disc.loc[disc.date.ge("2010-10-01")].reset_index(drop=True)
    greedy_book = Book(early, modules)
    objective = BasketIndex(objective_view.customer_id, objective_view.basket)
    greedy_results = []

    def greedy_pair(name, ranks, sizes, scope_obj, seed=""):
        native = choose(greedy_book, ranks, sizes, 100, "combination")
        all_candidates = [p for g, group in ranks.items() for p in direct_pool(scored(greedy_book, group, "native"), g)]
        # Bounded candidate frontier per group, applied to both selectors.
        native_keys = {(p.group, p.stats.key) for p in native}
        frontier = []
        per_group = Counter()
        for pick in all_candidates:
            if per_group[pick.group] < 500 or (pick.group, pick.stats.key) in native_keys:
                frontier.append(pick)
            per_group[pick.group] += 1
        chosen = greedy(greedy_book, frontier, objective, 100, scope_obj)
        ref = full_hits(greedy_book, native, val)
        for algorithm, pool in (("native", native), ("greedy", chosen)):
            hit = full_hits(greedy_book, pool, val)
            greedy_results.append({
                **report_hits({"system": name, "seed": seed, "algorithm": algorithm}, hit, ref, val.all),
                "rules": len(pool), "candidate_frontier": len(frontier),
                "discovery_objective_hits": full_hits(greedy_book, pool, objective).bit_count(),
            })

    greedy_pair("global", {"GLOBAL": greedy_book.global_ranks}, {"GLOBAL": len(early)}, None)
    for seed in [""] + list(range(1000, 1000 + seed_count)):
        labels = groupings["rfm_form"]
        mapping = dict(zip(profile.index, map(str, labels))) if seed == "" else group_random(profile, labels, seed)
        dsc, ranks = greedy_book.local(labels_for(early, mapping))
        greedy_pair("rfm_form" if seed == "" else "A1_rfm_form", ranks, count_groups(dsc), None, seed)
        if seed != "" and (seed - 999) % 20 == 0:
            print(f"B: {seed - 999}/{seed_count} A1 matched greedy selections", flush=True)

    summaries = pd.DataFrame(summaries)
    paired_results = []
    for partition in ("all", "winter", "spring"):
        subset = coverage_scopes[partition]
        interval = Paired(view, subset)
        for name in groupings:
            for i, label in enumerate(("raw", "quality_v1")):
                left = mask_cache[name, 100, "combination"][i]
                for ref in ["global"] + (["rfm", "frequency"] if name == "rfm_form" else []):
                    right = mask_cache[ref, 100, "combination"][i]
                    paired_results.append({
                        **report_hits({"system": name, "reference": ref, "partition": partition, "metric": label},
                                      left, right, subset), **interval.interval(left, right),
                    })
    rollout = []
    for partition in ("all", "winter", "spring"):
        subset = rec_scopes[partition]
        interval = Paired(view, subset)
        for name, hits in slot_masks.items():
            rollout.append({**report_hits({"system": name, "partition": partition}, hits, g_hits, subset),
                            **interval.interval(hits, g_hits)})
        for name in ("rfm_form_added_shared", "rfm_form_gap_shared", "rfm_form_gap_restricted"):
            a, b = slot_masks[name], slot_masks["global_tail"]
            rollout.append({**report_hits({"system": name + "_vs_global_tail", "partition": partition}, a, b, subset),
                            **interval.interval(a, b)})

    season = purchase_season(retail, disc)
    season.to_csv(output / "a_season_categories.csv", index=False)
    seasonal = set(season.loc[season.seasonal_exposed, "category"])
    monthly = quality_family_diagnostic(book, val, all_pools["global", 100, "combination"], seasonal, view)
    # Prior-year comparison is retrospective; the rule list was discovered later.
    prior = build_view(retail, retail.between("2009-12-01", PROFILE_END, set(profile.index)), price)
    prior_ix = BasketIndex(prior.customer_id, prior.basket)
    monthly += quality_family_diagnostic(book, prior_ix, all_pools["global", 100, "combination"], seasonal, prior)
    pd.DataFrame(monthly).to_csv(output / "a_season_monthly_rules.csv", index=False)
    pd.DataFrame(sizes_rows).to_csv(output / "a_group_sizes.csv", index=False)
    summaries.to_csv(output / "a_systems.csv", index=False)
    compare_random(summaries, "A1_", "rate", ["budget", "identity", "partition", "metric"]).to_csv(
        output / "a_random_summary.csv", index=False)
    pd.DataFrame(paired_results).to_csv(output / "a_paired_intervals.csv", index=False)
    pd.DataFrame(policy_rows).to_csv(output / "b_top5_policies.csv", index=False)
    slots = pd.DataFrame(slot_rows)
    slots.to_csv(output / "b_slot5_systems.csv", index=False)
    compare_random(slots, "A1_", "delta_pp", ["partition", "shrink_m"]).to_csv(
        output / "b_slot5_random_summary.csv", index=False)
    pd.DataFrame(rollout).to_csv(output / "b_slot5_paired_intervals.csv", index=False)
    pd.DataFrame(greedy_results).to_csv(output / "b_greedy.csv", index=False)
    (output / "ab_manifest.json").write_text(json.dumps(
        {"original_validation_reproduced": original, "rule_config": "P5", "budgets": BUDGETS,
         "seeds_for_each_RFM_variant": seed_count, "frequency_split_inclusive": freq_cuts,
         "profile_customers": len(profile), "discovery_orders": len(disc), "validation_orders": len(view),
         "masked_orders": arena.all.bit_count(), "profile_price_bands": price,
         "greedy_first_window_orders": len(early), "greedy_objective_orders": len(objective_view)},
        indent=2, ensure_ascii=False
    ), encoding="utf-8")
    print("A/B: outputs verified and written", flush=True)
