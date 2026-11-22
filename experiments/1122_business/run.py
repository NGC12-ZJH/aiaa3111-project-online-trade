"""1122 business extension: money-weighted metrics and a category-to-SKU feasibility check.

Registered in registration.json (committed before computation). Validation only.
Reuses the 1122 code unchanged and asserts that every unweighted number it rebuilds
matches the committed 1122 outputs before any weighted or SKU-level value is written.
"""
import argparse
from collections import Counter, defaultdict
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "1122"
sys.path.insert(0, str(SOURCE))

from retail_ab import choose, count_groups, labels_for, make_groups  # noqa: E402
from retail_c import FOLDS as C_FOLDS, defined_sections, prepare, route  # noqa: E402
from retail_data import (CUTOFF, DISCOVERY_END, PROFILE_END, asof_profile, build_view,  # noqa: E402
                         find_repository, group_random, load_retail, price_bands)
from retail_rules import (Arena, Book, Paired, direct_pool, full_hits, report_hits, runtime,  # noqa: E402
                          scored, split_masks, union)

PIVOT = "2011-03-01"
REPEATS = 1500
SEEDS = range(1000, 1100)
BUDGETS = (20, 50, 100)


def load_module(name, path):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gating = load_module("gating_l1_soft", SOURCE / "followup_gating_l1_soft/run.py")
fusion = load_module("fusion_time", SOURCE / "followup_fusion_time/run.py")
for module in (gating, fusion):
    module.split_masks, module.union, module.report_hits = split_masks, union, report_hits
    module.Arena, module.Book, module.Paired = Arena, Book, Paired
to_array, to_mask = fusion.array, fusion.to_mask


# ---------------------------------------------------------------- weights and intervals

def target_value(retail, frame):
    """Value of the masked target category's lines in each order (0 when nothing is masked)."""
    values = []
    for invoice, target in zip(frame.id, frame.target):
        values.append(sum(q * p for _, c, q, p, _ in retail.items[invoice] if target and c == target))
    return np.array(values, dtype=float)


def weighted_rate(mask, scope, weights, n):
    hit, base = to_array(mask & scope, n), to_array(scope, n)
    return float(weights[hit].sum() / weights[base].sum())


class WeightedPaired(Paired):
    """1122 block bootstrap (same blocks, same RNG draws) with order weights."""

    def __init__(self, frame, scope, weights, repeats=REPEATS):
        super().__init__(frame, scope, repeats)
        self.w = np.asarray(weights, dtype=float)[self.active]
        self.wden = self.weights @ np.bincount(self.codes, weights=self.w, minlength=len(self.groups))

    def winterval(self, left, right):
        lv = self.vector(left)[self.active].astype(float)
        rv = self.vector(right)[self.active].astype(float)
        sums = np.bincount(self.codes, weights=self.w * (lv - rv), minlength=len(self.groups))
        values = 100 * (self.weights @ sums) / self.wden
        lo, hi = np.quantile(values, [.025, .975])
        return dict(low95_pp=float(lo), high95_pp=float(hi))


def describe(row, mask, reference, scope, n, weight_sets):
    """Unweighted report_hits row plus weighted rates and differences."""
    out = report_hits(row, mask, reference, scope)
    for label, w in weight_sets.items():
        a, b = weighted_rate(mask, scope, w, n), weighted_rate(reference, scope, w, n)
        out[f"rate_{label}"] = a
        out[f"reference_rate_{label}"] = b
        out[f"delta_pp_{label}"] = 100 * (a - b)
    return out


def add_intervals(out, frame, mask, reference, scope, weight_sets):
    out.update({f"unweighted_{k}": v for k, v in Paired(frame, scope).interval(mask, reference).items()
                if k != "resampling_blocks"})
    for label, w in weight_sets.items():
        ci = WeightedPaired(frame, scope, w).winterval(mask, reference)
        out.update({f"{label}_{k}": v for k, v in ci.items()})
    return out


# ---------------------------------------------------------------- M1 coverage

def m1_coverage(retail, rt, profile, groupings, price, out, checks):
    BasketIndex = rt[0]
    disc = build_view(retail, retail.between(PROFILE_END, DISCOVERY_END, set(profile.index)), price)
    view = build_view(retail, retail.between(DISCOVERY_END, CUTOFF, set(profile.index)), price)
    assert len(disc) == 7521 and len(view) == 4862
    book = Book(disc, rt)
    val = BasketIndex(view.customer_id, view.basket)
    n = len(view)
    w = view.gross_purchase_amount.to_numpy(dtype=float)
    weights = {"order_amount": w}
    scope = val.all

    def pool_hits(ranks, sizes, budget):
        return full_hits(book, choose(book, ranks, sizes, budget, "combination"), val)

    masks = {}
    for b in BUDGETS:
        masks["global", b] = pool_hits({"GLOBAL": book.global_ranks}, {"GLOBAL": len(disc)}, b)
    for name, labels in groupings.items():
        mapping = dict(zip(profile.index, map(str, labels)))
        dsc, ranks = book.local(labels_for(disc, mapping))
        for b in BUDGETS:
            masks[name, b] = pool_hits(ranks, count_groups(dsc), b)
    got = {k: masks[k, 100].bit_count() for k in ("global", "rfm_form")}
    assert got == {"global": 3667, "rfm_form": 3715}, got
    checks["M1_unweighted_hits_global_rfm_form_B100"] = got

    rows = []
    for (name, b), mask in masks.items():
        rows.append({"system": name, "seed": "", "budget": b, "orders": n, "covered": mask.bit_count(),
                     "rate": mask.bit_count() / n, "rate_order_amount": weighted_rate(mask, scope, w, n)})
    for seed in SEEDS:
        for version in ("rfm", "rfm_form"):
            mapping = group_random(profile, groupings[version], seed)
            dsc, ranks = book.local(labels_for(disc, mapping))
            for b in BUDGETS:
                mask = pool_hits(ranks, count_groups(dsc), b)
                rows.append({"system": "A1_" + version, "seed": seed, "budget": b, "orders": n,
                             "covered": mask.bit_count(), "rate": mask.bit_count() / n,
                             "rate_order_amount": weighted_rate(mask, scope, w, n)})
    systems = pd.DataFrame(rows)
    systems.to_csv(out / "m1_coverage_systems.csv", index=False)

    random_rows = []
    for version in ("rfm", "rfm_form"):
        for b in BUDGETS:
            real = systems.query("system == @version and budget == @b").iloc[0]
            rand = systems.query("system == 'A1_' + @version and budget == @b")
            for metric in ("rate", "rate_order_amount"):
                random_rows.append({"system": version, "budget": b, "metric": metric, "real": real[metric],
                                    "A1_min": rand[metric].min(), "A1_median": rand[metric].median(),
                                    "A1_max": rand[metric].max(), "A1_ge_real": int(rand[metric].ge(real[metric]).sum()),
                                    "seeds": len(rand)})
    pd.DataFrame(random_rows).to_csv(out / "m1_coverage_random.csv", index=False)

    paired = []
    for name in groupings:
        for ref in ["global"] + (["rfm", "frequency"] if name == "rfm_form" else []):
            row = describe({"system": name, "reference": ref, "budget": 100}, masks[name, 100], masks[ref, 100],
                           scope, n, weights)
            paired.append(add_intervals(row, view, masks[name, 100], masks[ref, 100], scope, weights))
    pd.DataFrame(paired).to_csv(out / "m1_coverage_paired.csv", index=False)

    amounts = pd.Series(w)
    checks["M1_order_amount_summary"] = {"orders": n, "total": float(amounts.sum()),
                                         "median": float(amounts.median()),
                                         "top10pct_share": float(amounts.nlargest(n // 10).sum() / amounts.sum())}
    print("M1 coverage done", flush=True)


# ---------------------------------------------------------------- M2 ladder (+ SKU systems)

def fusion_masks(arena, view, book, main, l1, baseline, head, tail, local, vsc):
    """Rebuild the early-half selection of run_fusion and return every arm's masks."""
    categories = sorted(book.orders.items)
    indices = {c: i for i, c in enumerate(categories)}
    early = arena.subset(view.date.lt(PIVOT))
    pop = fusion.conditional_prior(arena, book, main, l1, categories)
    seen = np.stack([to_array(arena.observed[c], len(view)) for c in categories], axis=1)
    targets = np.array([indices.get(t, -1) for t in view.target])
    head_f = fusion.feature_blocks(arena, book, head, indices)
    extras = {
        "G200": fusion.feature_blocks(arena, book, tail, indices),
        "G100_L100_restricted": fusion.feature_blocks(arena, book, local, indices, vsc, shrink=50),
        "G100_L100_shared": fusion.feature_blocks(arena, book, local, indices, shrink=50),
    }

    def predict(score):
        score[seen] = -np.inf
        positions = np.argsort(-score, axis=1, kind="stable")[:, :5]
        return to_mask((positions == targets[:, None]).any(axis=1)) & arena.all

    result = {}
    for name, extra in extras.items():
        best = {}
        for mode in ("max", "discounted"):
            options = [w for w in fusion.GRID if w[1] != 0]
            scored_options = []
            for idx, w in enumerate(options):
                hit = predict(w[0] * head_f[mode] + w[2] * pop + w[1] * extra[mode])
                scored_options.append(((hit & early).bit_count(), idx, hit, w))
            val, idx, hit, w = min(scored_options, key=lambda x: (-x[0], x[1]))
            best[mode] = (val, hit, w)
        selected = min(("max", "discounted"), key=lambda m: (-best[m][0], ("max", "discounted").index(m)))
        result[name] = {"selected": best[selected][1], "selected_mode": selected, "selected_weights": best[selected][2],
                        "max": best["max"][1], "max_weights": best["max"][2]}
    return result


def ladder_context(retail, rt, profile, groupings, price):
    mapping = dict(zip(profile.index, map(str, groupings["rfm_form"])))
    training = build_view(retail, retail.between(PROFILE_END, DISCOVERY_END, set(profile.index)), price)
    view = build_view(retail, retail.between(DISCOVERY_END, CUTOFF, set(profile.index)), price)
    arena = Arena(view)
    assert (len(training), len(view), arena.all.bit_count()) == (7521, 4862, 4311)
    book = Book(training, rt)
    dm, dg, _ = gating.make_context(training, retail.taxonomy, mapping)
    vm, vg, _ = gating.make_context(view, retail.taxonomy, mapping)
    l1, joint = gating.conditional_tables(training, dm, dg)
    head = direct_pool(scored(book, book.global_ranks[:100], "native"))
    tail = direct_pool(scored(book, book.global_ranks[100:200], "native"))
    excluded = {p.stats.key for p in head}
    dsc, ranks = book.local(labels_for(training, mapping))
    vsc = book.scopes(labels_for(view, mapping))
    local = choose(book, ranks, count_groups(dsc), 100, "direction", "added", excluded)
    g_props = arena.proposals(book, head)
    pops = {"global": arena.popular(book),
            "l1": gating.contextual_proposals(arena, book, vm, vg, l1, joint, "l1"),
            "form_l1": gating.contextual_proposals(arena, book, vm, vg, l1, joint, "form_l1")}
    masks = {"pure_global_pop": union(arena.replay(pops["global"])[0]),
             "G100_global_pop": union(arena.replay(g_props + pops["global"])[0]),
             "G100_form_l1_pop": union(arena.replay(g_props + pops["form_l1"])[0])}
    l1_result = arena.replay(g_props + pops["l1"])
    masks["G100_l1_pop"] = union(l1_result[0])
    source = gating.fifth_sources(arena, list(gating.info_proposals(arena, book, head)))
    frozen_tail = list(gating.info_proposals(arena, book, tail))
    masks["l1_gated_G_tail"], _, _ = arena.slot5(l1_result, gating.gate_lists(arena, source, frozen_tail, "weak", .45))
    fused = fusion_masks(arena, view, book, vm, l1, masks["G100_l1_pop"], head, tail, local, vsc)
    for name, info in fused.items():
        masks[f"fusion_{name}"] = info["selected"]
        masks[f"fusion_{name}_max"] = info["max"]
    return training, view, arena, book, masks, fused


def m2_ladder(retail, ctx, out, checks):
    training, view, arena, book, masks, fused = ctx
    n = len(view)
    late, early = arena.subset(view.date.ge(PIVOT)), arena.subset(view.date.lt(PIVOT))
    late_hits = {k: (v & late).bit_count() for k, v in masks.items()}
    expected = {"pure_global_pop": 586, "G100_global_pop": 629, "G100_l1_pop": 660, "l1_gated_G_tail": 684,
                "G100_form_l1_pop": 645}
    reference = pd.read_csv(SOURCE / "followup_fusion_time/results/fusion_late.csv")
    for name, info in fused.items():
        rows = reference.loc[reference.arm.eq(name)]
        expected[f"fusion_{name}"] = int(rows.loc[rows.aggregation.eq(info["selected_mode"]), "hits"].iloc[0])
        expected[f"fusion_{name}_max"] = int(rows.loc[rows.aggregation.eq("max"), "hits"].iloc[0])
    assert all(late_hits[k] == v for k, v in expected.items()), (late_hits, expected)
    checks["M2_unweighted_late_hits"] = late_hits
    checks["M2_fusion_selection"] = {k: {"mode": v["selected_mode"], "weights": v["selected_weights"],
                                         "max_weights": v["max_weights"]} for k, v in fused.items()}

    weights = {"target_value": target_value(retail, view),
               "order_amount": view.gross_purchase_amount.to_numpy(dtype=float)}
    steps = [("pure_global_pop", None), ("G100_global_pop", "pure_global_pop"), ("G100_l1_pop", "G100_global_pop"),
             ("fusion_G200", "G100_l1_pop"), ("fusion_G100_L100_shared", "G100_l1_pop"),
             ("fusion_G100_L100_restricted", "G100_l1_pop")]
    extra = [("fusion_G200_max", "G100_l1_pop"), ("l1_gated_G_tail", "G100_l1_pop"),
             ("G100_form_l1_pop", "G100_global_pop"), ("fusion_G100_L100_shared", "fusion_G200"),
             ("fusion_G100_L100_restricted", "fusion_G200"), ("fusion_G200", "pure_global_pop")]
    rows = []
    for half, scope in (("late", late), ("early", early)):
        for role, pairs in (("registered_step", steps), ("descriptive", extra)):
            for name, ref in pairs:
                reference_mask = masks[ref] if ref else masks[name]
                row = describe({"half": half, "role": role, "system": name, "reference": ref or ""},
                               masks[name], reference_mask, scope, n, weights)
                if half == "late" and ref:
                    add_intervals(row, view, masks[name], reference_mask, scope, weights)
                rows.append(row)
    pd.DataFrame(rows).to_csv(out / "m2_ladder.csv", index=False)
    print("M2 ladder done", flush=True)
    return weights


# ---------------------------------------------------------------- M3 cold start

def m3_cold_start(retail, rt, out, checks):
    """Same loop as retail_c.route_c, keeping the masks instead of writing only counts."""
    fixed = prepare(retail, PROFILE_END, DISCOVERY_END, rt)
    initial_known = set(retail.between("2009-12-01", PROFILE_END).customer_id) - {""}
    frames, hits_all, shift = [], {}, 0
    for fold, start, end, train_start in C_FOLDS:
        orders = retail.between(start, end)
        frame = build_view(retail, orders, fixed.price)
        arena = Arena(frame)
        fixed_base = arena.replay(arena.proposals(fixed.book, fixed.pools["global"]) + arena.popular(fixed.book))
        refreshed = fixed.profile if start == DISCOVERY_END else asof_profile(retail, start, fixed.price)
        rolling = fixed if start == DISCOVERY_END else prepare(retail, train_start, start, rt)
        rolling_view = frame if rolling is fixed else build_view(retail, orders, rolling.price)
        rolling_arena = Arena(rolling_view)
        rolling_base = rolling_arena.replay(rolling_arena.proposals(rolling.book, rolling.pools["global"])
                                            + rolling_arena.popular(rolling.book))
        common = fixed_base[1][5] & rolling_base[1][5]
        frame["common_top5"] = [bool(common & (1 << i)) for i in range(len(frame))]
        fold_hits = {
            "popularity_fixed": union(arena.replay(arena.popular(fixed.book))[0]),
            "global_fixed": union(fixed_base[0]),
            "global_rolling": union(rolling_base[0]),
            "cart_fixed": route(fixed, frame, fixed.profile, arena, "cart", fixed_base)[0],
            "hybrid_fixed": route(fixed, frame, fixed.profile, arena, "hybrid", fixed_base)[0],
            "hybrid_features_refreshed": route(fixed, frame, refreshed, arena, "hybrid", fixed_base)[0],
            "cart_rolling": route(rolling, rolling_view, rolling.profile, rolling_arena, "cart", rolling_base)[0],
            "hybrid_rolling": route(rolling, rolling_view, rolling.profile, rolling_arena, "hybrid", rolling_base)[0],
        }
        frame["profile_member"] = frame.customer_id.isin(initial_known)
        frame["new_at_forecast"] = frame.customer_id.ne("") & frame.first_day.ge(start)
        frames.append(frame)
        for name, value in fold_hits.items():
            hits_all[name] = hits_all.get(name, 0) | (value << shift)
        shift += len(frame)
        print(f"M3: {fold} done", flush=True)
    aligned = pd.concat(frames, ignore_index=True)
    assert len(aligned) == 8067 and aligned.date.max() < CUTOFF
    arena = Arena(aligned)
    n = len(aligned)
    weights = {"target_value": target_value(retail, aligned),
               "order_amount": aligned.gross_purchase_amount.to_numpy(dtype=float)}
    reference = pd.read_csv(SOURCE / "results/route_c/c_aggregate.csv")
    rows, mismatches = [], 0
    for segment, subset in defined_sections(arena, aligned).items():
        for name, hits in hits_all.items():
            refs = ["global_fixed"] + (["global_rolling"] if name in ("cart_rolling", "hybrid_rolling") else [])
            for ref in refs:
                row = describe({"system": name, "reference": ref, "segment": segment}, hits, hits_all[ref],
                               subset, n, weights)
                old = reference.query("system == @name and reference == @ref and segment == @segment").iloc[0]
                mismatches += int(old.hits != row["hits"] or old.orders != row["orders"])
                if name != ref:
                    add_intervals(row, aligned, hits, hits_all[ref], subset, weights)
                rows.append(row)
    assert mismatches == 0
    checks["M3_unweighted_rows_matching_c_aggregate"] = len(rows)
    pd.DataFrame(rows).to_csv(out / "m3_cold_start.csv", index=False)
    print("M3 cold start done", flush=True)


# ---------------------------------------------------------------- S category to SKU

def sku_part(retail, ctx, out, checks):
    training, view, arena, book, masks, _ = ctx
    n = len(view)
    pop_count = defaultdict(Counter)
    for invoice in training.id:
        for sku, cat in {(line[0], line[1]) for line in retail.items[invoice]}:
            pop_count[cat][sku] += 1
    pop_rank = {cat: sorted(c, key=lambda s: (-c[s], s)) for cat, c in pop_count.items()}

    history = retail.orders.loc[retail.orders.customer_id.ne(""), ["customer_id", "invoice_datetime", "id"]]
    by_customer = {k: g.sort_values(["invoice_datetime", "id"]).itertuples(index=False)
                   for k, g in history.groupby("customer_id")}
    by_customer = {k: list(v) for k, v in by_customer.items()}

    def from_history(customer, before, target, k, frozen):
        counts, last = Counter(), {}
        for order in by_customer.get(customer, []):
            if order.invoice_datetime >= before or (frozen and order.invoice_datetime >= DISCOVERY_END):
                break
            for sku in {line[0] for line in retail.items[order.id] if line[1] == target}:
                counts[sku] += 1
                last[sku] = order.invoice_datetime
        position = {s: i for i, s in enumerate(pop_rank.get(target, []))}
        ranked = sorted(counts, key=lambda s: (-counts[s], _desc(last[s]), position.get(s, 10 ** 6), s))
        for s in pop_rank.get(target, []):
            if len(ranked) >= k:
                break
            if s not in ranked:
                ranked.append(s)
        return ranked[:k], bool(counts)

    rows = []
    match = {f"{s}_k{k}": np.zeros(n, dtype=bool) for s in ("pop", "hist", "hist_frozen") for k in (1, 3)}
    has_history = np.zeros(n, dtype=bool)
    hidden_sizes = np.zeros(n, dtype=int)
    for i, row in enumerate(view.itertuples(index=False)):
        if not row.target:
            continue
        hidden = {line[0] for line in retail.items[row.id] if line[1] == row.target}
        hidden_sizes[i] = len(hidden)
        # The k=1 choice is the first element of the k=3 list (same ordering and fallback).
        live, has_history[i] = from_history(row.customer_id, row.invoice_datetime, row.target, 3, False)
        frozen, _ = from_history(row.customer_id, row.invoice_datetime, row.target, 3, True)
        for k in (1, 3):
            match[f"pop_k{k}"][i] = bool(hidden & set(pop_rank.get(row.target, [])[:k]))
            match[f"hist_k{k}"][i] = bool(hidden & set(live[:k]))
            match[f"hist_frozen_k{k}"][i] = bool(hidden & set(frozen[:k]))
    match_masks = {k: to_mask(v) & arena.all for k, v in match.items()}
    history_mask = to_mask(has_history) & arena.all
    halves = {"late": arena.subset(view.date.ge(PIVOT)), "early": arena.subset(view.date.lt(PIVOT)), "all": arena.all}
    systems = ["G100_global_pop", "G100_l1_pop", "fusion_G200"]
    for half, scope in halves.items():
        for subset_name, subset in (("all_masked", scope), ("bought_category_before", scope & history_mask),
                                    ("never_bought_category", scope & ~history_mask)):
            base = subset.bit_count()
            for strategy, m in match_masks.items():
                record = {"half": half, "subset": subset_name, "strategy": strategy, "orders": base,
                          "sku_match_rate": (m & subset).bit_count() / base if base else np.nan}
                for system in systems:
                    cat = masks[system] & subset
                    record[f"{system}_category_hit5"] = cat.bit_count() / base if base else np.nan
                    record[f"{system}_sku_hit5"] = (cat & m).bit_count() / base if base else np.nan
                    record[f"{system}_sku_given_category"] = ((cat & m).bit_count() / cat.bit_count()
                                                              if cat.bit_count() else np.nan)
                rows.append(record)
    pd.DataFrame(rows).to_csv(out / "s_sku.csv", index=False)
    paired = []
    late = halves["late"]
    interval = Paired(view, late)
    for system in systems:
        for left, right in (("hist_k1", "pop_k1"), ("hist_frozen_k1", "pop_k1"), ("hist_k1", "hist_frozen_k1"),
                            ("hist_k3", "pop_k3")):
            a, b = masks[system] & match_masks[left], masks[system] & match_masks[right]
            paired.append({**report_hits({"system": system, "left": left, "right": right}, a, b, late),
                           **interval.interval(a, b)})
    pd.DataFrame(paired).to_csv(out / "s_sku_paired.csv", index=False)
    checks["S_hidden_skus_per_masked_order"] = {
        "mean": float(hidden_sizes[to_array(arena.all, n)].mean()),
        "median": float(np.median(hidden_sizes[to_array(arena.all, n)]))}
    checks["S_masked_orders_with_category_history"] = int(history_mask.bit_count())
    print("S category to SKU done", flush=True)


def _desc(timestamp):
    """Sort key that puts later timestamps first."""
    return tuple(-ord(ch) for ch in timestamp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=HERE / "results")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--parts", nargs="+", default=["m1", "m2", "m3", "s"], choices=["m1", "m2", "m3", "s"])
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    repo = find_repository(SOURCE)
    checks = {}
    with threadpool_limits(limits=1):
        rt = runtime(repo)
        retail = load_retail(repo, args.cache)
        assert retail.orders.invoice_datetime.max() < CUTOFF
        price = price_bands(retail, retail.between("2009-12-01", PROFILE_END))
        profile = asof_profile(retail, PROFILE_END, price)
        groupings, _ = make_groups(profile)
        if "m1" in args.parts:
            m1_coverage(retail, rt, profile, groupings, price, args.out, checks)
        if {"m2", "s"} & set(args.parts):
            ctx = ladder_context(retail, rt, profile, groupings, price)
            if "m2" in args.parts:
                m2_ladder(retail, ctx, args.out, checks)
            if "s" in args.parts:
                sku_part(retail, ctx, args.out, checks)
        if "m3" in args.parts:
            m3_cold_start(retail, rt, args.out, checks)
    git = lambda *a: subprocess.check_output(["git", "-C", str(repo), *a], text=True).strip()
    manifest = {"registration": "experiments/1122_business/registration.json",
                "registration_commit": git("log", "-1", "--format=%h", "--", "experiments/1122_business/registration.json"),
                "code_commit": git("rev-parse", "--short", "HEAD"), "parts": args.parts,
                "cutoff_exclusive": CUTOFF, "max_order_read": retail.orders.invoice_datetime.max(),
                "bootstrap_repeats": REPEATS, "checks": checks}
    path = args.out / "manifest.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if old.get("checks") and set(args.parts) != {"m1", "m2", "m3", "s"}:
        manifest["checks"] = {**old["checks"], **checks}
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
