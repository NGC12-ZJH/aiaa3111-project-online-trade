# D：Validation 比较

负责人：Chenrui XIANG。2026-11-16 已实现并在本地 CPU 运行。当前仅比较五套配置和预算20/50/100，不推荐配置、不冻结最终方案、不评价Test。

输入固定为 C 的 `ac2b8a3` 核心包和 A 的 `2ae672b` 快照。主口径为限群使用、A1历史活跃度随机对照；共享使用、S和A2单独报告。规则排名、群标签、taxonomy及Discovery预算配额不变。

## 运行

```powershell
python -m pip install -r requirements-validation.txt
python -X utf8 scripts/prepare_validation_inputs.py
python -X utf8 scripts/run_validation.py
python -X utf8 scripts/report_validation.py
python -X utf8 scripts/check_validation_independently.py
```

首次克隆需有两个固定提交的Git对象（完整克隆已包含）。Windows下建议克隆前设置仅此命令的 `-c core.autocrlf=false -c core.eol=lf`，保留冻结CSV字节；已有仓库不要覆盖个人更改。`-X utf8` 同时避免系统默认GBK解码中文JSON。原taxonomy测试需使用 `PYTHONUTF8=1` 以传给测试子进程。

`validation.py` 使用精确订单位集合重算规则计数和系统覆盖。先复算C的6,660条Discovery系统结果及预算规则计数，再评价Validation。保留映射后的空篮和单品类篮。前件为0时confidence/lift不可估；三品类增量由未来两个单前件重新计算。

顾客配对bootstrap为2,000次、种子3111，同一顾客的所有订单一起抽样。随机结果以种子为单位，范围不是置信区间，多指标未作校正。共享模式的规则质量状态仍按原生群范围报告，不能当成共享后的全局规则置信度。

配置见 `configs/validation.json`；中文结果说明见 `docs/validation_results.md` 和可离线打开的 `docs/validation_results.html`。汇总输出在 `results/tables/validation/` 和 `results/figures/validation/`；顾客级输入与逐订单/逐规则证据在被忽略的 `data/processed/local/D_validation/`。

本批次仅评价冻结预算规则的品类层结果，未覆盖全部候选池、SKU层未来评价或等每用户预算重选。这是 Validation 阶段的评价范围。

## 统一质量扩展（2026-11-18）

先读 `docs/validation_quality_plan.md` 一页方案；固定协议在 `configs/validation_quality.json`。用既有Validation订单和冻结规则补算，不覆盖原结果：

```powershell
python -X utf8 scripts/run_validation_quality.py
python -X utf8 scripts/report_validation_quality.py
python -X utf8 scripts/check_validation_quality.py
```

结果在 `results/tables/validation_quality/`，中文报告在 `docs/validation_quality_results.md` / `.html`。这是已看过原Validation后的探索性扩展。按顾客聚类的t近似、BY校正及工作性阈值的边界见 `docs/validation_quality_methods.md`。可靠关联覆盖是同一期验收后的回顾性指标；不选参数、不运行Test。

## 群体特异性与优势保持（2026-11-19）

方案：`docs/validation_specificity_plan.md`；协议：`configs/validation_specificity.json`。先准备原输入并运行 `scripts/run_validation.py`，再执行：

```powershell
python -X utf8 scripts/run_validation_specificity.py
python -X utf8 scripts/report_validation_specificity.py
python -X utf8 scripts/check_validation_specificity.py
```

不依赖GPU或完整大候选包。报告在 `docs/validation_specificity_results.md` / `.html`，汇总在 `results/tables/validation_specificity/`。真实/随机完整规则证据在忽略目录，不上传顾客级数据。分开解释Top榜名单差异、群内关联、群间强度、方向保持和同预算互补覆盖。严格主标准和探索性限制详见报告。

## 正式 Test（2026-11-21）

冻结的 P5／100 主结果及补充比较见 [Test 报告](../../../docs/test_results.md)。独立工作树复现命令和冻结提交见 [D 交付入口](../../../docs/d_validation_handoff.md)。
