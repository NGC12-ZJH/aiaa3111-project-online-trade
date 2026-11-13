"""Step 2: tag every code with an L2 product type (keyword rules, then cluster-majority fallback, else other)."""
import json
import re

import pandas as pd

from .paths import CACHE, RESULTS, TAXONOMY
from .rules_v0 import RULES

COMPILED = [(l2, re.compile(rx)) for l2, _, rx in RULES]
L1_OF = {l2: l1 for l2, l1, _ in RULES}


def rule_tag(desc):
    for l2, rx in COMPILED:
        if rx.search(desc.upper()):
            return l2
    return None


if __name__ == "__main__":
    cat = pd.read_csv(CACHE / "catalog_clusters.csv", dtype={"stock_code": str})
    variants = pd.read_csv(TAXONOMY / "item_description_variants.csv", dtype=str).set_index("stock_code").variants.map(json.loads)
    cat["l2_rule"] = cat.canonical_description.map(rule_tag)
    tagged = cat[cat.schema_item & cat.l2_rule.notna()]
    majority = tagged.groupby("cluster").l2_rule.agg(lambda s: (s.value_counts().index[0], s.value_counts().iloc[0] / len(s)))

    def final(row):
        if pd.notna(row.l2_rule):
            return row.l2_rule, "rule"
        m = majority.get(row.cluster)
        if m is not None and m[1] >= 0.5:
            return m[0], "cluster_majority"
        return "other", "other"

    res = cat.apply(final, axis=1, result_type="expand")
    cat["l2_id"], cat["label_source"] = res[0], res[1]
    cat["l1_id"] = cat.l2_id.map(L1_OF).fillna("other")
    cat["taxonomy_version"] = "taxonomy_v0"
    cols = ["stock_code", "canonical_description", "l2_id", "l1_id", "label_source", "first_seen_split", "schema_item",
            "n_variants", "cluster", "cluster_sim", "discovery_lines", "taxonomy_version"]
    cat[cols].sort_values("stock_code").to_csv(TAXONOMY / "item_taxonomy_v0.csv", index=False)

    # quality checks that need no human labels
    vtags = {c: {rule_tag(v) or "none" for v in vs} for c, vs in variants.items()}
    multi = cat[cat.n_variants > 1]
    variant_ok = multi.stock_code.map(lambda c: len(vtags[c] - {"none"}) <= 1)
    fam = cat.assign(prefix=cat.stock_code.str[:5]).groupby("prefix").filter(lambda g: len(g) > 1).groupby("prefix").l2_id.nunique()
    w = cat.discovery_lines.sum()
    top300 = cat.sort_values("discovery_lines", ascending=False).head(300)
    quality = {
        "codes": len(cat),
        "l2_types_excluding_other": int(cat.l2_id.nunique() - 1),
        "l1_groups_excluding_other": int(cat.l1_id.nunique() - 1),
        "codes_by_label_source": cat.label_source.value_counts().to_dict(),
        "discovery_line_share_by_label_source": (cat.groupby("label_source").discovery_lines.sum() / w).round(4).to_dict(),
        "variant_wording_consistency": round(float(variant_ok.mean()), 4),
        "multi_wording_codes": int(len(multi)),
        "prefix_family_consistency": round(float((fam == 1).mean()), 4),
        "prefix_families": int(len(fam)),
        "top300_other": int((top300.l2_id == "other").sum()),
        "top300_cluster_majority": int((top300.label_source == "cluster_majority").sum()),
    }
    (RESULTS / "taxonomy_v0_quality.json").write_text(json.dumps(quality, indent=1))
    by_l2 = cat.groupby(["l1_id", "l2_id"]).agg(codes=("stock_code", "size"), discovery_lines=("discovery_lines", "sum")).reset_index()
    by_l2["discovery_line_share"] = (by_l2.discovery_lines / w).round(4)
    by_l2.sort_values("discovery_lines", ascending=False).to_csv(RESULTS / "taxonomy_v0_category_sizes.csv", index=False)
    print(json.dumps(quality, indent=1))
