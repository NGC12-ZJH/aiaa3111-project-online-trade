"""Merge A/D agreement and C's adjudication into the final gold labels (standard library + openpyxl).

Rule: label = A's label when A and D agree, unless C overrode it on the optional review sheet; otherwise C's decision.
Inputs : data/taxonomy/gold/gold_human_AD.csv (from gold_agreement.py), data/taxonomy/gold/label_C.xlsx
Output : data/taxonomy/gold/gold_final_v1.csv  stock_code, stratum, gold_l2, gold_l1, source, unsure_A, unsure_D
"""
import csv
import json
import warnings
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[3]
GOLD = ROOT / "data/taxonomy/gold"
TAX = json.loads((ROOT / "configs/taxonomy/taxonomy_v1.json").read_text())
L1 = {c["id"]: c["l1"] for c in TAX["l2"]} | {"other": "other"}

if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=UserWarning)
    rows = {r["stock_code"]: r for r in csv.DictReader(open(GOLD / "gold_human_AD.csv"))}
    wb = load_workbook(GOLD / "label_C.xlsx")
    decided, overrides = {}, {}
    for sheet, store in (("分歧（必裁）", decided), ("一致但两人都不确定（可选复核）", overrides)):
        for r in wb[sheet].iter_rows(min_row=2, values_only=True):
            if r[1] is None:
                continue
            code, lab = str(r[1]).strip(), (r[13] or "").strip()
            if lab:
                assert lab in L1, f"C: invalid label {lab!r} for {code}"
                store[code] = lab
    missing = [c for c, r in rows.items() if r["agree"] == "0" and c not in decided]
    assert not missing, f"C did not adjudicate: {missing}"
    out, src_count = [], {}
    for c, r in sorted(rows.items()):
        if r["agree"] == "1":
            lab, src = (overrides[c], "C_override") if c in overrides else (r["agreed_label"], "A=D")
        else:
            lab = decided[c]
            src = "C=A" if lab == r["label_A"] else "C=D" if lab == r["label_D"] else "C_third"
        src_count[src] = src_count.get(src, 0) + 1
        out.append([c, r["stratum"], lab, L1[lab], src, r["unsure_A"], r["unsure_D"]])
    with open(GOLD / "gold_final_v1.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stock_code", "stratum", "gold_l2", "gold_l1", "source", "unsure_A", "unsure_D"])
        w.writerows(out)
    print(f"gold_final_v1.csv: {len(out)} items | sources {src_count} | distinct L2 {len({o[2] for o in out})}")
