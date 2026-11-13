"""Human review of doubtful popular items in the final taxonomy_v1 labels (standard library + openpyxl).

  python make_review_sheet.py          -> data/taxonomy/v1_work/review_v1.xlsx   (to fill in)
  python make_review_sheet.py --read   -> data/taxonomy/v1_work/review_v1_decisions.csv  (from review_v1_B.xlsx)

The sheet lists results/v1_review_list.csv (top 1,000 codes by Discovery lines that are other / invalid / inconsistent
across wordings, prefix family or name series). This review happens AFTER the gold evaluation and is not blind: it
shows the current LLM label and the evidence. Leave "复核后子类" empty to keep the current label.
"""
import csv
import json
import re
import sys
import warnings
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "data/taxonomy/v1_work"
TAX = json.loads((ROOT / "configs/taxonomy/taxonomy_v1.json").read_text())
ZH = json.loads((ROOT / "configs/taxonomy/annotation_guide_zh_v1.json").read_text())
NAME = {c["id"]: c["name_zh"] for c in TAX["l2"]} | {"other": "其他"}
IDS = [c["id"] for c in TAX["l2"]] + ["other"]
REASON = {"other": "被标为 other", "invalid": "LLM 两次都没给出合法答案", "wording_inconsistent": "不同写法得到不同子类（R5）",
          "family_inconsistent": "同编码前缀的商品子类不一致", "series_inconsistent": "同名系列的商品子类不一致"}


def stem(desc):
    m = re.split(r"\s+-\s+|,", desc, maxsplit=1)
    return m[0].strip() if len(m) > 1 else None


def lab(x):
    return f"{x}（{NAME.get(x, '?')}）"


def build():
    items = {r["stock_code"]: r for r in csv.DictReader(open(ROOT / "data/taxonomy/item_taxonomy_v1.csv"))}
    review = list(csv.DictReader(open(ROOT / "experiments/b_taxonomy/results/v1_review_list.csv")))
    r5 = defaultdict(list)
    for r in csv.DictReader(open(ROOT / "experiments/b_taxonomy/results/llm_runs/R5/labels.csv")):
        r5[r["stock_code"]].append(f"{r['wording']} → {lab(r['l2_id'])}")
    fam, ser = defaultdict(list), defaultdict(list)
    for c, r in items.items():
        fam[c[:5]].append(c)
        s = stem(r["canonical_description"])
        if s:
            ser[s].append(c)

    wb = Workbook()
    ws = wb.active
    ws.title = "复核"
    ws.append(["序号", "商品编码", "规范商品名", "Discovery 购买行数", "为什么要复核", "当前子类（LLM）", "当前中文名", "依据",
               "复核后子类（空 = 不改）", "复核后中文名（自动）", "备注"])
    for i, r in enumerate(review, 2):
        c = r["stock_code"]
        ev = []
        if c in r5 and "wording" in r["reason"]:
            ev.append("各写法：" + "；".join(r5[c]))
        if "family" in r["reason"]:
            ev.append("同前缀：" + "；".join(f"{x} {items[x]['canonical_description']} → {lab(items[x]['l2_id'])}"
                                          for x in fam[c[:5]] if x != c))
        if "series" in r["reason"]:
            s = stem(items[c]["canonical_description"])
            ev.append("同系列：" + "；".join(f"{x} {items[x]['canonical_description']} → {lab(items[x]['l2_id'])}"
                                          for x in ser.get(s, []) if x != c))
        if items[c]["llm_tag_note"]:
            ev.append("LLM 备注：" + items[c]["llm_tag_note"])
        ev.append(f"v0：{items[c]['v0_l2']}")
        why = "；".join(REASON[x] for x in r["reason"].strip(";").split(";") if x)
        ws.append([i - 1, c, r["canonical_description"], int(r["discovery_lines"]), why, r["l2_id"], NAME.get(r["l2_id"], ""),
                   "\n".join(ev), None, f'=IFERROR(VLOOKUP(I{i},类别清单!$C:$D,2,FALSE),"")', None])
    bold, fill = Font(bold=True), PatternFill("solid", fgColor="E2EFDA")
    for cell in ws[1]:
        cell.font, cell.fill = bold, fill
    for col, w in zip("ABCDEFGHIJK", (5, 10, 36, 10, 26, 24, 18, 70, 26, 20, 30)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "D2"
    cl = wb.create_sheet("类别清单")
    cl.append(["大类代码", "大类", "子类代码", "中文名", "是什么", "包括", "不包括"])
    for c in sorted(TAX["l2"], key=lambda x: (x["l1"], x["id"])) + [{"id": "other", "l1": "other", "name_zh": "其他"}]:
        z = ZH["l2"][c["id"]]
        cl.append([c["l1"], ZH["l1_zh"].get(c["l1"], "其他"), c["id"], c["name_zh"], z["def"], z["inc"], z["exc"]])
    for col, w in zip("ABCDEFG", (18, 12, 26, 20, 40, 40, 40)):
        cl.column_dimensions[col].width = w
    dv = DataValidation(type="list", formula1=f"=类别清单!$C$2:$C${len(IDS) + 1}", allow_blank=True, showErrorMessage=True,
                        error="请从下拉菜单选择")
    ws.add_data_validation(dv)
    dv.add(f"I2:I{len(review) + 1}")
    note = wb.create_sheet("说明")
    note.column_dimensions["A"].width = 110
    for t in ["这是评测之后的人工复核（不是盲标）：只复核最热门 1,000 个商品中有疑问的商品。",
              "认为当前子类正确：I 列留空。认为不对：在 I 列从下拉菜单选正确子类。依据请参考 docs/annotation_guide_v1.md。",
              "修改会记为 label_source = human_override，LLM 原始输出保留，修改数量写进报告。",
              "TOAST ITS 系列已按 B 的决定统一为 kitchen_tools，不在本表中。",
              "完成后另存为 data/taxonomy/v1_work/review_v1_B.xlsx。"]:
        note.append([t])
        note.cell(note.max_row, 1).alignment = Alignment(wrap_text=True)
    out = WORK / "review_v1.xlsx"
    wb.save(out)
    print(f"wrote {out.relative_to(ROOT)} ({len(review)} items)")


def read():
    warnings.filterwarnings("ignore", category=UserWarning)
    src = next(p for p in (WORK / "review_v1_B.xlsx", ROOT / "data/taxonomy/gold/review_v1_B.xlsx") if p.exists())
    print("reading", src.relative_to(ROOT))
    ws = load_workbook(src)["复核"]
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[1] is None:
            continue
        new = (r[8] or "").strip()
        if new:
            assert new in IDS, f"invalid label {new!r} for {r[1]}"
            if new != r[5]:
                rows.append([str(r[1]), r[5], new, (r[10] or "").strip()])
        elif r[10]:
            print(f"  note without change on {r[1]} {r[2]}: {r[10]}")
    with open(WORK / "review_v1_decisions.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stock_code", "llm_l2", "reviewed_l2", "note"])
        w.writerows(rows)
    print(f"wrote review_v1_decisions.csv ({len(rows)} changes)")


if __name__ == "__main__":
    read() if "--read" in sys.argv else build()
