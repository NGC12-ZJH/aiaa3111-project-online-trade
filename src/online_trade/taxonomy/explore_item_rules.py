"""Exploration (before taxonomy_v0): how many of C's item-level rules are same-series, by a keyword heuristic.

narrow = same 5-character code prefix, or identical name once colour/size words are removed.
broad  = names share any word once colour and generic words are removed (same type or same design line).
"""
import json
import re

import pandas as pd

from .paths import INPUT, RESULTS

COLOUR = set("""RED PINK BLUE GREEN WHITE BLACK IVORY CREAM YELLOW PURPLE ORANGE SILVER GOLD BROWN GREY GRAY
NATURAL ANTIQUE VINTAGE SPOTTY SPOTS SPOT RETROSPOT POLKADOT DOTS DOT STRIPE STRIPES STRIPEY PAISLEY BAROQUE
PASTEL BRIGHT LIGHT DARK CLEAR COLOUR COLOURED ASSORTED FINISH FLORAL LILAC TURQUOISE MAGENTA""".split())
GENERIC = set("SET OF THE AND WITH IN PACK DESIGN SMALL LARGE MINI MEDIUM TIER PIECE".split())

names = pd.read_csv(INPUT / "product_names.csv", dtype=str).set_index("stock_code").description.to_dict()


def content(code):
    return {t for t in re.findall(r"[A-Z]+", names.get(code, "")) if len(t) > 1 and t not in COLOUR and t not in GENERIC}


def narrow(a, c):
    return a[:5] == c[:5] or (bool(content(a)) and content(a) == content(c))


def broad(a, c):
    return bool(content(a) & content(c))


ev = pd.read_csv(INPUT / "rule_evidence.csv.gz", dtype={"seed": str, "group_id": str})
ev = ev[ev.eligible == True].copy()  # noqa: E712
ev["ante"] = ev.antecedent.map(json.loads)
ev["cons"] = ev.consequent.map(lambda s: json.loads(s)[0])
ev["narrow"] = [any(narrow(a, c) for a in A) for A, c in zip(ev.ante, ev.cons)]
ev["broad"] = [any(broad(a, c) for a in A) for A, c in zip(ev.ante, ev.cons)]
rows = []
for (m, s, g), d in ev.groupby(["method", ev.seed.fillna(""), "group_id"]):
    rows.append(dict(method=m, seed=s, group=g, qualified=len(d), left_after_narrow=int((~d.narrow).sum()),
                     left_after_broad=int((~d.broad).sum())))
out = pd.DataFrame(rows)
out.to_csv(RESULTS / "explore_item_rules_keyword_same_series.csv", index=False)
print(out[out.method != "R"].to_string(index=False))
print(out[out.method == "R"].groupby("group")[["qualified", "left_after_narrow", "left_after_broad"]].median())
