# Validation 方法与字段

[返回 Validation 总览](README.md)

## 共同质量验收方案

**版本：quality_v1 · 2026-11-18。** 已看过原Validation结果后新增的探索性评价；先记录本方案，再补算质量指标。本次只比较，不推荐/冻结参数，不评价Test。P1–P5使用同一标准，冻结规则、顾客标签、taxonomy、原预算与排名不变，不补选规则。

**要回答的问题：** 规则在未来是否仍有足够证据、提供超出商品热门程度的关联，并能覆盖一定数量的订单？覆盖不等于推荐准确率、因果增销或商业收益。

| 验收环节 | 对所有P1–P5统一执行的主标准 |
|---|---|
| 评价对象 | Validation `[2010-12-01,2011-06-01)` 的4,862张合格订单、1,458名历史顾客；保留空篮和单品类篮。预算20/50/100分开比较。 |
| 证据量 | 前件至少20单且来自10名顾客；联合至少10单且来自5名顾客；任何一名顾客贡献的联合订单不超过50%。不足记“证据不足”，不等于关联失效。 |
| 有实际幅度的关联 | 未来lift≥1.2，且 `confidence−后件基础出现率≥5个百分点`。后件基础率在同一评价范围内计算。 |
| 不只是偶然 | 对上述关联提升做单侧检验；按顾客聚类计算近似标准误，同一顾客的订单不当作独立样本。主验收使用BY多重比较校正值≤0.05。 |
| 三品类的额外价值 | AB→C的confidence比A→C和B→C都至少高5个百分点；对两个增量与整体关联的检验取最大p值，再共同校正。二品类无此项。 |
| 规则使用范围 | 限群：在原群内验收并仅服务该群。共享：在全部主比较订单上重新验收、去重后匹配；不沿用群内质量判定。 |
| 共同分母 | 保持率分母为原部署规则名额，包含未触发与证据不足规则；同时给出去重比例。可靠关联覆盖的分母为全部4,862单。 |

**输出与解读：** ①证据充分比例；②可靠关联保持率；③可靠关联订单覆盖/顾客等权覆盖；④未触发、证据不足、幅度不足、增量不足、统计证据不足的数量；⑤未来相对Discovery的置信度变化与lift变化。重复规则名额不返还，任何规则只给订单覆盖贡献一次。

**校正范围与边界：** 每个系统（G、L或某随机种子）把五配置/三预算的候选验收身份合并去重，原范围与共享范围一起构成一个校正家族。BY允许检验间依赖；所用顾客聚类t近似仍有有限样本局限，且不保证跨全部系统比较的总体错误率。区间为逐项95%区间，不是同时区间。BH只作探索性敏感性输出。公式和来源见补充方法说明。

**阈值不是自然定律。** 20/10计数、5个百分点、lift1.2与50%集中度是本次工作性定义；统一报告预写定的宽/严门槛敏感性，不依据结果换主标准。原Validation输出不覆盖。质量覆盖是用同一期质量判定后的回顾性指标，不是可事先部署的预测覆盖；不得据此删除/补齐冻结清单。后续Test须另行固定验收与选择流程。

## 质量统计方法与字段

本说明补充一页方案，不更改其中阈值。所有标准在新质量补算前写入 `configs/validation_quality.json`，方案哈希写入结果manifest。原Validation结果已被看过，因此仍是探索性扩展。

### 一、计数与效应

在当前评价范围中记订单总量N、前件次数A、后件次数C、联合次数J：

- confidence = J/A；后件基础率 = C/N；lift = (J/A)/(C/N)。
- confidence_uplift = J/A − C/N。该差值消除了只看高置信度时对热门后件的误读，但不是因果效应。
- 三品类AB→C分别与A→C、B→C比较，取较小置信度差，乘100记为百分点。两个单前件不需要通过任何配置筛选。

按顾客i汇总Ji、Ai、Ci、Ni。对于两个比率之差 d=X/D−Y/E，顾客影响值为 `u_i=(X_i−(X/D)D_i)/D − (Y_i−(Y/E)E_i)/E`；近似方差为 `m/(m−1)×Σu_i²`，m为评价范围内有订单的顾客数。按顾客聚类可以保留同人订单相关性，不假设每张订单独立。

整体关联使用(X,D,Y,E)=(J,A,C,N)。三品类增量分别用(联合AB,C的次数, AB次数, 联合A,C次数, A次数)和对应B计数。单侧零假设为差值≤0，以t(m−1)近似计算p；逐项95%区间为 `d ± t(0.975,m−1)SE`。若无分母、顾客不足2或标准误退化，则不把该规则视为有可靠统计证据（p=1，区间留空）。这不是精确检验，低计数情形须谨慎。

### 二、多重比较

二品类只有整体关联检验；三品类要求整体关联和两个增量都为正，对三个单侧p取最大值，作为“都成立”的intersection-union检验。主标准还另外要求点估计uplift≥5pp、lift≥1.2，三品类增量≥5pp。p值检验正方向，不检验效应是否以95%置信超过这几个幅度门槛。

每个系统(control,method,seed)为一个家族：联合五配置/三预算的所有原群范围及共享全局范围身份，按(评价范围,rule_id)去重。P1/P2重复选中或多个预算重复选中不重复检验。原全局G范围与共享GLOBAL为同一身份。

对m个排序p值，BY调整为 `min_{j≥i}(p_(j)×m×H_m/j)` 并截断到1，其中 `H_m=Σ1/k`。BH省去H_m，只作敏感性比较。BY处理依赖检验的依据见 [Statsmodels官方多重比较文档](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html) 和 [官方实现](https://www.statsmodels.org/stable/_modules/statsmodels/stats/multitest.html)。顾客聚类sandwich与有限样本修正的通用说明见 [官方聚类协方差文档](https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_cluster.html)；本项目的比率差影响函数按上述公式直接实现，并非调用回归API。

q≤0.05不是“该规则有95%概率为真”。本项目的p是近似值，校正只在每个系统内，不控制全部系统、配置选择和叙事选择的全局错误率。随机系统上尾比例只作描述。不得宣传为确认性显著结论。

### 三、输出列

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

## 群体差异与优势保持方案

2026-11-19 · 在已有Validation之后新增的探索性分析。只使用冻结规则和Discovery/Validation；不重新挖掘、不选参、不运行Test。本方案在新指标计算前保存。

### 要回答的四件事

1. **规则名单不同吗？** 对同系统预算的L与G计算方向规则/无方向组合Jaccard、新增比例；保留真实去重数量。另记录“不在G Top100”，不把Top榜缺席称为Global从未发现。
2. **同一条规则在目标群更强吗？** 每条选中规则都放回目标群、其余两群合并、各其他群及Global计算。主差异为confidence目标−群外；另比较“confidence−后件基础率”的差异，排除只由后件热门程度差异解释的信号。lift比值只作诊断。
3. **群体优势保持吗？** 先用Discovery点估计定义候选，再在Validation看方向和证据。不能只用Validation挑出的优势规则作为存活率分母。
4. **不同有补充价值吗？** 区分前件独有触达、完整共现独有覆盖、双方独有订单与净差；同预算G/L比较及已有G50+L50去重匹配K实验分开解读。

### 固定主标准

- 目标群通过已有quality_v1的共同证据量、顾客集中度、lift≥1.2、基础率提升≥5pp、三品类增量≥5pp点估计标准。
- 群外前件至少20单、10名顾客；目标群相对群外confidence至少高5pp，且相对基础率的关联提升更高。
- Discovery符合以上点估计/证据标准即为“优势候选”，不把Discovery p值当独立发现证据。
- Validation额外要求新群间比较联合检验的系统内BY q≤0.05。质量原q不能复用于新问题。严格特异性另外要求比两个其他群都强，并且各群前件证据足够。
- 统计以顾客为独立单元，用比率差影响函数近似；目标群与群外互斥顾客，方差相加，t自由度取两边顾客数较小值减1。小样本和退化SE保守记证据未解决。
- 每个真实/随机系统合并五配置、三预算的去重(群,规则)身份，把one-vs-rest与严格两种假设一起BY校正；BH仅作敏感性。不是整个研究所有系统的总体校正。

### 输出与边界

输出名单差异、Discovery与Validation群间效应/区间、方向保持、效应保留比例、具有统计证据的优势保持比例、分群相对S/A1/A2，以及独有/净覆盖。前件0、样本不足、方向反转和统计证据不足分开。效应保留比仅对Discovery差值≥5pp计算。

置信度差可能反映热门程度，因此同时看关联提升差；这仍是观察性共购差异，不是因果偏好或推荐效果。未通过不等于证明无差异。群之间更强也不要求Global Top榜中没有此规则；名单缺席和群体优势是两条不同轴。
