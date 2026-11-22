# Validation 密集预算重做与 P5／90 Test 补测

这一组实验把 P1–P5 的系统预算细化为每 10 条一档，比较实际去重并补齐后的规则池。原始 [D 正式 Test](../../docs/evaluation/test/README.md) 使用的是 P5／100 限群协议。本目录的 P5／90 结果是同一历史 Test 时段上的独立补测。

| 阶段 | 入库规则和结果 | 入口 |
| --- | --- | --- |
| Validation 密集预算 | P1–P5 各跑 10–100；分别控制有向规则与无向组合数量，报告合计覆盖、每加 10 条的增量和随机对照 | [报告与曲线](results/README.md) · [G/L 明细](results/global_local_curves.csv) |
| Validation 质量敏感性 | 在同一固定名单上比较原 quality_v1 与收紧证据量、Lift、Added Value 和三品类增量 | [P1／90 与 P5／90 敏感性](results/quality_gate_sensitivity_P1_P5_90.csv) |
| Validation 严质量选参 | Added Value 至少 10 pp，其他 quality_v1 条件沿用。用每套系统原共同 BY 家族，比较 G、L 与 100 套 A1 | [50 格汇总](results/strict_validation_grid.csv) · [选参结果](results/strict_validation_selection.csv) · [逐种子](results/strict_validation_systems.csv) |
| P5／90 Test 补测 | 按冻结名单直接匹配，报告原覆盖、可靠覆盖、规则质量、配对区间和 A1 | [Test 补测](test_p5_90/README.md) · [独立冻结协议](test_p5_90/freeze.json) |

## Validation 到冻结

基础 quality_v1 下，允许 G/L 各距其最高可靠覆盖 1 个百分点时，最小预算为 P1／90。将 Added Value 提到 10 pp 后，以同样的 1 个百分点标准选择 **P5／90、无向组合去重后共享**。严格可靠覆盖为 G 74.35%、L 73.36%。P5 从 90 到 100 时，G/L 分别再增加 0.76／0.56 个百分点。A1 中位数为 73.55%，100 套中有 73 套的严格可靠覆盖达到或超过 L。A1 用作分群对照，选参根据可靠覆盖与实际预算。

独立冻结记录在本轮运行前锁定 G、L 和 100 套 A1 的规则清单，每套 90 个不同无向组合。补测共有 5,730 张历史顾客订单。严格可靠覆盖为 **G 74.38%、L 73.72%**，L−G 为 **−0.66 pp**，顾客配对 95% 区间 **[−1.16, −0.18]**；63/100 套 A1 达到或超过 L。

## 复算

按 [D 复现说明](../../docs/evaluation/reproduce.md) 准备输入、依赖和 Git 换行配置。建议用单独结果目录重跑，以便冻结协议继续引用已提交的字节。以下命令从仓库根目录执行。

    $env:PYTHONUTF8 = '1'
    python -B experiments/validation_budget_redesign/run.py --out tmp/validation-budget
    python -B experiments/validation_budget_redesign/report.py tmp/validation-budget
    python -B experiments/validation_budget_redesign/strict_validation.py --out tmp/validation-budget-strict
    New-Item -ItemType Directory -Path tmp/test-p5-90
    Copy-Item experiments/validation_budget_redesign/test_p5_90/freeze.json tmp/test-p5-90
    Copy-Item experiments/validation_budget_redesign/test_p5_90/frozen_rule_lists.csv tmp/test-p5-90
    python -B experiments/validation_budget_redesign/test_p5_90/run.py run --dest tmp/test-p5-90
    python -B experiments/validation_budget_redesign/test_p5_90/report.py tmp/test-p5-90

严格质量脚本从已提交的密集预算规则路径读取 G/L/A1。Test 脚本读取冻结清单并验证哈希，从 A 快照取历史时段数据。仓库提交的是脚本、聚合结果、规则清单、图和核验记录。
