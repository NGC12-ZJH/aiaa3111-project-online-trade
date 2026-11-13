"""Draw the 200-item gold standard and write blind annotation sheets (no machine labels shown).

Design (README section 6, fixed before any labelling):
- Stratum "head": 100 codes drawn at random from the 500 codes with most Discovery lines.
- Stratum "tail": 100 codes from the remaining codes: 10 v0 `cluster_majority`, 10 v0 `other`, and
  80 v0 `rule` codes stratified by v0 L1 (proportional, largest remainder, at least 2 per L1).
- Only codes first seen in Profile / Discovery / Validation are eligible (no Test-period items).
- Fixed seed; the sample list is committed before anyone labels it.

Outputs (data/taxonomy/gold/):
- gold_items_v1.csv           stock_code, stratum, v0 L1 used for stratification (for the analysis only)
- gold_blind_sheet_A.csv / _D.csv   shuffled; only code and wordings; empty label columns
"""
import json

import numpy as np
import pandas as pd

from .taxonomy_io import GOLD_DIR, load_catalog

SEED = 3111
N_HEAD, TOP_K, N_TAIL_FALLBACK, N_TAIL_OTHER, N_TAIL_RULE = 100, 500, 10, 10, 80


def largest_remainder(sizes, total, minimum):
    alloc = {k: minimum for k in sizes.index}
    rest = total - minimum * len(sizes)
    quota = sizes / sizes.sum() * rest
    for k in sizes.index:
        alloc[k] += int(np.floor(quota[k]))
    left = total - sum(alloc.values())
    for k in (quota - np.floor(quota)).sort_values(ascending=False).index[:left]:
        alloc[k] += 1
    return alloc


if __name__ == "__main__":
    out = GOLD_DIR / "gold_items_v1.csv"
    if out.exists():
        raise SystemExit(f"{out} already exists; the gold sample is fixed once drawn. Delete it only on purpose.")
    rng = np.random.default_rng(SEED)
    cat = load_catalog()
    elig = cat[cat.first_seen_split.isin(["profile", "discovery", "validation"])]
    ranked = elig.sort_values(["discovery_lines", "stock_code"], ascending=[False, True])
    top = ranked.head(TOP_K)
    head = top.loc[rng.choice(top.index, N_HEAD, replace=False)].assign(stratum="head")

    rest = elig.drop(top.index)
    parts = []
    for src, n in (("cluster_majority", N_TAIL_FALLBACK), ("other", N_TAIL_OTHER)):
        pool = rest[rest.label_source == src]
        parts.append(pool.loc[rng.choice(pool.index, n, replace=False)].assign(stratum=f"tail_{src}"))
    rule = rest[rest.label_source == "rule"]
    alloc = largest_remainder(rule.l1_id.value_counts().sort_index(), N_TAIL_RULE, 2)
    for l1, n in alloc.items():
        pool = rule[rule.l1_id == l1]
        parts.append(pool.loc[rng.choice(pool.index, n, replace=False)].assign(stratum="tail_rule"))
    gold = pd.concat([head] + parts)
    assert len(gold) == 200 and gold.stock_code.is_unique

    w = cat.discovery_lines.sum()
    gold[["stock_code", "stratum", "l1_id"]].rename(columns={"l1_id": "v0_l1_for_stratification"}) \
        .sort_values("stock_code").to_csv(out, index=False)

    for who, seed in (("A", SEED + 1), ("D", SEED + 2)):
        sheet = gold.sample(frac=1, random_state=seed)
        pd.DataFrame({
            "row": range(1, len(sheet) + 1),
            "stock_code": sheet.stock_code.values,
            "all_wordings": [" | ".join(v) for v in sheet.variants],
            "l2_id": "", "uncertain": "", "note": "",
        }).to_csv(GOLD_DIR / f"gold_blind_sheet_{who}.csv", index=False)

    summary = {
        "seed": SEED, "n": len(gold), "strata": gold.stratum.value_counts().to_dict(),
        "tail_rule_by_v0_l1": alloc,
        "top500_share_of_discovery_lines": round(float(top.discovery_lines.sum() / w), 4),
        "gold_share_of_discovery_lines": round(float(gold.discovery_lines.sum() / w), 4),
        "first_seen_split": gold.first_seen_split.value_counts().to_dict(),
    }
    (GOLD_DIR / "gold_sample_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
