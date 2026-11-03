# Online Retail 数据处理说明

本文档面向第一次看到本项目的人。读完后应当能够回答以下问题：

1. 原始数据是什么？
2. 数据处理中检查和处理了哪些问题？
3. 哪些记录被保留，哪些记录不进入主分析？
4. “干净明细”“订单表”“主购物篮”和“审计表”分别是什么？
5. 四位成员分别应该使用哪些数据？
6. 如何重新运行并验证处理结果？

本目录负责四人版研究计划中的 T0：数据清洗、订单构建、购物篮构建、时间切分、样本资格定义、数据审计和复现。这里不负责正式计算 RFM、聚类、关联规则或最终覆盖率，但会为这些工作提供统一的数据输入。

---

## 1. 最简说明

原始 Excel 是订单商品明细，一行代表一张订单中的一个商品记录。原始数据不能直接用于聚类或关联规则，因为其中包含：

- 取消订单和负数量退货；
- 邮费、折扣、手续费和人工调整；
- 零价格记录；
- 缺失客户编号；
- 完全重复候选；
- 商品编码大小写不一致；
- 极端数量和金额；
- 2011 年 12 月的范围外数据。

本流程不会修改原始 Excel，也不会直接丢弃原始证据。它会保留全部 541,909 条原始明细，并增加清洗标记，然后生成适合不同任务的订单表和购物篮表。

数据流如下：

```text
data/raw/Online Retail.xlsx
        │
        ▼
clean_transactions.csv.gz       全部原始明细 + 清洗标记
        │
        ├────────► orders.csv.gz             一行一个订单，供 RFM 和评价使用
        │
        ├────────► baskets.csv.gz            一行一个购物篮
        │
        ├────────► baskets_long.csv.gz       一行一个订单—商品组合，供 FP-Growth 使用
        │
        └────────► audit/sensitivity files   对账、异常检查和敏感性分析
```

---

## 2. 项目目录

以下目录均以本 Git 仓库根目录为基准：

```text
aiaa3111-project-online-trade/
├── data/
│   ├── raw/
│   │   └── Online Retail.xlsx        本地只读输入，不提交 Git
│   └── processed/                    本地生成输出，不提交 Git
├── src/online_trade/data/
│   ├── config.py                     清洗口径和路径配置
│   ├── pipeline.py                   核心处理逻辑
│   ├── policy_audit.py               重复项和零价格敏感性统计
│   ├── time_conflicts.py             订单时间冲突检查
│   └── validation.py                 输出验证
├── scripts/
│   ├── process_online_retail.py
│   ├── inspect_data_policy.py
│   ├── check_time_conflicts.py
│   └── validate_data_outputs.py
└── docs/
    └── data_processing_guide.md
```

`data/raw/Online Retail.xlsx` 是只读输入。所有新结果写入 `data/processed/`。这两个数据目录中的实际数据受 `.gitignore` 保护，不应上传到 GitHub。

---

## 3. 原始数据

原始工作表名为 `Online Retail`，包含以下字段：

| 字段 | 含义 | 原始数据中的注意点 |
|---|---|---|
| `InvoiceNo` | 订单号 | 普通订单通常为数字；以 `C` 开头的订单为取消订单；也存在其他字母前缀 |
| `StockCode` | 商品编码 | 既包含真实商品，也包含邮费、折扣、手续费和人工调整编码 |
| `Description` | 商品描述 | 存在缺失、大小写和空格不一致 |
| `Quantity` | 商品数量 | 存在负数、零值和极端值 |
| `InvoiceDate` | 订单日期时间 | Excel 日期格式，需要转换为真正的日期时间 |
| `UnitPrice` | 商品单价 | 存在零价格、负价格和异常高价格 |
| `CustomerID` | 客户编号 | 大量缺失；Excel 读取时可能表现为带 `.0` 的数字 |
| `Country` | 国家或地区 | 用于描述和订单一致性检查，不用于当前主分群特征 |

当前原始数据共有 541,909 条明细，时间范围为 2010-12-01 至 2011-12-09。

---

## 4. 运行环境

程序使用 Python 3 标准库直接流式读取 `.xlsx` 内部 XML，不依赖 pandas、openpyxl 或 pyarrow。

当前验证环境：

```text
Python 3.10.12
```

这样设计的原因是远程环境没有预装数据分析包，而标准库版本可以直接运行，不需要修改服务器环境。

---

## 5. 如何运行

进入克隆后的 Git 仓库根目录，将原始工作簿放在 `data/raw/Online Retail.xlsx`，然后依次执行：

```bash
python3 scripts/process_online_retail.py
python3 scripts/inspect_data_policy.py
python3 scripts/check_time_conflicts.py
python3 scripts/validate_data_outputs.py
```

四个脚本的作用分别是：

1. `process_online_retail.py`：读取原始 Excel，清洗并生成主数据表和审计表。
2. `inspect_data_policy.py`：计算重复候选和零价格记录的敏感性统计。
3. `check_time_conflicts.py`：检查同一订单的多个时间戳是否跨越实验阶段。
4. `validate_data_outputs.py`：检查输出是否完整、金额是否对账、时间切分是否正确、购物篮是否有效。

正常完成时，最后一条命令应输出：

```text
Validation passed: all required files, reconciliations, split boundaries, baskets, and eligibility checks are valid.
```

如果验证失败，不应继续运行聚类、规则挖掘或未来评价。应先修复数据问题并重新生成全部输出。

---

## 6. 数据处理的基本原则

### 6.1 原始文件不修改

程序只读取 `data/raw/Online Retail.xlsx`。不会覆盖、另存或修改原始工作簿。

`run_manifest.json` 保存原始文件的 SHA-256。当前输入文件哈希为：

```text
43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16ae4c3936424676d
```

如果将来哈希发生变化，说明原始文件版本发生变化，旧结果不应与新结果直接混用。

### 6.2 保留原始证据

`clean_transactions.csv.gz` 保留全部原始明细。所谓“删除重复项”或“排除零价格商品”，是指这些记录不进入主金额、主购物篮或主实验，不是从证据表中彻底抹掉。

### 6.3 一条记录可以有多个问题

例如一条记录可能同时满足：

- 取消订单；
- 负数量；
- 非商品编码；
- 重复候选。

因此程序同时保存多个布尔标记。`primary_exclusion_reason` 只用于生成互斥的排除汇总，不能代替全部标记。

这解释了为什么：

- 重复候选标记有 5,268 行，但以“重复候选”为主要排除原因的只有 5,226 行；
- 非商品标记有 2,959 行，但以“非商品”为主要排除原因的只有 2,364 行；
- 零价格标记有 2,515 行，但以“零价格”为主要排除原因的只有 1,156 行。

差异来自标记重叠，而不是统计错误。

---

## 7. 字段标准化

### 7.1 订单号

`InvoiceNo` 转换为字符串并保存为 `invoice_id`，避免数字订单号和字母订单号使用不同数据类型。

### 7.2 商品编码

程序同时保存：

- `stock_code_raw`：原始商品编码；
- `stock_code`：统一转为大写后的标准商品编码。

例如 `15056bl` 和 `15056BL` 会统一为 `15056BL`，避免同一商品被当作两个商品。

不能简单删除所有含字母的编码，因为 `85123A`、`84029G` 等也是正常商品。

### 7.3 客户编号

客户编号统一转换为字符串。例如 Excel 中的 `17850.0` 转换为 `17850`。

缺失客户保持为空，不填成 `unknown`，因为所有匿名订单不能被错误地合并成同一个客户。

### 7.4 文本字段

商品描述和国家字段会去除首尾空格，并合并连续空格。不会根据商品描述合并商品，商品身份以标准化后的 `StockCode` 为主。

### 7.5 日期

Excel 日期序列转换为 Python 日期时间，输出格式类似：

```text
2010-12-01 08:26:00
```

### 7.6 金额

每条明细的金额定义为：

```text
line_amount = Quantity × UnitPrice
```

金额输出保留两位小数。计算内部使用 `Decimal`，减少二进制浮点误差。

---

## 8. 清洗规则

### 8.1 取消订单

规则：

```text
InvoiceNo 以 C 开头 → is_cancelled_invoice = 1
```

取消订单保留在干净明细和订单表中，但不进入主购物篮或正向购买金额。

当前共有 9,288 条取消订单明细。这里的数字是明细行数，不是取消订单数。

### 8.2 负数量和退货

规则：

```text
Quantity < 0 → is_negative_quantity = 1
```

负数量记录不进入主购物篮。符合商品条件的负数量或取消记录计入订单表的 `return_amount`。

当前共有 10,624 条负数量明细。其中一部分同时属于取消订单。

本流程没有强行把每一条退货匹配到某一张历史购买订单，因为原数据没有可靠的原订单引用。它只保留订单级退款金额。后续报告中不能声称所有退货都已与原购买一一匹配。

### 8.3 零数量

`Quantity == 0` 的记录不能进入主购物篮或有效金额。目前数据审计没有发现零数量记录。

### 8.4 负价格

`UnitPrice < 0` 的记录不能进入主购物篮或有效金额。当前共有 2 条负价格记录。

### 8.5 零价格

当前主口径：

- 零价格记录保留在干净明细；
- 标记 `is_zero_price = 1`；
- 不进入主购物篮；
- 不定义 RFM 有效订单；
- 金额为零；
- 另行生成零价格敏感性统计。

当前共有 2,515 条零价格明细，涉及 2,155 个订单和 31 个可识别客户。

采用这一口径的原因是零价格记录可能代表赠品、库存调整或缺失价格。如果直接进入购物篮，可能产生“商品 → 免费赠品”规则，并使只包含零价格项目的订单增加 Frequency。

### 8.6 完全重复候选

程序使用以下字段识别完全重复候选：

```text
invoice_id
stock_code
description
quantity
invoice_datetime
unit_price
customer_id
country
```

第一条记录保留为主记录，后续完全相同的记录标记为：

```text
is_exact_duplicate_candidate = 1
```

当前主口径：

- 后续重复候选不进入主金额；
- 后续重复候选不重复进入主购物篮；
- 原始行和重复标记仍保留；
- 订单表同时保存“包含重复项”的敏感性金额。

当前共有：

| 指标 | 数值 |
|---|---:|
| 重复候选额外行 | 5,268 |
| 占全部明细 | 0.972% |
| 受影响订单 | 1,933 |
| 受影响客户 | 960 |
| 候选副本对应的正向购买金额 | 24,573.74 |
| 候选副本对应的退款金额 | 2,832.76 |

删除重复候选不会改变同一订单中的商品是否出现，因为购物篮会对商品二值化；它主要影响订单金额和 RFM Monetary。

### 8.7 非商品编码

邮费、折扣、手续费、佣金、人工调整、礼品券及无法确认的单次异常编码不进入主商品购物篮。

当前配置排除以下编码：

```text
AMAZONFEE
B
BANK CHARGES
C2
CRUK
D
DOT
M
PADS
POST
S
GIFT_0001_10
GIFT_0001_20
GIFT_0001_30
GIFT_0001_40
GIFT_0001_50
DCGS0055
DCGS0057
DCGS0066P
DCGS0067
DCGS0068
DCGS0071
DCGS0072
DCGS0073
DCGS0074
```

主要含义：

| 编码 | 含义 |
|---|---|
| `POST` | 邮费 |
| `DOT` | 网上订单邮费 |
| `M` | 人工调整 |
| `C2` | 运费 |
| `D` | 折扣 |
| `BANK CHARGES` | 银行手续费 |
| `AMAZONFEE` | Amazon 费用 |
| `CRUK` | 佣金或费用 |
| `GIFT_...` | 礼品券 |
| `DCGS0055` 等 | 描述缺失或仅写作 `ebay` 的单次异常编码 |

真实商品编码如 `15056BL`、`DCGSSGIRL`、`DCGSSBOY`、`DCGS0003`、`DCGS0069`、`DCGS0070` 和 `DCGS0076` 保留。

`79323GR` 和 `79323LP` 在原数据中的描述为 `Unsaleable, destroyed.`。这些具体明细会因负数量或其他无效条件被排除，但不会永久禁止整个商品编码。

### 8.8 缺失客户

当前有 135,080 条明细缺失 `CustomerID`。

处理方式：

- 保留在干净明细；
- 如果商品记录有效，可以出现在全局数据描述中；
- 不能计算客户级 RFM；
- 不能分配真实客户群；
- 不进入 G/L/R 主公平比较；
- 单独报告匿名订单的范围。

不能把匿名客户填成同一个固定 ID，否则会制造一个不存在的超级客户。

### 8.9 缺失商品描述

当前有 1,454 条明细缺失 `Description`。

商品描述缺失不会自动导致商品被删除，因为 `StockCode` 才是商品主键。但记录仍会被标记，并出现在特殊编码和人工审计结果中。

### 8.10 极端数量和金额

极端值不因“看起来很大”而自动删除。批发订单可能是真实交易。

程序输出：

- `extreme_lines.csv`：数量绝对值或明细金额绝对值最大的记录；
- `extreme_orders.csv`：毛购买金额最大的订单。

这些文件用于人工检查和后续敏感性分析。如果团队决定限制极端订单，必须报告规则和影响，不能根据测试结果临时删除。

---

## 9. 有效记录定义

### 9.1 主购物篮有效商品

一条明细要进入主购物篮，需要同时满足：

```text
InvoiceNo 非空
StockCode 非空
InvoiceDate 有效
Quantity > 0
UnitPrice > 0
不是取消订单
不是非商品编码
不是后续完全重复候选
```

满足时：

```text
is_valid_basket_item = 1
```

### 9.2 有效金额明细

当前主口径下，有效金额明细与主购物篮商品使用相同的正向购买条件：

```text
is_valid_amount_line = 1
```

当前有效金额/购物篮商品明细为 522,537 行。

### 9.3 RFM 有效订单

订单至少包含一条正价格有效商品明细时：

```text
is_valid_rfm_order = 1
```

零价格订单、取消订单、纯邮费订单和纯调整订单不能增加 Frequency。

---

## 10. 订单构建

原始数据是一行一个商品明细，RFM 需要一行一个订单。因此程序按 `InvoiceNo` 聚合生成 `orders.csv.gz`。

每张订单检查：

- 是否对应多个客户；
- 是否对应多个国家；
- 是否出现多个时间；
- 是否至少含一个有效商品；
- 是否含重复候选；
- 是否含取消或非商品记录；
- 主金额和敏感性金额是否对账。

当前结果：

- 不同订单号：25,900；
- 客户冲突订单：0；
- 国家冲突订单：0；
- 时间不一致订单：43；均未跨越时间阶段。

时间不一致订单保存在 `invoice_conflicts.csv`。`check_time_conflicts.py` 已逐一检查全部时间戳：43 个订单都发生在同一日、同一实验阶段内，最大时间差为 60 秒，没有订单跨越画像期、发现期、验证期、测试期或范围外边界。因此使用订单最早时间不会改变阶段归属。详细证据保存在 `time_conflict_stage_check.csv`。

### 10.1 订单金额字段

主金额删除后续重复候选：

```text
gross_purchase_amount
return_amount
net_amount = gross_purchase_amount - return_amount
```

敏感性金额保留重复候选：

```text
gross_purchase_amount_with_duplicates
return_amount_with_duplicates
net_amount_with_duplicates
```

当前全部订单的主毛购买金额约为 10,247,219.32，含重复项版本约为 10,271,433.06。

---

## 11. 购物篮构建

购物篮表示一张订单中出现过哪些有效商品。

处理规则：

1. 以 `InvoiceNo` 为购物篮 ID。
2. 只使用 `is_valid_basket_item = 1` 的商品。
3. 同一商品在同一订单中出现多次时，只保留一次。
4. 商品按编码排序，保证重复运行结果一致。
5. 有效单商品购物篮保留。
6. 没有有效商品的订单不进入购物篮，但仍保留在订单表和审计表。

示例：

```text
原始订单：A、A、B（零价格）、POST（邮费）、D（折扣）
主购物篮：{A}
```

当前共有：

| 指标 | 数值 |
|---|---:|
| 有效购物篮 | 19,773 |
| 单商品购物篮 | 1,500 |
| 多商品购物篮 | 18,273 |
| 订单—商品组合 | 517,287 |

单商品购物篮虽然不能单独产生二项关联规则，但必须保留在后续覆盖率评价分母中。

---

## 12. 时间切分

所有窗口使用左闭右开形式：包含开始时间，不包含结束时间。

| 阶段 | 时间窗口 | 作用 |
|---|---|---|
| `profile` | `[2010-12-01, 2011-04-01)` | 建立历史客户集合，供 B 计算 RFM 和聚类 |
| `discovery` | `[2011-04-01, 2011-07-01)` | C 挖掘全局、真实群体和随机群体规则 |
| `validation` | `[2011-07-01, 2011-09-01)` | 选择少量配置、规则预算和筛选方式 |
| `test` | `[2011-09-01, 2011-12-01)` | 冻结后进行最终未来评价 |
| `out_of_scope` | 其他时间 | 不进入主实验；当前主要是 2011 年 12 月数据 |
| `invalid_date` | 无法解析日期 | 不进入主实验 |

代码中的等价逻辑：

```python
profile = 2010-12-01 <= date < 2011-04-01
discovery = 2011-04-01 <= date < 2011-07-01
validation = 2011-07-01 <= date < 2011-09-01
test = 2011-09-01 <= date < 2011-12-01
```

不能使用发现期、验证期或测试期数据计算历史 RFM。不能根据测试结果改变清洗规则、商品名单、聚类数量或规则筛选标准。

### 12.1 各阶段当前规模

| 阶段 | 原始明细 | 有效购物篮 | 可识别客户 | 不同商品 | 画像期客户的合格购物篮 |
|---|---:|---:|---:|---:|---:|
| 画像期 | 142,083 | 5,164 | 2,132 | 3,094 | 4,681 |
| 发现期 | 103,820 | 4,428 | 1,988 | 3,025 | 2,914 |
| 验证期 | 74,802 | 2,791 | 1,493 | 2,854 | 1,797 |
| 测试期 | 195,679 | 6,574 | 2,845 | 3,161 | 3,688 |
| 范围外 | 25,525 | 816 | 614 | 2,433 | 0 |

这里的“可识别客户”是当前阶段有有效购物篮且 `CustomerID` 非空的客户；“画像期客户的合格购物篮”还要求客户在画像期已经出现。

---

## 13. 历史客户和主实验资格

### 13.1 画像期客户

客户满足以下条件时属于画像期客户：

```text
CustomerID 非空
画像期至少有一张有效正价格商品订单
```

当前共有 2,132 个画像期客户。

### 13.2 主实验合格订单

订单满足以下条件时：

```text
is_eligible_for_main_comparison = 1
```

条件包括：

1. 订单存在有效主购物篮；
2. 客户编号可识别；
3. 客户在画像期出现过；
4. 订单位于画像、发现、验证或测试窗口之一。

这样可以保证全局规则 G、真实分群规则 L 和随机分群规则 R 使用同一类可识别历史客户，避免某个方案因为样本不同而获得不公平优势。

新客户和匿名客户不进入主 G/L/R 比较，但要报告其数量和被排除范围。

---

## 14. 输出文件说明

### 14.1 `clean_transactions.csv.gz`

粒度：一行一个原始交易明细。

主要字段：

| 字段 | 含义 |
|---|---|
| `source_row_id` | 对应原 Excel 的数据行编号，从 1 开始，不含表头 |
| `invoice_id` | 标准字符串订单号 |
| `stock_code_raw` | 原始商品编码 |
| `stock_code` | 大写标准商品编码 |
| `description` | 清理空格后的描述 |
| `quantity` | 数量 |
| `invoice_datetime` | 日期时间 |
| `unit_price` | 单价 |
| `line_amount` | 数量乘单价 |
| `customer_id` | 标准字符串客户编号，缺失保持空值 |
| `country` | 国家或地区 |
| `split` | 时间阶段 |
| `is_cancelled_invoice` | 是否为取消订单 |
| `is_negative_quantity` | 数量是否小于零 |
| `is_zero_quantity` | 数量是否等于零 |
| `is_zero_price` | 单价是否等于零 |
| `is_negative_price` | 单价是否小于零 |
| `is_missing_customer` | 客户编号是否缺失 |
| `is_missing_description` | 商品描述是否缺失 |
| `is_non_product` | 是否为配置中的非商品编码 |
| `is_exact_duplicate_candidate` | 是否为完全重复的后续副本 |
| `is_valid_basket_item` | 是否进入主购物篮 |
| `is_valid_amount_line` | 是否进入主正向购买金额 |
| `primary_exclusion_reason` | 用于互斥排除汇总的主要原因 |

用途：数据追溯、人工核验、敏感性分析。不要直接把整张表交给 FP-Growth。

### 14.2 `orders.csv.gz`

粒度：一行一个订单号。

主要字段：

| 字段 | 含义 |
|---|---|
| `basket_id` | 订单号，也是购物篮 ID |
| `customer_id` | 唯一客户编号；若订单客户冲突则为空 |
| `invoice_datetime` | 订单最早时间 |
| `country` | 唯一国家；若冲突则为空 |
| `gross_purchase_amount` | 删除重复候选后的正向购买金额 |
| `return_amount` | 删除重复候选后的退款金额 |
| `net_amount` | 主毛购买金额减主退款金额 |
| `gross_purchase_amount_with_duplicates` | 含重复候选的正向购买金额 |
| `return_amount_with_duplicates` | 含重复候选的退款金额 |
| `net_amount_with_duplicates` | 含重复候选的净金额 |
| `basket_size` | 不同有效商品数量 |
| `line_count` | 原始明细行数 |
| `valid_basket_line_count` | 有效购物篮明细行数 |
| `valid_amount_line_count` | 有效正向金额明细行数 |
| `split` | 时间阶段 |
| `is_valid_order` | 是否存在有效主购物篮 |
| `is_valid_rfm_order` | 是否至少包含一项正价格有效商品 |
| `is_identified_customer` | 是否有唯一客户编号 |
| `is_profile_customer` | 是否属于画像期客户 |
| `is_eligible_for_main_comparison` | 是否符合主 G/L/R 比较资格 |
| `has_customer_conflict` | 同一订单是否出现多个客户 |
| `has_country_conflict` | 同一订单是否出现多个国家 |
| `has_datetime_conflict` | 同一订单是否出现多个时间 |
| `datetime_span_seconds` | 同一订单不同时间的最大跨度 |
| `duplicate_candidate_count` | 订单内重复候选副本数 |
| `cancelled_line_count` | 取消明细数 |
| `non_product_line_count` | 非商品明细数 |

用途：B 计算 RFM，D 确定客户、订单、阶段和评价分母。

### 14.3 `baskets.csv.gz`

粒度：一行一个有效购物篮。

`items` 使用 JSON 数组保存，例如：

```json
["21730", "22752", "71053", "84029E"]
```

主要用途：D 按订单判断规则前件和后件是否命中，也方便人工检查完整购物篮。

### 14.4 `baskets_long.csv.gz`

粒度：一行一个订单—商品组合。

示例：

| basket_id | customer_id | stock_code | split |
|---|---|---|---|
| 536365 | 17850 | 21730 | profile |
| 536365 | 17850 | 22752 | profile |

主要用途：C 转换为 FP-Growth 所需的交易集合，或按客户群构建局部购物篮。

### 14.5 审计和敏感性文件

| 文件 | 作用 |
|---|---|
| `audit_summary.csv` | 汇总原始行、各标记、订单、购物篮、客户、商品和时间阶段数量 |
| `exclusion_summary.csv` | 按互斥的主要排除原因汇总明细行 |
| `invoice_conflicts.csv` | 列出客户、国家或时间不一致的订单 |
| `time_conflict_stage_check.csv` | 逐单检查时间冲突是否跨越实验阶段，并保存全部时间戳和跨度 |
| `special_stock_codes.csv` | 列出异常/非标准编码、出现次数、常见描述和当前是否排除 |
| `extreme_lines.csv` | 数量或明细金额绝对值最大的记录 |
| `extreme_orders.csv` | 毛购买金额最大的订单 |
| `audit_order_samples.csv` | 单商品、多商品、匿名、取消和非商品订单人工核验样例 |
| `duplicate_sensitivity_summary.csv` | 重复候选的数量、阶段、订单、客户和金额影响 |
| `zero_price_summary.csv` | 零价格记录涉及的订单、客户和阶段 |
| `zero_price_codes.csv` | 零价格商品编码和常见描述 |
| `run_manifest.json` | 输入哈希、Python 版本、运行时间、配置、输出文件和核心数量 |

审计文件不是聚类或规则挖掘的直接输入。它们用于证明数据处理可信、解释排除范围和复核异常。

---

## 15. 四位成员分别使用什么数据

### 15.1 A：数据与复现

A 负责本处理流程，应检查全部输出，重点包括：

```text
clean_transactions.csv.gz
audit_summary.csv
exclusion_summary.csv
invoice_conflicts.csv
time_conflict_stage_check.csv
special_stock_codes.csv
extreme_lines.csv
extreme_orders.csv
duplicate_sensitivity_summary.csv
zero_price_summary.csv
run_manifest.json
```

A 的职责：

- 确保清洗规则可解释；
- 确保数量和金额能够对账；
- 确保时间窗口无重叠；
- 向 B、C、D 提供固定接口；
- 在最终提交前独立复现结果；
- 不根据测试表现改变清洗规则。

### 15.2 B：RFM、聚类和随机分组

B 主要使用：

```text
data/processed/orders.csv.gz
```

建立客户画像的基础范围：

```text
split == "profile"
customer_id 非空
```

RFM 建议计算方式：

- Recency：以 2011-04-01 为统一截止点，减去客户画像期最后一次有效正向购买日期；
- Frequency：统计 `is_valid_rfm_order == 1` 的不同订单数；
- Monetary：团队需要在正式实验前冻结毛购买口径或净金额口径。

推荐主版本：

- R/F 只使用有效正向购买订单；
- M 主版本使用画像期有效正向订单的 `gross_purchase_amount`，保证 Monetary 非负并兼容 `log1p`；
- 使用含重复项金额作为敏感性检查，而不是主输入。

`net_amount` 可作为退款敏感性版本。如果使用净金额，不能先把所有取消/退款订单过滤掉；应先确定画像期客户，再对这些客户在画像期的 `net_amount` 求和。

B 应输出至少：

```text
customer_id
R
F
M
cluster_id
random_group
seed
```

### 15.3 C：关联规则挖掘

C 主要使用：

```text
data/processed/baskets_long.csv.gz
```

并连接 B 的客户群标签：

```text
customer_id → cluster_id
```

主规则发现范围：

```text
split == "discovery"
is_eligible_for_main_comparison == 1
```

全局规则 G、真实分群规则 L 和随机分群规则 R 应使用同一批合格客户订单。不能让全局方法使用匿名/新客户，而局部方法只使用画像期客户。

C 不应直接从 `clean_transactions.csv.gz` 挖掘规则，否则可能重新引入：

- 取消和退货；
- 邮费和折扣；
- 零价格商品；
- 重复商品行；
- 不符合主实验资格的订单。

### 15.4 D：验证和未来评价

D 主要使用：

```text
data/processed/orders.csv.gz
data/processed/baskets.csv.gz
B 的客户群标签
C 的固定规则表
```

验证期：

```text
split == "validation"
is_eligible_for_main_comparison == 1
```

测试期：

```text
split == "test"
is_eligible_for_main_comparison == 1
```

`orders.csv.gz` 用于确定订单、客户、阶段和评价分母；`baskets.csv.gz` 用于判断一张未来订单是否包含规则前件和后件。

D 不应重新挖掘测试期规则，也不能根据测试覆盖率选择清洗设置。

---

## 16. 如何读取压缩 CSV

### 16.1 使用 pandas

如果环境安装了 pandas：

```python
import pandas as pd

orders = pd.read_csv("data/processed/orders.csv.gz")
baskets_long = pd.read_csv("data/processed/baskets_long.csv.gz")
```

pandas 会根据 `.gz` 后缀自动解压。

### 16.2 使用 Python 标准库

```python
import csv
import gzip

with gzip.open(
    "data/processed/orders.csv.gz",
    "rt",
    encoding="utf-8",
    newline="",
) as file:
    rows = csv.DictReader(file)
    first_order = next(rows)
    print(first_order)
```

### 16.3 读取购物篮 JSON 数组

```python
import csv
import gzip
import json

with gzip.open(
    "data/processed/baskets.csv.gz",
    "rt",
    encoding="utf-8",
    newline="",
) as file:
    for row in csv.DictReader(file):
        items = json.loads(row["items"])
        print(row["basket_id"], items)
        break
```

---

## 17. 自动验证做了什么

`validate_data_outputs.py` 会检查：

1. 所有必需输出文件存在且非空；
2. `source_row_id` 唯一；
3. 每条明细的时间阶段与日期边界一致；
4. 每个订单号在订单表中唯一；
5. 主金额满足 `gross - return = net`；
6. 含重复项金额也满足 `gross - return = net`；
7. 主毛购买金额不大于含重复项毛购买金额；
8. 合格订单同时满足有效订单、RFM 有效订单、可识别客户和画像期客户条件；
9. 每个购物篮非空；
10. 购物篮内没有重复商品；
11. `basket_size` 等于商品集合实际长度；
12. 购物篮不包含配置中的非商品编码；
13. `baskets_long.csv.gz` 与 `baskets.csv.gz` 中的商品集合完全一致；
14. 运行清单记录数与实际文件一致。

当前版本已经通过全部检查。

自动验证不能代替人工判断。人工仍需查看：

- 特殊商品编码；
- 时间冲突订单；
- 极端数量和金额；
- 代表性的普通、单商品、匿名、取消和非商品订单。

---

## 18. 当前数据处理结果快照

以下结果对应当前 `config.py` 和输入哈希，改变配置后必须重新生成：

| 指标 | 数值 |
|---|---:|
| 原始明细 | 541,909 |
| 订单号 | 25,900 |
| 取消明细 | 9,288 |
| 负数量明细 | 10,624 |
| 负价格明细 | 2 |
| 零价格明细 | 2,515 |
| 客户编号缺失明细 | 135,080 |
| 商品描述缺失明细 | 1,454 |
| 完全重复候选 | 5,268 |
| 非商品明细 | 2,959 |
| 主有效商品/金额明细 | 522,537 |
| 有效购物篮 | 19,773 |
| 单商品购物篮 | 1,500 |
| 多商品购物篮 | 18,273 |
| 订单—商品组合 | 517,287 |
| 画像期客户 | 2,132 |

主要排除原因是互斥统计，当前为：

| 主要原因 | 行数 |
|---|---:|
| 取消订单 | 9,288 |
| 完全重复候选 | 5,226 |
| 负数量 | 1,336 |
| 非商品 | 2,364 |
| 零价格 | 1,156 |
| 负价格 | 2 |

这些主要原因加总不能与全部标记逐项比较，因为一条记录可能同时具有多个标记。

---

## 19. 修改配置

所有核心设置集中在：

```text
src/online_trade/data/config.py
```

包括：

- 输入文件和输出目录；
- 时间窗口；
- 非商品编码名单；
- 是否让零价格商品进入购物篮；
- 是否保留完全重复候选；
- 审计样本数量。

修改配置后必须重新执行全部四个命令：

```bash
python3 scripts/process_online_retail.py
python3 scripts/inspect_data_policy.py
python3 scripts/check_time_conflicts.py
python3 scripts/validate_data_outputs.py
```

并保存新的：

```text
run_manifest.json
audit_summary.csv
duplicate_sensitivity_summary.csv
zero_price_summary.csv
```

不能只修改 CSV 结果，不更新代码和运行清单。

---

## 20. 测试集保护规则

测试阶段为 2011-09-01 至 2011-11-30。

在配置冻结前，可以检查测试期的：

- 文件是否能读取；
- 日期格式是否正确；
- 有多少订单、客户和商品；
- 历史客户订单覆盖范围；
- 是否存在空值或结构问题。

不能根据以下内容调整配置：

- 哪个 K 在测试期表现最好；
- 哪组规则测试覆盖率最高；
- 删除哪些订单能提高局部规则表现；
- 哪个商品门槛能获得更好测试结果；
- 哪个随机种子最不利或最有利。

如果测试后发现代码错误，应记录变更并对 G/L/R 全部方法重新运行。如果根据测试效果改变研究设计，结果必须标记为探索性结果。

---

## 21. 已知限制

1. 数据没有原始明细行 ID，完全重复候选被视为很可能的重复导出/录入，但不能从源系统证明。
2. 取消和退货没有可靠的原订单引用，因此未做强制一一匹配。
3. 匿名客户不能计算客户级 RFM，也不能进入分群主实验。
4. 非商品编码名单来自当前数据审计，若原始数据版本改变，需要重新检查。
5. 商品描述可能变化或缺失，商品身份主要依赖标准化 `StockCode`。
6. 极端批发订单当前保留，后续只能作为预先说明的敏感性分析处理。
7. 2011 年 12 月数据不在主时间协议中，标记为 `out_of_scope`。
8. 当前流程准备 RFM 输入，但没有替 B 决定最终 K 或聚类标签。
9. 当前流程准备购物篮，但没有替 C 决定 FP-Growth 的最低支持次数和规则预算。
10. 当前流程定义评价对象，但没有替 D 计算最终覆盖率或 bootstrap 区间。

---

## 22. 常见问题

### 为什么不直接删除所有异常行？

研究需要可审计性。保留原始记录和标记，才能说明删除了什么、为什么删除以及删除后结果是否变化。

### 为什么单商品订单还要保留？

单商品订单不能形成二项关联规则，但它仍是真实未来购物篮，必须进入覆盖率评价分母。删除它会人为提高覆盖率。

### 为什么匿名订单不能进入主比较？

局部方法需要知道客户属于哪个群。匿名客户无法分群。为了公平，全局、真实分群和随机分群方法都应在相同的可识别历史客户订单上比较。

### 为什么重复候选影响 Monetary，却通常不影响关联规则？

同一商品在购物篮中只记一次，所以重复明细不会增加商品出现次数；但重复明细会重复计算数量乘价格，因此会增加订单金额。

### 为什么零价格商品不进入主购物篮？

它可能代表赠品或数据问题，会产生与正常购买行为含义不同的规则。记录仍保留，可在敏感性分析中重新纳入。

### 为什么邮费和折扣不算商品？

研究目标是商品组合。若保留邮费、折扣和手续费，可能得到“购买某商品后出现邮费”这类没有商品组合意义的规则。

### 为什么不能用测试期调整清洗规则？

这样会把测试答案提前泄漏到数据处理和模型选择中，使最终未来表现不再是独立检验。

### 为什么有订单时间冲突？

同一 `InvoiceNo` 的不同明细可能记录不同时间。程序将其列入冲突表并使用最早时间，但这些订单需要人工复核。

---

## 23. 最终冻结前检查清单

数据负责人 A：

- [ ] 原始文件哈希与 `run_manifest.json` 一致；
- [ ] 四个脚本均能在干净环境运行；
- [ ] `validate_data_outputs.py` 通过；
- [x] 43 个时间冲突订单已检查：全部同日、同阶段，最大相差 60 秒；
- [ ] 检查特殊编码和极端订单；
- [ ] 确认零价格和重复候选口径已获团队同意；
- [ ] 确认非商品编码名单已冻结；
- [ ] 向 B、C、D 提供同一版本输出；
- [ ] 记录处理日期、配置和代码版本。

分群负责人 B：

- [ ] 只使用画像期数据计算 RFM；
- [ ] Frequency 使用订单数，不使用明细行数；
- [ ] 明确 Monetary 的毛额或净额口径；
- [ ] 输出客户—群体映射和随机分组标签。

规则负责人 C：

- [ ] 只使用发现期合格购物篮挖掘主规则；
- [ ] 全局、真实群体和随机群体使用相同对象；
- [ ] 不把测试月份放入候选规则池；
- [ ] 保留规则的原始计数、分母和配置编号。

评价负责人 D：

- [ ] 验证期和测试期使用相同数据口径；
- [ ] 所有方法使用相同评价订单；
- [ ] 单商品购物篮保留在分母；
- [ ] 测试前冻结规则、预算、指标和随机种子；
- [ ] 不按测试结果重新分配预算或选择配置。

---

## 24. 一句话总结

本流程把 541,909 条原始订单商品明细保留为可追溯的干净明细，并按照固定规则生成订单表、19,773 个主购物篮、时间切分、历史客户资格和完整审计证据，使 B、C、D 能在相同、可复现且无未来信息泄漏的数据基础上完成分群、规则挖掘和未来评价。
