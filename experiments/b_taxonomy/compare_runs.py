"""Compare LLM tagging runs without human labels (no API calls).

For each run: completion, invalid outputs, other share (by codes and Discovery-weighted), confidence profile.
For each pair of runs: L2 / L1 agreement overall, by gold stratum (head / tail), and the most common disagreements.
Against v0: L1 agreement, and L2 agreement on subcategories whose id is unchanged from v0 (reference only; v0 is
not validated).

Pre-registered check (README section 6): R1 vs R3 L2 agreement >= 85 %.

Usage: python compare_runs.py R1 R2 R3        -> results/llm_runs/compare_R1_R2_R3.md (+ printed)
"""
import itertools
import json
import sys

import pandas as pd

from paths import RESULTS
from taxonomy_io import GOLD_DIR, TAX_CFG, load_catalog

RUNS = RESULTS / "llm_runs"


def load_run(r):
    df = pd.read_csv(RUNS / r / "labels.csv", dtype={"stock_code": str})
    if df.stock_code.duplicated().any():  # per-variant runs: keep one row per code for code-level comparison
        df = df.sort_values(["stock_code", "wording"]).drop_duplicates("stock_code")
    return df.set_index("stock_code")


def pct(x):
    return f"{100 * x:.1f}%"


if __name__ == "__main__":
    runs = sys.argv[1:] or ["R1", "R2", "R3"]
    runs = [r for r in runs if (RUNS / r / "labels.csv").exists()]
    cat = load_catalog().set_index("stock_code")
    strata = pd.read_csv(GOLD_DIR / "gold_items_v1.csv", dtype=str).set_index("stock_code").stratum
    v1_ids = {c["id"] for c in json.loads((TAX_CFG / "taxonomy_v1.json").read_text())["l2"]}
    w = cat.discovery_lines
    L = [f"# LLM 打标签轮次比较：{', '.join(runs)}", "",
         "> `compare_runs.py` 生成；不需要人工标签。一致率不是准确率，准确率要等人工金标准。", "",
         "## 各轮概况", "", "| 轮次 | 商品数 | 不合法 | other（按商品） | other（按购买加权） | 置信度中位数 | 置信度 < 0.7 | 新花费（美元） |",
         "|---|---|---|---|---|---|---|---|"]
    data = {r: load_run(r) for r in runs}
    for r, d in data.items():
        s = json.loads((RUNS / r / "summary.json").read_text())
        ww = w.reindex(d.index).fillna(0)
        oth_w = ww[d.l2_id == "other"].sum() / ww.sum() if ww.sum() else 0
        L.append(f"| {r} | {len(d)} | {int((~d.valid).sum())} | {pct((d.l2_id == 'other').mean())} | {pct(oth_w)} | "
                 f"{d.confidence.median():.2f} | {int((d.confidence < 0.7).sum())} | {s.get('new_cost', 0):.3f} |")
    L += ["", "## 轮次两两一致率（子类 L2 / 大类 L1）", "",
          "| 比较 | L2 一致 | L1 一致 | L2 一致（热门 100） | L2 一致（长尾 100） |", "|---|---|---|---|---|"]
    pairs = {}
    for a, b in itertools.combinations(runs, 2):
        j = data[a][["l2_id", "l1_id"]].join(data[b][["l2_id", "l1_id"]], lsuffix="_a", rsuffix="_b", how="inner")
        j["same2"], j["same1"] = j.l2_id_a == j.l2_id_b, j.l1_id_a == j.l1_id_b
        j["stratum"] = strata.reindex(j.index).fillna("?").str.startswith("head").map({True: "head", False: "tail"})
        pairs[(a, b)] = j
        L.append(f"| {a} vs {b} | {pct(j.same2.mean())} | {pct(j.same1.mean())} | "
                 f"{pct(j[j.stratum == 'head'].same2.mean())} | {pct(j[j.stratum == 'tail'].same2.mean())} |")
    if ("R1", "R3") in pairs:
        ok = pairs[("R1", "R3")].same2.mean() >= 0.85
        L += ["", f"**预先写定的检查：R1 vs R3 子类一致率 ≥ 85% → {'通过 ✅' if ok else '未通过 ❌'}**"]
    L += ["", "## 与 v0 对照（只作参考，v0 未经验证）", "",
          "| 轮次 | L1 一致 | L2 一致（只算 v1 中沿用 v0 id 的子类） |", "|---|---|---|"]
    for r, d in data.items():
        v0 = cat.reindex(d.index)
        same_id = v0.l2_id.isin(v1_ids) | d.l2_id.eq("other")
        L.append(f"| {r} | {pct((d.l1_id == v0.l1_id).mean())} | {pct((d.l2_id == v0.l2_id)[same_id].mean())}（n={int(same_id.sum())}） |")
    for (a, b), j in pairs.items():
        diff = j[~j.same2]
        if diff.empty:
            continue
        L += ["", f"## {a} vs {b}：不一致的商品（共 {len(diff)} 个）", "", f"| 编码 | 商品名 | {a} | {b} |", "|---|---|---|---|"]
        for code, row in diff.iterrows():
            L.append(f"| {code} | {cat.canonical_description.get(code, '')} | {row.l2_id_a} | {row.l2_id_b} |")
    out = RUNS / f"compare_{'_'.join(runs)}.md"
    out.write_text("\n".join(L))
    print("\n".join(L[:40]))
    print(f"\nwrote {out}")
