"""Two pre-Test experiments: score fusion and temporal/seasonal updates."""
import argparse
from collections import Counter, defaultdict
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

PIVOT = "2011-03-01"
FOLDS = (
    ("winter", "2010-12-01", "2011-03-01"),
    ("early_spring", "2011-03-01", "2011-05-01"),
    ("late_spring", "2011-05-01", "2011-06-01"),
)
GRID = (
    (1., .25, .25), (1., .25, 1.), (1., .25, 3.),
    (1., .5, .25), (1., .5, 1.), (1., .5, 3.),
    (1., 1., .25), (1., 1., 1.), (1., 1., 3.),
    (1., 0., .25), (1., 0., 1.), (1., 0., 3.),
)
SEASONS = {"christmas": {10, 11, 12}, "easter": {3, 4}}
SEASON_CUTS = {.65: "strict", .35: "s35", .20: "s20"}


def array(mask, n):
    p = np.frombuffer(mask.to_bytes((n + 7) // 8, "little"), dtype=np.uint8)
    return np.unpackbits(p, count=n, bitorder="little").astype(bool)


def to_mask(values):
    return int.from_bytes(np.packbits(values, bitorder="little").tobytes(), "little")


def conditional_prior(arena, book, keys, l1, categories):
    counts = np.array([book.orders.items[c].bit_count() for c in categories], dtype=float)
    prior = counts / counts.sum()
    by_context = {}
    for key in sorted(set(keys)):
        histogram = l1.get(key, Counter())
        v = np.array([histogram[c] for c in categories], dtype=float)
        by_context[key] = (v + 30 * prior) / (v.sum() + 30)
    return np.stack([by_context[k] for k in keys])


def feature_blocks(arena, book, pool, category_position, scopes=None, shrink=0):
    entries = defaultdict(list)
    for pick in pool:
        key = pick.stats.key
        rule = book.rules[key]
        trigger = arena.antecedent(rule.antecedent) & ~arena.observed[rule.consequent]
        if scopes is not None:
            trigger &= scopes[pick.group]
        conf = (pick.stats.joint + shrink * book.prior(key)) / (pick.stats.total + shrink)
        entries[rule.consequent].append((conf, frozenset(rule.antecedent), trigger, rule.identifier))
    p1 = np.zeros((arena.n, len(category_position)))
    p2 = np.zeros_like(p1)
    comparable = 0
    for c, rows in entries.items():
        first, second = 0, 0
        sources = []
        for confidence, ant, mask, rid in sorted(rows, key=lambda x: (-x[0], x[3])):
            correlated = union(mask0 for ant0, mask0 in sources if ant0 & ant)
            add = mask & first & ~correlated & ~second
            if add:
                p2[array(add, arena.n), category_position[c]] = confidence
                second |= add
            best = mask & ~first
            if best:
                p1[array(best, arena.n), category_position[c]] = confidence
                sources.append((ant, best))
                first |= best
        comparable |= second
    return {"max": p1, "discounted": p1 + .5 * (1 - p1) * p2,
            "multi_evidence_rows": comparable}


def run_fusion(out, arena, view, book, main, l1, baseline, gated_tail, g_head, g_tail, local, vsc):
    categories = sorted(book.orders.items)
    indices = {c: i for i, c in enumerate(categories)}
    early = arena.subset(view.date.lt(PIVOT))
    late = arena.subset(view.date.ge(PIVOT))
    upper = Paired(view, late)
    pop = conditional_prior(arena, book, main, l1, categories)
    seen = np.stack([array(arena.observed[c], len(view)) for c in categories], axis=1)
    targets = np.array([indices.get(t, -1) for t in view.target])
    unavailable = int((targets[array(arena.all, len(view))] < 0).sum())
    head = feature_blocks(arena, book, g_head, indices)
    extras = {
        "G100": None,
        "G200": feature_blocks(arena, book, g_tail, indices),
        "G100_L100_restricted": feature_blocks(arena, book, local, indices, vsc, shrink=50),
        "G100_L100_shared": feature_blocks(arena, book, local, indices, shrink=50),
    }

    def predict(score):
        score[seen] = -np.inf
        positions = np.argsort(-score, axis=1, kind="stable")[:, :5]
        found = positions == targets[:, None]
        hit = to_mask(found.any(axis=1)) & arena.all
        rank_n = [to_mask(found[:, i]) & arena.all for i in range(5)]
        assert union(rank_n) == hit
        return hit, rank_n

    tuning, eval_rows, paired = [], [], []
    chosen_masks = {"G_prior_order": baseline}
    specifications = ["max", "discounted"]
    for name, extra in extras.items():
        name_results = {}
        for mode in specifications:
            combinations = [w for w in GRID if (w[1] == 0) == (extra is None)]
            for idx, w in enumerate(combinations):
                score = w[0] * head[mode] + w[2] * pop
                if extra:
                    score += w[1] * extra[mode]
                hit, ranks = predict(score)
                detail = {"arm": name, "aggregation": mode, "w_G": w[0], "w_extra": w[1], "w_pop": w[2]}
                val = (hit & early).bit_count()
                tuning.append({**report_hits(detail, hit, baseline, early), "weight_index": idx})
                name_results[mode, idx] = (val, hit, ranks, detail)
        best_modes = {}
        for mode in specifications:
            specs = [(j, x) for (m, j), x in name_results.items() if m == mode]
            j, best = min(specs, key=lambda x: (-x[1][0], x[0]))
            best_modes[mode] = best
            hit, rk, detail = best[1:]
            data = report_hits(detail, hit, baseline, late)
            data.update(upper.interval(hit, baseline))
            data["ndcg5_late"] = sum((late & m).bit_count() / np.log2(i + 2) for i, m in enumerate(rk)) / late.bit_count()
            multi = head["multi_evidence_rows"] | (extra["multi_evidence_rows"] if extra else 0)
            data["late_any_disjoint_evidence"] = (late & multi).bit_count()
            eval_rows.append(data)
        mode = min(specifications, key=lambda m: (-best_modes[m][0], specifications.index(m)))
        chosen_masks[name] = best_modes[mode][1]
        chosen = best_modes[mode][3]
        print("Fusion", name, mode, chosen, flush=True)
        for row in eval_rows:
            if row["arm"] == name:
                row["aggregation_selected_on_early"] = row["aggregation"] == mode
        d, m = best_modes["discounted"][1], best_modes["max"][1]
        paired.append({**report_hits({"left": name + "_discounted", "right": name + "_max"}, d, m, late),
                       **upper.interval(d, m)})

    reference = chosen_masks["G200"]
    for arm in ("G100_L100_restricted", "G100_L100_shared"):
        hits = chosen_masks[arm]
        paired.append({**report_hits({"left": arm, "right": "G200"}, hits, reference, late),
                       **upper.interval(hits, reference)})
    for arm in ("G200", "G100_L100_restricted", "G100_L100_shared"):
        hits = chosen_masks[arm]
        paired.append({**report_hits({"left": arm, "right": "prior_gated_g_tail"}, hits, gated_tail, late),
                       **upper.interval(hits, gated_tail)})
    pd.DataFrame(tuning).to_csv(out / "fusion_tuning.csv", index=False)
    pd.DataFrame(eval_rows).to_csv(out / "fusion_late.csv", index=False)
    pd.DataFrame(paired).to_csv(out / "fusion_paired.csv", index=False)
    return {"fusion_early": early.bit_count(), "fusion_late": late.bit_count(),
            "fusion_baseline_late_hits": (baseline & late).bit_count(), "unavailable_targets": unavailable, "prior_gated_g_tail_late_hits": (gated_tail & late).bit_count()}


def seasonal_categories(retail, training):
    totals, seasonal = Counter(), defaultdict(Counter)
    for invoice in training.id:
        for _, item, _, _, season in retail.items[invoice]:
            if item == "other":
                continue
            totals[item] += 1
            if season in SEASONS:
                seasonal[item][season] += 1
    rows = []
    flags = {name: {} for name in SEASON_CUTS.values()}
    for item, n in sorted(totals.items()):
        for season in SEASONS:
            tagged = seasonal[item][season]
            weights = {f"used_{name}": tagged >= 20 and tagged / n >= cut for cut, name in SEASON_CUTS.items()}
            rows.append({"category": item, "season": season, "tagged_discovery_lines": tagged,
                         "discovery_lines": n, "share": tagged / n, **weights})
            for name in flags:
                if weights[f"used_{name}"]:
                    assert item not in flags[name]
                    flags[name][item] = season
    return flags, rows


def run_temporal(out, retail, arena, view, historical, book, original, l1_picks, head, training):
    flags, audit = seasonal_categories(retail, training)
    pd.DataFrame(audit).to_csv(out / "season_flags.csv", index=False)
    hlives = {"exp90": 90, "exp180": 180, "exp365": 365}
    timestamps = pd.to_datetime(historical.invoice_datetime)
    categories = list(book.orders.items)
    train_x = {c: np.array([c in basket for basket in historical.basket]) for c in categories}
    ground = {}
    for pick in head:
        r = book.rules[pick.stats.key]
        a = np.logical_and.reduce([train_x[i] for i in r.antecedent])
        ground[pick.stats.key] = a, a & train_x[r.consequent]
    choices = {name: 0 for name in ["fixed", "expanding_equal", *hlives]}
    seasonal_hits = {f"{base}_{policy}": 0 for base in ("fixed", "expanding_equal", *hlives)
                     for policy in SEASON_CUTS.values()}
    phase_rows, counts = [], []
    months = np.array(view.date.str[5:7], dtype=int)
    fold_masks = {}
    touched = defaultdict(int)
    ready = arena.all

    for fold, start, end in FOLDS:
        select_eval = arena.subset(view.date.ge(start) & view.date.lt(end))
        fold_masks[fold] = select_eval
        allowed = (timestamps < pd.Timestamp(start)).to_numpy()
        assert not (allowed & (timestamps >= pd.Timestamp(start)).to_numpy()).any()
        age = (pd.Timestamp(start) - timestamps).dt.total_seconds().to_numpy() / 86400
        weights = {"fixed": (timestamps < pd.Timestamp(DISCOVERY_END)).to_numpy().astype(float),
                   "expanding_equal": allowed.astype(float)}
        for name, days in hlives.items():
            weights[name] = np.where(allowed, np.exp2(-np.maximum(age, 0) / days), 0.)
        for name, weight in weights.items():
            rule_scores = []
            for pick in head:
                a, both = ground[pick.stats.key]
                j, n = weight[both].sum(), weight[a].sum()
                conf = j / n if n else 0.
                if name == "fixed":
                    assert abs(conf - pick.stats.confidence) < 1e-12
                rule_scores.append((pick, conf))
            p = []
            q = {policy: [] for policy in flags}
            seasonal_touched = dict.fromkeys(flags, 0)
            for pick, score in sorted(rule_scores, key=lambda x: (
                -x[1], -x[0].stats.joint, -x[0].stats.lift, book.rules[x[0].stats.key].identifier
            )):
                r = book.rules[pick.stats.key]
                mask = ready & arena.antecedent(r.antecedent) & ~arena.observed[r.consequent]
                p.append((r.consequent, mask))
                for policy, items in flags.items():
                    tag = items.get(r.consequent)
                    allowed_mask = mask
                    if tag:
                        vacation = arena.subset(~np.isin(months, list(SEASONS[tag])))
                        seasonal_touched[policy] |= mask & vacation & select_eval
                        allowed_mask &= ~vacation
                    q[policy].append((r.consequent, allowed_mask))
            main = arena.replay(p + l1_picks)
            assert main[1][5] == ready
            hit = union(main[0]) & select_eval
            choices[name] |= hit
            outcomes = [(name, hit)]
            for policy, proposals in q.items():
                other = arena.replay(proposals + l1_picks)
                assert other[1][5] == ready
                gated_hit = union(other[0]) & select_eval
                seasonal_name = f"{name}_{policy}"
                seasonal_hits[seasonal_name] |= gated_hit
                touched[policy] |= seasonal_touched[policy]
                outcomes.append((seasonal_name, gated_hit))
            for variant, hits in outcomes:
                phase_rows.append(report_hits({"fold": fold, "train_end_exclusive": start,
                                               "eval_end_exclusive": end, "arm": variant},
                                              hits, original, select_eval))
            counts.append({"fold": fold, "arm": name, "positive_weight_orders": int((weight > 0).sum()),
                           "effective_weighted_orders": weight.sum() ** 2 / (weight ** 2).sum(),
                           **{f"off_window_{policy}_orders": value.bit_count()
                              for policy, value in seasonal_touched.items()}})
    assert choices["fixed"] == original
    assert choices["fixed"] & fold_masks["winter"] == choices["expanding_equal"] & fold_masks["winter"]
    early = fold_masks["winter"]
    late = fold_masks["early_spring"] | fold_masks["late_spring"]
    selected = min(hlives, key=lambda h: (-(choices[h] & early).bit_count(), hlives[h]))
    interval = Paired(view, late)
    results = []
    for name, reference in (("expanding_equal", "fixed"), (selected, "fixed"), (selected, "expanding_equal")):
        all_masks = {**choices, **seasonal_hits}
        a, b = all_masks[name], all_masks[reference]
        results.append({**report_hits({"arm": name, "reference": reference}, a, b, late), **interval.interval(a, b)})
    diag = []
    for policy in flags:
        exposure = touched[policy] & late
        for label, subset in [("all", late), ("off_window_trigger", exposure)]:
            if not subset:
                continue
            for base in ("fixed", selected):
                name = f"{base}_{policy}"
                src = {**choices, **seasonal_hits}
                diag.append({**report_hits({"subset": label, "arm": name, "reference": base, "policy": policy},
                                           src[name], src[base], subset), **Paired(view, subset).interval(src[name], src[base])})
    pd.DataFrame(phase_rows).to_csv(out / "time_by_window.csv", index=False)
    pd.DataFrame(counts).to_csv(out / "time_effective_sample.csv", index=False)
    pd.DataFrame(results).to_csv(out / "time_late_paired.csv", index=False)
    pd.DataFrame(diag).to_csv(out / "season_late_paired.csv", index=False)
    print("Temporal selected", selected, "eligible seasonal categories", flags, flush=True)
    return {"half_life_selected_early": hlives[selected], "strong_seasonal_l2": flags,
            "late_off_season_trigger_orders": {name: (v & late).bit_count() for name, v in touched.items()}, "temporal_available_rows": len(historical)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "results")
    p.add_argument("--cache", type=Path)
    args = p.parse_args()
    project = args.project.resolve()
    sys.path.insert(0, str(project))
    global Arena, Book, Paired, report_hits, union, DISCOVERY_END
    from retail_rules import Arena, Book, Paired, report_hits, union, split_masks, runtime, scored, direct_pool
    from retail_data import find_repository, CUTOFF, DISCOVERY_END, PROFILE_END, asof_profile, price_bands, build_view, load_retail
    from retail_ab import choose, count_groups, labels_for, make_groups

    f = project / "followup_gating_l1_soft/run.py"
    spec = spec_from_file_location("earlier_l1_fallback", f)
    previous = module_from_spec(spec)
    spec.loader.exec_module(previous)
    previous.split_masks = split_masks
    previous.union = union

    repo = find_repository(args.project)
    args.out.mkdir(exist_ok=True, parents=True)
    with threadpool_limits(limits=1):
        rt = runtime(repo)
        retail = load_retail(repo, args.cache)
        profile_orders = retail.between("2009-12-01", PROFILE_END)
        price = price_bands(retail, profile_orders)
        profile = asof_profile(retail, PROFILE_END, price)
        groupings, _ = make_groups(profile)
        mapping = dict(zip(profile.index, map(str, groupings["rfm_form"])))
        training = build_view(retail, retail.between(PROFILE_END, DISCOVERY_END, set(profile.index)), price)
        view = build_view(retail, retail.between(DISCOVERY_END, CUTOFF, set(profile.index)), price)
        arena = Arena(view)
        assert (len(training), len(view), arena.all.bit_count()) == (7521, 4862, 4311)
        book = Book(training, rt)
        dm, dg, _ = previous.make_context(training, retail.taxonomy, mapping)
        vm, vg, tc = previous.make_context(view, retail.taxonomy, mapping)
        l1, joint = previous.conditional_tables(training, dm, dg)
        l1_picks = previous.contextual_proposals(arena, book, vm, vg, l1, joint, "l1")
        head = direct_pool(scored(book, book.global_ranks[:100], "native"))
        tail = direct_pool(scored(book, book.global_ranks[100:200], "native"))
        excluded = {p.stats.key for p in head}
        dsc, ranks = book.local(labels_for(training, mapping))
        vsc = book.scopes(labels_for(view, mapping))
        local = choose(book, ranks, count_groups(dsc), 100, "direction", "added", excluded)
        assert len(local) == len(tail) == len(head) == 100
        assert not excluded.intersection(p.stats.key for p in local)
        result = arena.replay(arena.proposals(book, head) + l1_picks)
        assert result[1][5] == arena.all
        baseline = union(result[0])
        ref = pd.read_csv(project / "followup_gating_l1_soft/results/fallback.csv")
        expected = int(ref.query("fallback == 'l1_pop' and policy == 'rules_plus_pop' and window == 'late'").hits.iloc[0])
        assert (baseline & arena.subset(view.date.ge(PIVOT))).bit_count() == expected == 660
        full_proposals = list(previous.info_proposals(arena, book, head))
        source = previous.fifth_sources(arena, full_proposals)
        frozen_tail = list(previous.info_proposals(arena, book, tail))
        gated_tail, _, _ = arena.slot5(result, previous.gate_lists(arena, source, frozen_tail, "weak", .45))
        assert (gated_tail & arena.subset(view.date.ge(PIVOT))).bit_count() == 684
        fusion = run_fusion(args.out, arena, view, book, vm, l1, baseline, gated_tail, head, tail, local, vsc)
        historical = pd.concat([training, view], ignore_index=True)
        assert historical.date.max() < CUTOFF
        temporal = run_temporal(args.out, retail, arena, view, historical, book, baseline, l1_picks, head, training)
        meta = {**fusion, **temporal, "validation_end_exclusive": CUTOFF,
                "max_source_order": retail.audit["maximum_date_in_analysis"], "baseline_l1_reproduced": True}
        (args.out / "checks.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(meta, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
