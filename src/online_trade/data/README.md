# A 数据处理与复现

负责人：Qingyang LI（qli863@connect.hkust-gz.edu.cn）

清洗订单、构建购物篮、时间切分、顾客留存审计、数据敏感性分析、README 与最终复现打包。

已实现 Online Retail II 双工作表流式读取、跨表重叠核验、规范来源选择、清洗标记、订单聚合、购物篮、四时期切分、Profile 客户资格、留存/敏感性审计和输出验证。

交付：`clean_transactions.csv.gz`、`orders.csv.gz`、`baskets.csv.gz`、`baskets_long.csv.gz`、审计文件和 manifest。

运行：

```bash
python3 scripts/run_all.py
```

字段和完整规则见[数据处理说明](../../../docs/data_processing_guide.md)，模块接口见[数据接口](../../../docs/data_contract.md)。
