"""Step 4: re-label C's item-level rules with taxonomy_v0 (same-type vs cross-type) and list high-lift concept pairs."""
import json

import pandas as pd

from paths import CACHE, INPUT, RESULTS, TAXONOMY

tax = pd.read_csv(TAXONOMY / "item_taxonomy_v0.csv", dtype={"stock_code": str}).set_index("stock_code").l2_id
ev = pd.read_csv(INPUT / "rule_evidence.csv.gz", dtype={"seed": str, "group_id": str})
ev = ev[ev.eligible == True]  # noqa: E712
ev["same_type"] = [any(tax.get(a) == tax.get(json.loads(c)[0]) for a in json.loads(A))
                   for A, c in zip(ev.antecedent, ev.consequent)]
rows = []
for (m, s, g), d in ev.groupby(["method", ev.seed.fillna(""), "group_id"]):
    rows.append(dict(method=m, seed=s, group=g, qualified=len(d), same_type=int(d.same_type.sum()),
                     same_type_share=round(d.same_type.mean(), 4), cross_type=int((~d.same_type).sum())))
out = pd.DataFrame(rows)
out.to_csv(RESULTS / "item_rules_same_type_share.csv", index=False)
print("[A] C's item-level qualified rules: antecedent and consequent in the same L2 type")
print(out[out.method != "R"].to_string(index=False))
r = out[out.method == "R"]
print(f"  R (60 groups): same-type share median {r.same_type_share.median():.0%}, cross-type median {r.cross_type.median():.0f}")

res = pd.read_pickle(CACHE / "concept_rules_all_scopes.pkl")
print("\n[B] concept pairs with lift >= 2 and joint >= 50")
for k in [("G", "", "ALL"), ("L", "", "0"), ("L", "", "1"), ("L", "", "2")]:
    d = res[k]
    q = d[d.eligible & (d.lift >= 2) & (d.joint >= 50) & (d.ante.map(len) == 1)]
    print(" ", k[0], k[2], q.drop_duplicates("itemset").shape[0])
d = res[("G", "", "ALL")]
top = (d[d.eligible & (d.joint >= 50) & (d.ante.map(len) == 1)]
       .sort_values(["lift", "joint"], ascending=False).drop_duplicates("itemset").head(25))
top = top[["joint", "support", "confidence", "lift"]].round(4)
top.to_csv(RESULTS / "concept_G_top_pairs_by_lift.csv")
print("\n[C] G top concept pairs by lift (joint >= 50)")
print(top.head(15).to_string())
