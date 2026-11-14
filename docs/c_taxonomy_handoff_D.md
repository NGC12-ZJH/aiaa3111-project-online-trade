# C → D：taxonomy 品类层模式挖掘交接注意事项

交付日期：2026-11-14。分支：`c/pattern-mining-taxonomy`。本分支基于 SKU 实验分支 `c/pattern-mining` 的 `fb734c4`，保留原有 SKU 实验作为对照。

## 1. 当前状态与 D 的任务

新增实验全部使用 Discovery；未使用 Validation/Test。严格档是重点候选配置，**不是已由 Validation 选定的最终配置**。D 应在 Validation 比较事先约定的参数与预算，冻结方案后在 Test 做一次最终评价。不要以必须得到“分群优于全局”为目标。

当前最重要的负面结果：严格档＋增量检查，在系统总预算20/50/100下，G覆盖率55.06%/63.25%/66.12%，L为38.78%/52.12%/59.31%；L均在20个随机种子的结果范围内。此结果仅针对当前排序和配额，不是推荐准确率或未来表现。

## 2. 核心交付位置

以下路径均相对 `experiments/c_pattern/`：

|位置|用途|
|---|---|
|`taxonomy_analysis/item_taxonomy_v1.csv`、`taxonomy_v1.json`|冻结标签及中文定义|
|`taxonomy_analysis/candidate_taxonomy.csv`|原SKU共同候选池的三分类标签|
|`cross_category_analysis/GL_cross_category_rules.csv`|SKU层G/L跨类合格规则|
|`category_patterns/candidate_rules.csv`|91,535条品类层共同候选规则字典|
|`category_patterns/compact_evidence/`|64范围、5,858,240行精确计数，含generated_here和eligible|
|`category_patterns/scope_audit.csv`|订单分母、客户数、空篮与单品类篮|
|`category_screening/`|三档门槛×增量开关的统计、Top50及随机种子汇总|
|`category_fixed_budget/selected_rules.csv`|严格档加增量检查的B=20/50/100实际部署清单|
|`category_fixed_budget/allocation_audit.csv`|组内预算及实际规则数|
|`category_fixed_budget/order_coverage.csv.gz`|固定预算逐订单覆盖，用于核对|
|`category_visualizations/`|PNG、SVG、汇总表及图表说明|
|`taxonomy_delivery_manifest.json`|交付文件校验哈希、压缩格式及省略文件说明|

`candidate_rules.csv`包含全部范围的联合候选池，**不能把池内全部规则视为每个群原生发现的规则**。常规native比较必须同时满足`generated_here`和筛选条件。随机候选加入共同池只服务证据重算，不构成正式独立假设检验。

## 3. 数据与 taxonomy 必须保持一致

- A/B冻结快照沿用原实验，客户标签位于`labels/`，输入哈希记录在各阶段manifest。
- taxonomy来自B分支提交`c89430d4cb894154d6084b3eae7f70ba18a04069`，版本`taxonomy_v1`；本分支复制冻结文件，不改标签。
- Discovery为[2010-06-01,2010-12-01)，Validation为[2010-12-01,2011-06-01)，Test为[2011-06-01,2011-12-01)。Profile标签固定，不在未来期重新聚类。
- 主分析Discovery为7,521张订单，C0/C1/C2分别801/2,173/4,547张。未来期按同一客户纳入规则处理；新客户或无Profile标签客户不能悄悄并入G而不纳入L/R。
- SKU映射到`l2_id`；排除other；每篮同一子类只计一次。纳入样本中映射后空篮保留分母。当前76个子类、2张空篮、974张单品类篮。
- 标签覆盖全期编码，且包含人工修订。不要把冻结日期等同于仅用Profile拟合。标签构建使用了哪些描述或阶段信息，应结合B的taxonomy方法文档披露，不宣称所有预处理均无未来信息。
- SKU层、跨类SKU层、L2层分开报告；跨层覆盖率及lift都受粒度变化影响，不能直接判优。

## 4. 参数、增量及计数

|配置|support|confidence|lift|联合/前件次数|
|---|---|---|---|---|
|baseline|≥1%|≥20%|≥1.0|均≥20|
|moderate|≥2%|≥40%|≥1.3|均≥20|
|strict|≥3%|≥50%|≥1.5|均≥20|

每档都比较三品类增量开/关。增量=`confidence(AB→C)-max(confidence(A→C),confidence(B→C))`，要求≥0.05；两个单前件无论是否通过当前筛选，都用其实际计数。二品类不受增量检查影响。该增量是描述指标，不是显著性检验。

规则为单后件方向规则；A→B与B→A各计一条。不同组合数对前后件并集去重。严格档加增量后G/C0/C1/C2二品类70/108/53/93条，三品类1,046/2,263/803/1,407条。

未来期零前件时confidence及lift未定义，不填成可靠的0或沿用Discovery数值；应报告可评价规则数、零前件规则数。类别无出现也要保留冻结规则身份。

## 5. 固定预算与评价口径

- 总预算B=20/50/100，不是每群各B。
- G使用全部预算；L及每个R种子按Discovery订单数，用最大余数法分配，平局按group_id，不补发空缺。当前所有配置均满额。
- 排序：联合次数↓、confidence↓、lift↓、rule_id↑。二/三品类混排；无长度配额。同规则在不同群各占名额，反向规则分别占名额。
- 当前L配额分别为2/6/12、5/15/30、11/29/60。
- 建议D评价当前Discovery选定列表及配额，不能默认用Validation订单数重分配。若计划用Validation选新排序/配额，须记录为调参，Test前冻结。
- 完整覆盖率：订单完整包含至少一条部署规则的前后件并集；L/R仅使用订单所属组规则。系统分母为全部合格订单，不是三个群覆盖率的简单平均。
- 前件触达率另列，不能当作完整覆盖或推荐精确率。这里尚未实现遮蔽后件/预测式推荐评价。
- 一个随机种子产生一个全系统指标，20个种子为20次重复。筛选报告的组指标等权均值与固定预算的订单加权系统指标不同，不能混用。
- 当前预算文件只针对strict＋increment5pp；如D比较其他档位，需按同一规则重新选取预算列表。

## 6. 无损计数证据与复现

为避免约1GB重复输出和GitHub单文件限制，交付完整候选字典与精确整数计数，省略可重建的重复长表。每个compact文件的`candidate_index`为字典的零基行号，顺序和哈希均已校验。包含联合、前件、后件、群外联合及前件计数，以及原生生成/原基线合格标记。scope_audit给出分母，足以精确重算support/confidence/lift及群内外差异。

在仓库根目录执行（先按`experiments/c_pattern/requirements-lock.txt`准备Python环境）：

```powershell
$patternRoot = (Resolve-Path 'experiments/c_pattern').Path
python experiments/c_pattern/restore_category_evidence.py --root $patternRoot
python experiments/c_pattern/screen_category_rules.py --root $patternRoot
python experiments/c_pattern/category_fixed_budget.py --root $patternRoot
python experiments/c_pattern/visualize_category_results.py --root $patternRoot
```

需要从购物篮重新挖掘时，先运行`mine_categories.py --root $patternRoot`；无需这样做即可使用交付计数。该脚本使用mlxtend FP-Growth核心，并针对无缺失布尔矩阵跳过逐项缺失值后处理，对生成组合逐一直接核对计数。请使用锁定依赖版本。

重新生成SKU标签与跨类报告时依次运行`taxonomy_analysis.py`、`export_cross_category.py`，同样传入`--root $patternRoot`。发布版标签脚本从随包冻结文件读取，不依赖本机工作区名称。

省略文件及可重建路径见delivery manifest。完整本地原始输出仍保留，交付压缩并非抽样。还原可能占用数百MB磁盘。

## 7. 建议给报告保留的案例与限制

- 全局：悬挂装饰→烛台灯笼，说明共性采购结构；注意悬挂装饰类别偏宽。
- C0：笔和美术用品→小物/首饰盒；C1：派对用品→缝纫手工；C2：午餐袋→大购物袋，检查群内外差异在未来是否保持。
- 三品类：C2的{烛台灯笼,家具旋钮}→杯子，检查相对单前件的增量及客户集中度，不强行解释成业务互补。
- SKU三分类按全部商品判断：同l2优先，其次全部同非none设计系列，剩余跨类；三品类的两个子类和三个子类并不相同，应参看distinct_l2_count。
- 不把客户直接命名为批发商/零售商；不把共现解释为因果增销；不把销售额当利润。当前未完成未来稳定性、客户集中度或推荐效用证明。

建议D回交：Validation参数选择表、冻结配置与规则清单、固定预算G/L/R结果、代表案例稳定性及失败案例；最后另交独立Test结果。
