"""Exploration: (1) do bulk buyers buy only one product line? (2) how new are products in Validation?

Uses Discovery and Validation only; the Test period is not read.
"""
import re

import numpy as np
import pandas as pd

from .paths import INPUT, RESULTS

COLOUR = set("""RED PINK BLUE GREEN WHITE BLACK IVORY CREAM YELLOW PURPLE ORANGE SILVER GOLD BROWN GREY GRAY
NATURAL ANTIQUE VINTAGE SPOTTY SPOTS SPOT RETROSPOT POLKADOT DOTS DOT STRIPE STRIPES STRIPEY PAISLEY BAROQUE
PASTEL BRIGHT LIGHT DARK CLEAR COLOUR COLOURED ASSORTED FINISH FLORAL LILAC TURQUOISE MAGENTA""".split())
GENERIC = set("SET OF THE AND WITH IN PACK DESIGN SMALL LARGE MINI MEDIUM TIER PIECE".split())
names = pd.read_csv(INPUT / "product_names.csv", dtype=str).set_index("stock_code").description.to_dict()
words = {c: {w for w in re.findall(r"[A-Z]+", d) if len(w) > 1 and w not in COLOUR and w not in GENERIC} for c, d in names.items()}


def linked(a, b, strict):
    if a[:5] == b[:5]:
        return True
    wa, wb = words.get(a, set()), words.get(b, set())
    return (bool(wa) and wa == wb) if strict else bool(wa & wb)


def series_stats(codes, strict):
    codes = list(codes)
    parent = list(range(len(codes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            if linked(codes[i], codes[j], strict):
                parent[find(i)] = find(j)
    sizes = pd.Series([find(i) for i in range(len(codes))]).value_counts()
    return len(sizes), sizes.iloc[0] / len(codes), sizes[sizes > 1].sum() / len(codes)


cl = pd.read_csv(INPUT / "customer_clusters.csv", dtype=str).set_index("customer_id").cluster_id
t = pd.read_csv(INPUT / "clean_transactions.csv.gz", dtype={"invoice_id": str, "stock_code": str, "customer_id": str},
                usecols=["invoice_id", "stock_code", "quantity", "customer_id", "split", "is_valid_basket_item"])
t = t[(t.is_valid_basket_item == 1) & (t.split == "discovery") & t.customer_id.isin(cl.index)]
t = t.groupby(["invoice_id", "customer_id", "stock_code"], as_index=False).quantity.sum()
cust_type = t.groupby("customer_id").quantity.median().map(
    lambda q: "bulk (median qty/line >= 12)" if q >= 12 else ("small (<= 2)" if q <= 2 else "middle"))
rows = []
for (inv, cust), g in t.groupby(["invoice_id", "customer_id"]):
    for strict in (False, True):
        k, top, paired = series_stats(g.stock_code, strict)
        rows.append(dict(definition="strict" if strict else "broad", customer_type=cust_type[cust], items=len(g),
                         series=k, largest_series_share=top, items_with_partner=paired))
b = pd.DataFrame(rows)
summary = (b.groupby(["definition", "customer_type"])
           .agg(baskets=("items", "size"), items_median=("items", "median"), series_median=("series", "median"),
                largest_series_share_median=("largest_series_share", "median"),
                items_with_same_series_partner=("items_with_partner", "mean"),
                single_series_baskets=("series", lambda s: (s == 1).mean())).round(3).reset_index())
summary.to_csv(RESULTS / "explore_basket_composition.csv", index=False)
print(summary.to_string(index=False))

bl = pd.read_csv(INPUT / "baskets_long.csv.gz", dtype=str)
bl = bl[bl.is_eligible_for_main_comparison == "1"]
seen = set(bl[bl.split == "discovery"].stock_code)
v = bl[bl.split == "validation"].assign(new=lambda d: ~d.stock_code.isin(seen))
per = v.groupby("basket_id").new
novelty = dict(validation_baskets=v.basket_id.nunique(), line_share_unseen=round(v.new.mean(), 4),
               baskets_with_any_unseen=round(per.any().mean(), 4), baskets_all_unseen=round(per.all().mean(), 4),
               line_share_unseen_prefix5=round((~v.stock_code.str[:5].isin({c[:5] for c in seen})).mean(), 4))
pd.Series(novelty).to_csv(RESULTS / "explore_validation_novelty.csv", header=["value"])
print(novelty)
