# C：Pattern Mining 已完成工作与复现说明

## 状态与范围

截至2026-11-11，C完成Discovery开发版规则挖掘及探索分析，未用Validation选择配置，未评价Test性能。本提交不是已冻结的最终实验，也不证明真实分群优于全局。

全部独立实验保存在 `experiments/c_pattern/`，不修改A的数据处理、B的聚类或D的评价模块。它是当前可复现实验交付，尚未整合成仓库统一run_all入口。原始Excel、顾客级数据、虚拟环境、编码矩阵和含订单编号的案例样例不随功能分支上传。结果表中的商品编码和规则指标保留。

## 数据与交接

沿用A的Online Retail II清洗口径。Profile为[2009-12-01,2010-06-01)，Discovery为[2010-06-01,2010-12-01)。主样本限Profile已知顾客：1928名顾客、7521个Discovery有效购物篮、3321个商品，含709个单商品篮。所有G/L/R使用相同订单。

A/B数据固定取快照提交 `2ae672b7ea6edb7f5e1561b6a64823004dea833e`：A文件在 `data/processed/A_data_preparation/`，B标签在 `data/processed/B_customer_clustering/`。购物篮SHA256为 `30aef702f812ab42224271871271daff5b4e37a594696eee82208252198367bf`。每项实验manifest保留输入哈希；结果来自本地原始脚本运行，发布时只调整两个脚本的仓库路径，历史manifest中的代码哈希仍代表当时版本，不能作为发布脚本哈希。

## 一、算法对照

CPU mlxtend 0.23.4 FP-Growth和默认Apriori，稠密布尔输入，支持度1%/2%、最长项集2/3，四组设置、每种算法三次独立进程，共24次运行。两算法项集和整数计数全部一致，并逐项重算。

|支持度|长度|项集数|FP-Growth中位秒|Apriori中位秒|FP-Growth峰值MiB|Apriori峰值MiB|
|---|---|---|---|---|---|---|
|2%|2|326|1.37|2.06|641|824|
|2%|3|327|1.28|2.33|638|824|
|1%|2|1062|5.31|19.39|657|4044|
|1%|3|1194|6.58|23.42|664|4072|

耗时仅挖掘调用，内存为约5ms采样的进程RSS峰值，包含环境和输入，非算法独占内存。进程高水位另列，含导入阶段。Apriori有较大运行波动，原始结果均保留，不宣称普遍速度优势。

## 二、G/L/R挖掘与公平筛选

FP-Growth运行64次：G一次、L三个真实群、R二十个seed（42–61）各三组。随机标签以顾客为单位，画像期各组人数匹配。各群Discovery订单量C0=801、C1=2173、C2=4547。

开发参数：support>=1%、联合次数>=20、前件次数>=20、confidence>=0.2、lift>=1；前件1–2商品、后件1商品。C0实际支持度下限20/801≈2.50%。合格方向规则G=1116、C0=46、C1=843、C2=1590。

共同候选池11246条，按商品前后件去重，再为64个范围计算719744行证据。保留前件、后件、联合次数、群内support/confidence/lift、群外指标、全局排名及本范围是否独立发现。相同门槛下完整FP-Growth应找到同样的合格规则，因此native/common_pool可能相同；共同池本身不是收益证据。

系统总预算20/50/100；局部按Discovery订单量比例用最大余数法分配，余数相同按群号排序，空缺不重新分配。按联合次数、confidence、lift降序及rule_id升序筛选，仅去完全重复规则。群体条件不同占不同名额。预算50时真实群5/15/30条。

完整订单覆盖同一篮只计一次。Discovery订单覆盖G为22.32%/28.59%/39.72%，L为13.96%/22.02%/27.46%；R中位数13.25%/20.58%/26.53%。这些是发现期结果，随机范围不是置信区间，无显著性或未来效果结论。顾客宏平均另报。

## 三、规则解释与可视化

全局高排名主要涉及礼品家居、袋类、烘焙配件的同系列共购，不代表正式品类销量占比。C0暖手袋和玩具屋系列排名提前；C1毛毡靠垫较突出；C2袋类与白色木质家居较突出且与全局重合较多。C2贡献约60.5%的Discovery篮子，影响全局统计。

反例：C0玩具屋卧室→厨房群内support较高，但confidence低于群外，不能说条件关联更强。样例是探索性挑选，未做多重检验。商品名称来自Discovery有效交易中该编码最常见描述。

四张中文PNG/SVG图位于pattern_analysis/figures。排行榜HTML包含全部64个范围，可切换Top10/20/50、搜索名称；C0仅46条。每组TopN不是系统总预算B。全局50条方向规则仅26个商品并集，存在完整覆盖冗余，后续去冗余须一致用于G/L/R。

## 四、高金额订单补充

按全体合格Discovery订单毛购买金额90%分位数筛选，金额>=£888.47，包含并列；753张订单、310位顾客，占42.51%毛购买额，C0/C1/C2分别53/99/601张。固定原计数门槛20，因此高金额实际支持度约2.66%；得到1128条合格方向规则。

蛋糕纸杯、午餐盒、蛋糕架和茶具搭配更突出。高金额篮商品种类中位数29，其余14。按篮子大小分层后部分差异减弱；这不是因果调整。匹配规则的整单金额不能归因给规则、不能跨规则相加。此补充不是新的G/L/R未来效果实验，不预测订单是否高金额。

## 输出与交接

- `patterns/selected_rules.csv`、`config.json`：给D的固定开发规则与配置，按flow/method/seed/budget筛选，避免把不同预算或种子叠加。
- `patterns/rule_evidence.csv.gz`：完整候选证据；`scope_audit.csv`和`budget_audit.csv`核对分母与实际容量。
- `results/`：算法对照原始运行与汇总。
- `pattern_analysis/`：案例、群差异、覆盖、冗余和图片。
- `pattern_top_rules/`：完整排行榜、文本和JSON。
- `high_value_analysis/`：独立高金额规则、分层证据、中文HTML报告与图片。

## 复现

需要Python 3.12和Git。建议新建虚拟环境，依赖精确版本见 experiments/c_pattern/requirements-lock.txt（Windows实验环境）。从仓库根目录执行：

```powershell
python -m venv .venv-c
.venv-c/Scripts/python.exe -m pip install -r experiments/c_pattern/requirements-lock.txt
.venv-c/Scripts/python.exe experiments/c_pattern/prepare_inputs.py
.venv-c/Scripts/python.exe experiments/c_pattern/benchmark.py
.venv-c/Scripts/python.exe experiments/c_pattern/pattern_mining.py
.venv-c/Scripts/python.exe experiments/c_pattern/validate_patterns.py
.venv-c/Scripts/python.exe experiments/c_pattern/analyze_patterns.py
.venv-c/Scripts/python.exe experiments/c_pattern/visualize_patterns.py
.venv-c/Scripts/python.exe experiments/c_pattern/export_top_rules.py
.venv-c/Scripts/python.exe experiments/c_pattern/high_value_patterns.py
.venv-c/Scripts/python.exe experiments/c_pattern/report_high_value.py
```

prepare_inputs从固定Git快照提取A购物篮/订单、B标签，并构造Discovery矩阵；报告中文字体依赖Microsoft YaHei。benchmark会再次生成相同编码输入并运行对照；可直接跳到pattern_mining以跳过耗时对照。脚本会覆盖实验输出，重跑前请备份或使用独立checkout。参数集中在pattern_mining.py的CFG；其他分析脚本目前有固定数据量检查和少量显示文字，变更数据/阈值须同步检查，不能声称是任意数据通用工具。

可选从原始Excel重跑A的完整清洗与验证，请按主仓库文档操作；audit_data.py针对本实验processed目录运行审计。prepared快照仅按核心哈希核验，不替代A的全部审计。

## 已执行验证与限制

本地数据验证通过；G/L/R标签唯一、20个随机顾客置换人数匹配、逐篮编码核验、相同订单范围、系统预算、规则唯一性通过；150条部署规则用独立Python集合计数复核；高金额Top50独立复核；原G/L/R文件哈希未变。发布路径调整后再执行语法和规则检查，未为上传重新运行全部64次挖掘。

Validation/Test规则表现尚未评价；阈值未冻结；额外去冗余、实际规则容量匹配、未来区间尚待与D协作。建议先以预算50比较当前政策与统一去冗余政策，再开展小范围计数阈值敏感性。不要通过Test挑参数。

## 工具使用披露

C使用AI辅助编写和运行实验、汇总证据、生成图表及说明。算法调用mlxtend，数据处理和群标签沿用A/B固定快照。组员须复核口径和代码、理解结论并按课程要求披露；不将AI生成解释当作额外实验证据。
