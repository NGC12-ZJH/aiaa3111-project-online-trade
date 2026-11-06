# Online Retail II：四时期数据处理

本目录用于新的 UCI Online Retail II 两年数据实验。所有新增配置、数据说明、处理代码、
运行入口和本地输出均放在本目录，不覆盖仓库现有的一年数据处理流程。

## 研究设计

| 阶段 | 时间窗口 | 用途 |
|---|---|---|
| `profile` | `[2009-12-01, 2010-06-01)` | 计算 RFM、选择 K、拟合 Cluster、生成客户级随机分组 |
| `discovery` | `[2010-06-01, 2010-12-01)` | 使用固定客户标签挖掘 G/L/R 候选规则 |
| `validation` | `[2010-12-01, 2011-06-01)` | 选择支持度、置信度、冗余处理和系统总规则预算 |
| `test` | `[2011-06-01, 2011-12-01)` | 所有设置冻结后的最终未来评价 |
| `out_of_scope` | 其他时间 | 当前主要为 2011-12-01 至 2011-12-09 |

完整方案见 [`docs/four_period_plan.md`](docs/four_period_plan.md)，字段、清洗和交接说明见
[`docs/data_processing_guide.md`](docs/data_processing_guide.md)。
运行证据见 [`docs/experiment_log.md`](docs/experiment_log.md)，AIGC使用见
[`docs/aigc_usage.md`](docs/aigc_usage.md)。

## 数据来源

- UCI 数据集：Online Retail II，ID 502；
- 页面：https://archive.ics.uci.edu/dataset/502/online+retail+ii
- DOI：https://doi.org/10.24432/C5CG6D
- 许可：CC BY 4.0；
- 官方文件：`online_retail_II.xlsx`；
- 已核对的工作簿 SHA-256：
  `bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980`。

原始文件只放在本地 `data/raw/`，不提交 Git。完整交易明细和处理输出只放在本地
`data/processed/`，经检查的汇总结果如需共享，应另行登记。

## 目录

```text
new dataset/
├── README.md
├── .gitignore
├── configs/
│   ├── data_processing.json
│   └── experiment.json
├── data/
│   ├── raw/
│   └── processed/
├── docs/
│   ├── four_period_plan.md
│   └── data_processing_guide.md
├── scripts/
│   └── README.md
└── src/
    └── README.md
```

## 运行

从仓库根目录执行：

```bash
python3 "new dataset/scripts/run_all.py"
```

该入口依次完成主处理、重复和零价格敏感性、时间冲突检查及最终验证。只有最后显示
`Validation passed` 时，输出才可以交给 B、C、D。

当前完整运行结果：1,067,371 条物理明细、1,044,848 条规范来源明细、53,628 个订单、
39,516 个有效购物篮和 2,684 名 profile 客户。具体数量和文件哈希以本地
`data/processed/run_manifest.json` 为准。

