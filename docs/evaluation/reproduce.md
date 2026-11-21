# D 分支复现

[返回交付入口](README.md)

A 的订单快照固定为 `2ae672b7ea6edb7f5e1561b6a64823004dea833e`，C 的交接冻结于 `ac2b8a3338198c24c7cf6203aa623be11a02d2f8`。准备脚本从 Git 对象提取约 15 MB 核心包。顾客级输入和本地明细位于被忽略的 `data/processed/local/D_validation/`。

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

使用上面的 Windows 换行配置和依赖版本。已发布分支可运行 `python -X utf8 scripts/report_frozen_test.py`，根据保存的汇总核验覆盖并生成报告。在当前分支运行报告脚本之前，也需要准备本地输入。冻结提交为 `0bb4815`，原结果提交为 `3d18441`。
