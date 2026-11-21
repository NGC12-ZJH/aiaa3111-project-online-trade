# D：Validation 交付与阅读入口

## 最终 Test 交付（2026-11-21）

正式主设置采用 P5／100，20／50／100 预算曲线完整保留。见 [Test 结果](test_results.md)、[冻结协议](../configs/test_frozen.json) 和 [Test 原始汇总](../results/tables/test/)。下文保留交付时的 Validation 阶段记录。

更新：2026-11-19 · 分支：`d/evaluation` · 负责人：Chenrui XIANG。

## 当前交付与阅读顺序

本分支包含四层证据：原覆盖与预算比较、统一未来质量、G50+L50互补性、群间差异与优势保持。冻结标签与规则不变，未正式选参、未评价Test。

| 想回答的问题 | 推荐入口 |
|---|---|
| Cluster选出的东西和Global差多大？优势未来保持吗？ | [群体差异与优势保持结果](validation_specificity_results.md) · [离线HTML](validation_specificity_results.html) |
| Cluster能否补充Global遗漏的订单？ | [G50＋L50去重匹配K报告](validation_hybrid_results.md) |
| 规则到了未来仍有价值吗？ | [统一质量结果](validation_quality_results.md) · [离线HTML](validation_quality_results.html) |
| 原覆盖、公平预算与顾客区间是多少？ | [原Validation结果](validation_results.md) · [离线HTML](validation_results.html) |
| 共同标准和群体差异分别怎么定义？ | [一页质量标准](validation_quality_plan.md) · [群体差异方案](validation_specificity_plan.md) |
| 如何运行和解释字段？ | [模块说明](../src/online_trade/evaluation/README.md) · [质量方法与字段](validation_quality_methods.md) |

GitHub通常显示HTML源码；下载HTML后在浏览器打开可离线看表和内嵌图。建议开会先讲“名单差异、群体强度、优势保持、互补覆盖”是不同问题。

当前观察：P3合并规则比同预算G60净多覆盖121单；P5/100有22条不同规则不在G前100，19个D优势候选中15个保持正方向。但主BY标准无单条真实群规则通过全部未来群体优势要求，BH敏感性下有1个提示案例。不能据此宣称已证明RFM特有收益，也不能把未通过解释成所有规则都失效。

## 四批结果分开保存

| 位置 | 内容 |
|---|---|
| `results/tables/validation/` | 原Validation的6,660条系统结果、G/L摘要、随机对照、2,000次顾客配对bootstrap、样本与回退审计、Discovery复算、核验与manifest |
| `results/tables/validation_quality/` | 统一标准的6,660条系统质量结果、G/L逐规则证据、11套主/敏感性定义、随机汇总、校正家族、核验与manifest |
| `results/tables/validation_hybrid/` | G50＋L50去重、实际K、匹配全局基线、配对区间与质量复核 |
| `results/tables/validation_specificity/` | 名单差异、群内/群外强度、方向保持、221个真实/随机系统、互补覆盖与核验 |
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

## 当前核验与结果边界

- 原计算：6,660条Discovery系统结果及所有预算规则计数与C一致；独立集合算法检查150组Validation系统。
- 质量计算：50,161个原范围规则身份的计数/点估计与原结果一致；全部6,660条原覆盖逐项一致；独立库核对222个BY/BH校正家族；独立集合算法检查全部60组G/L质量覆盖与顾客等权覆盖。
- 合并比较：15组完整/可靠覆盖独立集合核对。群体差异：49,934个目标群规则身份的D/V计数核对，6,630条原L/R覆盖复现，221个新BY家族核对，440组真实规则×时期效应与区间独立核对。当前23项测试通过。
- 主样本4,862单、1,458名历史顾客；另有2,502张有标识非Profile订单和703张匿名订单单独做全局回退。
- 新质量标准是在已看过原Validation后添加，记录为探索性扩展。t近似、BY校正和工作性效应门槛都有适用边界，不作全研究确认性显著结论。程序核验不等于人工科学复核通过。
- 主标准下P5/100的可靠覆盖G=74.85%、L=62.77%；仅为已计算观察，不构成正式选参。验收门槛敏感性和全部设置均保留。

## 后续尚待完成

全组审阅统一标准与比较目标，正式确定配置/预算、主规则使用方式和主随机对照；记录冻结清单及选择理由之后，才可独立评价Test。本分支不包含最终Test结果、Report.pdf或Poster.pdf。

## 新增交付：互补规则与群体优势（2026-11-19）

- [G50＋L50去重匹配预算实验](validation_hybrid_results.md)：分群规则是否补充全局Top榜。
- [群体差异补算方案](validation_specificity_plan.md)：名单差异与群体优势分开。
- [群体差异与未来保持结果](validation_specificity_results.md)／[离线HTML](validation_specificity_results.html)：含S/A1/A2、群内/群外效应与独立核验。

这些是既有Validation后的探索性扩展，未改变最终配置，未使用Test。

补算协议里的push_to_github=false是计算时的“不自动推送”记录，本次发布依据用户后续授权；不更改历史协议与其哈希。
