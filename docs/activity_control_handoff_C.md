# 活跃度匹配随机对照：思路说明与交接给 C

> 来自 B（Jinghan ZHAO）· 2026-11-15 · 分支 `b/activity-random-groups`
> 完整结果见 [`activity_matched_control.md`](activity_matched_control.md)。这里讲**为什么这样做**，以及 **C 需要做什么**。
> 全部只用 Discovery 期，没有用 Validation 或 Test。

## 0. 一句话

原来的随机分组只匹配了**人数**。改成只在"活跃度相同的顾客"之间打乱标签之后：**品类层的群间差异仍然显著（p ≈ 0.01–0.02），但比随机多出的部分缩小了约一半，剩下的主要来自 C0；固定预算覆盖率上，L 依然不比随机好。** 品类层我已经算完，并且和 C 的数字逐项核对一致。**商品层需要 C 用新的随机分组重跑。**

---

## 1. 思路

### 1.1 原来的对照有什么问题

原来的 20 套随机分组（下文叫 **S**），是把真实群标签在全部 2,684 位顾客里整体打乱。这保证了每组人数和真实分群一样（700 / 1,263 / 721），但**每组有多少订单完全没有控制**：

| Discovery 期篮子数 | C0 | C1 | C2 |
|---|---|---|---|
| 真实分群 | 801 | 2,173 | 4,547 |
| S（20 个种子的中位数） | 1,974 | 3,531 | 1,992 |

真实的 C0 只有 801 个篮子，随机的"C0"有约 2,000 个；真实的 C2 有 4,547 个，随机的"C2"只有约 2,000 个。这会带来三个问题：

1. **抽样噪声不同。** 篮子越少，support 估计越不稳，和别的组算出来的"差异"就越大。所以 C0 和随机组比"差异更大"，可能只是因为它小。
2. **规则门槛的效果不同。** 规则要求"联合次数 ≥20"。篮子少的组能过线的规则少，规则数量和覆盖率因此没法直接比较。
3. **买得多的人本来就买不同的东西。** 高频顾客（C2）的订单更大、品类更杂。如果随机组的活跃度构成和真实分群不同，那么真实分群和随机分组之间的任何差别，都可能只是"买得多 vs 买得少"的差别，而不是分群抓到了什么偏好。

所以，在 S 下看到"真实分群比随机更不同"，**不能说明分群揭示了独特的购物偏好**。

### 1.2 怎么改：只在同一活跃度档里打乱

把顾客按活跃度分档，**只在同一档内部打乱真实群标签**。这样：

- 每个档里，每组的人数都和真实分群完全一样，所以每组的活跃度构成也和真实分群一样；
- 每组的总人数仍然是 700 / 1,263 / 721，和原来的 S 一致；
- 真实分群和这种随机组唯一的区别，就是"同等活跃度下，具体是哪些顾客"。如果真实分群还是比它更不同，这部分差异就不能用活跃度解释。

做了两种分档：

| 对照 | 按什么分档 | 档位 | 种子 | 定位 |
|---|---|---|---|---|
| **A1** | Profile 期订单数 | 1 / 2 / 3–4 / 5–9 / 10+ | 1000–1099（100 个） | **主对照**。只用分群时已有的信息，和 HANDOFF 里的计划一致 |
| **A2** | Discovery 期篮子数 | 0 / 1 / 2 / 3–4 / 5–9 / 10+ | 1000–1099（100 个） | **补充**。直接对齐挖规则时每组的篮子量。Discovery 信息只用来生成随机组，不碰分群本身 |

为什么要两个：A1 是"干净"的，因为它只用分群当时就有的信息；但 Profile 的活跃度不能完全预测 Discovery 的活跃度（C0 是"流失顾客"，同样下过 1 单，在 Discovery 期回来得更少）。A2 正好补上这一点，直接把篮子量对齐。两个对照结论一致，结果才可信。

匹配效果（Discovery 篮子数，100 个种子的中位数）：

| | C0 | C1 | C2 |
|---|---|---|---|
| 真实分群 | 801 | 2,173 | 4,547 |
| A1 | 963 | 2,163 | 4,400 |
| A2 | 832 | 2,277 | 4,400 |

### 1.3 这个对照回答的是什么问题

RFM 本身就含频率 F，所以 A1 实际回答的是：**"除了买得多不多，分群还提供了别的信息吗？"**

要注意：Profile 订单数 ≥5 的 385 位顾客里，有 383 位是 C2。所以在 A1 下，随机的"C2"和真实 C2 本来就差不多，A1 **对 C2 几乎没有检验力**，主要检验的是 C0 和 C1 之间的区别（也就是 Recency 和 Monetary 带来的信息）。这一点在汇报时要说明。

### 1.4 为什么用 100 个种子

经验 p = (1 + 随机 ≥ 真实的次数) / (1 + 种子数)。20 个种子时 p 最小只能到 0.048，正好卡在 0.05 附近，说服力不够；100 个种子时最小能到 0.0099。品类层的计算很快（全部约 10 秒），商品层估计见第 3.3 节。

---

## 2. 我已经做了什么（品类层）

1. **复现 C 的结果**：数据（A 快照 `2ae672b`）、taxonomy（`item_taxonomy_v1.csv`，和 C 那份的 sha256 相同）、门槛、排序、预算分配全部按 C 的设定。我用穷举计数代替 FP-Growth（所有在 Discovery 里联合次数 ≥20 的 2/3 品类组合，共 52,451 个），结果等价。用 C 原来的 20 个随机种子跑一遍，**14 项数字全部和 C 一致**（`results/tables/activity_control/reproduction_check_vs_C.csv`）。
2. **用 S、A1、A2 三种对照**，计算 C 用过的两类指标：群间差异（Bray–Curtis，群 vs 群外、群与群之间，二品类和三品类分开），以及固定预算（20/50/100）的系统覆盖率。

主要结果（详见 [`activity_matched_control.md`](activity_matched_control.md) 第 4 节）：

| 指标 | 真实分群 | S 中位数（p） | A1 中位数（p） | A2 中位数（p） |
|---|---|---|---|---|
| 群 vs 群外差异，二品类 | 0.112 | 0.083（0.05） | 0.096（**0.01**） | 0.090（**0.02**） |
| 群与群之间差异，二品类 | 0.132 | 0.096（0.05） | 0.105（**0.01**） | 0.102（**0.01**） |
| 覆盖率，预算 50 | 52.1% | 51.2%（0.19） | 52.1%（0.49） | 51.4%（0.22） |
| 群内合格但 G 不合格的比例 | 68.4% | 57.0%（0.10） | 62.5%（0.03） | 61.3%（0.17） |

逐群看，C0 在两种对照下都显著（A1 p = 0.01，A2 p = 0.03）；C1 边缘显著；C2 不显著。

**对 C 已有结论的影响**：

- C 报告 7.5 节"尚未证明品类层群间差异超过随机"：现在可以补上，**超过了，而且匹配活跃度后仍然成立，但幅度减半，主要来自 C0**。
- C 报告第 8 节"L 处于随机范围内"：**结论不变，而且更强了**。匹配活跃度后，L 落在随机分布中间；预算 20 时，94 个 A1 随机组覆盖率不低于 L（共 100 个）。
- C 报告 7.4 节"68.35% 的群内合格规则在 G 中不合格"：**随机分组也有 57–63%**，这个比例不能当作分群有用的证据，建议在报告里注明。

---

## 3. 交接给 C：需要做什么

### 3.1 拿到新的随机分组

本分支的 `data/processed/B_customer_clustering/` 已经带有这两份顾客级文件；也可以在本地用脚本自己生成。结果完全确定，可以用 sha256 核对：

```bash
git fetch origin && git switch b/activity-random-groups
```

```bash
cp experiments/c_pattern/labels/customer_clusters.csv data/processed/local/customer_clusters.csv
```

```bash
cp experiments/c_pattern/labels/random_groups.csv data/processed/local/random_groups.csv
```

```bash
python scripts/run_activity_control.py
```

脚本会用 `git show` 从 A 的快照提交 `2ae672b` 读取购物篮，所以本地仓库里要有这个提交（C 的 `prepare_inputs.py` 已经 fetch 过；没有的话先运行 `git fetch origin a/online-retail-ii-data-snapshot`）。

（中间两步把 C 分支里那两份标签复制过去。它们和 B 本地的完全相同，sha256 分别是 `fc3826…5bcf` 和 `f60048…a3db`。如果是在 C 自己的分支上操作，先从本分支取出 `scripts/`、`src/`、`configs/experiment.json`。）

生成后应得到：

| 文件 | 行数 | sha256 |
|---|---|---|
| `data/processed/local/random_groups_A1_profile_frequency.csv` | 268,400（2,684 人 × 100 个种子） | `cec6323091538e1436e7075efe4e92b1caefb9c5dd9bad586fcb09b8c8c6839d` |
| `data/processed/local/random_groups_A2_discovery_baskets.csv` | 268,400 | `cea8ee0b237ccfd568f5fdc6cb6cff191a085e3554f626e277515dbab3691f40` |

格式和原来的 `random_groups.csv` 一样，只多了一列 `stratum`（所在档位，C 不需要用）：

```
customer_id,random_group_id,seed,stratum
12346,0,1000,1
```

种子是 1000–1099，和原来的 42–61 不重叠，结果表里不会混淆。

### 3.2 优先级

| 优先级 | 任务 | 说明 |
|---|---|---|
| **必做** | **商品层**用 A1 重跑随机对照 | 我只做了品类层。商品层是 C 的主交付，原来的 `random_similarity` 和 `pattern_analysis` 里的 G/L/R 结论都只对 S 成立 |
| 建议 | 商品层用 A2 再跑一遍 | 和品类层一样，两个对照一致才放心 |
| 不用做 | 品类层重跑 | 我已经复现了 C 的数字。C 想自己核对的话，用 `scripts/run_activity_control.py` 的输出即可 |

### 3.3 C 的代码要改哪里

C 的脚本里写死了"20 个种子 / 64 个范围"。用 100 个种子需要改这些断言（行号对应 `c/pattern-mining-taxonomy` 的 `0673ce3`）：

| 文件 | 位置 | 现在 | 改成 |
|---|---|---|---|
| `pattern_mining.py` | 第 26 行 | `assert len(seeds)==20` | 种子数从输入里读 |
| `compare_random_similarity.py` | 第 14、47 行 | `len(seeds)==20`、`len(r)==20` | 同上 |
| `mine_categories.py` | 第 43 行 | `len(scopes)==64` | `1 + 3 + 3 × 种子数` |
| `screen_category_rules.py` | 第 67 行 | `base_reconciled==64` | 同上 |
| `category_fixed_budget.py` | 第 15、45 行 | `len(rules)==64`、`len(r)==20` | 同上 |

另外，各脚本都从 `labels/random_groups.csv` 读随机组。建议加一个参数，比如 `--random-groups labels/random_groups_A1.csv`；输出也写到**新的目录**（比如 `patterns_A1/`），**不要覆盖**现有的 S 结果，最后三种对照并排报告。

**运行时间**：C 原来商品层的 60 个随机组挖掘共用了约 408 秒，平均每组约 7 秒。100 个种子是 300 组，估计**每种对照约 35 分钟**。如果来不及，可以先跑种子 1000–1019（20 个），但要在看结果**之前**决定用多少个种子，并在报告里写明，因为 20 个种子时 p 最小只有 0.048。

### 3.4 汇报时请统一口径

- **每个种子算一个系统级指标**（3 组取等权平均，或者算系统覆盖率），100 个种子就是 100 个值。不要把 300 个随机组当作独立样本。这和 C 现在的做法一致。
- **经验 p 是单侧的**：p = (1 + 随机 ≥ 真实的次数) / (1 + 种子数)。
- 表格里**同时列出 S、A1、A2 三种对照**。S 的结果保留，用来说明"只匹配人数会高估分群的差异"。
- 写清局限：A1 对 C2 检验力很弱；多个指标分别算 p，没有做多重比较校正；这些都只是 Discovery 期的描述。

---

## 4. 需要组里（最好在 11-18 冻结前）决定的事

1. **Test 期评价用哪种随机对照？** 我建议**用 A1 作为主随机对照**，S 作为参考。A1 只用了分群当时就有的信息，能提前冻结；A2 用到了 Discovery 的活跃度，放到 Test 期要重新定义（例如改用 Test 期之前的活跃度）。这关系到 D 在 Validation 和 Test 期的评价方式，需要 D 一起确认。
2. **随机分组文件放哪里？** 现在 C 把 `random_groups.csv` 提交到了自己的分支（`experiments/c_pattern/labels/`），和"顾客级文件不进功能分支"的约定不一致。建议统一放在快照分支 `a/online-retail-ii-data-snapshot` 的 `data/processed/B_customer_clustering/` 下，和原来的 `random_groups.csv` 放在一起，需要 A 同意。
3. **C 报告里第 7.4 节的"群内合格但 G 不合格"比例**，是否加上随机对照的说明（见第 2 节）。

---

## 5. 文件清单

| 文件 | 内容 |
|---|---|
| `configs/experiment.json` 的 `activity_matched_control` 部分 | 分档、种子、指标的全部参数 |
| `src/online_trade/clustering/activity_control.py` | 生成活跃度匹配的随机分组，并检查每档每组人数和真实分群一致 |
| `src/online_trade/taxonomy/category_controls.py` | 品类层计数、严格档规则、固定预算覆盖率、Bray–Curtis 差异 |
| `scripts/run_activity_control.py` | 入口：生成随机分组、跑全部对照、核对 C 的数字、写出结果表 |
| `scripts/plot_activity_control.py` | 画图 |
| `tests/test_activity_control.py` | 分档、打乱后人数守恒、预算分配三个测试 |
| `results/tables/activity_control/` | 全部结果表（各文件内容见 [`activity_matched_control.md`](activity_matched_control.md) 第 6 节） |
| `results/figures/activity_control_real_vs_random.png` | 真实分群 vs 三种对照 |
| `docs/activity_matched_control.md` | 完整结果和解读 |
| `docs/activity_control_handoff_C.md` | 本文件 |

有问题请在组群里 @B，或直接在本分支的 PR 里留言。
