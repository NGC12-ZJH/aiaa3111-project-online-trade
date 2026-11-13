"""Inter-annotator agreement on the gold standard (A vs D) and the blind adjudication sheet for C. No machine labels.

Inputs : data/taxonomy/gold/gold_labels_{A,D}.xlsx (returned workbooks), gold_items_v1.csv, taxonomy_v1.json
Outputs: experiments/b_taxonomy/results/gold/agreement_A_D.md      report
         data/taxonomy/gold/gold_human_AD.csv                        one row per item: both labels, uncertainty, notes
         data/taxonomy/gold/adjudication_C.xlsx                       disagreements for C (+ optional sheet: agreed
                                                                      but both unsure); dropdown of valid ids
Standard library + openpyxl only:  python gold_agreement.py
"""
import csv
import json
from collections import Counter
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "data/taxonomy/gold"
OUT = ROOT / "experiments/b_taxonomy/results/gold"
OUT.mkdir(parents=True, exist_ok=True)
TAX = json.loads((ROOT / "configs/taxonomy/taxonomy_v1.json").read_text())
ZH = json.loads((ROOT / "configs/taxonomy/annotation_guide_zh_v1.json").read_text())
L1 = {c["id"]: c["l1"] for c in TAX["l2"]} | {"other": "other"}
NAME = {c["id"]: c["name_zh"] for c in TAX["l2"]} | {"other": "其他"}
IDS = sorted(L1)


def read(who):
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning)
    ws = load_workbook(GOLD / f"gold_labels_{who}.xlsx")["标注"]
    orig = {r["stock_code"]: r for r in csv.DictReader(open(GOLD / f"gold_blind_sheet_{who}.csv"))}
    out = {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[1] is None:
            continue
        code = str(r[1]).strip()
        assert code in orig and str(r[2]) == orig[code]["all_wordings"], f"{who}: row for {code} was modified"
        lab = (r[3] or "").strip()
        assert lab in L1, f"{who}: invalid label {lab!r} for {code}"
        alt = (r[6] or "").strip()
        out[code] = dict(label=lab, unsure=(r[5] == "是"), alt=alt if alt in L1 else "", note=(r[7] or "").strip(),
                         wording=str(r[2]))
    assert len(out) == len(orig), f"{who}: {len(out)} rows, expected {len(orig)}"
    return out


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n / n
    return po, (po - pe) / (1 - pe) if pe < 1 else 1.0


def pct(x):
    return f"{100 * x:.1f}%"


if __name__ == "__main__":
    A, D = read("A"), read("D")
    strata = {r["stock_code"]: r["stratum"] for r in csv.DictReader(open(GOLD / "gold_items_v1.csv"))}
    lines = {r["stock_code"]: int(r["discovery_lines"]) for r in csv.DictReader(open(ROOT / "data/taxonomy/item_taxonomy_v0.csv"))}
    codes = sorted(A)
    head = [c for c in codes if strata[c] == "head"]
    tail = [c for c in codes if strata[c] != "head"]

    def stats(cs):
        a2, d2 = [A[c]["label"] for c in cs], [D[c]["label"] for c in cs]
        po2, k2 = kappa(a2, d2)
        po1, k1 = kappa([L1[x] for x in a2], [L1[x] for x in d2])
        soft = sum(A[c]["label"] == D[c]["label"] or A[c]["label"] == D[c]["alt"] or D[c]["label"] == A[c]["alt"]
                   for c in cs) / len(cs)
        w = sum(lines[c] for c in cs)
        wag = sum(lines[c] for c in cs if A[c]["label"] == D[c]["label"]) / w if w else float("nan")
        return dict(n=len(cs), po2=po2, k2=k2, po1=po1, k1=k1, soft=soft, wag=wag)

    S = {"全部 200": stats(codes), "热门 100": stats(head), "长尾 100": stats(tail)}
    agree = [c for c in codes if A[c]["label"] == D[c]["label"]]
    dis = [c for c in codes if A[c]["label"] != D[c]["label"]]
    bucket = Counter((A[c]["unsure"], D[c]["unsure"]) for c in codes)

    def rate(cs):
        return pct(sum(A[c]["label"] == D[c]["label"] for c in cs) / len(cs)) if cs else "—"

    both_sure = [c for c in codes if not A[c]["unsure"] and not D[c]["unsure"]]
    one = [c for c in codes if A[c]["unsure"] != D[c]["unsure"]]
    both_unsure = [c for c in codes if A[c]["unsure"] and D[c]["unsure"]]
    pairs = Counter(tuple(sorted((A[c]["label"], D[c]["label"]))) for c in dis)
    by_l1 = Counter(L1[A[c]["label"]] for c in dis) + Counter(L1[D[c]["label"]] for c in dis)

    R = ["# 金标准人工标注一致性：A vs D", "",
         "> `gold_agreement.py` 生成。只比较两位标注人，不涉及任何机器标签。κ = Cohen's kappa（扣除碰巧一致后的一致程度；"
         "> 0.8 以上通常视为很好，0.6–0.8 较好）。“宽松一致”= 一方的答案等于另一方的答案或第二选择。", "",
         "## 1. 一致率", "", "| 范围 | 商品数 | 子类一致 | 子类 κ | 大类一致 | 大类 κ | 宽松一致（含第二选择） | 按购买量加权的子类一致 |",
         "|---|---|---|---|---|---|---|---|"]
    for k, s in S.items():
        R.append(f"| {k} | {s['n']} | {pct(s['po2'])} | {s['k2']:.3f} | {pct(s['po1'])} | {s['k1']:.3f} | {pct(s['soft'])} | {pct(s['wag'])} |")
    R += ["", "## 2. 不确定标记", "",
          f"- A 标了 {sum(A[c]['unsure'] for c in codes)} 个不确定，D 标了 {sum(D[c]['unsure'] for c in codes)} 个；"
          f"A 用了 {sum(A[c]['label'] == 'other' for c in codes)} 次 other，D 用了 {sum(D[c]['label'] == 'other' for c in codes)} 次。",
          "", "| 情况 | 商品数 | 子类一致 |", "|---|---|---|",
          f"| 两人都确定 | {len(both_sure)} | {rate(both_sure)} |",
          f"| 只有一人不确定 | {len(one)} | {rate(one)} |",
          f"| 两人都不确定 | {len(both_unsure)} | {rate(both_unsure)} |", "",
          "## 3. 分歧最多的子类对", "", "| 子类 1 | 子类 2 | 次数 |", "|---|---|---|"]
    for (x, y), n in pairs.most_common(15):
        R.append(f"| {x}（{NAME[x]}） | {y}（{NAME[y]}） | {n} |")
    R += ["", "分歧涉及的大类（每个分歧计两次）：" + "，".join(f"{ZH['l1_zh'].get(k, k)} {v}" for k, v in by_l1.most_common()), "",
          f"## 4. 全部分歧（{len(dis)} 个，交 C 裁定）", "",
          "| 编码 | 商品写法 | A | A 不确定/第二选择 | D | D 不确定/第二选择 | 层 |", "|---|---|---|---|---|---|---|"]
    for c in dis:
        a, d = A[c], D[c]
        R.append(f"| {c} | {a['wording'].replace('|', '/')} | {a['label']} | {'是 → ' + a['alt'] if a['unsure'] else ''} | "
                 f"{d['label']} | {'是 → ' + d['alt'] if d['unsure'] else ''} | {strata[c]} |")
    (OUT / "agreement_A_D.md").write_text("\n".join(R))

    with open(GOLD / "gold_human_AD.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stock_code", "stratum", "label_A", "unsure_A", "alt_A", "note_A", "label_D", "unsure_D", "alt_D",
                    "note_D", "agree", "agreed_label"])
        for c in codes:
            a, d = A[c], D[c]
            w.writerow([c, strata[c], a["label"], int(a["unsure"]), a["alt"], a["note"], d["label"], int(d["unsure"]),
                        d["alt"], d["note"], int(c in agree), a["label"] if c in agree else ""])

    # adjudication workbook for C (blind: human labels only)
    wb = Workbook()
    bold, fill = Font(bold=True), PatternFill("solid", fgColor="FCE4D6")
    head_row = ["序号", "商品编码", "商品写法", "A 的答案", "A 中文名", "A 不确定", "A 第二选择", "A 备注",
                "D 的答案", "D 中文名", "D 不确定", "D 第二选择", "D 备注", "C 最终子类代码", "C 备注"]

    def sheet(ws, cs):
        ws.append(head_row)
        for i, c in enumerate(cs, 1):
            a, d = A[c], D[c]
            ws.append([i, c, a["wording"], a["label"], NAME[a["label"]], "是" if a["unsure"] else "", a["alt"], a["note"],
                       d["label"], NAME[d["label"]], "是" if d["unsure"] else "", d["alt"], d["note"], None, None])
        for cell in ws[1]:
            cell.font, cell.fill = bold, fill
        for col, wd in zip("ABCDEFGHIJKLMNO", (5, 10, 40, 22, 16, 7, 22, 30, 22, 16, 7, 22, 30, 24, 30)):
            ws.column_dimensions[col].width = wd
        for r in ws.iter_rows(min_row=2):
            for cell in r:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "D2"
        dv = DataValidation(type="list", formula1=f"=类别清单!$C$2:$C${len(IDS) + 1}", allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"N2:N{len(cs) + 1}")

    ws = wb.active
    ws.title = "分歧（必裁）"
    sheet(ws, dis)
    sheet(wb.create_sheet("一致但两人都不确定（可选复核）"), [c for c in both_unsure if c in agree])
    cl = wb.create_sheet("类别清单")
    cl.append(["大类代码", "大类", "子类代码", "中文名", "是什么", "包括", "不包括"])
    for c in [x for l1 in sorted({c['l1'] for c in TAX['l2']}) for x in TAX["l2"] if x["l1"] == l1] + [{"id": "other", "l1": "other", "name_zh": "其他"}]:
        z = ZH["l2"][c["id"]]
        cl.append([c["l1"], ZH["l1_zh"].get(c["l1"], "其他"), c["id"], c["name_zh"], z["def"], z["inc"], z["exc"]])
    for cell in cl[1]:
        cell.font = bold
    for col, wd in zip("ABCDEFG", (18, 12, 26, 20, 40, 40, 40)):
        cl.column_dimensions[col].width = wd
    note = wb.create_sheet("裁定说明")
    note.column_dimensions["A"].width = 110
    for t in ["C 的任务：对“分歧（必裁）”表中每一行，在 N 列从下拉菜单选出最终子类（可以是 A 的、D 的，或第三个子类）。",
              "依据：docs/annotation_guide_v1.md 的定义与判断原则；可以上网搜图。请不要查看仓库中任何机器标签文件（v0、LLM 结果）。",
              "“一致但两人都不确定”表为可选复核：如认为两人共同选错，在 N 列填写正确子类；同意则留空。",
              "完成后改名为 adjudicated_C.xlsx 交回 B。"]:
        note.append([t])
        note.cell(note.max_row, 1).alignment = Alignment(wrap_text=True)
    wb.save(GOLD / "adjudication_C.xlsx")

    s = S["全部 200"]
    print(f"L2 agree {pct(s['po2'])} kappa {s['k2']:.3f} | L1 agree {pct(s['po1'])} kappa {s['k1']:.3f} | soft {pct(s['soft'])}")
    print(f"disagreements {len(dis)} | unsure buckets (A,D): {dict(bucket)}")
    print("wrote", (OUT / "agreement_A_D.md").relative_to(ROOT), "|", (GOLD / "adjudication_C.xlsx").relative_to(ROOT))
