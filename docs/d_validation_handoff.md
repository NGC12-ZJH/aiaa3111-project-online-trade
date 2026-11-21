# D 分支交付与复现

更新于 2026-11-21。D 分支覆盖从 Validation 比较、P5 选参冻结到最终 Test 的完整流程。

## 先看结果

| 想了解的问题 | 阅读入口 |
|---|---|
| 最终 Test 的主结果、预算曲线和不确定性 | [Test 报告](test_results.md) · [结果表和运行清单](../results/tables/test/) |
| 何时冻结、选了什么、沿用哪些规则 | [冻结协议](../configs/test_frozen.json) · [实验记录](experiment_log.md) |
| 为什么选 P5／100 | [原 Validation 报告](validation_results.md) · [统一质量报告](validation_quality_results.md) |
| 群体规则与全局规则差多少、优势是否保持 | [群体差异报告](validation_specificity_results.md) · [离线图表](validation_specificity_results.html) |
| 分群规则能否补充全局规则 | [Validation 合并实验](validation_hybrid_results.md) · [Test 中的 P3 补充结果](test_results.md) |
| 质量门槛和群体差异怎么定义 | [共同验收方案](validation_quality_plan.md) · [质量方法与字段](validation_quality_methods.md) · [群体差异方案](validation_specificity_plan.md) |

主设置采用 P5、总预算 100、限群使用和 A1 活跃度匹配对照。Test 的 5,730 张合格订单中，全局覆盖 74.50%，真实分群 64.28%，A1 中位数 63.35%。P3 混合是探索性补充，覆盖 65.86%，同预算全局覆盖 63.70%。该比较缺少随机混合基线。口径与区间见 [Test 报告](test_results.md)。

## 交付文件

| 内容 | 位置 |
|---|---|
| Validation 原覆盖与顾客区间 | [validation](../results/tables/validation/) |
| 统一质量与敏感性 | [validation_quality](../results/tables/validation_quality/) |
| 去重合并与同预算比较 | [validation_hybrid](../results/tables/validation_hybrid/) |
| 名单差异、群内／群外强度、跨期保持和随机对照 | [validation_specificity](../results/tables/validation_specificity/) |
| Test 主结果、逐种子结果、区间、质量及样本审计 | [test](../results/tables/test/) |
| 图表、命令与实现 | [figures](../results/figures/) · [scripts](../scripts/) · [评价模块](../src/online_trade/evaluation/) |

A 的订单快照固定为 `2ae672b7ea6edb7f5e1561b6a64823004dea833e`，C 的规则交接固定为 `ac2b8a3338198c24c7cf6203aa623be11a02d2f8`。准备脚本从 Git 对象提取已固定的约 15 MB 核心包。顾客级输入及本地明细位于忽略目录 `data/processed/local/D_validation/`。

## 复现 Validation（CPU）

Windows使用以下命令可避免自动换行破坏冻结哈希：

```powershell
git -c core.autocrlf=false -c core.eol=lf clone --branch d/evaluation https://github.com/NGC12-ZJH/aiaa3111-project-online-trade.git
cd aiaa3111-project-online-trade
git config --local core.autocrlf false
git config --local core.eol lf
python -m pip install -r requirements-validation.txt
python -X utf8 scripts/prepare_validation_inputs.py
python -X utf8 scripts/run_validation.py
python -X utf8 scripts/report_validation.py
python -X utf8 scripts/check_validation_independently.py
python -X utf8 scripts/run_validation_quality.py
python -X utf8 scripts/report_validation_quality.py
python -X utf8 scripts/check_validation_quality.py
python -X utf8 scripts/run_validation_hybrid.py
python -X utf8 scripts/report_validation_hybrid.py
python -X utf8 scripts/run_validation_specificity.py
python -X utf8 scripts/report_validation_specificity.py
python -X utf8 scripts/check_validation_specificity.py
```

需要完整克隆包含A/C固定提交；浅克隆应先获取对应源分支。测试命令（UTF-8环境变量传给taxonomy测试子进程）：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH=Join-Path (Get-Location) 'src'
python -m unittest discover -s tests -v
```

已验证环境：Python3.13.13、NumPy2.4.6、pandas3.0.3、SciPy1.18.0、Matplotlib3.11.0。依赖固定在 `requirements-validation.txt`。

## 复现正式 Test（CPU）

在完整克隆中，用独立工作树检出冻结提交。这个目录的已提交文件对应看 Test 之前的版本，运行器会核对规则顺序、配额、输入哈希和工作树状态。

```powershell
git worktree add --detach ../aiaa3111-test-replay 0bb4815
cd ../aiaa3111-test-replay
python -X utf8 scripts/prepare_validation_inputs.py
python -X utf8 scripts/run_frozen_test.py run
```

使用上面的 Windows 换行配置和依赖版本。已发布分支可运行 `python -X utf8 scripts/report_frozen_test.py`，根据保存的汇总核验覆盖并生成报告。原计算冻结提交为 `0bb4815`，结果提交为 `3d18441`。

Test 用同一批订单比较各系统。限群模式的规则名额是系统总预算，各顾客可使用数量随所属群变化。共同质量覆盖是回顾性的共购指标，Test 和 Validation 的校正家族范围不同，详见报告。
