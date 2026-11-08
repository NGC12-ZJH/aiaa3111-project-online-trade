# data/processed（数据快照：各步骤交付物）

本分支 `a/online-retail-ii-data-snapshot` 只用于分发数据，**禁止合并到 `main`，也不能作为 PR 来源**。代码改动仍走各成员的功能分支和 PR。

每一步的交付物放在各自的文件夹中，按流程顺序：

| 步骤 | 文件夹 | 负责人 | 交付内容 | 下游使用者 |
|---|---|---|---|---|
| 1 数据清洗与四时期切分 | [`A_data_preparation/`](A_data_preparation/) | A · Qingyang LI | 逐行清洗明细、订单表、购物篮、订单—商品长表、全部审计表、运行清单 | B（订单表算 RFM）、C（长表挖规则）、D（订单表与购物篮做评价） |
| 2 顾客分群与随机对照 | [`B_customer_clustering/`](B_customer_clustering/) | B · Jinghan ZHAO | 冻结的顾客群标签（K-means，K = 3）、20 次同规模随机分组、选择摘要 | C（按群/随机组挖规则）、D（真实分群与随机分组对照） |
| 3 规则挖掘 | 待添加（`C_pattern_mining/`） | C · Anqi ZHAO | — | D |
| 4 评价 | 待添加（`D_evaluation/`） | D · Chenrui XIANG | — | 报告与海报 |

原始工作簿在 `data/raw/online_retail_II.xlsx`。每个文件夹内的 README 记录文件清单、行数、SHA-256、生成命令和代码版本；下载后先核对校验值。

## 获取方式

不必检出整个分支，用 `git show` 取出需要的文件即可（在你自己的仓库根目录执行）：

```bash
git fetch origin a/online-retail-ii-data-snapshot
S=origin/a/online-retail-ii-data-snapshot

# A 的订单表 → B 运行 run_clustering.py 的默认输入位置
git show $S:data/processed/A_data_preparation/orders.csv.gz > data/processed/orders.csv.gz

# B 的群标签和随机分组 → C、D 的本地位置（被 .gitignore 忽略）
mkdir -p data/processed/local
git show $S:data/processed/B_customer_clustering/customer_clusters.csv > data/processed/local/customer_clusters.csv
git show $S:data/processed/B_customer_clustering/random_groups.csv > data/processed/local/random_groups.csv

sha256sum data/processed/orders.csv.gz data/processed/local/*.csv   # 与各文件夹 README 中的值核对
```

`.csv.gz` 文件和 `data/processed/local/` 都被 `.gitignore` 忽略，取出后不会被误提交到功能分支。

## 版本说明

- `A_data_preparation/` 中的文件与快照提交 `ed1c57a0f3f974712bd80624ecbff51462585a39` 逐字节相同，2026-11-08 只移动了位置。
- `B_customer_clustering/` 于 2026-11-08 加入。

完整存放规则见 `main` 分支根目录 README，交接字段见 `docs/data_contract.md`。
