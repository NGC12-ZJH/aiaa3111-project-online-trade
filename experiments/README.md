# D 分支补充实验

这些目录保存主评价之后的补充分析、复算脚本和已核验结果。各实验节标出 Discovery、Validation 或历史 Test 补测。正式冻结 Test 的结果见 [D 评价入口](../docs/evaluation/README.md)。

| 顺序 | 实验 | 输出 |
| --- | --- | --- |
| 1 | [Discovery 残差补位](discovery_residual_refill/README.md) | 去重补满后，G、L 和随机规则池的覆盖、补位与方向规则清单 |
| 2 | [Validation 四类指标](validation_four_metrics/README.md) | P1–P5、三档预算、触发准确率、遮挡推荐、跨期、加权覆盖和多样性 |
| 3 | [Validation 热门补齐与局部残差重排](validation_hybrid_residual/README.md) | 给满 Top‑5，分真实群拆分，再用同一批 G 漏单比较 L 和 A1 |
| 4 | [Validation G 后续规则对照](validation_global_tail/README.md) | 同一批漏单上对照 G 后续 B 条与局部 B 条，列出共同及独有补回 |

| 5 | [Validation 密集预算与 P5／90 Test 补测](validation_budget_redesign/README.md) | 每 10 条的边际覆盖、跨群去重、质量门槛敏感性、独立冻结及 Test 复算 |

复算前依照 [D 复现说明](../docs/evaluation/reproduce.md) 准备冻结输入。然后在仓库根目录按表中顺序运行前 3 项的 run.py 和第 4 项的 compare.py。第 3、4 项读取前项结果。第 5 项在自己的目录列出复算命令。顾客标签和交易明细通过既有准备脚本取得，本目录提交的是规则编号、聚合表、报告和代码。

## 1122 独立实验

[1122 实验入口](1122/README.md)汇总重做项目的全部方案、结果及复算步骤。

## 1123 分群与推荐补测

[1123 实验入口](1123/INDEX.md)汇总三种分群的共同预算结果、冻结记录，以及推荐收益的三项历史 Test 补测。

[全部指标和分母](../docs/evaluation/metrics_index.md)
