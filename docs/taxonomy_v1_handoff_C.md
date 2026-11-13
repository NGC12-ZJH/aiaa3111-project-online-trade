# 交接给 C：taxonomy_v1 商品品类标签

> 来自 B（Jinghan ZHAO）· 2026-11-13 · 分支 `b/taxonomy`
> 版本：**`taxonomy_v1`（已正式冻结）**，冻结记录在 `data/taxonomy/v1_work/FREEZE_taxonomy_v1_final.json`。方法和评测见 [`taxonomy_v1.md`](taxonomy_v1.md)，完整过程见 [`taxonomy_workflow.md`](taxonomy_workflow.md)。

## 1. 用哪个文件

**`data/taxonomy/item_taxonomy_v1.csv`**：每个商品编码一行，覆盖全部 4,724 个有效编码（和 A 快照里的 `stock_code` 一致）。

| 列 | 含义 | 挖规则时用不用 |
|---|---|---|
| `stock_code` | 商品编码 | 用来和购物篮连接 |
| `l2_id` | **子类**（76 个，外加 other） | **品类层用这一列** |
| `l1_id` | 大类（10 个，外加 other） | 可选：更粗的一层 |
| `season` | christmas / easter / valentine / halloween / none | 可选：分析用 |
| `design_line` | 设计系列（22 个，例如 retrospot、spaceboy、dolly_girl）或 none | **规则三分类要用** |
| `label_source` | `llm_R6`（LLM）、`human_gold`（金标准人工标签）、`human_override`（评测后人工修正）、`llm_invalid_other`（LLM 没给出合法答案，记为 other） | 只用于说明标签来源 |
| `llm_tag_l2`、`llm_tag_confidence`、`llm_tag_note` | LLM 的原始输出，人工修正时不会被覆盖 | 不用 |
| `canonical_description`、`first_seen_split`、`n_variants`、`discovery_lines`、`v0_l2`、`v0_l1` | 参考信息 | 不用 |
| `taxonomy_version` | 一律为 `taxonomy_v1` | 写进规则表 |

子类代码的中文名、定义和边界规则见 `configs/taxonomy/taxonomy_v1.json`，或 [`annotation_guide_v1.md`](annotation_guide_v1.md) 第 6 节。

## 2. 标签质量

- 在 200 个人工金标准商品上：子类准确率 **90.0%**（95% CI 85–93%），大类 **92.5%**；按购买量加权的子类准确率 **93.1%**。
- 最终表里，金标准的 200 个商品直接用人工标签；另外 30 个商品是评测后人工修正的。
- 同一商品的不同写法得到相同子类：91.8%。
- other：按商品占 1.3%，按 Discovery 购买加权只占 0.2%。

## 3. 怎么用：三种粒度

和 README 第 4 节的约定一致。

```python
import pandas as pd
tax = pd.read_csv("data/taxonomy/item_taxonomy_v1.csv", dtype={"stock_code": str})
l2 = tax.set_index("stock_code").l2_id

b = pd.read_csv(".../baskets_long.csv.gz", dtype=str)            # A 的购物篮长表
b["l2"] = b.stock_code.map(l2)
concept = (b[b.l2 != "other"]                                    # 品类层：商品换成子类
           .drop_duplicates(["basket_id", "l2"]))                # 同一篮子里同一子类只算一次
```

| 粒度 | 做法 |
|---|---|
| 商品层 | 原样，不变 |
| 商品层、只保留跨类规则 | 挖完之后，去掉前件和后件所有商品属于**同一个 `l2_id`** 的规则 |
| 品类层 | 用上面的 `concept` 表挖规则，前后件都是子类 |

**规则三分类**（RQ1，商品层规则）：

| 类型 | 判定 |
|---|---|
| 同类换款 | 前后件的 `l2_id` 相同 |
| 同系列配套 | `l2_id` 不同，但 `design_line` 相同且不是 none |
| 真正跨类搭配 | 其他情况 |

建议在规则表里加三列：`granularity`、`taxonomy_version`（填 `taxonomy_v1`）、`rule_type`。

## 4. 注意事项

1. **品类层要重新选门槛**。v0 时沿用商品层门槛，品类层得到 3.6 万条规则，排在前面的都是 lift 1.3–1.6 的大众组合。品类层需要更高的 lift 门槛或改用 lift 排序，**只能在 Validation 期选**，不能看 Test 期。
2. **悬挂装饰（`hanging_ornaments`）偏大**：占 Discovery 购买的 6.7%，其他子类都在 4.2% 以下。原因是圣诞树挂饰并了进来（节日用 `season` 属性单独表示）。品类层的热门规则里它可能出现得特别多，解读时要注意。
3. **other 不参与品类层**，建议在挖之前去掉，这样做只损失 0.2% 的购买。
4. **跨粒度比较**：品类层的命中率天然更高，不能直接和商品层比；跨层比较只能用 lift，或者相对热门基线的提升。
5. **不要改标签文件**。发现明显错标请告诉 B，由 B 统一修正，记为 `human_override` 后重新冻结。

## 5. 有问题找谁

B（Jinghan ZHAO）。复现方法见 [`taxonomy_v1.md`](taxonomy_v1.md) 第 3 节：所有 LLM 输出都有缓存，`--offline` 可以不联网重建。
