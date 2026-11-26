# 1123 · Fig. 4 Validation → Test 数据与复算

本目录对应海报第 4 张的 RQ2a。继续使用 1123 的 Profile 分群标签、B2 分层和种子 1000–1099。共购特征固定为 Discovery 至少出现 20 单的 2,786 个无向二品类组合。两期各用能匹配 Profile 标签的订单，Validation 为 4,862 单，Test 为 5,730 单。对每个群与群外计算品类对支持率的 Bray–Curtis 距离，三个群等权平均。

空心点是 Validation，实心点是 Test。横坐标为真实分群的距离减去对应 100 套 B2 的中位数。右侧报距离达到或超过真实分群的 B2 套数。

| 分群 | Validation 横坐标 | Test 横坐标 | B2 ≥ 真实（Validation → Test） |
| --- | ---: | ---: | ---: |
| RFM | +0.006474 | +0.001324 | 7 → 41 |
| RFM＋采购形态 | +0.051520 | +0.062852 | 0 → 0 |
| 纯采购形态 | −0.040312 | −0.044786 | 88 → 81 |

[完整精度与原始距离](results/fig4_values.csv) · [600 个 B2 逐种子结果](results/b2_draws.csv) · [核验与输入哈希](results/audit.json)

## 复算

按 [1123 总入口](../../INDEX.md#本地复算) 准备同级的 `1123` 和 `repository`，并准备本地评估输入。`--snapshot-repo` 指向含冻结数据快照的 Git 仓库。以下命令从这两个目录的父目录运行，并将结果写到一个新目录。

```powershell
python -X utf8 -B 1123/review_followup/test_distinct/run.py --project 1123 --snapshot-repo repository --out 1123/review_followup/test_distinct/results_replay
```

程序会用分支已发表的 Validation 数值、B2 中位数和达到次数复核 Validation，然后写出两个时期的数据。这里的 B2 指标是**共购结构距离**。[B2 与贪心 G 的 Test 补测](../test/README.md)衡量订单覆盖、规则质量和推荐命中。
