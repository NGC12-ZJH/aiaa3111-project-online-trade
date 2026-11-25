# 1123 · B2 与贪心 G Test 补测

固定 P5／120，使用已保存的 305 套规则库。普通 G 和三种真实分群的结果逐项复现。新评价包含贪心 G 和每种分群对应的 100 套 B2。全店覆盖用 10,890 张订单，可靠覆盖和规则质量用 10,262 张有顾客 ID 的订单，品类 Hit@5 用 9,728 张可遮挡订单。

- 贪心 G 覆盖 **79.32%（8,638 单）**，比普通 G 净多覆盖 **163 单**，比纯采购形态净多覆盖 **67 单**。贪心 G 的品类 Hit@5 为 **31.35%**。
- 对纯采购形态的真实规则库，**25/100** 套 B2 达到或超过其全店覆盖，**55/100** 套达到或超过其严格可靠覆盖。

## 结果与核验

| 文件 | 内容 |
| --- | --- |
| [结果汇总](results/RESULTS.md) | 五套真实规则库的主要指标、贪心 G 配对差值与 B2 分布 |
| [逐系统指标](results/systems.csv) · [推荐结果](results/recommendation.csv) | 各规则库覆盖与质量指标，各订单样本的 Hit@5、NDCG@5 和命中变化 |
| [B2 对照](results/B2_comparisons.csv) · [贪心 G 配对比较](results/greedy_paired.csv) | 每种分群的 B2 范围和达到真实分群的次数，以及 2,000 次配对重抽区间 |
| [逐规则质量](results/GL_quality.csv) | 普通 G、三种真实分群和贪心 G 的规则质量证据 |
| [运行前清单](results/freeze.json) · [规则名单](results/rosters.csv) · [核验记录](results/audit.json) | 输入哈希、120 个不同组合的规则名单、Test 分母和主结果复现检查 |

## 复算

先按 [1123 总入口](../../INDEX.md#本地复算) 准备同级 `repository` 和 `1123` 目录及评估输入。`--snapshot-repo` 指向含有冻结数据快照提交的本地 Git 仓库。命令使用一个新的输出目录。

```powershell
python -X utf8 -B 1123/review_followup/test/run.py freeze --project 1123 --snapshot-repo repository --out 1123/review_followup/test/results_replay
python -X utf8 -B 1123/review_followup/test/run.py test --project 1123 --snapshot-repo repository --out 1123/review_followup/test/results_replay
```
