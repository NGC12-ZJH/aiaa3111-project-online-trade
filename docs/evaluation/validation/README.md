# Validation

[返回 D 分支交付](../README.md) · [正式 Test](../test/README.md) · [复现命令](../reproduce.md)

## 比较与选参

同一批 4,862 张合格订单、1,458 名历史顾客用于比较 P1–P5 和 20／50／100 条系统总预算。G 是全局规则，L 是真实分群规则，A1 是按历史购买频次匹配的随机分组。每张订单只计算一次完整共购覆盖。

**正式主设置选 P5／100、限群使用、A1 为主随机对照。** 在本次比较范围内，P5／100 的 G 和 L 原始订单覆盖率和共同质量验收后的覆盖率均为观察值最高。预算 20、50 保留为正式预算曲线。冻结提交 `0bb4815` 固定了排名、各群配额、输入与评价口径。

| P5／100，限群使用 | G | L | A1 中位数 |
|---|---:|---:|---:|
| 原始覆盖 | 74.87% | 62.88% | 61.94% |
| 可靠关联覆盖 | 74.85% | 62.77% | 61.61% |

## 三项补充分析

- **共同验收。** 在初次 Validation 之后引入统一标准，检查订单和顾客证据量、相对后件基础率的提升、lift、两前件规则的增量和统计不确定性。P5／100 的 G 和 L 分别有 99% 和 97% 的规则名额通过。同一期买篮用于规则验收与覆盖统计，因此可靠覆盖是回顾性指标。见 [共同质量验收与统计方法](methods.md)。
- **规则互补。** 合并 G50 与分群总预算 50 的规则，按方向去重后与同数量的全局规则比较。P3 合并后的 60 条规则比 G60 净多覆盖 121 单（+2.49 个百分点）。P5 合并后的 58 条规则比 G58 少覆盖 72 单（−1.48 个百分点）。此实验缺少随机合并对照。
- **群体差异。** P5／100 有 22 条不同方向的分群规则未进 G 前 100。Discovery 的 19 个群体优势候选中，15 个到 Validation 仍保持正方向。本次验证的真实分群规则中，达到预先列明的群体优势全部条件并通过 BY 校正的数量为零。名单差异、效应方向和校正后的证据分别报告。

## 完整表格与备查

| 分析 | 完整报告 | 结果文件 |
|---|---|---|
| 原覆盖、预算曲线和配对区间 | [原覆盖报告](details/validation_results.md) · [离线图表](details/validation_results.html) | [原覆盖表](../../../results/tables/validation/) |
| 共同质量、通过率和敏感性 | [质量结果](details/validation_quality_results.md) · [离线图表](details/validation_quality_results.html) | [质量结果表](../../../results/tables/validation_quality/) |
| G50＋L50 与同数量全局规则 | [合并规则报告](details/validation_hybrid_results.md) | [合并结果表](../../../results/tables/validation_hybrid/) |
| 群内／群外差异、优势保持和随机对照 | [群体差异报告](details/validation_specificity_results.md) · [离线图表](details/validation_specificity_results.html) | [差异结果表](../../../results/tables/validation_specificity/) |

下载 HTML 后可以在浏览器离线查看。使用 GitHub 网页阅读时，建议打开 Markdown 报告。

计算协议分别见 [原覆盖](../../../configs/validation.json)、[共同质量](../../../configs/validation_quality.json)、[合并规则](../../../configs/validation_hybrid.json) 与 [群体差异](../../../configs/validation_specificity.json)。阶段日期、验证与参数冻结记录见 [实验日志](../../experiment_log.md)。
