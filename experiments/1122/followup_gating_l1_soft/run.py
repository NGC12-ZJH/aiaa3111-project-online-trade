"""Validation-only Slot-5 gating, L1 backoff, and soft routing."""
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
import argparse
import json
import sys

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

PIVOT = "2011-03-01"


def ordered(book, pool):
    return sorted(pool, key=lambda p: (-p.score, -p.stats.joint, -p.stats.lift,
                                       book.rules[p.stats.key].identifier, p.group))


def info_proposals(arena, book, pool):
    for p in ordered(book, pool):
        r = book.rules[p.stats.key]
        mask = arena.antecedent(r.antecedent) & ~arena.observed[r.consequent]
        yield r.consequent, mask, p.stats.confidence


def fifth_sources(arena, proposals):
    """Record the score of the rule that actually occupies the fifth position."""
    occupied = [arena.all, 0, 0, 0, 0, 0]
    emitted = defaultdict(int)
    sources = []
    for category, mask, confidence in proposals:
        mask &= ~emitted[category] & ~occupied[5]
        fifth = mask & occupied[4]
        if fifth:
            sources.append((confidence, fifth, category))
        emitted[category] |= mask
        for rank in range(5, 0, -1):
            occupied[rank] |= mask & occupied[rank - 1]
    assert occupied[5] == sum(mask for _, mask, _ in sources)
    return sources, occupied[5]


def gate_lists(arena, source, candidates, kind, value=None):
    fallback = arena.all & ~source[1]
    if kind == "open":
        return [(c, m) for c, m, _ in candidates]
    if kind == "pop_only":
        return [(c, m & fallback) for c, m, _ in candidates]
    if kind == "weak":
        allowed = fallback | union(mask for confidence, mask, _ in source[0] if confidence < value)
        return [(c, m & allowed) for c, m, _ in candidates]
    if kind == "margin":
        return [(c, m & (fallback | union(mask for confidence, mask, _ in source[0]
                                         if p >= confidence + value))) for c, m, p in candidates]
    raise ValueError(kind)


def make_context(frame, taxonomy, group_mapping):
    cat_l1 = taxonomy.loc[taxonomy.l2_id.ne("other"), ["l2_id", "l1_id"]].drop_duplicates()
    assert not cat_l1.l2_id.duplicated().any()
    parent = dict(zip(cat_l1.l2_id, cat_l1.l1_id))

    def dominant(visible):
        counts = Counter(parent[x] for x in visible if x in parent)
        return min(counts, key=lambda x: (-counts[x], x)) if counts else "UNKNOWN"

    main = [dominant(v) for v in frame.observed]
    target_parent = [parent.get(t, "UNKNOWN") for t in frame.target]
    groups = frame.customer_id.map(group_mapping).fillna("UNKNOWN").tolist()
    return main, groups, target_parent


def conditional_tables(train, main, groups):
    l1 = defaultdict(Counter)
    joint = defaultdict(Counter)
    for a, g, target in zip(main, groups, train.target):
        if not target:
            continue
        l1[a][target] += 1
        joint[a, g][target] += 1
    return l1, joint


def contextual_proposals(arena, book, keys_l1, keys_g, l1, joint, mode):
    candidates = tuple(sorted(book.orders.items))
    global_counts = {c: book.orders.items[c].bit_count() for c in candidates}
    global_rate = {c: n / sum(global_counts.values()) for c, n in global_counts.items()}
    conditions = keys_l1 if mode == "l1" else list(zip(keys_l1, keys_g))
    masks = split_masks(conditions, set(conditions))
    # Smoothing preserves a fallback for categories not observed in a small context.
    result = []
    for condition in sorted(masks):
        if mode == "l1":
            a = condition
        else:
            a, _ = condition
        l1_counts = l1.get(a, {})
        l1_n = sum(l1_counts.values())
        l1_rate = {c: (l1_counts.get(c, 0) + 30 * global_rate[c]) / (l1_n + 30) for c in candidates}
        score = l1_rate
        if mode != "l1":
            j = joint.get(condition, {})
            n = sum(j.values())
            score = {c: (j.get(c, 0) + 30 * l1_rate[c]) / (n + 30) for c in candidates}
        subset = masks[condition] & arena.all
        result.extend((c, subset & ~arena.observed[c]) for c in sorted(candidates, key=lambda c: (-score[c], c)))
    return result


def filter_context(view, arena, a, b):
    return {
        "early": arena.subset(view.date.lt(PIVOT)),
        "late": arena.subset(view.date.ge(PIVOT)),
        "late_same_l1": arena.subset(view.date.ge(PIVOT) & (np.asarray(a) == np.asarray(b))),
        "late_cross_l1": arena.subset(view.date.ge(PIVOT) & (np.asarray(a) != np.asarray(b))),
    }


def score_stats(hits, ref, mask, metadata, interval=None, changed=None):
    out = report_hits(metadata, hits, ref, mask)
    if interval:
        out.update(interval.interval(hits, ref))
    if changed is not None:
        out["replaced_fifth"] = (changed & mask).bit_count()
    return out


def ab_experiment(retail, rt, output):
    price = price_bands(retail, retail.between("2009-12-01", PROFILE_END))
    profile = asof_profile(retail, PROFILE_END, price)
    groups, _ = make_groups(profile)
    mapping = dict(zip(profile.index, map(str, groups["rfm_form"])))
    eligible = set(profile.index)
    training = build_view(retail, retail.between(PROFILE_END, DISCOVERY_END, eligible), price)
    view = build_view(retail, retail.between(DISCOVERY_END, CUTOFF, eligible), price)
    book = Book(training, rt)
    arena = Arena(view)
    ga = direct_pool(scored(book, book.global_ranks[:100], "native"))
    global_ranked = list(info_proposals(arena, book, ga))
    pair = [(c, m) for c, m, _ in global_ranked]
    source = fifth_sources(arena, global_ranked)
    assert source[1] == arena.replay(pair)[1][5]
    tail = direct_pool(scored(book, book.global_ranks[100:200], "native"))
    dsc, ranks = book.local(labels_for(training, mapping))
    vsc = book.scopes(labels_for(view, mapping))
    blocked = {x.stats.key for x in ga}
    candidates = {
        "G_tail": list(info_proposals(arena, book, tail)),
        "L_gap_shared": list(info_proposals(arena, book,
                              choose(book, ranks, count_groups(dsc), 100, "direction", "gap", blocked))),
    }
    l_pool = choose(book, ranks, count_groups(dsc), 100, "direction", "added", blocked)
    shrunk = []
    for p in l_pool:
        prob = (p.stats.joint + 50 * book.prior(p.stats.key)) / (p.stats.total + 50)
        rank = prob - (p.stats.confidence - p.stats.added)
        shrunk.append(Pick(p.group, p.stats, float(rank)))
    restricted = []
    for p in ordered(book, shrunk):
        r = book.rules[p.stats.key]
        confidence = (p.stats.joint + 50 * book.prior(p.stats.key)) / (p.stats.total + 50)
        mask = arena.antecedent(r.antecedent) & ~arena.observed[r.consequent] & vsc[p.group]
        restricted.append((r.consequent, mask, confidence))
    candidates["L_shrunk_restricted"] = restricted

    tm, tg, _ = make_context(training, retail.taxonomy, mapping)
    vm, vg, target_parent = make_context(view, retail.taxonomy, mapping)
    l1, joint = conditional_tables(training, tm, tg)
    proposals = {"global_pop": arena.popular(book),
                 "l1_pop": contextual_proposals(arena, book, vm, vg, l1, joint, "l1"),
                 "form_l1_pop": contextual_proposals(arena, book, vm, vg, l1, joint, "form_l1")}
    regimes = {name: arena.replay(pair + p) for name, p in proposals.items()}
    assert len(view) == 4862 and arena.all.bit_count() == 4311
    assert all(r[1][5] == arena.all for r in regimes.values())
    base = union(regimes["global_pop"][0])
    assert base.bit_count() == 1173
    partitions = filter_context(view, arena, vm, target_parent)
    cis = {k: Paired(view, mask) for k, mask in partitions.items() if k.startswith("late")}
    fallback_rows = []
    for name, p in proposals.items():
        pure = union(arena.replay(p)[0])
        mixed = union(regimes[name][0])
        pure_baseline = union(arena.replay(proposals["global_pop"])[0])
        for label, mask in partitions.items():
            for policy, hits, benchmark in (("pop_only", pure, pure_baseline), ("rules_plus_pop", mixed, base)):
                fallback_rows.append(score_stats(hits, benchmark, mask, {
                    "fallback": name, "policy": policy, "window": label}, cis.get(label)))
    fallback = pd.DataFrame(fallback_rows)
    fallback.to_csv(output / "fallback.csv", index=False)
    # Pick one conditional fallback without seeing late scores. Global remains the comparison.
    early_fb = fallback.query("policy == 'rules_plus_pop' and window == 'early' and fallback != 'global_pop'")
    selected_fallback = early_fb.sort_values(["hits", "fallback"], ascending=[False, True]).iloc[0].fallback

    gates = [("keep", None), ("pop_only", None)]
    gates += [("weak", x) for x in (.45, .5, .55, .6, .65, .7, .75)]
    gates += [("margin", x) for x in (0, .05, .10)]
    gates += [("open", None)]
    tuning = []
    evaluated = {}
    for name, rules in candidates.items():
        for fallback, r in regimes.items():
            ref = union(r[0])
            for index, (kind, threshold) in enumerate(gates):
                p = [] if kind == "keep" else gate_lists(arena, source, rules, kind, threshold)
                hit, replaced, _ = arena.slot5(r, p)
                evaluated[name, fallback, index] = (hit, replaced)
                tuning.append({**score_stats(hit, ref, partitions["early"], {}), "candidate": name,
                               "fallback": fallback, "gate": kind, "threshold": threshold, "index": index})
    tune = pd.DataFrame(tuning)
    tune.to_csv(output / "gate_tuning_early.csv", index=False)

    selected = {}
    for key, eligible_gates in tune.loc[~tune.gate.eq("open")].groupby(["candidate", "fallback"]):
        best = eligible_gates.sort_values(["hits", "index"], ascending=[False, True]).iloc[0]
        selected[key] = int(best["index"])

    table, provenance, pairwise = [], [], []
    for name in candidates:
        for fallback in regimes:
            ref = union(regimes[fallback][0])
            cases = {"keep": 0, "unconditional": len(gates) - 1, "only_pop": 1,
                     "selected_gate": selected[name, fallback]}
            gated, opened = (evaluated[name, fallback, cases[k]][0] for k in ("selected_gate", "unconditional"))
            pairwise.append(score_stats(gated, opened, partitions["late"], {"candidate": name, "fallback": fallback},
                                        cis["late"]))
            for scenario, index in cases.items():
                hit, changed = evaluated[name, fallback, index]
                kind, threshold = gates[index]
                for label, mask in partitions.items():
                    group = {"candidate": name, "fallback": fallback, "scenario": scenario,
                             "gate": kind, "threshold": threshold, "window": label}
                    row = score_stats(hit, ref, mask, group, cis.get(label), changed)
                    row["delta_pp_vs_original_global"] = score_stats(hit, base, mask, {})["delta_pp"]
                    table.append(row)
                if fallback == "global_pop":
                    for label in ("early", "late"):
                        mask = partitions[label]
                        for origin, selection in (("original_fifth_rule", source[1]),
                                                  ("original_fifth_pop", arena.all & ~source[1])):
                            selection &= mask
                            provenance.append(score_stats(
                                hit, ref, selection, {"candidate": name, "scenario": scenario, "window": label,
                                                     "source": origin}, changed=changed))
    pd.DataFrame(table).to_csv(output / "slot5.csv", index=False)
    pd.DataFrame(provenance).to_csv(output / "slot5_source.csv", index=False)
    pd.DataFrame(pairwise).to_csv(output / "slot5_marginal_gate.csv", index=False)
    result = {"conditional_fallback_selected_early": selected_fallback,
              "ab_early_masked": partitions["early"].bit_count(), "ab_late_masked": partitions["late"].bit_count(),
              "training_context_orders": int(training.has_target.sum()), "original_global_hit_orders": 1173}
    print("Frozen A/B baseline reconciled; conditional popularity and gated replacement evaluated.", flush=True)
    return result


def soft_catalog(arena, book, pool):
    groups = defaultdict(list)
    for priority, pick in enumerate(ordered(book, pool)):
        rule = book.rules[pick.stats.key]
        available = arena.antecedent(rule.antecedent) & ~arena.observed[rule.consequent]
        groups[pick.group].append((rule.consequent, available, pick.score, priority))
    return groups


def soft_slot(arena, model, frame, regime, mode, temperature, baseline):
    cart, combo, history = features_for(frame, model.profile)
    cart_labels, cart_eligible = model.cart.route(cart)
    hist_labels, hist_eligible = model.hybrid.route(combo)
    use_history = history & hist_eligible if mode == "hybrid" else np.zeros(len(frame), dtype=bool)
    d_cart = model.cart.distances(cart)
    d_hist = model.hybrid.distances(combo)
    distances = np.where(use_history[:, None], d_hist, d_cart)
    labels = np.where(use_history, hist_labels, cart_labels)
    # Router confidence / abstention is held fixed. Only the use of group membership changes.
    eligible = (use_history | cart_eligible) & frame.has_target.to_numpy()
    if temperature:
        scale = np.where(use_history, np.median(model.hybrid.radii ** 2), np.median(model.cart.radii ** 2))
        d2 = distances ** 2
        logits = -(d2 - d2.min(axis=1)[:, None]) / (temperature * np.maximum(scale, 1e-9)[:, None])
        weights = np.exp(logits)
        weights /= weights.sum(axis=1)[:, None]
    else:
        weights = np.eye(3)[labels]

    ranked = {"cart": soft_catalog(arena, model.book, model.pools["cart"]),
              "hybrid": soft_catalog(arena, model.book, model.pools["hybrid"])}
    proposals = defaultdict(int)
    boundaries = 0
    for i, w in enumerate(weights):
        bit = 1 << i
        if not eligible[i] or not (regime & bit):
            continue
        family = ranked["hybrid" if use_history[i] else "cart"]
        d = np.sort(distances[i])
        if (d[1] - d[0]) / max(d[1], 1e-9) <= .15:
            boundaries |= bit
        totals, tie = defaultdict(float), {}
        for g, weight in enumerate(w):
            if weight < 1e-12:
                continue
            seen = set()
            for c, available, score, priority in family[str(g)]:
                if c in seen or not ((available & bit) and not (baseline[2][c] & bit)):
                    continue
                seen.add(c)
                totals[c] += weight * score
                tie[c] = min(tie.get(c, priority), priority)
        if totals:
            best = min(totals, key=lambda c: (-totals[c], tie[c], c))
            proposals[best] |= bit
    hits, changed, _ = arena.slot5(baseline, list(proposals.items()))
    return hits, changed, boundaries


def c_experiment(retail, rt, output):
    model = prepare(retail, PROFILE_END, DISCOVERY_END, rt)
    view = build_view(retail, retail.between(DISCOVERY_END, CUTOFF), model.price)
    arena = Arena(view)
    base = arena.replay(arena.proposals(model.book, model.pools["global"]) + arena.popular(model.book))
    base_hits = union(base[0])
    # Match the previous rolling-vs-fixed common eligibility; earlier audit showed
    # only 14 exclusions, all in the first fold where fixed and rolling coincide.
    regime = base[1][5]
    assert regime.bit_count() == 7122 and (base_hits & regime).bit_count() == 1958
    early = arena.subset(view.date.lt(PIVOT)) & regime
    late = arena.subset(view.date.ge(PIVOT)) & regime
    results, tuned = [], []
    temps = (0, .15, .4, 1.0, 2.5)
    for mode in ("cart", "hybrid"):
        stats = {t: soft_slot(arena, model, view, regime, mode, t, base) for t in temps}
        hard = stats[0][0]
        known_hard, _, _, _, _ = route(model, view, model.profile, arena, mode, base)
        assert ((hard ^ known_hard) & regime) == 0, (mode, ((hard ^ known_hard) & regime).bit_count())
        choices = []
        for t in temps:
            hit, changed, _ = stats[t]
            row = score_stats(hit, hard, early, {"mode": mode, "temperature": t}, changed=changed)
            tuned.append(row)
            if t:
                choices.append((row["hits"], t))
        selected = min(choices, key=lambda x: (-x[0], x[1]))[1]
        partitions = {
            "all": late, "identified_first_order": late & arena.subset(view.first_order),
            "anonymous": late & arena.subset(view.customer_id.eq("")),
            "near_boundary": late & stats[0][2],
        }
        for name, mask in partitions.items():
            interval = Paired(view, mask)
            for variant, temp in (("hard", 0), ("soft_selected_early", selected)):
                hit, changed, _ = stats[temp]
                for ref, comparison in (("hard_router", hard), ("global_fixed", base_hits)):
                    row = score_stats(hit, comparison, mask,
                                      {"mode": mode, "variant": variant, "temperature": temp,
                                       "reference": ref, "stratum": name}, interval, changed)
                    results.append(row)
    pd.DataFrame(tuned).to_csv(output / "soft_tuning_early.csv", index=False)
    pd.DataFrame(results).to_csv(output / "soft_late.csv", index=False)
    print("Soft routing evaluated on fixed candidate catalogs, including first-order and anonymous slices.", flush=True)
    return {"c_early_masked": early.bit_count(), "c_late_masked": late.bit_count(),
            "c_common_top5_orders": regime.bit_count(), "fixed_global_hits_reconciled": 1958}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "results")
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.project.resolve()))
    global PROFILE_END, DISCOVERY_END, CUTOFF, load_retail, asof_profile, build_view, price_bands
    global make_groups, choose, labels_for, count_groups, prepare, route, features_for
    global runtime, Book, Arena, Pick, Paired, scored, direct_pool, union, split_masks, report_hits
    from retail_data import find_repository, CUTOFF, DISCOVERY_END, PROFILE_END, asof_profile, build_view, \
        load_retail, price_bands
    from retail_ab import choose, count_groups, labels_for, make_groups
    from retail_c import features_for, prepare, route
    from retail_rules import Arena, Book, Paired, Pick, direct_pool, report_hits, runtime, scored, split_masks, union
    repo = find_repository(args.project)
    args.out.mkdir(parents=True, exist_ok=True)
    with threadpool_limits(limits=1):
        retail = load_retail(repo, args.cache)
        rt = runtime(repo)
        ab = ab_experiment(retail, rt, args.out)
        c = c_experiment(retail, rt, args.out)
    checks = {**ab, **c, "validation_tune_before": PIVOT, "evaluation_end_exclusive": CUTOFF,
              "source_maximum_date": retail.audit["maximum_date_in_analysis"]}
    (args.out / "verification.json").write_text(json.dumps(checks, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
