"""Evaluate labelling methods on the final gold standard and apply the pre-registered selection rule (no API calls).

Methods: v0 keyword rules, R2 (LLM zero-shot), R1 (LLM + 5 examples, main), R3 (R1 with reworded prompt), and
the two human annotators as a reference (their accuracy is optimistic: the gold labels are built from them).

Metrics: L2 / L1 accuracy (Wilson 95% CI), macro-F1 over L2, Discovery-weighted L2 accuracy, head / tail strata,
items both annotators were sure about vs. any-unsure items, exact McNemar test for R1 vs R2 / R1 vs v0.

Pre-registered rule (README section 6): among v0, R2, R1 the highest L2 accuracy wins; within 2 points prefer the higher
Discovery-weighted accuracy. Freeze only if L1 >= 90 % and L2 >= 80 %; 70-80 % allows one revision re-checked on a fresh
100-item sample; < 70 % means the main experiments use L1.

v0 note: v0 uses the old 53 subcategories, so at L2 it can only be right where the gold subcategory keeps a v0 id; we
also report v0 on that subset.

Usage: python scripts/run_taxonomy.py evaluate_gold   -> results/gold/evaluation_v1.md (+ printed summary)
"""
import json
from math import comb, sqrt

import pandas as pd

from .paths import RESULTS, ROOT
from .taxonomy_io import GOLD_DIR, TAX_CFG, load_catalog

OUT = RESULTS / "gold"
OUT.mkdir(parents=True, exist_ok=True)


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def mcnemar(a_ok, b_ok):
    b = int((a_ok & ~b_ok).sum())
    c = int((~a_ok & b_ok).sum())
    n = b + c
    p = min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n) if n else 1.0
    return b, c, p


def macro_f1(y, p):
    labels = sorted(set(y) | set(p))
    f = []
    for lab in labels:
        tp = ((y == lab) & (p == lab)).sum()
        fp = ((y != lab) & (p == lab)).sum()
        fn = ((y == lab) & (p != lab)).sum()
        f.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return sum(f) / len(f)


def pct(x):
    return f"{100 * x:.1f}%"


if __name__ == "__main__":
    tax = json.loads((TAX_CFG / "taxonomy_v1.json").read_text())
    v1_ids = {c["id"] for c in tax["l2"]} | {"other"}
    name = {c["id"]: c["name_zh"] for c in tax["l2"]} | {"other": "其他"}
    g = pd.read_csv(GOLD_DIR / "gold_final_v1.csv", dtype=str).set_index("stock_code")
    h = pd.read_csv(GOLD_DIR / "gold_human_AD.csv", dtype=str).set_index("stock_code")
    cat = load_catalog().set_index("stock_code")
    g["w"] = cat.discovery_lines.reindex(g.index).astype(float)
    g["head"] = g.stratum.eq("head")
    g["sure"] = g.unsure_A.eq("0") & g.unsure_D.eq("0")

    preds = {"v0 关键词规则": (cat.l2_id.reindex(g.index), cat.l1_id.reindex(g.index))}
    notes = {}
    for r, label in (("R2", "R2 LLM 不给例子"), ("R1", "R1 LLM + 5 例子（主方法）"), ("R3", "R3 换措辞（稳定性）")):
        d = pd.read_csv(RESULTS / "llm_runs" / r / "labels.csv", dtype=str).set_index("stock_code")
        preds[label] = (d.l2_id.reindex(g.index), d.l1_id.reindex(g.index))
        notes[label] = d.note.reindex(g.index).fillna("")
    l1_of = {c["id"]: c["l1"] for c in tax["l2"]} | {"other": "other"}
    for who in ("A", "D"):
        lab = h[f"label_{who}"].reindex(g.index)
        preds[f"标注人 {who}（参照）"] = (lab, lab.map(l1_of))

    rows, ok = [], {}
    for m, (p2, p1) in preds.items():
        c2, c1 = p2.eq(g.gold_l2), p1.eq(g.gold_l1)
        ok[m] = c2
        lo, hi = wilson(int(c2.sum()), len(g))
        rows.append(dict(method=m, l2=c2.mean(), ci=f"{pct(lo)}–{pct(hi)}", l1=c1.mean(), f1=macro_f1(g.gold_l2, p2.fillna("NA")),
                         wl2=(g.w * c2).sum() / g.w.sum(), hd=c2[g["head"]].mean(), tl=c2[~g["head"]].mean(),
                         sure=c2[g.sure].mean(), unsure=c2[~g.sure].mean()))
    T = pd.DataFrame(rows).set_index("method")

    same_id = g.gold_l2.isin(set(cat.l2_id))
    v0_sub = ok["v0 关键词规则"][same_id].mean()

    cand = ["v0 关键词规则", "R2 LLM 不给例子", "R1 LLM + 5 例子（主方法）"]
    best = T.loc[cand].l2.idxmax()
    close = [m for m in cand if T.loc[best].l2 - T.loc[m].l2 <= 0.02]
    chosen = max(close, key=lambda m: T.loc[m].wl2)
    l1c, l2c = T.loc[chosen].l1, T.loc[chosen].l2
    verdict = ("达标，可以冻结（大类 ≥ 90%、子类 ≥ 80%）" if l1c >= 0.9 and l2c >= 0.8 else
               "子类在 70–80%：允许改一次，在新抽的 100 个商品上复验" if l2c >= 0.7 else "子类 < 70%：主实验改用大类")

    L = ["# taxonomy_v1_rc1 金标准评测", "",
         f"> `evaluate_gold.py` 生成。金标准 200 个商品（A、D 独立盲标，C 裁定 15 个分歧），覆盖 {g.gold_l2.nunique()} 个子类。"
         "准确率的 95% 置信区间用 Wilson 方法；n = 200 时区间宽约 ±5 个百分点。", "",
         "## 1. 主表", "",
         "| 方法 | 子类准确率 | 子类 95% CI | 大类准确率 | 子类宏平均 F1 | 按购买量加权子类准确率 | 热门 100 | 长尾 100 | 两人都确定的 146 个 | 有人不确定的 54 个 |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for m, r in T.iterrows():
        L.append(f"| {m} | **{pct(r.l2)}** | {r.ci} | {pct(r.l1)} | {r.f1:.3f} | {pct(r.wl2)} | {pct(r.hd)} | {pct(r.tl)} | {pct(r.sure)} | {pct(r.unsure)} |")
    L += ["", f"- v0 只有旧的 53 个子类，在被拆分过的子类上必然答错。只看金标准子类仍沿用 v0 代码的 {int(same_id.sum())} 个商品，v0 子类准确率为 {pct(v0_sub)}。",
          "- 标注人 A、D 的准确率偏高（金标准就是由他们得出的），只作为“人能做到多好”的参照上限。", ""]
    b, c, p = mcnemar(ok["R1 LLM + 5 例子（主方法）"], ok["R2 LLM 不给例子"])
    b0, c0, p0 = mcnemar(ok["R1 LLM + 5 例子（主方法）"], ok["v0 关键词规则"])
    L += ["## 2. 两两比较（McNemar 精确检验）", "",
          "| 比较 | 只有前者对 | 只有后者对 | p 值 |", "|---|---|---|---|",
          f"| R1 vs R2（例子的作用） | {b} | {c} | {p:.3f} |",
          f"| R1 vs v0 | {b0} | {c0} | {p0:.3g} |", "",
          "## 3. 按预先写定规则的结论", "",
          f"- 候选（v0、R2、R1）中子类准确率最高：**{best}**；与其相差 ≤ 2 个百分点的候选：{', '.join(close)}；按规则选出主方法：**{chosen}**。",
          f"- 主方法大类 {pct(l1c)}、子类 {pct(l2c)} → **{verdict}**。", ""]

    r1 = preds["R1 LLM + 5 例子（主方法）"][0]
    err = g[~ok["R1 LLM + 5 例子（主方法）"]].assign(pred=r1)
    pairs = err.groupby(["gold_l2", "pred"]).size().sort_values(ascending=False)
    L += [f"## 4. R1 的错误（{len(err)} 个）", "",
          "| 编码 | 商品名 | 金标准 | R1 | 人是否确定 | 来源 | R1 备注 |", "|---|---|---|---|---|---|---|"]
    for code, r in err.iterrows():
        L.append(f"| {code} | {cat.canonical_description.get(code, '')} | {r.gold_l2}（{name.get(r.gold_l2, '')}） | {r.pred}（{name.get(r.pred, '')}） | "
                 f"{'都确定' if r.sure else '有人不确定'} | {r.source} | {notes['R1 LLM + 5 例子（主方法）'].get(code, '')} |")
    L += ["", "R1 最常见的错误方向（金标准 → R1）：" + "；".join(f"{a} → {b} ×{n}" for (a, b), n in pairs.head(8).items()), ""]
    (OUT / "evaluation_v1.md").write_text("\n".join(L))
    (OUT / "evaluation_v1.json").write_text(json.dumps({"table": T.round(4).to_dict(orient="index"), "chosen": chosen,
                                                        "verdict": verdict, "v0_same_id_subset": round(v0_sub, 4),
                                                        "mcnemar_R1_R2": [b, c, p], "mcnemar_R1_v0": [b0, c0, p0]},
                                                       ensure_ascii=False, indent=1))
    print(T[["l2", "ci", "l1", "f1", "wl2", "hd", "tl", "sure", "unsure"]].round(3).to_string())
    print(f"\nv0 on same-id subset ({int(same_id.sum())}): {v0_sub:.3f} | McNemar R1 vs R2 b={b} c={c} p={p:.3f} | R1 vs v0 b={b0} c={c0} p={p0:.3g}")
    print(f"chosen: {chosen} -> {verdict}")
