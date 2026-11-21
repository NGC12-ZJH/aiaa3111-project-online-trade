# 活跃度匹配的随机分组（B → C，2026-11-15）

这个分支提供两份**顾客级随机分组**，供 C 在**商品层和品类层**重跑 G/L/R 对比。生成代码和 B 的品类层结果也已放在本分支（见 `docs/activity_matched_control.md`）。为了让 C 的重跑是独立的，**请先跑完再看 B 的结果**，最后两边核对品类层数字。

## 为什么要换随机分组

原来的 20 套随机分组（`random_groups.csv`，种子 42–61，下文叫 S）只匹配了每组**人数**（700 / 1,263 / 721），没有匹配**活跃度**。Discovery 期每组的篮子数差得很远：

| Discovery 篮子数 | C0 | C1 | C2 |
|---|---|---|---|
| 真实分群 | 801 | 2,173 | 4,547 |
| S（中位数） | 1,974 | 3,531 | 1,992 |
| **A1**（中位数） | 963 | 2,163 | 4,400 |
| **A2**（中位数） | 832 | 2,277 | 4,400 |

篮子数不同，会影响 support 的抽样噪声和"联合次数 ≥20"的过线数量；买得多的人买的东西本来也不同。所以只和 S 比，不能说明分群抓到了购物偏好。新的分组**只在同一活跃度档内打乱真实群标签**：每档每组的人数和真实分群完全相同，总人数仍是 700 / 1,263 / 721。

## 文件

| 文件 | 分档依据 | 档位 | 定位 |
|---|---|---|---|
| `random_groups_A1_profile_frequency.csv` | Profile 期订单数（`customer_clusters.csv` 的 `frequency`） | 1 / 2 / 3–4 / 5–9 / 10+ | **主对照**：只用分群时已有的信息 |
| `random_groups_A2_discovery_baskets.csv` | Discovery 期合格篮子数 | 0 / 1 / 2 / 3–4 / 5–9 / 10+ | **补充**：直接对齐挖规则时的篮子量；Discovery 信息只用来生成随机组 |

- 格式：`customer_id,random_group_id,seed,stratum`，前三列和原来的 `random_groups.csv` 相同；`stratum` 是档位，挖规则用不到。
- 种子 **1000–1099，共 100 个**，和原来的 42–61 不重叠；每个文件 268,400 行（2,684 位 Profile 顾客 × 100 个种子）。
- 每个种子都核对过：每个档位里各组人数和真实分群一致。
- sha256：
  - A1：`cec6323091538e1436e7075efe4e92b1caefb9c5dd9bad586fcb09b8c8c6839d`
  - A2：`cea8ee0b237ccfd568f5fdc6cb6cff191a085e3554f626e277515dbab3691f40`
- 真实分群仍用原来的 `customer_clusters.csv`（快照 `2ae672b`，和 C 分支里 `labels/` 下的那份相同）。

注意：Profile 订单数 ≥5 的 385 人里有 383 人是 C2，所以 A1 对 C2 几乎没有检验力，主要检验 C0 和 C1 的区别。

## 请 C 做的事

1. **商品层**（`patterns/`、`random_similarity/`、`pattern_analysis/` 里的 G/L/R 对比）和**品类层**（`category_patterns/` → `category_screening/` → `category_fixed_budget/`）各用 A1 跑一遍；有时间再用 A2 跑一遍。
2. 代码里写死了 20 个种子 / 64 个范围，需要改这些断言（行号对应 `c/pattern-mining-taxonomy` 的 `0673ce3`）：
   - `pattern_mining.py` 第 26 行；
   - `compare_random_similarity.py` 第 14、47 行；
   - `mine_categories.py` 第 43 行；
   - `screen_category_rules.py` 第 67 行；
   - `category_fixed_budget.py` 第 15、45 行。

   范围数应为 1 + 3 + 3 × 种子数。
3. 随机组文件路径建议改成参数传入；输出写到新目录（例如 `patterns_A1/`、`category_fixed_budget_A1/`），**不要覆盖**现有的 S 结果。
4. 运行时间：原来商品层的 60 个随机组约 408 秒，100 个种子（300 组）估计每种对照约 35 分钟。如果只跑前 20 个种子（1000–1019），请在看结果**之前**决定并写明，因为 20 个种子时 p 最小只有 0.048。
5. 汇报口径：
   - 每个种子算一个系统级指标（不要把 300 个随机组当独立样本）；
   - 单侧经验 p = (1 + 随机 ≥ 真实的次数) / (1 + 种子数)；
   - S、A1、A2 三种对照并排列出；
   - 写明只是 Discovery 期的描述，多个指标没有做多重比较校正。

## 还要组里决定

- Test 期评价用哪种随机对照：B 建议用 A1 作为主对照、S 作为参考。A2 用了 Discovery 的活跃度，放到 Test 期要重新定义。需要 D 一起确认，最好在 11-18 冻结前定下来。
- 这两份顾客级文件按约定应该放到快照分支 `a/online-retail-ii-data-snapshot`。这里先放在功能分支方便 C 取用，冻结时再统一迁移。
