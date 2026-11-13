"""After R5 and R6: robustness check, final label table and quality checks for taxonomy_v1 (no API calls).

R5 check (pre-registered): share of multi-wording codes whose wordings all get the same L2 >= 90 %.
Final labels: R6 (main method = R2 configuration). For the 200 gold items the human gold label is used instead
(label_source = human_gold; README section 6 allows human corrections recorded as such, never overwriting the LLM
output, which stays in llm_tag_* columns). Invalid LLM outputs are kept as other (label_source = llm_invalid_other).

Checks: other share by codes and Discovery-weighted (<= 5 %), invalid count, prefix-family consistency,
consecutive-code series consistency (same description stem, e.g. "TOAST ITS - ..."), agreement with v0 at L1,
subcategory sizes. Writes a human review list ordered by Discovery lines (top 1,000 popular codes that are other,
invalid, or inconsistent within their family / series).

Outputs: data/taxonomy/item_taxonomy_v1.csv, results/v1_final_checks.md, results/v1_final_checks.json,
         results/v1_review_list.csv
"""
import json
import re

import pandas as pd

from paths import RESULTS, TAXONOMY
from taxonomy_io import GOLD_DIR, TAX_CFG, V1_WORK, load_catalog, prefix

RUNS = RESULTS / "llm_runs"


def pct(x):
    return f"{100 * x:.1f}%"


def stem(desc):
    """Series stem: text before ' - ' or ',' (e.g. 'TOAST ITS - DINOSAUR' -> 'TOAST ITS')."""
    m = re.split(r"\s+-\s+|,", desc, maxsplit=1)
    return m[0].strip() if len(m) > 1 else None


if __name__ == "__main__":
    tax = json.loads((TAX_CFG / "taxonomy_v1.json").read_text())
    l1_of = {c["id"]: c["l1"] for c in tax["l2"]} | {"other": "other"}
    name = {c["id"]: c["name_zh"] for c in tax["l2"]} | {"other": "其他"}
    cat = load_catalog()
    attrs = pd.read_csv(TAXONOMY / "item_attributes_v1.csv", dtype=str)
    gold = pd.read_csv(GOLD_DIR / "gold_final_v1.csv", dtype=str).set_index("stock_code")
    w_all = cat.discovery_lines.sum()

    # ---- R5: robustness across wordings
    r5 = pd.read_csv(RUNS / "R5" / "labels.csv", dtype=str)
    per = r5.groupby("stock_code").l2_id.agg(lambda s: s.nunique())
    r5_cons = float((per == 1).mean())
    r5_l1 = float(r5.assign(l1=r5.l2_id.map(l1_of)).groupby("stock_code").l1.nunique().eq(1).mean())
    r5_bad = per[per > 1].index

    # ---- R6: final labels
    r6 = pd.read_csv(RUNS / "R6" / "labels.csv", dtype=str).set_index("stock_code")
    missing = sorted(set(cat.stock_code) - set(r6.index))
    df = cat[["stock_code", "canonical_description", "first_seen_split", "schema_item", "n_variants", "discovery_lines",
              "l2_id", "l1_id"]].rename(columns={"l2_id": "v0_l2", "l1_id": "v0_l1"}).set_index("stock_code")
    df["llm_tag_l2"] = r6.l2_id.reindex(df.index)
    df["llm_tag_valid"] = r6.valid.reindex(df.index)
    df["llm_tag_confidence"] = r6.confidence.reindex(df.index)
    df["llm_tag_note"] = r6.note.reindex(df.index).fillna("")
    df["l2_id"] = df.llm_tag_l2.fillna("other")
    df["label_source"] = "llm_R6"
    df.loc[df.llm_tag_valid.eq("False"), "label_source"] = "llm_invalid_other"
    df.loc[df.llm_tag_l2.isna(), "label_source"] = "missing_other"
    g = gold.gold_l2.reindex(df.index)
    df.loc[g.notna(), "l2_id"] = g[g.notna()]
    df.loc[g.notna(), "label_source"] = "human_gold"
    # human corrections after evaluation (not blind): rules in configs + item-level review decisions
    ov = json.loads((TAX_CFG / "v1_label_overrides.json").read_text())
    fixes = [(c, r["to"]) for r in ov["rules"] for c in r["codes"]]
    rev_f = V1_WORK / "review_v1_decisions.csv"
    if rev_f.exists():
        fixes += [(r.stock_code, r.reviewed_l2) for r in pd.read_csv(rev_f, dtype=str).itertuples()]
    for c, to in fixes:
        assert to in l1_of, f"override target {to} not in taxonomy"
        if df.at[c, "label_source"] != "human_gold":
            df.at[c, "l2_id"] = to
            df.at[c, "label_source"] = "human_override"
    df["l1_id"] = df.l2_id.map(l1_of)
    df = df.join(attrs.set_index("stock_code"))
    df["taxonomy_version"] = "taxonomy_v1"
    cols = ["canonical_description", "l2_id", "l1_id", "season", "design_line", "label_source", "llm_tag_l2",
            "llm_tag_confidence", "llm_tag_note", "first_seen_split", "schema_item", "n_variants", "discovery_lines",
            "v0_l2", "v0_l1", "taxonomy_version"]
    df[cols].sort_index().to_csv(TAXONOMY / "item_taxonomy_v1.csv")

    # ---- checks
    oth = df.l2_id.eq("other")
    oth_w = df.discovery_lines[oth].sum() / w_all
    fam = df.assign(f=df.index.map(prefix)).groupby("f").filter(lambda x: len(x) > 1).groupby("f").l2_id.nunique()
    df["stem"] = df.canonical_description.map(stem)
    ser = df[df.stem.notna()].groupby("stem").filter(lambda x: len(x) > 1).groupby("stem").l2_id.nunique()
    sizes = df.groupby(["l1_id", "l2_id"]).agg(codes=("canonical_description", "size"), lines=("discovery_lines", "sum"))
    sizes["share"] = sizes.lines / w_all
    l1_v0 = float((df.l1_id == df.v0_l1).mean())
    gold_vs_llm = float((df.loc[g.notna(), "llm_tag_l2"] == g[g.notna()]).mean())

    top = df.sort_values("discovery_lines", ascending=False).head(1000)
    fam_bad = set(fam[fam > 1].index)
    ser_bad = set(ser[ser > 1].index)
    reasons = pd.Series("", index=top.index)
    reasons[top.l2_id.eq("other")] += "other;"
    reasons[top.label_source.eq("llm_invalid_other")] += "invalid;"
    reasons[top.index.map(prefix).isin(fam_bad)] += "family_inconsistent;"
    reasons[top.stem.isin(ser_bad)] += "series_inconsistent;"
    reasons[top.index.isin(r5_bad)] += "wording_inconsistent;"
    review = top[reasons.ne("")].assign(reason=reasons[reasons.ne("")])
    # add every member of a flagged family / series, even outside the top 1,000, so the whole group can be fixed
    fl_fam = {prefix(c) for c in review.index[review.reason.str.contains("family")]}
    fl_ser = set(review.stem[review.reason.str.contains("series")].dropna())
    extra = df[(df.index.map(prefix).isin(fl_fam) | df.stem.isin(fl_ser)) & ~df.index.isin(review.index)]
    extra = extra.assign(reason=["family_inconsistent;" if prefix(c) in fl_fam else "series_inconsistent;" for c in extra.index])
    review = pd.concat([review, extra]).assign(l2_name=lambda x: x.l2_id.map(name))
    review = review.sort_values("discovery_lines", ascending=False)
    review = review[~review.label_source.isin(["human_gold", "human_override"])]
    review[["canonical_description", "l2_id", "l2_name", "reason", "discovery_lines"]].to_csv(RESULTS / "v1_review_list.csv")

    res = {
        "R5_codes": int(per.size), "R5_l2_consistency": round(r5_cons, 4), "R5_l1_consistency": round(r5_l1, 4),
        "R5_pass_90": r5_cons >= 0.90,
        "R6_codes": int(len(r6)), "missing_codes": missing, "invalid": int(df.label_source.eq("llm_invalid_other").sum()),
        "human_gold_used": int(df.label_source.eq("human_gold").sum()),
        "human_override": int(df.label_source.eq("human_override").sum()),
        "gold_items_llm_equals_gold": round(gold_vs_llm, 4),
        "other_codes_share": round(float(oth.mean()), 4), "other_weighted_share": round(float(oth_w), 4),
        "other_pass_5pct": bool(oth.mean() <= 0.05 and oth_w <= 0.05),
        "prefix_family_consistency": round(float((fam == 1).mean()), 4), "prefix_families": int(len(fam)),
        "series_consistency": round(float((ser == 1).mean()), 4), "series": int(len(ser)),
        "l1_agreement_with_v0": round(l1_v0, 4), "n_l2_used": int(df.l2_id.nunique()),
        "max_l2_share": round(float(sizes.share.max()), 4), "review_list": int(len(review)),
        "season_counts": df.season.value_counts().to_dict(),
        "R6_cost_incl_cached": json.loads((RUNS / "R6" / "summary.json").read_text()).get("run_cost_incl_cached"),
        "R5_cost_incl_cached": json.loads((RUNS / "R5" / "summary.json").read_text()).get("run_cost_incl_cached"),
    }
    (RESULTS / "v1_final_checks.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))

    L = ["# taxonomy_v1 全量标签与质量检查", "", "> `v1_finalize_labels.py` 生成。最终标签 = R6（主方法 R2 配置）；200 个金标准商品使用人工标签。", "",
         "| 检查 | 结果 | 门槛 / 说明 |", "|---|---|---|",
         f"| R5 多写法一致（子类） | {pct(r5_cons)}（{per.size} 个多写法商品） | ≥ 90% → {'通过 ✅' if r5_cons >= 0.9 else '未通过 ❌'} |",
         f"| R5 多写法一致（大类） | {pct(r5_l1)} | 只报告 |",
         f"| R6 覆盖 | {len(r6)} / {len(cat)} | 缺失 {len(missing)} 个 |",
         f"| 不合法输出（记为 other） | {res['invalid']} | — |",
         f"| 人工标签：金标准 / 评测后人工修正 | {res['human_gold_used']} / {res['human_override']} | 修正记为 human_override，LLM 原始输出保留在 llm_tag_l2 |",
         f"| other 占比（按商品 / 按购买加权） | {pct(oth.mean())} / {pct(oth_w)} | ≤ 5% → {'通过 ✅' if res['other_pass_5pct'] else '未通过 ❌'} |",
         f"| 编码前缀家族内一致 | {pct(res['prefix_family_consistency'])}（{len(fam)} 个家族） | 只报告；v0 为 91.4% |",
         f"| 同名系列内一致（如 TOAST ITS） | {pct(res['series_consistency'])}（{len(ser)} 个系列） | 只报告 |",
         f"| 金标准 200 个：LLM 与人工一致 | {pct(gold_vs_llm)} | 应与 R2 的 90.0% 相同（同一缓存） |",
         f"| 与 v0 的大类一致 | {pct(l1_v0)} | 只作参考 |",
         f"| 用到的子类数 / 最大子类占购买比例 | {res['n_l2_used']} / {pct(res['max_l2_share'])} | — |",
         f"| 人工复核清单（最热门 1,000 个中有疑问的） | {len(review)} 个 | `results/v1_review_list.csv` |", "",
         "## 最大的 15 个子类（按 Discovery 购买）", "", "| 大类 | 子类 | 商品数 | 购买占比 |", "|---|---|---|---|"]
    for (l1, l2), r in sizes.sort_values("lines", ascending=False).head(15).iterrows():
        L.append(f"| {l1} | {l2}（{name.get(l2, '')}） | {r.codes} | {pct(r.share)} |")
    L += ["", "## R5：不同写法得到不同子类的商品（前 30 个）", "", "| 编码 | 各写法的标签 |", "|---|---|"]
    for code in list(r5_bad)[:30]:
        x = r5[r5.stock_code == code]
        L.append(f"| {code} | " + "；".join(f"{a} → {b}" for a, b in zip(x.wording, x.l2_id)) + " |")
    (RESULTS / "v1_final_checks.md").write_text("\n".join(L))
    print(json.dumps({k: v for k, v in res.items() if k != "missing_codes"}, indent=1, ensure_ascii=False))
