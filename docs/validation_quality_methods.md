# Validation统一质量：方法与字段

本说明补充一页方案，不更改其中阈值。所有标准在新质量补算前写入 `configs/validation_quality.json`，方案哈希写入结果manifest。原Validation结果已被看过，因此仍是探索性扩展。

## 一、计数与效应

在当前评价范围中记订单总量N、前件次数A、后件次数C、联合次数J：

- confidence = J/A；后件基础率 = C/N；lift = (J/A)/(C/N)。
- confidence_uplift = J/A − C/N。该差值消除了只看高置信度时对热门后件的误读，但不是因果效应。
- 三品类AB→C分别与A→C、B→C比较，取较小置信度差，乘100记为百分点。两个单前件不需要通过任何配置筛选。

按顾客i汇总Ji、Ai、Ci、Ni。对于两个比率之差 d=X/D−Y/E，顾客影响值为 `u_i=(X_i−(X/D)D_i)/D − (Y_i−(Y/E)E_i)/E`；近似方差为 `m/(m−1)×Σu_i²`，m为评价范围内有订单的顾客数。按顾客聚类可以保留同人订单相关性，不假设每张订单独立。

整体关联使用(X,D,Y,E)=(J,A,C,N)。三品类增量分别用(联合AB,C的次数, AB次数, 联合A,C次数, A次数)和对应B计数。单侧零假设为差值≤0，以t(m−1)近似计算p；逐项95%区间为 `d ± t(0.975,m−1)SE`。若无分母、顾客不足2或标准误退化，则不把该规则视为有可靠统计证据（p=1，区间留空）。这不是精确检验，低计数情形须谨慎。

## 二、多重比较

二品类只有整体关联检验；三品类要求整体关联和两个增量都为正，对三个单侧p取最大值，作为“都成立”的intersection-union检验。主标准还另外要求点估计uplift≥5pp、lift≥1.2，三品类增量≥5pp。p值检验正方向，不检验效应是否以95%置信超过这几个幅度门槛。

每个系统(control,method,seed)为一个家族：联合五配置/三预算的所有原群范围及共享全局范围身份，按(评价范围,rule_id)去重。P1/P2重复选中或多个预算重复选中不重复检验。原全局G范围与共享GLOBAL为同一身份。

对m个排序p值，BY调整为 `min_{j≥i}(p_(j)×m×H_m/j)` 并截断到1，其中 `H_m=Σ1/k`。BH省去H_m，只作敏感性比较。BY处理依赖检验的依据见 [Statsmodels官方多重比较文档](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html) 和 [官方实现](https://www.statsmodels.org/stable/_modules/statsmodels/stats/multitest.html)。顾客聚类sandwich与有限样本修正的通用说明见 [官方聚类协方差文档](https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_cluster.html)；本项目的比率差影响函数按上述公式直接实现，并非调用回归API。

q≤0.05不是“该规则有95%概率为真”。本项目的p是近似值，校正只在每个系统内，不控制全部系统、配置选择和叙事选择的全局错误率。随机系统上尾比例只作描述。不得宣传为确认性显著结论。

## 三、输出列

`GL_quality_summary.csv`、`system_quality.csv`、`GL_sensitivity.csv`共享主要列：

| 列 | 含义 |
|---|---|
| setting | 主标准primary或敏感性定义名称 |
| config / budget / control / method / seed / flow | 原配置、系统预算、对照、方法、种子与限群/共享 |
| n_baskets / n_customers | 固定主比较订单与顾客数 |
| actual_rule_slots | 原部署名额，重复来源不返还 |
| unique_evaluation_rules | 去重(评价范围,方向规则)数量；限群同规则在不同群是不同身份 |
| accepted_rule_slots / accepted_unique_rules | 通过验收的名额数/去重验收身份数 |
| accepted_slot_share / accepted_unique_rule_share | 对应保持比例，分母包含未触发和证据不足规则 |
| evaluable_slot_share | 通过共同证据量/顾客集中度检查的名额比例；不代表质量合格 |
| raw_covered_orders / raw_coverage | 原清单完整共现覆盖，与旧结果逐项一致 |
| quality_covered_orders / quality_coverage | 只由通过验收规则贡献的订单并集及比例，回顾性指标 |
| quality_customer_macro_coverage | 逐顾客质量覆盖率的等权平均 |
| max_customer_joint_share_mean | 所选名额中，单个最大顾客贡献占比的平均，忽略无联合订单值 |
| confidence_change_pp_median | 名额对应Validation−Discovery置信度差的中位数，百分点 |
| not_triggered | 前件为0的名额数 |
| insufficient_evidence | 计数/不同顾客数不足，或过于依赖单名顾客 |
| effect_below_minimum | 证据量够但lift/uplift点估计未达共同幅度 |
| increment_below_minimum | 三品类点估计增量未达共同幅度 |
| uncertainty_unresolved | 前述门槛通过，但校正后的统计证据不足 |
| accepted | 全部共同标准通过的名额数 |

状态按上述顺序互斥，合计为actual_rule_slots；未通过不等于被证明无效。状态优先级仅用于汇总，详细证据仍完整保留。

`GL_rule_quality.csv`为G/L的系统内逐验收身份证据，额外包含原/共享范围、前后件、订单计数、不同顾客数、最大顾客贡献、置信度、基础率、lift、uplift、逐项区间、三品类增量区间、关联/增量/联合p值、q_BY/q_BH及family_hypotheses。`confidence_ratio`为未来/发现期置信度；`lift_ratio`为未来/发现期lift，仅描述，不提供跨时期独立性假设下的伪区间。

`random_quality_comparisons.csv`与旧随机表结构对应，metric改为quality_coverage、accepted_slot_share、quality_customer_macro_coverage；descriptive_upper_tail明确只作描述。`family_audit.csv`列出每系统实际校正假设数量。全部明细与输入输出哈希见manifest。
