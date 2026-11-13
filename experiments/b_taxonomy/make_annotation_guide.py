"""Build the Chinese annotation guide and the blind annotation workbooks for the gold standard (no LLM).

Inputs : configs/taxonomy/taxonomy_v1.json (frozen), configs/taxonomy/annotation_guide_zh_v1.json (Chinese wording),
         configs/prompts/abbreviations_v1.txt, data/taxonomy/gold/gold_blind_sheet_{A,D}.csv
Outputs: docs/annotation_guide_v1.md
         data/taxonomy/gold/gold_annotation_{A,D}.xlsx   (needs openpyxl; dropdown of valid ids, no machine labels)

Leak check: no example shown in the guide may be the wording of a gold item.
Standard library + openpyxl only, so it can run in any small environment:
  python make_annotation_guide.py
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAX = json.loads((ROOT / "configs/taxonomy/taxonomy_v1.json").read_text())
ZH = json.loads((ROOT / "configs/taxonomy/annotation_guide_zh_v1.json").read_text())
ABBR = (ROOT / "configs/prompts/abbreviations_v1.txt").read_text().strip().splitlines()
GOLD = ROOT / "data/taxonomy/gold"
OUT_MD = ROOT / "docs/annotation_guide_v1.md"

L1_ORDER = sorted({c["l1"] for c in TAX["l2"]}, key=lambda k: ZH["l1_zh"][k])
ROWS = [c for l1 in L1_ORDER for c in TAX["l2"] if c["l1"] == l1] + [
    {"id": "other", "l1": "other", "name_zh": "其他", "examples": []}]

RULES = [
    ("按“它是什么东西、拿来做什么”判断", "颜色、图案、尺寸、材质、节日、主题和设计系列都不改变子类。例如圣诞图案的茶蜡座仍然是烛台，RETROSPOT 波点的挂钟仍然是时钟。"),
    ("看商品名里的“主体名词”", "商品名通常是“修饰词 + 主体”，主体决定子类。例如 BLACK BAROQUE WALL CLOCK 的主体是 WALL CLOCK（挂钟），BAROQUE 只是风格；GREEN ROSE CUSHION COVER 的主体是 CUSHION COVER（靠垫套），ROSE 只是图案。"),
    ("成套商品按套装里的商品判断", "“SET OF 6 ...”“S/3 ...”按套装里的商品归类（例如 6 个茶蜡一套仍是茶蜡）。带礼盒的商品请按第 6 节“礼品盒”的定义判断；拿不准就按原则 7 处理。"),
    ("一物多用时，选它最主要的用途", "例如带挂钩的墙面收纳板，主要用来收纳，就选挂钩搁板类，而不是黑板。实在分不清主次，就选你认为最可能的，并勾“不确定”。"),
    ("节日商品和普通商品同样处理", "圣诞、复活节、情人节、万圣节的商品按商品类型归入普通子类。节日已由系统另外记录，不需要在这里体现。"),
    ("可以上网搜商品名看图片", "用英文商品名搜索图片，帮助判断是什么东西（这家零售商的商品在网上很常见）。但不要查看本项目仓库里任何已有的标签文件（见第 2 节）。"),
    ("拿不准时：先选，再标“不确定”，写第二选择", "不要因为拿不准就选 other。选最接近的子类，在“不确定”一栏填“是”，并在“第二选择”填另一个候选。"),
    ("other 只在确实看不懂或不是商品时用", "例如完全无法理解的缩写、邮费、手续费等。"),
]


def md():
    L = ["# 商品品类人工标注指南（金标准 · taxonomy_v1_rc1）", "",
         f"> 版本：{TAX['version']}（冻结于 {TAX.get('frozen_at', '')}）· 由 `experiments/b_taxonomy/make_annotation_guide.py` 生成 · 负责人：B（Jinghan ZHAO）", "",
         "## 1. 你要做什么", "",
         "- 给 **200 个商品**各选一个“子类”。这 200 个商品是随机抽出的“金标准”，用来检验电脑自动标签（关键词规则和 LLM）准不准。",
         "- 两位标注人（A、D）**各自独立**标注同一批商品，C 裁定两人不一致的地方。",
         "- 预计用时 **1–1.5 小时**。每个商品通常几秒就能判断，难的可以上网搜图。",
         "- 文件：`data/taxonomy/gold/gold_annotation_A.xlsx`（A 用）或 `gold_annotation_D.xlsx`（D 用）。两份的商品相同，但顺序不同。", "",
         "## 2. 盲标纪律（很重要）", "",
         "为了让金标准真正独立，标注时请：",
         "",
         "1. **只看这份指南和你自己的 Excel。**",
         "2. **不要打开仓库里 `data/taxonomy/` 和 `experiments/b_taxonomy/results/` 下的其他文件**。里面有电脑给这些商品打的标签（v0、LLM 的 R1–R3 等），看了就不再是独立判断了。",
         "3. **标完之前不要和另一位标注人讨论**，也不要互看文件。",
         "4. 不要修改“编码”和“商品写法”两列，也不要增删行或调整顺序。",
         "", "## 3. Excel 怎么填", "",
         "| 列 | 怎么填 |", "|---|---|",
         "| 序号、商品编码、商品写法 | 已填好，不要改。“商品写法”里用竖线分隔的，是同一个商品的不同写法 |",
         "| **子类代码** | 点单元格右侧的小箭头，从下拉菜单里选一个（菜单内容 = 第 6 节的 77 个代码，含 other）。也可以直接输入代码 |",
         "| 子类中文名 | 自动显示，用来核对有没有选错；不用填 |",
         "| 不确定 | 拿不准就选“是”，有把握就留空 |",
         "| 第二选择 | 只在“不确定”时填，同样从下拉菜单选 |",
         "| 备注 | 可选。例如“搜图后发现是 xx”“两类都说得通，因为……” |",
         "", "Excel 里还有两张表：“类别清单”（与第 6 节相同，可筛选）和“标注规则”（第 4 节的简版）。WPS 和 Excel 都能用；如果下拉菜单不显示，直接输入代码即可。",
         "", "## 4. 判断原则", ""]
    for i, (t, d) in enumerate(RULES, 1):
        L.append(f"{i}. **{t}**。{d}")
    L += ["", "## 5. 常见缩写", "", "商品名经常缩写或被截断：", ""] + [f"- {a}" for a in ABBR]
    L += ["", "## 6. 子类清单（10 个大类、76 个子类，外加 other）", "",
          "每个子类给出：代码、中文名、“是什么”、“包括”、“不包括”，以及 3 个真实商品作例子（例子都不在这 200 个商品里）。", ""]
    for l1 in L1_ORDER:
        subs = [c for c in TAX["l2"] if c["l1"] == l1]
        L += [f"### {ZH['l1_zh'][l1]}（{l1}，{len(subs)} 个子类）", "",
              "| 代码 | 中文名 | 是什么 | 包括 | 不包括 | 例子 |", "|---|---|---|---|---|---|"]
        for c in subs:
            z = ZH["l2"][c["id"]]
            L.append(f"| `{c['id']}` | {c['name_zh']} | {z['def']} | {z['inc']} | {z['exc']} | {'; '.join(c['examples'])} |")
        L.append("")
    z = ZH["l2"]["other"]
    L += ["### 其他", "", "| 代码 | 中文名 | 是什么 | 包括 | 不包括 |", "|---|---|---|---|---|",
          f"| `other` | 其他 | {z['def']} | {z['inc']} | {z['exc']} |", "",
          "## 7. 常见问题", "",
          "- **两个子类看起来都对怎么办？** 先按第 4 节的原则 2（主体名词）和原则 4（主要用途）判断；还是分不清，就选一个，勾“不确定”，再填第二选择。这类商品正是我们最想知道人和电脑分歧在哪里的地方，如实标注就好。",
          "- **商品名看不懂？** 先查第 5 节的缩写表，再上网搜图。确实无法判断时才选 other。",
          "- **我觉得某个子类的定义本身有问题？** 照现在的定义标，然后在备注里写下你的意见。类别结构已经冻结，评测结束后再统一讨论修改。",
          "- **标到一半能停吗？** 可以，保存 Excel 后下次接着标。",
          "", "## 8. 交回", "",
          "- 标完后把文件重命名为 `gold_labels_A.xlsx` 或 `gold_labels_D.xlsx` 发给 B，保持 .xlsx 格式。",
          "- 建议 **11-14 前**交回（以组内约定为准），这样 B 能在 11-15 前算出准确率。",
          "- C 收到两份后，裁定两人不一致的商品。", ""]
    return "\n".join(L)


def leak_check():
    gold_words = set()
    for who in ("A", "D"):
        with open(GOLD / f"gold_blind_sheet_{who}.csv", newline="") as f:
            for r in csv.DictReader(f):
                gold_words |= {w.strip() for w in r["all_wordings"].split("|")}
    shown = {e for c in TAX["l2"] for e in c["examples"]}
    bad = shown & gold_words
    if bad:
        sys.exit(f"LEAK: guide examples equal gold wordings: {sorted(bad)}")
    # phrases written by hand in the rules (not the frozen taxonomy text) must not occur in gold wordings
    import re
    hand = " ".join(t + " " + d for t, d in RULES) + " " + " ".join(ABBR)
    allowed = {"SET OF"}
    hits = {p for p in re.findall(r"[A-Z][A-Z'/0-9-]+(?: [A-Z][A-Z'/0-9-]+)+", hand)
            if p not in allowed and any(p in g for g in gold_words)}
    if hits:
        sys.exit(f"LEAK: hand-written rule examples occur in gold wordings: {sorted(hits)}")
    return len(shown), len(gold_words)


def workbook(who):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "标注"
    head = ["序号", "商品编码", "商品写法", "子类代码", "子类中文名（自动）", "不确定", "第二选择", "备注"]
    ws.append(head)
    with open(GOLD / f"gold_blind_sheet_{who}.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    n = len(rows)
    for i, r in enumerate(rows, start=2):
        ws.append([int(r["row"]), r["stock_code"], r["all_wordings"], None,
                   f'=IFERROR(VLOOKUP(D{i},类别清单!$C:$D,2,FALSE),"")', None, None, None])
    bold, fill = Font(bold=True), PatternFill("solid", fgColor="DDEBF7")
    for cell in ws[1]:
        cell.font, cell.fill = bold, fill
    for col, w in zip("ABCDEFGH", (6, 11, 48, 26, 22, 8, 26, 40)):
        ws.column_dimensions[col].width = w
    for r in ws.iter_rows(min_row=2, max_col=3):
        r[2].alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "D2"

    cl = wb.create_sheet("类别清单")
    cl.append(["大类代码", "大类", "子类代码", "中文名", "是什么", "包括", "不包括", "例子"])
    for c in ROWS:
        z = ZH["l2"][c["id"]]
        cl.append([c["l1"], ZH["l1_zh"].get(c["l1"], "其他"), c["id"], c["name_zh"], z["def"], z["inc"], z["exc"],
                   "; ".join(c["examples"])])
    for cell in cl[1]:
        cell.font, cell.fill = bold, fill
    for col, w in zip("ABCDEFGH", (18, 12, 26, 20, 40, 40, 40, 60)):
        cl.column_dimensions[col].width = w
    for r in cl.iter_rows(min_row=2):
        for cell in r[4:]:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    cl.auto_filter.ref = f"A1:H{len(ROWS) + 1}"
    cl.freeze_panes = "D2"

    ids = f"=类别清单!$C$2:$C${len(ROWS) + 1}"
    dv = DataValidation(type="list", formula1=ids, allow_blank=True, showErrorMessage=True,
                        errorTitle="代码不在清单里", error="请从下拉菜单选择，或输入“类别清单”C 列中的代码。")
    dv2 = DataValidation(type="list", formula1=ids, allow_blank=True)
    yes = DataValidation(type="list", formula1='"是"', allow_blank=True)
    for v in (dv, dv2, yes):
        ws.add_data_validation(v)
    dv.add(f"D2:D{n + 1}")
    dv2.add(f"G2:G{n + 1}")
    yes.add(f"F2:F{n + 1}")

    ru = wb.create_sheet("标注规则")
    ru.column_dimensions["A"].width = 120
    ru.append([f"标注人：{who}    版本：{TAX['version']}    完整说明见 docs/annotation_guide_v1.md"])
    ru.append(["盲标纪律：只看本文件和指南；不要打开仓库 data/taxonomy/ 与 experiments/b_taxonomy/results/ 下的其他文件；标完前不和另一位标注人讨论。"])
    ru.append([""])
    for i, (t, d) in enumerate(RULES, 1):
        ru.append([f"{i}. {t}：{d}"])
    ru.append([""])
    ru.append(["常见缩写："])
    for a in ABBR:
        ru.append(["  " + a])
    for r in ru.iter_rows():
        r[0].alignment = Alignment(wrap_text=True)
    out = GOLD / f"gold_annotation_{who}.xlsx"
    wb.save(out)
    return out, n


if __name__ == "__main__":
    shown, gw = leak_check()
    assert set(ZH["l2"]) == {c["id"] for c in TAX["l2"]} | {"other"}, "Chinese wording must cover every subcategory"
    OUT_MD.write_text(md())
    print(f"leak check ok ({shown} examples vs {gw} gold wordings); wrote {OUT_MD.relative_to(ROOT)}")
    try:
        for who in ("A", "D"):
            out, n = workbook(who)
            print(f"wrote {out.relative_to(ROOT)} ({n} items)")
    except ImportError:
        print("openpyxl not installed: workbooks skipped (pip install openpyxl)")
