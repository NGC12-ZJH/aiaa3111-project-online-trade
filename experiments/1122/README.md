# 1122 实验

本目录保存采购形态分群、Top‑5 推荐与订单级路由的 Validation 扩展。结果包含代码、聚合统计、规则和参数对照、核验记录。正式冻结 Test 在 [D 评价入口](../../docs/evaluation/README.md)。

| 入口 | 内容 |
| --- | --- |
| [实验方案与结果汇总](1122_实验方案与结果汇总.md) | 全部已跑方案的方法、结果与原表入口 |
| [原始三路线报告](1122_三路线结果.md) | 采购形态与共购覆盖、固定第五位、收缩与贪心、订单路由与滚动 |
| [门控、L1 热门与软路由](followup_gating_l1_soft/三项追加实验结果.md) | 三项追加实验的分时段对照和逐方案结果 |
| [融合、时间衰减与季节开关](followup_fusion_time/两轮实验结果.md) | 同预算 G/L 融合、滚动时间窗口与季节敏感性 |

## 复算

从仓库根目录运行以下命令。脚本从 Git 仓库读冻结 A 数据对象和品类映射，并复用 D 的规则和统计工具。完整克隆应包含提交 2ae672b7ea6edb7f5e1561b6a64823004dea833e。若缺失此对象，先获取 a/online-retail-ii-data-snapshot 分支。

    $env:PYTHONUTF8 = '1'
    python -m pip install -r experiments/1122/requirements.txt
    python -B experiments/1122/run.py
    python -B experiments/1122/followup_gating_l1_soft/run.py
    python -B experiments/1122/followup_gating_l1_soft/report.py
    python -B experiments/1122/followup_fusion_time/run.py
    python -B experiments/1122/followup_fusion_time/report.py

结果写回各自的 results 目录。原始路线支持 --route audit、--route ab、--route c 和 --route report。运行脚本支持 --out 以使用独立的结果目录。最终融合轮读取前次 L1 热门实测值进行复现核验。

数据截止时间为 2011‑06‑01。顾客或交易级数据及可再生缓存沿原仓库的忽略规则处理。
