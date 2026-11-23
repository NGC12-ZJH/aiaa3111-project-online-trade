"""Rank the saved Validation grid at a cost of 0.50 pp per 10 combinations."""

import argparse
import csv
from fractions import Fraction
from hashlib import sha256
from pathlib import Path


HERE = Path(__file__).resolve().parent
COST = Fraction(1, 2)


def rank_grid(source):
    candidates = {}
    with source.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["control"] != "GL":
                continue
            key = row["config"], int(row["budget"])
            systems = candidates.setdefault(key, {})
            method = row["method"]
            assert method in ("G", "L") and method not in systems
            systems[method] = row
    assert set(candidates) == {(f"P{i}", b) for i in range(1, 6) for b in range(10, 301, 10)}
    rows = []
    for (config, budget), systems in candidates.items():
        assert set(systems) == {"G", "L"}
        assert {int(row["identified_orders"]) for row in systems.values()} == {7364}
        g, l = (systems[method] for method in ("G", "L"))
        g_hits, l_hits = (int(row["reliable_coverage_count"]) for row in (g, l))
        mean_pp = Fraction(100 * (g_hits + l_hits), 2 * 7364)
        penalty = COST * budget / 10
        rows.append(dict(config=config, budget=budget, G_reliable_hits=g_hits, L_reliable_hits=l_hits,
                         G_reliable_pct=Fraction(100 * g_hits, 7364), L_reliable_pct=Fraction(100 * l_hits, 7364),
                         mean_reliable_pp=mean_pp, cost_pp=penalty, score_pp=mean_pp - penalty,
                         G_quality_pass_pct=Fraction(100 * int(g["quality_pass_share_count"]), budget),
                         L_quality_pass_pct=Fraction(100 * int(l["quality_pass_share_count"]), budget)))
    return sorted(rows, key=lambda r: (-r["score_pp"], r["budget"], r["config"]))


def format_row(row, rank):
    g, l = (float(row[f"{method}_reliable_pct"]) for method in ("G", "L"))
    qg, ql = (float(row[f"{method}_quality_pass_pct"]) for method in ("G", "L"))
    return (f"| {rank} | {row['config']}／{row['budget']} | {g:.2f}% | {l:.2f}% | "
            f"{qg:.2f}%／{ql:.2f}% | {float(row['score_pp']):.4f} |")


def save(source, out):
    rows = rank_grid(source)
    out.mkdir(parents=True, exist_ok=True)
    fields = ["rank", *rows[0]]
    with (out / "ranking.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for rank, row in enumerate(rows, 1):
            writer.writerow({"rank": rank, **{k: f"{float(v):.9f}" if isinstance(v, Fraction) else v
                                              for k, v in row.items()}})
    best, runner_up = rows[:2]
    margin = float(best["score_pp"] - runner_up["score_pp"])
    best_p1 = next((i, r) for i, r in enumerate(rows, 1) if r["config"] == "P1")
    lines = [
        "# Validation 重新选参 · 每 10 个组合的成本为 0.50 个百分点", "",
        f"这次以 **{best['config']}／{best['budget']}** 为 Validation 选参结果。"
        f"评分比第二名高 **{margin:.4f} 个百分点**。"
        f"比第二名多维护 {best['budget'] - runner_up['budget']} 个组合，"
        f"G／L 分别多可靠覆盖 {best['G_reliable_hits'] - runner_up['G_reliable_hits']}／"
        f"{best['L_reliable_hits'] - runner_up['L_reliable_hits']} 单。", "",
        "在已完成的 P1–P5、10–300 共 150 档网格上，以 G 与 L 在同一批 **7,364 张有 ID 的订单**上的"
        "原版 quality_v1 可靠覆盖等权平均作为收益。评分为平均可靠覆盖（百分点）减去 "
        "`0.50 × 预算 / 10`。平局取较小预算，再按 P 编号排序。质量通过率一并报告，A1 不参与选参。", "",
        "| 排名 | 配置／预算 | G 可靠覆盖 | L 可靠覆盖 | 原版质量通过率 G／L | 扣成本后评分 |",
        "| --- | --- | --- | --- | --- | --- |",
        *[format_row(row, rank) for rank, row in enumerate(rows[:5], 1)],
        *([format_row(best_p1[1], best_p1[0])] if best_p1[0] > 5 else []), "",
        "这是在已有 Validation 网格上的追加选参。此前 P1／260 的冻结与 Test 补测按原选择协议保留。", "",
        "[完整排名](ranking.csv) · [Validation 源表](../results/validation_systems.csv)", "",
        "复算时在本目录运行 `python -B select_budget.py`。", "",
        f"源表 SHA-256 为 `{sha256(source.read_bytes()).hexdigest()}`。", "",
    ]
    (out / "README.md").write_bytes("\n".join(lines).encode("utf-8"))
    for rank, row in enumerate(rows[:5], 1):
        print(format_row(row, rank))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=HERE.parent / "results/validation_systems.csv")
    parser.add_argument("--out", type=Path, default=HERE)
    args = parser.parse_args()
    save(args.source, args.out)
