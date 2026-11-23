# 1123 三种分群与推荐 Test 补测

| 入口 | 内容 |
| --- | --- |
| [三种分群结果](results/README.md) | 纯 RFM、RFM＋采购形态、纯采购形态在共同 P5／120 下的覆盖、质量和 Hit@5 |
| [完整实验协议](README.md) | Discovery 组库、Validation 选参、冻结与历史 Test 的评价定义 |
| [三项推荐补测](test_utility/results/README.md) | L1 条件兜底、G100→G200、顾客历史选 SKU |
| [推荐补测协议](test_utility/README.md) | 配对对照、冻结设置和商品层评价时序 |

主实验在共同预算下比较分群来源，推荐补测每次改变一个因素。两份结果报告链接相应的排名、冻结记录、区间和审计表。

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
