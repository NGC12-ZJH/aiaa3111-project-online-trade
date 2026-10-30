# 四人分工与交接

项目：aiaa3111-project-online-trade。每人承担技术、写作和答辩。

## A Qingyang LI

邮箱：qli863@connect.hkust-gz.edu.cn

主责：数据处理与复现

任务：清洗订单、构建购物篮、时间切分、顾客留存审计、数据敏感性分析、README 与最终复现打包。

交付：清洗后的购物篮、数据审计表、切分记录、运行说明。

复核：Jinghan ZHAO 的历史窗口；Chenrui XIANG 的评价样本与分母。

代码目录：`src/online_trade/data/`

## B Jinghan ZHAO

邮箱：zhaojinghan06@gmail.com

主责：顾客分群与对照分组

任务：计算历史 RFM、标准化、K-means、群数与稳定性分析、随机顾客分组、未来群体差异分析。

交付：顾客群体映射、RFM 画像、随机分组标签及 seed、群体分析图。

复核：Qingyang LI 的顾客统计；Chenrui XIANG 的群体评价指标。

代码目录：`src/online_trade/clustering/`

## C Anqi ZHAO

邮箱：azhao258@connect.hkust-gz.edu.cn

主责：模式挖掘与解释

任务：全局、局部与随机组规则挖掘，共同候选池，同规则预算筛选，冗余处理，成功与失败案例；整合海报。

交付：规则表、支持度计数、预算配置、案例图、Poster.pdf。

复核：Chenrui XIANG 的规则匹配、前件覆盖和完整覆盖计数。

代码目录：`src/online_trade/patterns/`

## D Chenrui XIANG

邮箱：cxiang359@connect.hkust-gz.edu.cn

主责：公平实验与未来评价

任务：定义评价口径、全局与局部及随机对照、验证期配置选择、未来测试、配对区间；整合报告。

交付：实验配置、预算曲线、未来评价表、区间、Report.pdf。

复核：Anqi ZHAO 的规则预算、筛选流程及时间边界。

代码目录：`src/online_trade/evaluation/`

## 交接与共同责任

A 输出购物篮与历史订单；B 输出真实及随机标签；C 输出规则及预算配置；D 输出统一评价表。第一周用小样本贯通接口。数据无后续订单不等于规则失败。

C 整合海报，D 整合报告；A 负责 README、复现与最终 ZIP，B 负责群体分析与随机对照。提交前由另一成员复核。四人均参与答辩和个人同伴评价。

会议时间与课程截止见根目录 README。
