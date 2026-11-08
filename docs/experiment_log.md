# 实验记录

| 日期 | 负责人 | 配置/代码版本 | 时间窗口 | 对照与实际规则数 | 结果文件 | 结论与限制 | 复核人 |
|---|---|---|---|---|---|---|---|

尚未运行实验。不得用预期结果填表。

## 数据准备运行记录

| 日期 | 负责人 | 运行 | 配置/代码状态 | 结果 | 验证与限制 |
|---|---|---|---|---|---|
| 2026-11-06 | Qingyang LI | Online Retail II 四时期数据准备基线 | `configs/data_processing.json` v1；分支 `a/online-retail-ii-data-preparation` | 1,067,371 物理明细；1,044,848 规范明细；53,628 订单；39,516 购物篮；2,684 Profile 客户 | 自动验证通过；83 个多时间订单均未跨阶段；跨表冲突为 0；两次完整运行核心哈希一致。非商品编码需另一成员复核。 |

运行命令：

```bash
python3 scripts/run_all.py
```

完整输出哈希、大小和行数见本地 `data/processed/run_manifest.json`。

## 顾客分群运行记录

| 日期 | 负责人 | 运行 | 配置/代码状态 | 结果 | 验证与限制 |
|---|---|---|---|---|---|
| 2026-11-08 | Jinghan ZHAO | Profile 期 RFM 分群比较（4 方法 × K = 3、4、5）与 20 次随机对照 | `configs/experiment.json` 中 `clustering` 选择规则已确认（2026-11-08）；分支 `b/customer-clustering`；输入 `orders.csv.gz` v1 | 选中 K-means、K = 3，群规模 700 / 1,263 / 721；轮廓系数 0.361，抽样稳定性 ARI 0.93 | 2,684 名顾客与 A 的 Profile 名单一致；随机组各种子人数与真实分群一致；`log(R)` 敏感性 ARI 仅 0.36，需在报告局限中说明；群名称待确认；待另一成员审阅 |

运行命令：

```bash
python scripts/run_clustering.py
```

结果表与图见 `results/tables/clustering_*`、`results/figures/clustering_*`；顾客级输出的行数和 SHA-256 登记在 `data/processed/README.md`。
