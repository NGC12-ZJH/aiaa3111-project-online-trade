"""Write results/taxonomy_v1_review.md: a human-readable sheet of configs/taxonomy/taxonomy_v1.json (no LLM)."""
import json

import pandas as pd

from .paths import RESULTS
from .taxonomy_io import TAX_CFG, V1_WORK

if __name__ == "__main__":
    t = json.loads((TAX_CFG / "taxonomy_v1.json").read_text())
    seeds = pd.read_csv(V1_WORK / "seed_labels_v1.csv")
    n = seeds.l2_id.value_counts()
    fixed = seeds[seeds.source == "human_override"].l2_id.value_counts()
    cell = lambda x: str(x).replace("|", "/").replace("\n", " ")
    L = ["# taxonomy_v1 草稿审阅表", "",
         f"> 由 `v1_step3_build.py` 生成（{t['built']}），本表由 `v1_review_sheet.py` 生成。状态：{t['status']}",
         "> 修改请改 `configs/taxonomy/taxonomy_v1_decisions.json`（`edits` 改文字，`seed_overrides` 改种子标签），再重跑第 3 步。", "",
         f"共 {len(t['l2'])} 个子类、{len({c['l1'] for c in t['l2']})} 个大类，另有 other。"
         "“种子数”= 参考例子池里该子类的已标注早期商品数（括号内为人工纠正后移入的数量）；“✎”= 定义经人工修改。", ""]
    for l1 in sorted({c["l1"] for c in t["l2"]}):
        L += [f"## {l1}", "", "| id | 中文名 | 来源 | 种子数 | 定义 | 边界 | 例子 |", "|---|---|---|---|---|---|---|"]
        for c in (c for c in t["l2"] if c["l1"] == l1):
            o = c["origin"] + (" ＋合并 " + ", ".join(c["merged_from"]) if c.get("merged_from") else "")
            k = f"{n.get(c['id'], 0)}" + (f"（+{fixed[c['id']]}）" if c["id"] in fixed else "")
            mark = " ✎" if c.get("edited_by_human") else ""
            L.append(f"| `{c['id']}` | {cell(c['name_zh'])}{mark} | {o} | {k} | {cell(c['definition'])} | "
                     f"{cell(c['boundary'])} | {cell('; '.join(c['examples']))} |")
        L.append("")
    (RESULTS / "taxonomy_v1_review.md").write_text("\n".join(L))
    print("wrote", RESULTS / "taxonomy_v1_review.md")
