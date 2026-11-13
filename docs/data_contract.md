# 模块交接协议

以下是初始约定，字段变动应由四人共同确认。

| 输出方 | 数据 | 最低字段 |
|---|---|---|
| A | 购物篮 | basket_id, customer_id, invoice_date, items, split |
| A | 历史订单 | customer_id, basket_id, invoice_date, valid_amount |
| B | 顾客群体 | customer_id, cluster_id, recency, frequency, monetary, fitted_until |
| B | 随机分组 | customer_id, random_group_id, seed |
| C | 规则 | rule_id, group_id, antecedent, consequent, antecedent_count, joint_count, support, confidence, lift, config_id |
| D | 评价 | method, period, n_customers, n_baskets, actual_rule_count, coverage, config_id |

商品/顾客/订单标识按字符串保存。items、antecedent、consequent 使用无重复商品列表；CSV 中如需存列表，用合法 JSON 编码，不能使用 Python repr。全局规则 group_id 使用明确值 GLOBAL。可重新生成的清洗中间数据放 `data/interim/`；未检查、私密或外部共享的处理文件放 `data/processed/local/`，两处均被忽略。经检查的最终交接数据和小样本可按根目录 README 的规则选择性提交到 `data/processed/`，并在该目录 README 登记版本、校验值和获取/生成方式。

同一购物篮匹配多条规则只计一次覆盖；未来前件数量为零时 confidence 不可估；随机分组在顾客级执行。每个配置记录时间切分、阈值、预算、种子和代码版本。系统总规则预算比较与每用户规则预算比较分别报告。
