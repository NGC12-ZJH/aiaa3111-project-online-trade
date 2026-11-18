# D：Validation 交付与阅读入口

更新：2026-11-18 · 分支：`d/evaluation` · 负责人：Chenrui XIANG。

## 当前交付

本分支完成冻结品类规则的Validation比较及统一未来质量补算。五配置P1–P5 × 总预算20/50/100；G/L、S（20种子）、A1/A2（各100种子）；限群/共享分别报告。未正式选择或冻结参数，未评价Test。讨论中的参数建议不等于最终实验配置。

| 顺序 | 文档 | 用途 |
|---|---|---|
| 1 | [共同验收方案（一页）](validation_quality_plan.md) | 新质量标准、工作性阈值、适用范围 |
| 2 | [统一质量结果](validation_quality_results.md) · [离线图表版](validation_quality_results.html) | 可靠关联保持、覆盖及敏感性 |
| 3 | [原Validation结果](validation_results.md) · [离线图表版](validation_results.html) | 原始覆盖、顾客区间、原配置门槛保持 |
| 4 | [质量方法与字段](validation_quality_methods.md) | 顾客聚类近似、校正家族、列解释与限制 |
| 5 | [模块运行说明](../src/online_trade/evaluation/README.md) | 输入、依赖、命令与输出 |

GitHub通常显示HTML源代码；需要图表版时下载HTML后在浏览器打开，图片已内嵌，无外部资源。

## 两批结果分开保存

| 位置 | 内容 |
|---|---|
| `results/tables/validation/` | 原Validation的6,660条系统结果、G/L摘要、随机对照、2,000次顾客配对bootstrap、样本与回退审计、Discovery复算、核验与manifest |
| `results/tables/validation_quality/` | 统一标准的6,660条系统质量结果、G/L逐规则证据、11套主/敏感性定义、随机汇总、校正家族、核验与manifest |
| `results/figures/validation/` | 原覆盖比较图 |
| `results/figures/validation_quality/` | 原覆盖与可靠关联覆盖比较图 |
| `configs/validation.json` | 原比较协议，不选择参数 |
| `configs/validation_quality.json` | 在补算前固定的新质量协议，主标准及敏感性 |

旧“达到各自冻结门槛”和新“达到共同质量标准”不是同一指标，不能混用。后者是同一期Validation验收后的回顾性关联保持指标，不是部署后的预测效果。

## 输入获取与本地数据

- A数据快照：`2ae672b7ea6edb7f5e1561b6a64823004dea833e`。
- C交接提交：`ac2b8a3338198c24c7cf6203aa623be11a02d2f8`，使用其中约15MB的 `D_validation_core.zip`；不需要4.6GB完整候选附件。
- taxonomy与顾客标签沿用交接中的冻结版本；不重新聚类、不重新挖掘、不改规则排名、不补齐失败规则。
- 顾客级原始输入、逐订单命中、全量逐规则质量与随机敏感性明细仅在忽略目录 `data/processed/local/D_validation/`，本分支不上传。其他人用下面的准备命令从固定Git对象重建。
- 输入源购物篮含多个时期；准备脚本只导出Discovery复算及Validation，未导出或评价Test。

## 从全新克隆复现（CPU，无需GPU）

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
```

需要完整克隆包含A/C固定提交；浅克隆应先获取对应源分支。测试命令（UTF-8环境变量传给taxonomy测试子进程）：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH=Join-Path (Get-Location) 'src'
python -m unittest discover -s tests -v
```

已验证环境：Python3.13.13、NumPy2.4.6、pandas3.0.3、SciPy1.18.0、Matplotlib3.11.0。依赖固定在 `requirements-validation.txt`。

## 当前核验与结果边界

- 原计算：6,660条Discovery系统结果及所有预算规则计数与C一致；独立集合算法检查150组Validation系统。
- 质量计算：50,161个原范围规则身份的计数/点估计与原结果一致；全部6,660条原覆盖逐项一致；独立库核对222个BY/BH校正家族；独立集合算法检查全部60组G/L质量覆盖与顾客等权覆盖。
- 主样本4,862单、1,458名历史顾客；另有2,502张有标识非Profile订单和703张匿名订单单独做全局回退。
- 新质量标准是在已看过原Validation后添加，记录为探索性扩展。t近似、BY校正和工作性效应门槛都有适用边界，不作全研究确认性显著结论。程序核验不等于人工科学复核通过。
- 主标准下P5/100的可靠覆盖G=74.85%、L=62.77%；仅为已计算观察，不构成正式选参。验收门槛敏感性和全部设置均保留。

## 后续尚待完成

全组审阅统一标准与比较目标，正式确定配置/预算、主规则使用方式和主随机对照；记录冻结清单及选择理由之后，才可独立评价Test。本分支不包含最终Test结果、Report.pdf或Poster.pdf。
