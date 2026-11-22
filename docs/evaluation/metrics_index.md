# D 部分已测指标总览

本页对应 D 分支的品类规则评估。指标按用途归并，同一指标在不同阶段或不同匹配口径下重复计算时只解释一次。表中的「扩展」是本地实验。原冻结 Test 使用 P5，主预算 100，补充报告 20／50／100，限群为主、共享为辅。Validation 比较 P1–P5 和三个预算。

| 数据口径 | 主分母或比较单位 |
| --- | --- |
| Discovery 补满 | 7,521 张合格订单。残差补位率以各配置和预算的 G 漏单数为分母。 |
| Validation 共购 | 4,862 张合格订单、1,458 名顾客。限群限定本群规则，共享允许所有主样本订单匹配所有共享规则。 |
| Validation 遮挡推荐 | 4,311 张含至少两个品类的合格订单。每单遮住一个品类。 |
| 正式 Test | 5,730 张主比较订单、1,510 名顾客。另有 5,160 张非 Profile 订单单独报告全局回退。 |

## 1. 共购覆盖和使用范围

| 指标 | 含义 | 已测阶段 |
| --- | --- | --- |
| 原订单覆盖率 | 分子是满足至少一条规则的完整前件和后件的订单数。同单只计一次。分母是该口径全部订单。 | Validation、Test、Discovery 回放及补满 |
| 前件覆盖率 | 至少触发一条可用规则的订单数 ÷ 全部评价订单。满足前件即可，后件可以缺失。 | Validation、Test、Discovery 回放 |
| 顾客等权覆盖 | 先算每位顾客的订单覆盖率，再对顾客等权平均。可靠规则也有对应的顾客等权版本。 | Validation、Test |
| 顾客有命中比例 | 至少有一张订单被覆盖的顾客数 ÷ 评价顾客数。 | Validation、Test |
| L−G 覆盖差和预算曲线 | 在同批订单上比较订单覆盖差与顾客等权覆盖差，以百分点表示。分别报告 20／50／100。 | Validation、Test |
| 非 Profile 全局回退 | 在另列的非 Profile 订单上应用 G，报告订单数、命中数和覆盖率。 | Validation、Test |

来源：[Validation 系统表](../../results/tables/validation/system_metrics.csv) · [Validation 回退](../../results/tables/validation/non_profile_global_fallback.csv) · [Test 系统表](../../results/tables/test/system_metrics.csv) · [Test 回退](../../results/tables/test/non_profile_global_fallback.csv)

## 2. 规则质量和跨期稳定性

| 指标 | 含义 | 已测阶段 |
| --- | --- | --- |
| 联合计数、前件计数、后件计数 | 分别计同时满足前后件、满足前件、满足后件的订单数。证据量还记录前件、联合分别来自多少顾客，及单一顾客贡献的最大占比。 | Discovery、Validation、Test |
| Support、Confidence、后件基础率、Lift | Support＝联合数÷订单数。Confidence＝联合数÷前件数。后件基础率＝后件数÷订单数。Lift＝Confidence÷后件基础率。 | Discovery、Validation、Test |
| Added Value／Confidence uplift | 置信度减去同一评价范围的后件基础率。与 Lift 分别描述绝对百分点和相对倍数。 | Validation、Test；Validation 扩展另汇总中位数、四分位和可估条数 |
| 三品类增量 | AB→C 的置信度减去 A→C、B→C 中较高的置信度，考察联合前件额外带来的关联。 | Validation、Test |
| 原门槛保持率 | Discovery 选中的规则在未来仍符合各自配置门槛的比例。另列前件未触发、触发但零共现、低于阈值等状态。 | Validation、Test |
| 共同质量通过率 | 通过统一 quality_v1 的名额占全部名额的比例。另报去重验收身份的通过率、可评比例、通过数量及不通过原因。 | Validation、Test；Validation 有宽严等敏感性分析 |
| 可靠订单覆盖和顾客等权覆盖 | 只把当期通过 quality_v1 的规则计入覆盖。订单版本的分母仍是全部主比较订单；顾客版本先按人计算再等权平均。属于当期共购保持。 | Validation、Test |
| 跨期 confidence 差与比例、Lift 比例 | 未来期减 Discovery 的置信度差以百分点计。另记录未来期相对 Discovery 的 confidence 比与 Lift 比。 | Validation、Test；Validation 扩展另汇总分布 |
| 规则效应的区间与检验 | 关联提升、三品类增量等有逐项 95% 区间、单侧检验及多重比较校正。BY 用于主验收，BH 用于敏感性或诊断。 | Validation、Test（按各自校正家族） |

来源：[共同质量方法](validation/methods.md) · [Validation 逐规则表](../../results/tables/validation_quality/GL_rule_quality.csv) · [Validation 敏感性](../../results/tables/validation_quality/GL_sensitivity.csv) · [Test 质量表](../../results/tables/test/system_quality.csv) · [Test 逐规则表](../../results/tables/test/GL_rule_quality.csv)

## 3. 分群特色和规则库构成

| 指标 | 含义 | 已测阶段 |
| --- | --- | --- |
| 规则名额、不同方向规则数、不同品类组合数 | 分别对应原分配的名额、按有方向 rule_id 去重后的条数、忽略方向的品类组合数。另报每名顾客平均／最小／最大可用名额。 | Validation、Test；Discovery 补满另报补选前后 |
| 名单重叠、新增及 Jaccard | 记录 G/L 交集、并集、L 独有条数和占比、L 中不在 G100 的条数。Jaccard 为交集÷并集，方向规则和无方向组合分别算。 | Validation 群体差异 |
| 群内外置信度差、关联提升差、Lift 比 | 同一规则在目标群与合并群外、各个其他群或全局分别计算。关联提升差先分别减各自后件基础率，再比较。 | Discovery→Validation 群体差异；Validation 四类扩展 |
| 群体优势方向保持与有证据保持 | 对 Discovery 优势候选，分别看未来仍保持正向的数量和比例、仍通过共同幅度及统计要求的数量和比例、效应保留比。另列严格优势和新增规则中的保持情况。 | Validation 群体差异 |
| 后件多样性 | 不同后件品类数、实际有触发的后件种数、实际进入 Top‑5 的后件种数。 | Validation 四类扩展 |

来源：[名单差异](../../results/tables/validation_specificity/GL_rule_set_difference.csv) · [群体优势汇总](../../results/tables/validation_specificity/GL_advantage_summary.csv) · [群内外逐规则证据](../../results/tables/validation_specificity/GL_rule_strength.csv) · [四类扩展](../../experiments/validation_four_metrics/p1_p5_global_local.csv)

## 4. 互补、混合和残差

| 指标 | 含义 | 已测阶段 |
| --- | --- | --- |
| L 独有、G 独有、共同命中、并集命中 | 用两套系统命中订单的集合比较。另报 L 独有前件触发、净覆盖差和并集实际规则数。 | Discovery 回放、Validation 群体差异 |
| G50＋L50 合并与同预算 G_K | 合并按方向去重得到 K 条，共享使用，并和 G 前 K 条在同一批订单比较。报告新增／丢失／净订单数、普通和顾客等权覆盖、配对区间及共同质量复核。 | Validation 五配置；Test 只另报探索性 P3 |
| Discovery 去重补满前后 | 先保留各群初选的不同方向规则，再补满 B。记录初选不同规则数、补选数、最终不同组合数、补满前后共享覆盖和补位。 | Discovery 补满扩展 |
| Discovery 残差补位率 | L 在原 G_B 未覆盖的订单中捞回的单数 ÷ G_B 漏单数。另报追加到 G 后的覆盖和并集规则数，以及替换 G 时会丢失的覆盖。 | Discovery 补满扩展 |
| Validation 共现残差补位率 | 剔除 G 已选方向规则、用 Discovery Added Value 或群内外置信度差重排后，在原 G_B 完整共现漏单上计算补回数量和比例。 | Validation 热门补齐与残差扩展 |
| Validation Top‑5 残差补位率 | 分母是 G＋全站热门仍未猜中的遮挡订单。分子是残差规则尝试最多五项时能猜中的订单。另报漏单中能给出推荐的订单数，表示独立补位潜力。 | Validation 热门补齐与残差扩展 |
| G 后续规则对照 | 用 G 原排名 B+1 至 2B 的规则，在同一批 Validation 漏单上与 L 对照，列出共同补回、G 独有、L 独有和差值。 | Validation G 后续规则扩展 |

来源：[G/L 覆盖拆分](../../results/tables/validation_specificity/GL_complementarity.csv) · [Validation 合并对照](../../results/tables/validation_hybrid/paired_comparisons.csv) · [Test P3 合并](../../results/tables/test/P3_hybrid_exploratory.csv) · [Discovery 补满表](../../experiments/discovery_residual_refill/comparison.csv) · [Validation 残差表](../../experiments/validation_hybrid_residual/residual_systems.csv) · [G 后续规则与 L 的配对结果](../../experiments/validation_global_tail/paired_rescues.csv)

## 5. 触发准确率、购物篮推荐和加权覆盖

| 指标 | 含义 | 已测阶段 |
| --- | --- | --- |
| 触发后至少命中一条 | 至少完整命中一条规则的订单数 ÷ 至少触发一条规则的订单数。同单猜中多个或猜错多个都仍以订单为单位。 | Validation 四类扩展；可由正式 Validation、Test 系统计数复算 |
| 去重触发准确率 | 按「订单×后件」计数。同单同后件去重，猜中的对数÷触发的对数。 | Validation 四类扩展 |
| Hit@1／3／5，固定槽位 Precision@5 | Hit@K 是被遮挡品类排进前 K 的订单占全部遮挡订单比例。单目标时等于 Recall@K。固定槽位 Precision@5 分母为 5×遮挡订单数。 | Validation 四类扩展；热门补齐另报 Hit@1／5 |
| 实际推荐 Precision@5、NDCG@5 | 前者以实际发出的推荐项数为分母，后者按正确品类所在排名打折后对订单平均。 | Validation 四类扩展；热门补齐另报 NDCG@5 |
| 推荐覆盖与推荐数量 | 至少给出一项的订单比例、实际推荐项数、给满五项的订单数等。 | Validation 四类扩展、热门补齐扩展 |
| 热门补齐相对纯热门和只用规则的变化 | 比较规则优先＋热门补齐，与同范围纯热门及只用规则的 Hit@5 差。另报相对 G 的新命中、丢失命中，以及 C0/C1/C2 的拆分。 | Validation 热门补齐扩展 |
| IDF 加权覆盖 | 按 Discovery 后件流行度给冷门品类更高权重。同单用命中后件的最高权重，分母为各单可见品类最高权重之和。 | Validation 四类扩展 |
| 金额加权覆盖 | 命中订单的整单毛购买金额之和÷全部合格订单的毛购买金额。每单一次。 | Validation 四类扩展 |

来源：[四类扩展完整表](../../experiments/validation_four_metrics/p1_p5_global_local.csv) · [原热门基线](../../experiments/validation_four_metrics/popularity_baseline.csv) · [补满 Top‑5 及逐群拆分](../../experiments/validation_hybrid_residual/hybrid_global_local.csv)

## 6. 对照和不确定性

- **顾客配对 95% 区间**。按顾客为单位重复抽样，同一轮的 G/L 使用同一批抽到的顾客，用来估计覆盖及 L−G 的波动。合并对照另有配对区间。[Validation 区间](../../results/tables/validation/paired_customer_bootstrap.csv) · [Test 区间](../../results/tables/test/paired_customer_intervals.csv)
- **随机对照分布**。一个种子对应一整套随机系统。记录种子数、中位数、最小／最大值、达到或超过 L 的次数，部分表另列描述性上尾比例。A1 是主活跃度对照，正式表及 Discovery 补满另有 S、A2；两项近期 Validation 扩展使用 A1。[Validation 随机表](../../results/tables/validation/random_comparisons.csv) · [Test 随机表](../../results/tables/test/random_comparisons.csv) · [推荐 A1](../../experiments/validation_hybrid_residual/hybrid_a1_comparison.csv) · [残差 A1](../../experiments/validation_hybrid_residual/residual_a1_comparison.csv)

## Final Report 怎么用

1. **正式结果**放 P5／100 的普通覆盖、顾客等权覆盖、可靠覆盖、质量通过率、L−G 配对区间和 A1 对照。20／50／100 放预算曲线。[正式 Test](test/README.md)
2. **分群找到了什么不同**用 Jaccard、群内外关联差、优势保持和独有命中解释。需要讨论合并价值时，分别给出同预算 G_K 对照和固定 G 的残差补位。
3. **推荐场景**单列 Validation 探索。报告匹配热门基线后的 Hit@5、C0/C1/C2 与 A1，再报告重排后的 G 漏单补回。金额、IDF 和后件多样性可以做补充表。
4. 读表时区分三个分母：全部评价订单、至少触发规则的订单或订单×后件对、G 漏掉的订单。覆盖、推荐命中和残差补位分别描述共购、遮挡补全、候选互补。
