# 步骤 2 交付：顾客分群与随机对照（B · Jinghan ZHAO）

用 Profile 期（`[2009-12-01, 2010-06-01)`）RFM 特征，比较 K-means、高斯混合、层次聚类和 RFM 分档打分（各取 K = 3、4、5），按 2026-11-08 确认的规则选中 **K-means、K = 3**，并冻结。流程与结果解读见 `b/customer-clustering` 分支（合并后为 `main`）根目录 README 的“顾客分群（B）”一节。

## 文件

| 文件 | 内容 | 行数 | 大小 / SHA-256 |
|---|---|---:|---|
| `customer_clusters.csv` | `customer_id, cluster_id, recency, frequency, monetary, fitted_until, method, k`；每名 Profile 顾客一行 | 2,684 | 145,074 B；`fc3826532fde31491d6f76d1930629ce347719edd71114651ae162365c765bcf` |
| `random_groups.csv` | `customer_id, random_group_id, seed`；种子 42–61 各一套随机分组 | 53,680 | 590,513 B；`f6004881ba824a3275ac5be018a3db5c5488800db444bdf96cef52e313a7c3aa` |
| `clustering_summary.json` | 选中方法、K、选择规则、群规模 | — | — |

**群号含义**（0 为最低价值，数字越大价值越高；名称待全员确认）：

| `cluster_id` | 人数 | 建议名称 |
|---:|---:|---|
| 0 | 700 | Lapsed one-time buyers（流失的一次性买家） |
| 1 | 1,263 | Recent light buyers（近期低频买家） |
| 2 | 721 | Frequent high spenders（高频高额买家） |

每个种子下随机组人数与真实分群完全相同（700 / 1,263 / 721），且以顾客为单位分组。

## 使用方式（C、D）

- 取出后放在本地 `data/processed/local/`（被 `.gitignore` 忽略），方法见上一级 README；
- 用 `customer_id` 把各时期 `is_eligible_for_main_comparison = 1` 的购物篮关联到 `cluster_id`；随机对照对每个 `seed` 分别关联 `random_group_id`；
- 请直接使用本文件夹中的冻结版本，不要用自己重跑的结果替代：不同库版本的 K-means 可能让少数边界顾客换群。

## 生成方式与版本

```bash
python scripts/run_clustering.py
```

- 代码：`b/customer-clustering` 分支提交 `719d61d`；配置 `configs/experiment.json` 的 `clustering`、`random_control` 部分；
- 输入：`A_data_preparation/orders.csv.gz`（SHA-256 `2ff8420a…`）；
- 环境：Python 3.13、scikit-learn 1.9.1、pandas 3.0.5、numpy 2.5.3。

重跑可作复现检查：群规模和 `clustering_summary.json` 应一致；若哈希不同，以本文件夹版本为准。
