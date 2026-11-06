# Processed data

本目录只保存 Online Retail II 四时期流程的本地输出。完整哈希、大小和生成环境见
`run_manifest.json`。

## 主交接文件

| 文件 | 粒度 | 行数 | 使用者 | 用途 |
|---|---|---:|---|---|
| `orders.csv.gz` | 一行一个规范订单 | 53,628 | B、D | RFM、金额、阶段、资格和评价分母 |
| `baskets.csv.gz` | 一行一个有效购物篮 | 39,516 | D | 判断规则前件和后件命中 |
| `baskets_long.csv.gz` | 一行一个订单—商品组合 | 992,036 | C | FP-Growth 和分群购物篮 |
| `clean_transactions.csv.gz` | 一行一个物理来源明细 | 1,067,371 | A | 追踪清洗、重叠排除和敏感性分析 |

## 核心审计文件

| 文件 | 作用 |
|---|---|
| `sheet_reconciliation_summary.csv` | 对账两个工作表、规范来源和重叠区间 |
| `cross_sheet_overlap_exclusions.csv` | 保存被排除的第一张表完整重叠副本 |
| `cross_sheet_invoice_conflicts.csv` | 列出重叠订单内容差异；当前为0行 |
| `period_eligibility_summary.csv` | 汇总四时期明细、购物篮、客户和资格数量 |
| `four_period_retention_summary.csv` | 汇总 profile 客户在后续阶段的留存 |
| `duplicate_sensitivity_summary.csv` | 重复候选影响 |
| `zero_price_summary.csv`、`zero_price_codes.csv` | 零价格影响和编码 |
| `invoice_conflicts.csv`、`time_conflict_stage_check.csv` | 订单身份和时间冲突 |
| `special_stock_codes.csv` | 特殊编码及当前排除状态 |
| `extreme_lines.csv`、`extreme_orders.csv` | 极端数量和金额记录 |
| `audit_summary.csv`、`exclusion_summary.csv` | 总体对账和互斥排除原因 |

生成命令：

```bash
python3 "new dataset/scripts/run_all.py"
```

当前配置版本为1，原始工作簿 SHA-256 为
`bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980`。
在验证程序通过前，任何输出都不得作为 B、C、D 的正式输入。

