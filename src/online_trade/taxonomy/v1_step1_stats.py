"""taxonomy_v1 step 1 (no LLM): size statistics of the v0 subcategories and split / merge flags.

Structure is decided on schema items only (first seen before 2010-12-01). Discovery basket counts
are used only to flag subcategories that are too large or too small, never to label items.

Flags (fixed in advance):
- split: Discovery line share >= 3.5 %, or more than 150 schema codes (other is handled separately)
- merge: present in fewer than 20 Discovery baskets
Output: results/v1_subcategory_stats.csv
"""
import pandas as pd

from .paths import INPUT, RESULTS, SCHEMA_CUTOFF
from .taxonomy_io import load_catalog

SPLIT_SHARE, SPLIT_CODES, MERGE_BASKETS = 0.035, 150, 20

if __name__ == "__main__":
    cat = load_catalog()
    b = pd.read_csv(INPUT / "baskets_long.csv.gz", dtype=str, usecols=["basket_id", "stock_code", "split"])
    b = b[b.split == "discovery"].merge(cat[["stock_code", "l2_id"]], on="stock_code")
    baskets = b.groupby("l2_id").basket_id.nunique()
    schema = cat[cat.first_seen < SCHEMA_CUTOFF]
    s = cat.groupby(["l1_id", "l2_id"]).agg(codes=("stock_code", "size"), discovery_lines=("discovery_lines", "sum")).reset_index()
    s["schema_codes"] = s.l2_id.map(schema.l2_id.value_counts()).fillna(0).astype(int)
    s["discovery_line_share"] = (s.discovery_lines / cat.discovery_lines.sum()).round(4)
    s["discovery_baskets"] = s.l2_id.map(baskets).fillna(0).astype(int)
    s["flag"] = ""
    s.loc[(s.discovery_line_share >= SPLIT_SHARE) | (s.schema_codes > SPLIT_CODES), "flag"] = "split"
    s.loc[s.discovery_baskets < MERGE_BASKETS, "flag"] = "merge"
    s.loc[s.l2_id == "other", "flag"] = "reassign_other"
    s = s.sort_values("discovery_lines", ascending=False)
    s.to_csv(RESULTS / "v1_subcategory_stats.csv", index=False)
    print(s[s.flag != ""].to_string(index=False))
