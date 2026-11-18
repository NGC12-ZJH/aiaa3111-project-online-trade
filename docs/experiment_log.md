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

## 2026-11-16：D Validation（仅比较）

用户指定在本地 `repository` 文件夹创建 `d/evaluation`，并明确要求“先只比较，不推荐配置”。计算前记录 `configs/validation.json`：五套配置、预算20/50/100、限群为主、A1为主对照，S参考及A2敏感性、共享补充；无参数选择和Test评价。

输入固定为 A `2ae672b` 和 C `ac2b8a3`。先复算6,660条Discovery系统计数及全部预算规则计数，再评价4,862张Validation主比较订单、1,458名历史客户。覆盖之外输出顾客等权指标、2,000次顾客配对bootstrap、原范围规则状态和非Profile/匿名订单全局回退。详细结果、版本与输入输出哈希见 `results/tables/validation/run_manifest.json`，独立集合匹配检查见 `independent_check.json`。

Windows克隆自动换行会破坏冻结哈希：已将本地CSV恢复为Git原始字节，并设置仓库本地 `core.autocrlf=false`、`core.eol=lf`；数据内容与Git提交一致。使用UTF-8运行，避免默认GBK编码。代码语义测试与Discovery复算通过，人工科学复核仍待团队完成。

## 2026-11-18：统一未来质量验收补算

用户要求先写一页共同验收方案，再利用既有计数补算质量。先保存 `configs/validation_quality.json` 和 `docs/validation_quality_plan.md`，方案SHA-256为407bf20cf4f303b19816fdc134efb41d78239b3d167c1ca3a464009a208dd5d9，再执行补算。

所有P1–P5统一使用前件/联合订单和不同顾客数、顾客集中度、未来lift与置信度提升、三品类相对单前件增量及系统内BY校正。顾客聚类ratio-delta近似处理同人重复订单。限群原范围与共享全局范围分开计算质量，家族跨五配置/三预算去重；另做11套主/敏感性定义。新报告不覆盖旧Validation结果，不重新挖掘、不选参、不运行Test。既有Validation已被看过，明确记录为探索性扩展；验收后覆盖是同一期回顾性指标。

输出与核验见 `results/tables/validation_quality/`、`docs/validation_quality_results.md`、`docs/validation_quality_methods.md`；质量明细留在忽略目录。程序核验不代替人工方法复核。

## 2026-11-18：D分支交付整理

整理交付入口、两批结果说明、固定输入获取与CPU复现命令，保留全部设置和核验记录；仅提交代码、文档、图和不含顾客/订单标识的结果汇总。顾客级本地文件继续忽略。准备提交并推送 `d/evaluation`，不合并main、不创建PR、不冻结参数、不运行Test。
