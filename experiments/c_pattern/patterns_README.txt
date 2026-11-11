正式模式挖掘（Discovery 开发版）

运行：.\.venv\Scripts\python.exe pattern_mining.py
核验：.\.venv\Scripts\python.exe validate_patterns.py

输入沿用已核验的 Discovery 7521 个篮子；真实/随机标签来源及快照提交在 labels/source.json。每个顾客标签固定，所有随机种子均保留。仅本地保存，未上传 GitHub。

配置位于脚本 CFG 和输出 patterns/config.json。当前1%支持度、联合次数>=20、前件次数>=20、confidence>=0.2、lift>=1，前件1–2商品、后件1商品。最多3商品项集。参数未经过Validation选择，不能作为最终最优设置。所有匹配与计数均使用全部篮子，包括单商品篮。

流程：1个全局、3个真实群、20x3个随机群，共64次FP-Growth。合并各范围产生的商品规则为共同候选池（仅来自Discovery），对每个范围重算前件、后件、联合计数及群外指标。先保留挖掘候选池，再施加confidence/lift等合格条件。

native使用该范围自己挖到的候选；common_pool使用完整共同候选池。当前相同的support和联合次数门槛也用于重筛选，因此两个流程可能得到完全相同的合格集；这不是额外收益的证据。

预算为系统总预算20/50/100。局部按Discovery篮子数比例采用最大余数法分配，余数相同按group_id排序；空缺不重新分配。按联合次数、confidence、lift降序，rule_id升序取Top。仅去除完全重复规则，不启用额外冗余处理。实际规则不足时明确报出；本版未进行实际容量匹配的额外比较。

产物：
- scope_audit.csv：每群Discovery样本量，不能用Profile订单数代替。
- rule_evidence.csv.gz：完整共同候选证据、是否本范围产生、是否合格、全局合格排名、群外support/confidence及support差。
- selected_rules.csv：两种候选流程、全部预算、G/L/全部R seeds的可部署规则，交给D进行Validation评价。
- budget_audit.csv：分配名额、实际名额、合格候选数。
- mining_runtime.csv：64次挖掘耗时，不包含共同池证据重算。
- discovery_case_candidates.csv：按Discovery支持度差选出的探索性案例，不代表未来稳定或统计显著。
- case_order_examples.csv：案例可追溯订单（本地保存）。
- manifest.json：输入和代码哈希、配置、检查与耗时。

global_rank为空表示未通过当前全局完整筛选条件，不可直接说全局算法无法发现。native的generated_here才表示是否达到该范围项集挖掘门槛。规则名额计入群体条件；同商品规则在不同群占不同名额。缺少前件或后件时confidence/lift为空，不能估计时不填零。

范围：这是C的Discovery交付。尚需与D在Validation比较固定候选的覆盖和差异，选择配置并冻结，再评价Test。没有读取Validation/Test性能。商品描述和正式海报案例仍需人工核对；群差异也可能与订单规模、热门后件及多重筛选有关。
