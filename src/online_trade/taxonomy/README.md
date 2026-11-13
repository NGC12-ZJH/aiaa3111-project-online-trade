# 商品分类模块（B）

按主仓库的 `src → scripts → configs/data → results/docs` 分层组织。
实现包括 v0 探索基线与已冻结的 v1；商品分类不参与顾客 RFM 分群。

## 入口

在仓库根目录运行，使用安装了 `requirements-taxonomy.txt` 的 Python 环境：

```bash
python scripts/run_taxonomy.py --help
python scripts/run_taxonomy.py validate
python scripts/run_taxonomy.py run_v0
python scripts/run_taxonomy.py llm_tag --run R2 --offline
python scripts/run_taxonomy.py compare_runs R1 R2 R3
```

`validate` 仅用标准库，检查结构与最终冻结的哈希、编码唯一性、类别层级和版本。
其他命令复用原工作流，可能重写输出；`run_v0` 包含输入提取与完整 v0 探索。
需要交易快照和本地向量缓存的步骤，先按 [v0 复现说明](../../../../docs/taxonomy_v0.md) 准备输入。
`llm_tag --offline` 仅使用已缓存响应，缺失缓存时按原脚本行为停止，不会请求 API。
不要直接以文件路径运行包内模块；用统一入口传递步骤名和原参数。
`scripts/run_all.py` 仍是 A 的数据处理入口，分类步骤由这里单独运行。

## 模块职责

| 模块 | 职责 |
|---|---|
| `paths.py`、`taxonomy_io.py` | 根目录、固定输入版本、共享读取 |
| `prepare_inputs.py`、`run_v0.py` | 输入提取与 v0 流程编排 |
| `explore_*`、`step1_*` 至 `step4_*`、`rules_v0.py` | v0 分类及商品/品类关联探索 |
| `v1_step*`、`v1_review_sheet.py` | 类别提案、人工决定与结构生成 |
| `llm_client.py`、`llm_tag.py`、`compare_runs.py` | API/离线缓存、标注和轮次比较 |
| `gold_*`、`make_annotation_guide.py`、`evaluate_gold.py` | 抽样、盲标、裁定和金标准评测 |
| `make_review_sheet.py`、`v1_finalize_labels.py`、`v1_freeze.py` | 标签审阅、汇总和冻结 |
| `validate.py` | 只读交付校验 |

## 文件边界

- `configs/taxonomy/`、`configs/prompts/`：类别定义、参数、人工决定和提示词。
- `data/taxonomy/`：标签交付、人工标注、LLM 缓存与冻结记录，维持原路径。
- `data/processed/local/b_taxonomy_*`：本地输入和计算缓存，保持 Git 忽略。
- `results/tables/taxonomy/`：无顾客标识的分类结果、轮次标签、指标和配套 Markdown 解读。
- `docs/taxonomy*.md`：方法、研究进度与 C 的交接协议。

## 从旧实验目录迁移

`experiments/b_taxonomy/*.py` → 本模块；`experiments/b_taxonomy/results/` →
`results/tables/taxonomy/`；专用依赖文件 → 根目录 `requirements-taxonomy.txt`。
原命令 `python experiments/b_taxonomy/<步骤>.py ...` 改为
`python scripts/run_taxonomy.py <步骤> ...`。

已有结果逐字节搬迁。最终冻结清单只改结果文件的路径键，哈希与冻结时间保持原值；
冻结配置、缓存和历史工作簿中的旧路径文本作为历史记录保留，按上述映射查找。
此次迁移不代表重新进行实验或重新冻结科学结果。

架构回归检查：`python -m unittest discover -s tests -v`。
