# Online Retail II 四时期数据处理与交接说明

本文档是仓库主目录中 Online Retail II 数据处理流程的正式说明。它解释原始数据、双工作表重叠、字段标准化、清洗口径、四时期切分、订单与购物篮的区别、全部输出文件、成员接口和冻结规则。快速运行看根目录 `README.md`；复现和写报告以本文档、配置及 `run_manifest.json` 为准。

## 1. 最简说明

从仓库根目录运行：

```bash
python3 scripts/run_all.py
```

只有最后显示 `Validation passed`，输出才可以交给 B、C、D。

| 文件 | 粒度 | 使用者 | 作用 |
|---|---|---|---|
| `clean_transactions.csv.gz` | 一行一个物理来源明细 | A | 追踪清洗、重叠和敏感性 |
| `orders.csv.gz` | 一行一个规范订单 | B、D | RFM、金额、阶段、资格、评价分母 |
| `baskets.csv.gz` | 一行一个有效订单购物篮 | D | 判断规则前件和后件是否命中 |
| `baskets_long.csv.gz` | 一行一个订单—商品组合 | C | FP-Growth 和分群购物篮 |

“购物篮”不是把所有顾客归纳成若干种购物组合。一个购物篮就是一张有效订单中去重后的商品集合。例如订单 536365 的有效明细为 A、A、B，其购物篮是 `["A", "B"]`。两个订单即使商品集合相同，仍是两个购物篮。

## 2. 目录和职责

```text
./
├── README.md
├── configs/
│   ├── data_processing.json
│   └── experiment.json
├── data/
│   ├── raw/              # 原始工作簿，本地保存
│   └── processed/        # 生成结果，本地保存
├── docs/
├── scripts/              # 命令行入口
└── src/online_trade/data/ # 处理、审计和验证实现
```

`configs/` 是需要团队冻结的研究口径，`scripts/` 是入口，`src/` 是实现。原始数据和包含客户标识的完整输出默认不提交 Git。

## 3. 原始数据

### 3.1 来源、许可和哈希

- 数据集：UCI Online Retail II，ID 502；
- 页面：<https://archive.ics.uci.edu/dataset/502/online+retail+ii>；
- DOI：<https://doi.org/10.24432/C5CG6D>；
- 许可：CC BY 4.0；
- 文件：`online_retail_II.xlsx`；
- SHA-256：`bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980`。

程序在处理前验证哈希。内容不同会立即停止，防止成员使用不同数据版本。

### 3.2 两张工作表

| 工作表 | 物理明细行 | 日期范围 |
|---|---:|---|
| `Year 2009-2010` | 525,461 | 2009-12-01 至 2010-12-09 |
| `Year 2010-2011` | 541,910 | 2010-12-01 至 2011-12-09 |
| 合计 | 1,067,371 | 包含跨表重叠副本 |

“物理行”是工作簿中真实存在的一行；“规范来源行”是确定唯一来源后可进入分析的一行。

### 3.3 重叠核验和唯一来源

两表在 `[2010-12-01, 2010-12-10)` 重叠。流程按完整行值及重复次数进行多重集比较，而不是看到日期重叠便假设相同：

| 检查 | 结果 |
|---|---:|
| 两表各自的重叠物理行 | 22,523 |
| 完全相同的多重集行 | 22,523 |
| 仅存在于任一张表的行 | 0 |
| 共享订单号 | 1,088 |
| 内容不同的共享订单 | 0 |

核验后采用：

```text
Year 2009-2010：InvoiceDate < 2010-12-01
Year 2010-2011：InvoiceDate >= 2010-12-01
```

因此 1,067,371 条物理证据全部保留；第一张表的 22,523 条重叠副本标记为非规范来源；1,044,848 条规范来源行进入后续处理。重叠副本不进入订单、金额、购物篮、RFM 或实验。选择第二张表承担边界后的数据只是确定稳定的唯一来源，不代表第二张表质量更高。

## 4. 如何运行和复现

流程仅依赖 Python 标准库。从仓库根目录执行：

```bash
python3 scripts/run_all.py
```

它依次完成：

1. 输入哈希与工作表结构验证；
2. 双表流式读取和字段标准化；
3. 规范来源、清洗与重复候选处理；
4. 订单、购物篮和长表构建；
5. 重复、零价格和时间冲突审计；
6. 文件、金额、阶段、资格和跨表对账验证；
7. 输出行数、大小和 SHA-256 写入 manifest。

压缩 CSV 使用固定 gzip 元数据，同一输入、代码和配置应产生相同核心文件哈希。

## 5. 数据处理原则

### 5.1 不改原始文件

程序只读工作簿，结果全部写入 `data/processed/`。

### 5.2 保留证据，再控制用途

取消、退货、零价格、匿名、非商品和跨表重叠不会从逐行证据表消失。布尔标记决定其是否进入下游，使每项汇总都能追溯到工作表和行号。

### 5.3 多标记与互斥原因分开

一行可能同时为取消订单和负数量。所有布尔标记都保留；`primary_exclusion_reason` 按固定优先级只给一个原因，用于互斥汇总。因此不能把各标记数量直接相加当作排除总数。

### 5.4 不根据测试表现改清洗

清洗依据业务语义和审计证据，不依据聚类分数、规则覆盖率或 test 表现。正式实验前必须冻结。

## 6. 字段标准化

| Excel 字段 | 标准字段 | 处理 |
|---|---|---|
| `Invoice` | `invoice_id` | 标准字符串订单号 |
| `StockCode` | `stock_code_raw` / `stock_code` | 保留标准字符串，并生成大写商品键 |
| `Description` | `description` | 清理首尾及连续空白 |
| `Quantity` | `quantity` | 整数 |
| `InvoiceDate` | `invoice_datetime` | ISO 8601 日期时间 |
| `Price` | `unit_price` | Decimal 单价 |
| `Customer ID` | `customer_id` | 标准字符串，缺失为空 |
| `Country` | `country` | 清理空白 |

订单号、客户号和商品编码是标识，不应转成可计算整数。金额使用 Decimal：

```text
line_amount = quantity × unit_price
net_amount = gross_purchase_amount - return_amount
```

退款金额以正的绝对值保存，订单金额输出为两位小数。

## 7. 清洗规则

### 7.1 取消订单

订单号以 `C` 开头时标记 `is_cancelled_invoice = 1`。取消明细不进入正向购物篮或毛购买金额；符合商品和价格条件时，其绝对金额进入退款金额。

### 7.2 负数量与退货

`quantity < 0` 不进入正向购物篮或毛购买金额，符合条件时计入 `return_amount`。不能先删除全部负数量再计算净金额，否则会忽略退款。

### 7.3 零数量、负价格和零价格

- 数量为 0：保留审计，不进入购物篮或金额；
- 单价小于 0：保留审计，不进入主购物篮、购买金额或标准退款；
- 单价为 0：当前配置不进入购物篮或 RFM Frequency，但保留审计。

当前规范来源有 6,024 条零价格行，涉及 5,379 个订单。改变此规则必须在实验前重跑全部阶段。

### 7.4 完全重复候选

在规范来源内部，对以下完整标准化值计算指纹：

```text
invoice_id, stock_code, description, quantity, invoice_datetime,
unit_price, customer_id, country
```

第一次出现保留，后续完全相同行标记为 `is_exact_duplicate_candidate = 1`。当前配置删除其对主购物篮和主金额的影响，同时保留含重复候选金额作敏感性比较。

跨表重叠与普通重复候选不同：前者来自数据发布结构，先选择唯一来源；后者只在规范来源内部检测。非规范来源不参与普通重复检测，避免重复计算同一问题。

当前有 11,812 条后续重复候选，涉及 4,387 个订单，对正向购买金额的影响为 57,481.47。

### 7.5 非商品编码

邮费、折扣、费用、人工调整、测试记录和礼品券不代表可推荐实体商品，不进入购物篮。完整列表以 `configs/data_processing.json` 为准，当前包括 POST、DOT、D、M、C2、BANK CHARGES、AMAZONFEE、CRUK、PADS、ADJUST、TEST、GIFT 系列等。

`special_stock_codes.csv` 保存特殊编码、次数、常见描述和排除状态。冻结前应人工复核；不要只凭编码外观批量删除真实商品。

### 7.6 缺失客户和描述

缺失客户保持空值，不能把所有匿名订单合成一个客户。有效匿名商品订单可以保留，但无法连接历史客户标签，不能进入 G/L/R 主比较。

关联规则以商品编码为键，所以描述缺失本身不自动排除商品；描述主要供人工解释和审计。

### 7.7 极端值

极端数量和金额不自动删除。规范来源中数量或行金额绝对值最大的记录写入 `extreme_lines.csv`，毛购买金额最大的订单写入 `extreme_orders.csv`。截尾或稳健缩放若有需要，应作为 B 的建模决定记录。

### 7.8 主要排除优先级

`primary_exclusion_reason` 依次检查：

```text
missing_invoice → invalid_date → noncanonical_source_row →
missing_stock_code → invalid_quantity → invalid_unit_price →
cancelled_invoice → negative_quantity → zero_quantity → negative_price →
non_product → duplicate_candidate → zero_price
```

缺失客户和描述不是主购物篮的自动排除原因，只保留独立标记。

## 8. 有效记录定义

### 8.1 有效购物篮商品

`is_valid_basket_item = 1` 要求：订单号、商品编码、日期、数量和价格有效；属于规范来源；不是取消订单；数量大于 0；单价大于 0；不是非商品；不是被删除的后续完全重复候选。

### 8.2 有效正向金额行

`is_valid_amount_line = 1` 要求相同的共同条件和正价格。分别保留购物篮与金额标记，是为了让接口语义清楚并支持未来显式敏感性版本。

### 8.3 有效订单与 RFM 订单

- `is_valid_order = 1`：至少有一个有效购物篮商品；
- `is_valid_rfm_order = 1`：至少有一条有效正价格购买明细。

## 9. 订单构建

`orders.csv.gz` 按规范来源的非空订单号汇总，一行一个订单。它保存最早时间、唯一客户、唯一国家、金额、不同商品数、行数、冲突和资格。

同一订单出现多个客户时，`customer_id` 留空并标记冲突；国家同理。多时间戳订单取最早时间，并保存最大跨度。当前有 83 个多时间戳订单，全部未跨实验阶段，最大跨度 540 秒。

### 9.1 金额字段

| 字段 | 定义 |
|---|---|
| `gross_purchase_amount` | 删除重复候选后的有效正向购买金额 |
| `return_amount` | 删除重复候选后的取消/负数量退款绝对额 |
| `net_amount` | 主毛购买金额减主退款金额 |
| `*_with_duplicates` | 保留重复候选的对应敏感性金额 |
| `valid_amount` | 兼容旧接口，当前等于主毛购买金额 |

取消订单可能没有有效购物篮，但仍可在订单表保留退款金额。因此订单表既支持正向 RFM，也支持退款敏感性分析。

## 10. 购物篮构建

购物篮是一个订单内有效商品编码的去重集合：

```text
订单 10001 的有效明细：A, A, B
购物篮：["A", "B"]
```

同一商品的数量不在二值关联规则中重复计数。单商品购物篮保留，因为它们是支持度、覆盖率和未来订单分母的一部分。

- `baskets.csv.gz`：一行一个有效订单，`items` 是 JSON 数组；
- `baskets_long.csv.gz`：每个数组展开为多行，一行一个订单—商品。

验证程序确保两表可无损对账，没有空篮、重复商品对或非商品编码。

## 11. 四时期设计

所有区间左闭右开：

| 阶段 | 时间窗口 | 用途 |
|---|---|---|
| `profile` | `[2009-12-01, 2010-06-01)` | RFM、选择 K、拟合聚类、随机分组 |
| `discovery` | `[2010-06-01, 2010-12-01)` | 挖掘 G/L/R 候选规则 |
| `validation` | `[2010-12-01, 2011-06-01)` | 选择阈值、冗余处理和总规则预算 |
| `test` | `[2011-06-01, 2011-12-01)` | 冻结后的单次最终未来评价 |
| `out_of_scope` | 其他日期 | 不进入主实验 |

2011-12-01 至 12-09 有源数据，但为了四个完整半年窗口而标记 out of scope。

### 11.1 为什么聚类和规则挖掘不用同一时期

聚类描述历史画像期的客户状态，规则挖掘检验这些冻结客户群在后续发现期的购物模式。若两者使用同一时期，聚类特征和规则都由同一批交易决定，局部规则效果混入同时期适配。两年数据足以四分，所以主实验没有必要合并时期。

### 11.2 阶段规模

| 阶段 | 物理明细 | 规范明细 | 有效篮 | 已识别客户 | 活跃 Profile 客户 | 合格篮 |
|---|---:|---:|---:|---:|---:|---:|
| profile | 217,062 | 217,062 | 8,470 | 2,684 | 2,684 | 7,738 |
| discovery | 285,876 | 285,876 | 11,273 | 3,483 | 1,928 | 7,521 |
| validation | 231,552 | 209,029 | 8,067 | 2,716 | 1,458 | 4,862 |
| test | 307,355 | 307,355 | 10,890 | 3,465 | 1,510 | 5,730 |
| out_of_scope | 25,526 | 25,526 | 816 | 614 | 0 | 0 |

Validation 的物理行比规范行多 22,523，正是第一张表中日期落入 validation、但由第二张表承接的重叠副本。

## 12. Profile 客户与主实验资格

Profile 客户必须有唯一非空客户号，并在 profile 至少有一张有效正价格商品订单。当前共有 2,684 名，集合在 2010-06-01 冻结。

`is_eligible_for_main_comparison = 1` 要求：有效购物篮、已识别客户、属于冻结 Profile 客户、订单阶段在四个主时期内。G/L/R 在相应未来期使用同一批合格订单。匿名、新客户和 out-of-scope 订单可另做 Global-only 补充分析，不能混入主比较。

### 12.1 Profile 客户未来活跃

| 指标 | 客户数 | 比例 |
|---|---:|---:|
| discovery 活跃 | 1,928 | 71.83% |
| validation 活跃 | 1,458 | 54.32% |
| test 活跃 | 1,510 | 56.26% |
| 任一未来期活跃 | 2,184 | 81.37% |
| 三个未来期都活跃 | 1,066 | 39.72% |
| 未来均无有效篮 | 500 | 18.63% |

无未来订单客户不会被人为创建空购物篮。订单级评价以实际存在的合格未来订单为分母。

## 13. 核心输出字段

### 13.1 `clean_transactions.csv.gz`

一行一个物理来源明细，共 1,067,371 行。

| 字段组 | 字段及含义 |
|---|---|
| 来源 | `source_row_id`、`source_sheet`、`source_sheet_row` |
| 唯一来源 | `is_canonical_source_row`、`is_cross_sheet_overlap_excluded` |
| 标识 | `invoice_id`、`stock_code_raw`、`stock_code`、`customer_id` |
| 交易 | `description`、`quantity`、`invoice_datetime`、`unit_price`、`line_amount`、`country`、`split` |
| 问题标记 | 取消、负/零数量、负/零价格、缺客户、缺描述、非商品、重复候选 |
| 用途标记 | `is_valid_basket_item`、`is_valid_amount_line` |
| 汇总原因 | `primary_exclusion_reason` |

此表用于 A 的追溯和敏感性分析，不直接交给 FP-Growth。

### 13.2 `orders.csv.gz`

一行一个规范订单，共 53,628 行。

| 字段 | 含义 |
|---|---|
| `basket_id` | 订单号，也是购物篮 ID |
| `customer_id` | 唯一客户号；冲突或缺失时为空 |
| `invoice_date` / `invoice_datetime` | 订单最早时间，两个字段当前相等 |
| `country` | 唯一国家；冲突时为空 |
| 金额字段 | 主版本及含重复候选敏感性金额 |
| `basket_size` | 不同有效商品数 |
| `line_count` | 规范来源明细数 |
| `valid_basket_line_count` | 有效购物篮明细数，可能含同商品多行 |
| `valid_amount_line_count` | 有效正向金额明细数 |
| `split` | 按最早订单时间划分的阶段 |
| 有效/资格字段 | 有效订单、RFM 订单、已识别客户、Profile 客户、主比较合格 |
| 冲突字段 | 客户、国家、时间冲突及时间跨度 |
| 审计计数 | 重复候选、取消和非商品行数 |

B 只用 profile 行计算 RFM；D 只用 validation/test 合格行评价。同一张表能供两者使用，是因为每行有明确阶段和资格，而不是允许混用所有时期。

### 13.3 `baskets.csv.gz`

一行一个有效购物篮，共 39,516 行。字段包含订单、客户、时间、国家、JSON 商品数组、不同商品数、毛购买金额、阶段和资格。D 用它判断未来订单是否包含规则前件和后件。

### 13.4 `baskets_long.csv.gz`

一行一个订单—商品，共 992,036 行：

```text
basket_id, customer_id, invoice_date, invoice_datetime,
stock_code, split, is_eligible_for_main_comparison
```

C 使用 discovery 合格行。不要从逐行证据表重建购物篮，否则容易重新引入取消、费用、零价格和重复明细。

## 14. 审计与敏感性文件

| 文件 | 作用 |
|---|---|
| `audit_summary.csv` | 汇总来源行、标记、订单、篮、客户、商品和时期 |
| `exclusion_summary.csv` | 互斥主要排除原因 |
| `sheet_reconciliation_summary.csv` | 两表、规范来源和重叠对账 |
| `cross_sheet_overlap_exclusions.csv` | 22,523 条被排除重叠副本 |
| `cross_sheet_invoice_conflicts.csv` | 重叠订单内容差异，当前 0 行 |
| `period_eligibility_summary.csv` | 四时期规模和资格 |
| `four_period_retention_summary.csv` | Profile 客户未来活跃 |
| `invoice_conflicts.csv` | 客户、国家或时间不一致订单 |
| `time_conflict_stage_check.csv` | 时间冲突是否跨阶段 |
| `special_stock_codes.csv` | 特殊编码、描述和排除状态 |
| `extreme_lines.csv` / `extreme_orders.csv` | 极端明细和订单 |
| `audit_order_samples.csv` | 单商品、多商品、匿名、取消、非商品样例 |
| `duplicate_sensitivity_summary.csv` | 重复候选影响 |
| `zero_price_summary.csv` / `zero_price_codes.csv` | 零价格影响 |
| `run_manifest.json` | 输入、环境、Git、配置、数量和输出哈希 |

这些文件证明处理可信，不是聚类或规则挖掘的直接输入。

## 15. 四位成员如何使用

### 15.1 A：数据与复现

A 检查全部输出，重点是逐行证据、双表重叠、互斥排除、冲突、特殊编码、极端值、重复、零价格、阶段资格和 manifest。A 保证金额与数量对账、时期不重叠、接口固定，并在提交前独立复现。

### 15.2 B：RFM、聚类和随机分组

B 主要读取 `orders.csv.gz`，筛选 profile、非空客户和 Profile 客户。推荐：

- Recency：`2010-06-01` 减最后一次有效 profile 正向购买日期；
- Frequency：`is_valid_rfm_order == 1` 的不同订单数；
- Monetary：profile 有效正向订单 `gross_purchase_amount` 之和。

`net_amount` 可作退款敏感性版本。若用净额，先确定 Profile 客户，再汇总其 profile 全部订单净额，不能先过滤退款订单。B 至少输出：

```text
customer_id, R, F, M, cluster_id, random_group, seed
```

聚类和客户级随机分组必须在 discovery 前冻结。

### 15.3 C：关联规则挖掘

C 读取 `baskets_long.csv.gz`，筛选：

```text
split == "discovery"
is_eligible_for_main_comparison == 1
```

再连接 B 的冻结客户标签。G/L/R 必须使用同一批合格订单和相同系统总规则预算。C 不得用 validation/test 挖候选规则。

### 15.4 D：验证和未来评价

D 用 `orders` 确定订单、客户、时期、资格和分母，用 `baskets` 判断前件/后件命中。Validation 仅选择 discovery 已产生规则的预声明配置；Test 在全部冻结后评价一次：

```text
validation: split == "validation" and eligible == 1
test:       split == "test"       and eligible == 1
```

## 16. 读取示例

### 16.1 pandas

```python
import pandas as pd

orders = pd.read_csv(
    "data/processed/orders.csv.gz",
    dtype={"basket_id": "string", "customer_id": "string"},
)
profile_orders = orders[
    (orders["split"] == "profile")
    & (orders["is_profile_customer"] == 1)
]
```

### 16.2 标准库和 JSON 购物篮

```python
import csv, gzip, json

with gzip.open(
    "data/processed/baskets.csv.gz",
    "rt", encoding="utf-8", newline="",
) as stream:
    for row in csv.DictReader(stream):
        if row["split"] == "test" and row["is_eligible_for_main_comparison"] == "1":
            items = set(json.loads(row["items"]))
```

不要用逗号手工切分 `items`；它是 JSON 数组。各类 ID 必须按字符串读取。

## 17. 自动验证

`validation.py` 检查：

1. 21 个必需文件存在且有表头；
2. `source_row_id` 唯一并从 1 连续；
3. 明细阶段和规范来源标记符合配置；
4. 非规范行不进入购物篮、金额或重复规则；
5. 重叠区间无单边行和内容冲突订单；
6. 订单号唯一，毛额减退款等于净额；
7. 主金额不大于含重复候选金额；
8. 合格订单有效、有唯一客户且属于 Profile 客户；
9. 购物篮非空、商品唯一、数量一致且无非商品；
10. `baskets_long` 与 `baskets.items` 完全一致；
11. manifest 数量与文件一致，并记录每个输出哈希。

自动验证不能替代人工判断，如非商品列表是否合理、Monetary 口径是否获全组确认。

## 18. 当前快照

```text
物理来源明细                   1,067,371
规范来源明细                   1,044,848
跨表重叠排除                      22,523
跨表冲突订单                           0
规范订单                          53,628
有效购物篮                        39,516
订单—商品组合                    992,036
Profile 客户                       2,684
完全重复候选                      11,812
零价格记录                         6,024
多时间戳订单                          83
跨阶段时间冲突订单                     0
```

这是配置版本 1 的本地快照。精确结果和哈希以对应运行的 manifest 为准，不应把数字硬编码进下游脚本。

## 19. 修改配置

处理规则位于 `configs/data_processing.json`，实验规则位于 `configs/experiment.json`。修改非商品列表、零价格、重复策略、时间边界、RFM 口径、K、随机种子、规则阈值/预算或资格后，必须更新日志、从原始工作簿重跑、重新验证并生成新 manifest。禁止直接编辑 processed CSV。

## 20. Test 保护

查看 test 前必须冻结：数据哈希和来源策略、清洗规则、Profile 客户、RFM、缩放、K、聚类、随机分组、discovery 候选规则、validation 选出的阈值/去冗余/总预算，以及评价指标和分母。

Test 期间禁止重新聚类、重新挖规则、调参、改清洗或根据测试覆盖率选版本。真正代码错误应留痕、全流程重跑，并声明原 test 已被访问。

## 21. 已知限制

- 数据没有商品层级、成本、利润或推荐曝光；
- 主比较只代表可识别且在 profile 活跃的历史客户；
- 非商品列表依赖编码和描述人工审计；
- 取消/退货不能总与原购买逐行配对；
- 二值购物篮忽略同商品数量；
- 客户随时间流失，四时期样本会变化；
- out-of-scope 数据不用于主实验；
- 源时间按无时区本地时间解释，不因运行时区而平移；
- 结构验证不等于因果解释或商业可部署性。

## 22. 常见问题

### 最重要的是订单表和购物篮表吗？

它们是下游核心接口，但不是全部。`orders` 回答“一单属于谁、何时、多少钱、能否评价”；`baskets` 回答“一单有哪些有效商品”；逐行证据保证可追溯；长表供 FP-Growth 使用。

### 为什么 `orders` 能同时供聚类和评价？

因为它带 `split` 和资格字段。B 只读 profile，D 只读 validation/test。共享一张表保证统一口径，不表示共享同一时期。

### 聚类和 Pattern Mining 能用同一时期吗？

技术上可以，但不适合作为本项目主实验。独立 profile 与 discovery 能减少同时期适配，并表达“历史客户群的未来购物模式”。

### 为什么不直接删除异常行？

逐行保留并用标记控制下游，既能生成干净接口，又能审计每类排除的数量和金额影响。

### 为什么保留单商品订单？

它们是真实订单，也是支持度、覆盖率和未来订单分母。删除会人为抬高多商品规则表现。

### 为什么匿名订单不进主比较？

L/R 需要历史客户标签。若 Global 用匿名订单而 L/R 不用，样本不公平。

### 为什么重复更影响 Monetary？

购物篮对订单内商品二值化，重复行通常不增加商品；金额逐行求和，重复会直接放大 Monetary。

### 为什么零价格不进主篮？

零价格可能是赠品、录入错误或特殊操作。纳入可产生难解释规则，保留审计更稳妥。

### 为什么跨表重叠不等于普通重复？

跨表重叠来自发布结构，经完整多重集核验后选唯一来源；普通重复是规范来源内部的相同行，二者来源和审计不同。

### 为什么 Validation 的物理行和规范行不同？

第一张表的 22,523 条重叠副本日期属于 validation，但由第二张表作为唯一规范来源承接，所以证据保留、分析只计一次。

### 为什么有订单时间冲突？

少数订单明细相差数分钟。流程取最早时间并记录跨度。当前 83 个冲突订单均未跨日期或阶段。

## 23. 冻结前检查清单

### A

- [ ] 输入哈希一致，重叠行和 1,088 个共享订单完全一致；
- [ ] `Validation passed`；金额、篮和时期对账通过；
- [ ] 非商品、特殊编码、重复、零价格、极端值和冲突已复核；
- [ ] manifest、日志和 Git 提交对应；
- [ ] 原始交易与客户级输出未误提交 Git。

### B

- [ ] 只用 profile，Recency 截止点为 2010-06-01；
- [ ] Frequency 和 Monetary 口径已冻结；
- [ ] 缩放、K、种子和稳定性标准已登记；
- [ ] 客户标签一对一且可复现。

### C

- [ ] 只用 discovery 合格篮；
- [ ] 客户标签已冻结；
- [ ] G/L/R 使用相同订单池和总规则预算；
- [ ] 未用 validation/test 产生候选规则。

### D

- [ ] Validation 只选预声明配置，Test 冻结后只运行一次；
- [ ] 三种方法使用同一合格订单和分母；
- [ ] 前件分母为 0 时 confidence 记为不可估；
- [ ] 未为无未来订单客户制造空购物篮；
- [ ] Global-only 新客户结果与主比较分开。

## 24. 一句话总结

本流程保留 1,067,371 条物理证据，经严格核验排除 22,523 条跨表重叠副本，再用独立的 profile、discovery、validation 和 test 生成可追溯订单与购物篮接口，使聚类、规则发现、配置选择和最终评价共享统一口径，却不共享不应看到的时期。
