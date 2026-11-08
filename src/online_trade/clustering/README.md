# B 顾客分群与对照分组

结果解读与完整流程说明见根目录 [README](../../../README.md#顾客分群b)。

负责人：Jinghan ZHAO（zhaojinghan06@gmail.com）

在 Profile 期（`[2009-12-01, 2010-06-01)`）的 RFM 特征上比较 K-means、高斯混合（GMM）、层次聚类（Ward）和 RFM 分档打分四种方法，各取 K = 3、4、5，按预先约定的规则选出一个分群并冻结；再生成 20 次同规模的顾客级随机分组作为对照。只使用 Profile 期数据。

## 运行

先准备 A 的订单表 `data/processed/orders.csv.gz`（运行 `python3 scripts/run_all.py`，或从 `a/online-retail-ii-data-snapshot` 分支取出），然后在仓库根目录执行：

```bash
python scripts/run_clustering.py                        # 完整运行，约 1 分钟
python scripts/run_clustering.py --bootstrap-repeats 5  # 快速试跑
```

参数全部在 `configs/experiment.json` 的 `clustering` 与 `random_control` 部分。

## 代码结构

| 文件 | 内容 | 对应规划步骤 |
|---|---|---|
| `features.py` | 筛选 Profile 订单、计算 RFM、核对 A 的 2,684 名 Profile 顾客、构建标准化特征 | 1–2 |
| `methods.py` | 四种分群方法；群号按价值从低到高统一重排 | 3 |
| `evaluation.py` | 轮廓系数、抽样稳定性（ARI）、最小群规模，以及选择规则 | 4 |
| `pipeline.py` | 串联全流程，生成画像、随机分组、敏感性检查并写出文件 | 5–8 |
| `scripts/run_clustering.py` | 命令行入口 | — |

特征为 `[R（天）, log1p(F), log1p(M)]`，按这批顾客标准化。M 主版本为毛购买额；净额和 `log(R)` 只用于敏感性检查。

**R 用原始天数（2026-11-08 确认）**：R 分布不偏斜，无需取对数。敏感性检查显示改用 `log(R)` 后分群变化很大（ARI ≈ 0.36），报告须说明这一选择及其影响。

## 选择规则（2026-11-08 确认）

1. 淘汰最小群占比 < 5%、抽样稳定性 ARI < 0.8，或实际群数少于 K 的候选；
2. 剩余候选中选轮廓系数最高者；
3. 与最高分相差不超过 0.02 时，取更小的 K，再按 `kmeans → gmm → ward → rfm_score` 的顺序。

`selection_rule.status` 已改为 `confirmed_2026-11-08`。可解释性由人工在画像表和热力图上复核。

群名称写在配置 `cluster_names` 中（当前为建议名，`cluster_names_status` 待确认），只影响图上的标签，不影响分群结果。

## 输出

| 文件 | 内容 | 是否进 Git |
|---|---|---|
| `data/processed/local/customer_clusters.csv` | `customer_id, cluster_id, recency, frequency, monetary, fitted_until, method, k` | 否（含顾客编号） |
| `data/processed/local/random_groups.csv` | `customer_id, random_group_id, seed`，20 个种子的长表 | 否（含顾客编号） |
| `results/tables/clustering_candidates.csv` | 12 个候选的四项证据、是否合格、是否选中 | 是 |
| `results/tables/clustering_profile.csv` | 选中分群的人数、R/F/M 分位数、平均购物篮大小、Profile 购物篮数 | 是 |
| `results/tables/clustering_sensitivity.csv` | 净额、`log(R)` 口径下与选中结果的 ARI | 是 |
| `results/tables/clustering_summary.json` | 选中方法、K、规则与群规模 | 是 |
| `results/figures/clustering_rfm_boxplots.png`、`clustering_snake_plot.png` | 群画像图 | 是 |
| `results/figures/clustering_heatmap.png` | 命名用热力图：格内为中位数，颜色为相对全体平均的好坏（红差、灰平均、蓝好；R 已取反） | 是 |

群号 0 为最低价值群，数字越大价值越高。随机分组通过打乱真实群标签生成，因此每个种子下各组人数与真实分群完全相同。

字段与交接口径见[数据接口](../../../docs/data_contract.md)。
