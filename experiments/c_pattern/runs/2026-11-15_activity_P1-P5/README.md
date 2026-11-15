# 2026-11-15：A1/A2 活跃度对照与 P1–P5 新结果

这是独立的新实验批次，旧结果位于 `experiments/c_pattern/` 原有目录，保持原样。本批次未使用 Validation/Test。

## D 从这里开始

- [P1–P5 交接说明](category_P1_P5_handoff/D交接说明_P1-P5.md)
- [验证核心包（约15MB）](category_P1_P5_handoff/D_validation_core.zip)：完整预算选中规则及证据、标签/taxonomy、汇总。
- [配置表](category_P1_P5_handoff/configurations.csv)、[G/L规则数](category_P1_P5_handoff/GL_rule_counts.csv)、[覆盖率比较](category_P1_P5_handoff/coverage_comparison.csv)、[校验记录](category_P1_P5_handoff/verification.json)。
- [A1主对照报告](activity_controls_A1/A1独立重跑报告.md)、[A2敏感性报告](activity_controls_A2/A2敏感性分析报告.md)。

## 新旧结果区别

|批次|随机对照|配置|位置|
|---|---|---|---|
|旧结果|S，20种子|原商品层及品类严格+5pp等探索|本目录之外的原有实验目录|
|本批次A1|Profile频次分层，100种子|原商品层；品类严格+5pp|activity_controls_A1/|
|本批次A2|Discovery篮子数分层，100种子|同A1，作为敏感性分析|activity_controls_A2/|
|本批次P1–P5|A1主对照，S参考，A2敏感性|五套参数×总预算20/50/100，限群/共享|category_P1_P5_handoff/|

P3是严格档**不启用增量**，P4是中档+5pp，P5是中档+10pp。此前严格+5pp不属于这五套。

## 完整证据附件

[下载与本批次提交关联的完整结果附件](https://github.com/NGC12-ZJH/aiaa3111-project-online-trade/releases/tag/c-pattern-mining-20261115-p1-p5)。完整证据和缓存约4.6GB，放在Release附件，避免重复写入Git历史；分支保留报告、汇总、全部预算规则和小型核心包。

下载附件中的全部 `full-results-*.zip`，分别解压到同一个空目录（每个都是独立ZIP，不需要拼接）。得到 activity_controls_A1/、activity_controls_A2/、category_P1_P5_handoff/ 三个目录。完整P1–P5目录内含 `eligible_rules/` 和 `evidence/`；`load_rules.py`在完整目录下使用。仅克隆分支不能运行读取完整候选的工具，因为大证据在附件中。附件索引列出每个压缩包的SHA256和文件归属。

分支中的 `file_checksums.csv` 是原始全量本地包的清单，包含仅存于附件的文件，不代表这些文件全部进入Git。历史原始报告保留当时的“未上传”状态描述；本README及Release为上传状态入口。

## 复现及核验

code/保存本批次运行脚本。需要原项目快照中的Discovery baskets/matrix、原S规则证据与taxonomy数据；完整附件补齐A1/A2计数与挖掘缓存。`rerun_activity_A1.py`、`rerun_activity_A2.py`、`export_p1_p5.py`支持 --root；部分汇总脚本保留生成时本地路径，迁移机器时需修改R路径。不要将“合格规则数”当作独立规则去重数，也不要把三个随机组当独立样本。

664个范围、222个系统；6660条系统覆盖率独立复算一致；3320套范围/配置候选清单核对通过；无空组、无预算缺额。A1仍是主对照，不依据Discovery表现更换主对照。
