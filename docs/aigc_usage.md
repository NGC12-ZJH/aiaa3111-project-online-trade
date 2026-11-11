# AIGC 使用记录

2026-10-30：辅助整理仓库结构、任务分工、README、数据接口与实验配置草案。研究代码与结果尚未实现。成员后续应记录具体使用、人工核验和修改，最终报告单设披露。

## 2026-11-06 Online Retail II 数据处理

使用 Codex 协助对照仓库协议，检查 UCI Online Retail II 工作簿结构，识别并验证两张表在 2010-12-01 至 2010-12-09 的完整重叠，起草四时期配置、处理代码、审计输出和自动验证，并执行全量金额、购物篮、时间冲突及重复运行哈希检查。

人工仍需复核非商品编码业务含义，确认 K、支持度、置信度和总规则预算，并检查 B、C、D 是否遵守时期边界和共同评价对象。生成式模型没有推断或修改原始交易值；清洗标记、金额、订单和购物篮均由版本化配置与确定性 Python 代码生成。

## 2026-11-08 README 进度汇报与清洗说明摘要

使用 Claude 根据 `docs/data_processing_guide.md` 与快照分支的审计表（`audit_summary.csv`、`exclusion_summary.csv`、`four_period_retention_summary.csv`、`period_eligibility_summary.csv`）起草 README 中的进度汇报和数据清洗摘要，数字直接取自审计表。同日由 Claude 在 Profile 期 RFM 特征上做过探索性试跑，用于讨论分群方案，其数字不是正式结果，未写入 README。成员需核对摘要表述与 A 的实现一致。

## 2026-11-11 至 11-12 商品品类层级 taxonomy_v0（B）

使用 Claude 协助：检查 C 的商品层规则构成与订单商品构成；查阅并总结 Gholamian et al. (2024) 的 LLM 商品分类方法；编写 `experiments/b_taxonomy/` 的脚本；根据文本聚类样例起草 `rules_v0.py` 的 53 条关键词规则与类别命名；运行品类层 G/L/R 探索并起草 `docs/taxonomy_v0.md` 与 README 中的修改方案。

所有数字由确定性 Python 代码从固定提交的 A/B 快照与 C 规则证据计算，未读取 Test 期数据。v0 的分类规则和类别命名由 AI 起草，尚无人工金标准；组员需复核规则、类别边界和结论表述。后续 LLM 标注将作为研究方法写入报告方法部分，与此处的写作和编程辅助分开披露。
