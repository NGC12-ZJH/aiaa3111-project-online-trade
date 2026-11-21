# D 评价模块

组员阅读入口见 [D 分支交付](../../../docs/evaluation/README.md)，运行命令集中在 [复现说明](../../../docs/evaluation/reproduce.md)。

- `validation.py` 计算覆盖、随机对照与顾客配对区间。
- `quality.py` 计算共同验收与回顾性可靠覆盖。
- `hybrid.py` 负责合并规则和匹配预算。
- `specificity.py` 衡量名单重合、群内外差异与优势保持。
- `scripts/run_frozen_test.py` 校验冻结输入并执行正式 Test。
