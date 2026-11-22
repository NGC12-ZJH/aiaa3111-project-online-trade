"""Route C. Masked order routing and forward rolling Validation comparisons."""
from dataclasses import dataclass
import json

import numpy as np
import pandas as pd

from retail_data import CUTOFF, DISCOVERY_END, PROFILE_END, FormCluster, asof_profile, build_view, price_bands
from retail_rules import Arena, Book, GROUPS, Paired, direct_pool, report_hits, scored, select, split_masks, union

FOLDS = (
    ("winter", "2010-12-01", "2011-03-01", "2010-06-01"),
    ("early_spring", "2011-03-01", "2011-05-01", "2010-09-01"),
    ("late_spring", "2011-05-01", CUTOFF, "2010-11-01"),
)
HISTORY = ["recency", "frequency", "monetary", "qty", "price", "concentration"]
CART_LOG = [0, 1, 3, 6]
COMBINED_LOG = CART_LOG + [7, 8, 9, 10, 11]


@dataclass
class ServingModel:
    book: Book
    price: tuple
    cart: FormCluster
    hybrid: FormCluster
    pools: dict
    profile: pd.DataFrame
    train_start: str
    train_end: str


def features_for(view, profile):
    cart = np.stack(view.cart.to_list())
    history = profile.reindex(view.customer_id)[HISTORY]
    present = history.frequency.notna().to_numpy()
    filled = history.fillna(0).to_numpy()
    return cart, np.column_stack([cart, filled]), present


def prepare(retail, start, end, modules):
    assert start < end < CUTOFF
    train_orders = retail.between(start, end)
    price = price_bands(retail, train_orders)
    train = build_view(retail, train_orders, price)
    before_training = asof_profile(retail, start, price)
    history_at_origin = asof_profile(retail, end, price)
    cart, combo, present = features_for(train, before_training)
    mask = train.has_target.to_numpy()
    known = mask & present
    cart_model = FormCluster(cart[mask], CART_LOG)
    combined_model = FormCluster(combo[known], COMBINED_LOG)
    full_cart, _ = cart_model.route(cart)
    full_combo, _ = combined_model.route(combo)
    cart_groups = np.where(mask, full_cart.astype(str), "")
    hybrid_groups = np.where(known, full_combo.astype(str), "")
    book = Book(train, modules)
    native = direct_pool(scored(book, book.global_ranks[:100], "native"))
    frozen_keys = {pick.stats.key for pick in native}
    pools = {"global": native}
    for name, groups in (("cart", cart_groups), ("hybrid", hybrid_groups)):
        scopes, ranks = book.local(groups)
        sizes = {g: value.bit_count() for g, value in scopes.items()}
        pools[name] = select(book, {g: scored(book, rows, "added", frozen_keys) for g, rows in ranks.items()},
                             sizes, 100, "direction")
    return ServingModel(book, price, cart_model, combined_model, pools, history_at_origin, start, end)


def route(model, view, profile, arena, mode, baseline):
    cart, combo, present = features_for(view, profile)
    cs, ca = model.cart.route(cart)
    has_target = view.has_target.to_numpy()
    cart_scopes = split_masks(np.where(ca & has_target, cs.astype(str), ""), GROUPS)
    if mode == "hybrid":
        hs, ha = model.hybrid.route(combo)
        hybrid_scopes = split_masks(np.where(ha & present & has_target, hs.astype(str), ""), GROUPS)
        ready = union(hybrid_scopes.values())
        cart_scopes = {g: scope & ~ready for g, scope in cart_scopes.items()}
        promotions = arena.proposals(model.book, model.pools["hybrid"], hybrid_scopes)
        promotions.extend(arena.proposals(model.book, model.pools["cart"], cart_scopes))
    else:
        ready = 0
        promotions = arena.proposals(model.book, model.pools["cart"], cart_scopes)
    routed = ready | union(cart_scopes.values())
    result, changed, eligibility = arena.slot5(baseline, promotions)
    assert eligibility & ~routed == 0
    return result, routed, changed, eligibility, ready


def route_c(out, retail, modules):
    output = out / "route_c"
    output.mkdir(exist_ok=True, parents=True)
    fixed = prepare(retail, PROFILE_END, DISCOVERY_END, modules)
    initial_known = set(retail.between("2009-12-01", PROFILE_END).customer_id) - {""}
    fold_rows, train_rows, frames = [], [], []
    aggregate_hits, aggregate_routes, aggregate_changed, aggregate_eligible = {}, {}, {}, {}
    shift = 0
    for fold, start, end, train_start in FOLDS:
        orders = retail.between(start, end)
        frame = build_view(retail, orders, fixed.price)
        arena = Arena(frame)
        fixed_base = arena.replay(arena.proposals(fixed.book, fixed.pools["global"]) + arena.popular(fixed.book))
        fixed_hit = union(fixed_base[0])
        refreshed_profile = fixed.profile if start == DISCOVERY_END else asof_profile(retail, start, fixed.price)
        rolling = fixed if start == DISCOVERY_END else prepare(retail, train_start, start, modules)
        assert fixed.train_end <= start and rolling.train_end == start and end <= CUTOFF
        rolling_view = frame if rolling is fixed else build_view(retail, orders, rolling.price)
        rolling_arena = Arena(rolling_view)
        assert frame.id.equals(rolling_view.id) and frame.target.equals(rolling_view.target)
        rolling_base = rolling_arena.replay(rolling_arena.proposals(rolling.book, rolling.pools["global"])
                                           + rolling_arena.popular(rolling.book))
        common_top5 = fixed_base[1][5] & rolling_base[1][5]
        frame["common_top5"] = [bool(common_top5 & (1 << i)) for i in range(len(frame))]
        fixed_excluded = (arena.all & ~fixed_base[1][5]).bit_count()
        rolling_excluded = (arena.all & ~rolling_base[1][5]).bit_count()
        pop_result = arena.replay(arena.popular(fixed.book))
        fold_hits = {"popularity_fixed": (union(pop_result[0]), 0, 0, 0, 0),
                     "global_fixed": (fixed_hit, 0, 0, 0, 0),
                     "global_rolling": (union(rolling_base[0]), 0, 0, 0, 0)}
        fold_hits["cart_fixed"] = route(fixed, frame, fixed.profile, arena, "cart", fixed_base)
        fold_hits["hybrid_fixed"] = route(fixed, frame, fixed.profile, arena, "hybrid", fixed_base)
        fold_hits["hybrid_features_refreshed"] = route(fixed, frame, refreshed_profile, arena, "hybrid", fixed_base)
        fold_hits["cart_rolling"] = route(rolling, rolling_view, rolling.profile, rolling_arena, "cart", rolling_base)
        fold_hits["hybrid_rolling"] = route(rolling, rolling_view, rolling.profile, rolling_arena, "hybrid", rolling_base)

        frame["profile_member"] = frame.customer_id.isin(initial_known)
        frame["new_at_forecast"] = frame.customer_id.ne("") & frame.first_day.ge(start)
        frames.append(frame)
        sections = defined_sections(arena, frame)
        for name, (hits, routed, changed, eligibility, ready) in fold_hits.items():
            comparator = union(rolling_base[0]) if name.endswith("rolling") else fixed_hit
            for section, subset in sections.items():
                fold_rows.append({
                    **report_hits({"fold": fold, "system": name, "segment": section, "evaluation_from": start,
                                   "evaluation_until": end}, hits, comparator, subset),
                    "routed": (routed & subset).bit_count(), "actually_replaced_fifth": (changed & subset).bit_count(),
                    "eligible_suggestions": (eligibility & subset).bit_count(),
                    "history_plus_cart_routed": (ready & subset).bit_count(),
                })
            for target, value in ((aggregate_hits, hits), (aggregate_routes, routed),
                                  (aggregate_changed, changed), (aggregate_eligible, eligibility)):
                target[name] = target.get(name, 0) | (value << shift)
        for variant, model in (("fixed", fixed), ("rolling", rolling)):
            train_rows.append({
                "fold": fold, "variant": variant, "from": model.train_start, "until_exclusive": model.train_end,
                "train_orders": len(model.book.training), "eval_orders": len(frame),
                "masked_eval_orders": arena.all.bit_count(), "common_top5_orders": common_top5.bit_count(),
                "own_fewer_than_5": fixed_excluded if variant == "fixed" else rolling_excluded, "global_rule_count": len(model.pools["global"]),
                "cart_rule_count": len(model.pools["cart"]), "hybrid_rule_count": len(model.pools["hybrid"]),
            })
        shift += len(frame)
        print(f"C: {fold} forward evaluation completed", flush=True)

    aligned = pd.concat(frames, ignore_index=True)
    assert len(aligned) == 8067 and aligned.id.is_unique and aligned.date.max() < CUTOFF
    a = Arena(aligned)
    aggregate = []
    for section, subset in defined_sections(a, aligned).items():
        interval = Paired(aligned, subset)
        for name, hits in aggregate_hits.items():
            refs = ["global_fixed"]
            if name in ("cart_rolling", "hybrid_rolling"):
                refs += ["global_rolling"]
            for ref in refs:
                reference = aggregate_hits[ref]
                aggregate.append({
                    **report_hits({"system": name, "reference": ref, "segment": section}, hits, reference, subset),
                    **interval.interval(hits, reference), "routed": (aggregate_routes[name] & subset).bit_count(),
                    "eligible_suggestions": (aggregate_eligible[name] & subset).bit_count(),
                    "actually_replaced_fifth": (aggregate_changed[name] & subset).bit_count(),
                })
    pd.DataFrame(aggregate).to_csv(output / "c_aggregate.csv", index=False)
    pd.DataFrame(fold_rows).to_csv(output / "c_folds.csv", index=False)
    pd.DataFrame(train_rows).to_csv(output / "c_training_windows.csv", index=False)
    (output / "c_manifest.json").write_text(json.dumps({
        "evaluation_cutoff_exclusive": CUTOFF, "all_pretest_validation_orders": len(aligned),
        "masked_eval_orders": int(aligned.common_top5.sum()), "maskable_before_common_top5_check": a.all.bit_count(),
        "excluded_fewer_than_5_candidates": a.all.bit_count() - int(aligned.common_top5.sum()), "folds": FOLDS, "rules_per_pool_target": 100,
        "abstention_radius_training_quantile": .95, "masked_cart_features": True,
    }, indent=2), encoding="utf-8")
    print("C: results and pre-Test chronology verified", flush=True)


def defined_sections(arena, frame):
    common = arena.subset(frame.common_top5)
    masks = {
        "all": arena.all, "profile_member": arena.subset(frame.profile_member),
        "identified_first_order": arena.subset(frame.first_order),
        "identified_no_history_at_origin": arena.subset(frame.new_at_forecast),
        "identified_other_returning": arena.subset(frame.customer_id.ne("") & ~frame.profile_member & ~frame.first_order),
        "anonymous": arena.subset(frame.customer_id.eq("")),
    }


    return {name: mask & common for name, mask in masks.items()}
