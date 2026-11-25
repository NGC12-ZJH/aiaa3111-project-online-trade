# 1123 三种分群、推荐与审查补测

| 入口 | 内容 |
| --- | --- |
| [三种分群结果](results/README.md) | 纯 RFM、RFM＋采购形态、纯采购形态在共同 P5／120 下的覆盖、质量和 Hit@5 |
| [完整实验协议](README.md) | Discovery 组库、Validation 选参、冻结与 Test 评价定义 |
| [三项推荐补测](test_utility/results/README.md) | L1 条件兜底、G100→G200、顾客历史选 SKU |
| [推荐补测协议](test_utility/README.md) | 配对对照、冻结设置和商品层评价时序 |
| [四项审查补测结果](review_followup/results/README.md) | 跨期品类差异、篮子大小匹配 B2、G 贪心、分群稳定性与缩放 |
| [四项审查补测协议](review_followup/README.md) | 固定 P5／120 的 Discovery 与 Validation 计算口径 |
| [B2 与贪心 G 的 Test 补测](review_followup/test/README.md) | 同样的 120 个组合与同一批 Test 订单，比较普通 G、三种真实分群、贪心 G 和 300 套 B2 |

主实验在共同预算下比较分群来源，推荐补测每次改变一个因素。四项审查补测报告 Discovery 和 Validation，B2 与贪心 G 的 Test 补测沿用其中已保存的规则名单。

## 本地复算

仓库里的 `experiments/1123` 保存原冻结文件和代码。运行器沿用当时的本地目录布局。在工作目录下将此分支克隆为 `repository`，再把两个实验目录复制为它的同级目录。

```powershell
git clone --branch experiments/1123 https://github.com/NGC12-ZJH/aiaa3111-project-online-trade.git repository
Copy-Item -LiteralPath repository/experiments/1122 -Destination 1122 -Recurse
Copy-Item -LiteralPath repository/experiments/1123 -Destination 1123 -Recurse
Copy-Item -Path 1123/replay_inputs/1122/* -Destination 1122 -Recurse -Force
Push-Location repository
python -X utf8 -m pip install -r requirements-validation.txt
python -X utf8 -m pip install -r experiments/1122/requirements.txt
python -X utf8 -B scripts/prepare_validation_inputs.py
Pop-Location
```

复算附录保留了 1123 实际调用的 1122 依赖字节。上面的复制命令只在新建的同级 1122 目录中把这些依赖放回原位置。查看现成结果只需打开上方报告。要重新计算，主实验和推荐补测各使用一个新输出目录。推荐补测读取同级主实验的冻结清单。数据准备与引用校验见 [D 复现说明](../../docs/evaluation/reproduce.md)。

四项审查补测读取同级主实验的冻结名单。在上述目录布局下，可从工作目录运行 `python -X utf8 -B 1123/review_followup/run.py --out 1123/review_followup/results_replay`。

B2 与贪心 G 的 Test 补测入口、所需输入和复算命令见 [补测说明](review_followup/test/README.md)。
