# AIGC 使用记录

2026-10-30：辅助整理仓库结构、任务分工、README、数据接口与实验配置草案。研究代码与结果尚未实现。成员后续应记录具体使用、人工核验和修改，最终报告单设披露。

## 2026-11-06 Online Retail II 数据处理

使用 Codex 协助对照仓库协议，检查 UCI Online Retail II 工作簿结构，识别并验证两张表在 2010-12-01 至 2010-12-09 的完整重叠，起草四时期配置、处理代码、审计输出和自动验证，并执行全量金额、购物篮、时间冲突及重复运行哈希检查。

人工仍需复核非商品编码业务含义，确认 K、支持度、置信度和总规则预算，并检查 B、C、D 是否遵守时期边界和共同评价对象。生成式模型没有推断或修改原始交易值；清洗标记、金额、订单和购物篮均由版本化配置与确定性 Python 代码生成。

## 2026-11-08 README 进度汇报与清洗说明摘要

使用 Claude 根据 `docs/data_processing_guide.md` 与快照分支的审计表（`audit_summary.csv`、`exclusion_summary.csv`、`four_period_retention_summary.csv`、`period_eligibility_summary.csv`）起草 README 中的进度汇报和数据清洗摘要，数字直接取自审计表。同日由 Claude 在 Profile 期 RFM 特征上做过探索性试跑，用于讨论分群方案，其数字不是正式结果，未写入 README。成员需核对摘要表述与 A 的实现一致。

## 2026-11-11 至 11-12 商品品类层级 taxonomy_v0（B）

使用 Claude 协助：检查 C 的商品层规则构成与订单商品构成；查阅并总结 Gholamian et al. (2024) 的 LLM 商品分类方法；编写 `src/online_trade/taxonomy/` 的脚本；根据文本聚类样例起草 `rules_v0.py` 的 53 条关键词规则与类别命名；运行品类层 G/L/R 探索并起草 `docs/taxonomy_v0.md` 与 README 中的修改方案。

所有数字由确定性 Python 代码从固定提交的 A/B 快照与 C 规则证据计算，未读取 Test 期数据。v0 的分类规则和类别命名由 AI 起草，尚无人工金标准；组员需复核规则、类别边界和结论表述。后续 LLM 标注将作为研究方法写入报告方法部分，与此处的写作和编程辅助分开披露。

## 2026-11-12 至 11-13 商品品类层级 taxonomy_v1（B）

**写作与编程辅助（Claude）**：编写 `src/online_trade/taxonomy/` 中 v1 的全部脚本，包括 API 客户端、缓存、冻结、打标签、金标准抽样、标注指南、一致性与评测；起草提示词模板、中文标注指南、类别中文翻译、审阅建议，以及 `docs/taxonomy_v1.md`、`docs/taxonomy_workflow.md`。每条拆分、合并、定义修改和种子纠正都是 Claude 先提出建议，再由 B 逐条决定，决定记录在 `configs/taxonomy/taxonomy_v1_decisions.json`。

**作为研究方法的 LLM（DeepSeek V4 Pro，官方 API）**：① 提出子类拆分方案、重新归类 other、挑选设计系列关键词、起草子类定义；② 给商品打标签（R1–R3）。全部请求和返回保存在 `data/taxonomy/llm_cache/llm_cache.jsonl`，可以不联网复现。输入只有商品文字，没有销量、顾客、分群或时期信息。这部分应写进报告的方法章节。

**人工部分**：金标准由 A、D 独立盲标、C 裁定，三人都看不到任何机器标签；评测数字由确定性 Python 代码计算。未读取 Test 期数据。

## 2026-11-13：仓库架构整理

使用 Codex 辅助将 taxonomy 实现移入 src 包、增加 scripts 统一入口、迁移结果目录、更新路径引用和冻结清单路径，增加只读校验与架构回归测试。此工作不重新运行科学实验，不更改已冻结标签或评测结果。
