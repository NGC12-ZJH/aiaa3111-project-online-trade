# data/processed

Online Retail II 四时期流程直接在本目录生成本地输出。运行：

```bash
python3 scripts/run_all.py
```

当前主交接接口：

| 文件 | 粒度 | 使用者 | 用途 |
|---|---|---|---|
| `clean_transactions.csv.gz` | 一行一个物理来源明细 | A | 清洗、重叠和敏感性追溯 |
| `orders.csv.gz` | 一行一个规范订单 | B、D | RFM、金额、时期、资格、评价分母 |
| `baskets.csv.gz` | 一行一个有效订单购物篮 | D | 判断规则前件和后件命中 |
| `baskets_long.csv.gz` | 一行一个订单—商品 | C | FP-Growth 和分群购物篮 |

完整字段、审计文件和 A–D 使用边界见
[数据处理与交接说明](../../docs/data_processing_guide.md)。完整文件哈希、大小和行数见每次运行生成的 `run_manifest.json`。

保存供 A–D 交接的购物篮、特征、群标签和时间切分说明。经检查的 `.csv`、`.json`、`.jsonl`、`.parquet` 可选择性提交；小样本使用 `sample_` 前缀，直接放在本目录。规则也适用于子目录。其他数据格式默认忽略。

未检查、私密或通过外部共享位置分发的大文件放在 `local/` 子目录，该目录内全部内容被忽略。先在此生成并核查，再把确认可共享的交接文件放到本目录。数据许可、字段、大小与跨文件关联键应由交付人核对。

## 数据交接清单

完整客户级文件不进入 `main`，已发布在禁止合并的
[`a/online-retail-ii-data-snapshot`](https://github.com/NGC12-ZJH/aiaa3111-project-online-trade/tree/a/online-retail-ii-data-snapshot)
分支。快照按流程步骤分文件夹存放：A 的输出在 `data/processed/A_data_preparation/`（与快照提交 `ed1c57a0f3f974712bd80624ecbff51462585a39` 逐字节相同，2026-11-08 移入该文件夹），B 的输出在 `data/processed/B_customer_clustering/`；当前快照提交为 `2ae672b7ea6edb7f5e1561b6a64823004dea833e`。下载命令见快照分支的 `data/processed/README.md`。A 维护本清单，B/C/D 在使用前核对 SHA-256。B 的顾客级输出请直接使用快照中的冻结版本，不要用自己重跑的结果替代：不同库版本的 K-means 可能让少数边界顾客换群。

| 文件及版本 | 用途 / 负责人 | 时间窗口 / 行数 / 字段 | 大小 / SHA-256 | 获取方式及本地相对路径 | 生成命令 / 代码版本 / 配置 |
|---|---|---|---|---|---|
| `clean_transactions.csv.gz` v1 | A：逐行追溯和敏感性 | 全部物理来源；1,067,371 行；完整字段见处理说明 | 26,635,161 B；`01c6a69702b675723d2d9489f5771a45ea047946875eaae699384298afc9599b` | 快照分支；`data/processed/A_data_preparation/clean_transactions.csv.gz` | `python3 scripts/run_all.py`；处理基线 `301875b`；`configs/data_processing.json` v1 |
| `orders.csv.gz` v1 | B、D：RFM、金额、时期、资格和分母 | 四时期及 out-of-scope；53,628 行；键 `basket_id` | 1,266,845 B；`2ff8420a97ed2f89a303c57a6431590e130df35936ad143350adb40a5040d4c2` | 快照分支；`data/processed/A_data_preparation/orders.csv.gz` | 同上 |
| `baskets.csv.gz` v1 | D：未来规则命中 | 39,516 个有效订单篮；JSON `items` | 2,772,853 B；`30aef702f812ab42224271871271daff5b4e37a594696eee82208252198367bf` | 快照分支；`data/processed/A_data_preparation/baskets.csv.gz` | 同上 |
| `baskets_long.csv.gz` v1 | C：FP-Growth 和分群规则 | 992,036 个唯一订单—商品组合 | 3,977,938 B；`e95ae6da8b07677bdaf6ed2663c178ee44a6e9a1162a26eaa52cfeb62701f175` | 快照分支；`data/processed/A_data_preparation/baskets_long.csv.gz` | 同上 |
| `run_manifest.json` v1 | A–D：全部输出清单、哈希和环境 | 20 个数据/审计输出的元数据 | 7,222 B；`fc26e9fe52cf62ca5853b028fc7aab78b06d4cd0d13e1ab01e7412dd4f81554e` | 快照分支；`data/processed/A_data_preparation/run_manifest.json` | 同上；绝对路径仅记录生成环境 |
| `local/customer_clusters.csv` v1 | B → C、D：每名 Profile 顾客的群标签（K-means，K = 3） | Profile 期；2,684 行；`customer_id, cluster_id, recency, frequency, monetary, fitted_until, method, k` | 145,074 B；`fc3826532fde31491d6f76d1930629ce347719edd71114651ae162365c765bcf` | 快照分支 `data/processed/B_customer_clustering/customer_clusters.csv`；本地放 `data/processed/local/customer_clusters.csv`（被忽略） | `python scripts/run_clustering.py`；分支 `b/customer-clustering`；`configs/experiment.json` `clustering`（规则 2026-11-08 确认）；scikit-learn 1.9.1 |
| `local/random_groups.csv` v1 | B → C、D：20 次同规模顾客级随机分组 | 2,684 × 20 = 53,680 行；`customer_id, random_group_id, seed`（种子 42–61） | 590,513 B；`f6004881ba824a3275ac5be018a3db5c5488800db444bdf96cef52e313a7c3aa` | 快照分支 `data/processed/B_customer_clustering/random_groups.csv`；本地放 `data/processed/local/random_groups.csv`（被忽略） | 同上 |

获取方式应写明“随仓库提供”，或实际外部下载位置和访问方式。外部文件统一放入约定的 `data/processed/local/` 路径，并在运行配置中引用；不要提交密码或临时访问令牌。小样本还需记录抽样方式与随机种子。四人获取后核对版本和校验值再接续实验。

完整存放规则见[根目录 README](../../README.md#数据存放与四人交接)，交接字段见[模块协议](../../docs/data_contract.md)。
