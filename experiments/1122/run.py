"""Pre-Test entry point and validation of the redesign's invariants."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score
from threadpoolctl import threadpool_limits

from retail_ab import FORM, RFM, make_groups, route_ab
from retail_c import route_c
from retail_data import CUTOFF, PROFILE_END, FormCluster, asof_profile, build_view, features, group_random, \
    find_repository, load_retail, price_bands
from retail_rules import Arena, runtime, union


def verify_masks(arena, proposals, takeover, baseline, targets):
    replayed = arena.replay(proposals)
    slot, changed, chosen = arena.slot5(baseline, takeover)
    for i, target in enumerate(targets):
        bit = 1 << i
        predictions = []
        for cat, avail in proposals:
            if avail & bit and cat not in predictions and len(predictions) < 5:
                predictions.append(cat)
        assert bool(union(replayed[0]) & bit) == (target in predictions)
        choices = [cat for cat, allowed in takeover if allowed & bit and cat not in predictions[:4]]
        assert bool(chosen & bit) == bool(choices)
        if choices:
            assert bool(changed & bit) == (choices[0] != predictions[4])
            predictions[4] = choices[0]
        assert bool(slot & bit) == (target in predictions)


def audit(out, retail):
    folder = out / "audit"
    folder.mkdir(parents=True, exist_ok=True)
    hist = retail.between("2009-12-01", PROFILE_END)
    price = price_bands(retail, hist)
    profile = asof_profile(retail, PROFILE_END, price)
    groups, _ = make_groups(profile)
    rows = []
    for name, labels in groups.items():
        for group in sorted(set(labels)):
            data = profile.loc[labels == group]
            rows.append({
                "system": name, "group": group, "customers": len(data),
                **{f"{field}_median": data[field].median() for field in RFM + FORM + ["nonuk", "cancel_share"]},
                "fraction_has_historical_cancellation": data.cancel_share.gt(0).mean(),
            })
    pd.DataFrame(rows).to_csv(folder / "profile_groups.csv", index=False)
    stability = []
    rng = np.random.default_rng(1122)
    draws = [rng.choice(len(profile), size=int(.8 * len(profile)), replace=False) for _ in range(20)]
    for name, columns in [("rfm", RFM), ("rfm_form", RFM + FORM)]:
        log = [i for i, key in enumerate(columns) if key in ("monetary", "frequency", "qty", "skus", "price")]
        feats = profile[columns].to_numpy()
        for replicate, draw in enumerate(draws):
            predicted, _ = FormCluster(feats[draw], log).route(feats)
            stability.append({"system": name, "replicate": replicate,
                              "ARI_to_full_profile_partition": adjusted_rand_score(groups[name], predicted)})
    pd.DataFrame(stability).to_csv(folder / "profile_stability.csv", index=False)

    freq_bin = pd.cut(profile.frequency, bins=[0, 1, 2, 4, 8, 16, 32, np.inf], labels=False)
    for name in ("rfm", "rfm_form"):
        old = pd.crosstab(freq_bin, groups[name].astype(str)).sort_index(axis=1)
        for seed in range(1000, 1100):
            labels = group_random(profile, groups[name], seed)
            new = pd.crosstab(freq_bin, list(labels.values())).sort_index(axis=1)
            assert old.equals(new), (name, seed)
    test_sample = build_view(retail, retail.between("2010-12-01", "2010-12-07"), price)
    count = 0
    for row in test_sample.itertuples():
        if not row.target:
            continue
        lines = retail.items[row.id]
        changed = [(a, b, c * 100, d * 100, e) if b == row.target else (a, b, c, d, e)
                   for a, b, c, d, e in lines]
        assert np.array_equal(np.asarray(row.cart), features([x for x in changed if x[1] != row.target], *price))
        assert row.target not in row.observed
        count += 1
    rng = np.random.default_rng(1123)
    n = 123
    cats = list("ABCDEFGHI")
    targets = rng.choice(cats, size=n).tolist()
    check_arena = Arena(pd.DataFrame({"target": targets, "observed": [frozenset()] * n}))
    proposals = [(cat, (1 << n) - 1) for cat in cats]
    proposals = [(cat, int.from_bytes(rng.bytes(16), "little") & ((1 << n) - 1))
                 for cat in cats[:3]] + proposals
    baseline = check_arena.replay(proposals)
    takeover = [(cat, int.from_bytes(rng.bytes(16), 'little') & ((1 << n) - 1)) for cat in cats[::-1]]
    verify_masks(check_arena, proposals, takeover, baseline, targets)
    details = {**retail.audit, "price_bands_profile": price, "random_strata_checks": 200,
               "masked_cart_price_quantity_perturbations": count, "slot5_scalar_reconciliations": n,
               "cutoff_exclusive": CUTOFF}
    (folder / "source_and_checks.json").write_text(json.dumps(details, ensure_ascii=False, indent=2),
                                                   encoding="utf-8")
    print("Audit: random strata, masked features and exact Slot-5 verified", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "results")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--route", choices=("all", "ab", "c", "audit", "report"), default="all")
    parser.add_argument("--seeds", type=int, default=100)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with threadpool_limits(limits=1):
        if args.route != "report":
            args.repo = args.repo or find_repository(Path(__file__).resolve().parent)
            retail = load_retail(args.repo, args.cache)
        if args.route in ("all", "audit"):
            audit(args.out, retail)
        if args.route in ("all", "ab"):
            route_ab(args.repo, args.out, retail, runtime(args.repo), args.seeds)
        if args.route in ("all", "c"):
            route_c(args.out, retail, runtime(args.repo))
        if args.route in ("all", "report"):
            from retail_report import report
            report(args.out)


if __name__ == "__main__":
    main()
