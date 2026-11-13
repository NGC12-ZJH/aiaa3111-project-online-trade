# scripts

Online Retail II 数据处理的统一入口：

```bash
python3 scripts/run_all.py
```

运行顺序为主处理、重复和零价格敏感性、时间冲突检查及最终验证。只有显示
`Validation passed` 后，输出才能交给 B、C、D。

单独入口：

| 文件 | 作用 |
|---|---|
| `process_online_retail_ii.py` | 生成逐行证据、订单和购物篮 |
| `inspect_data_policy.py` | 生成重复与零价格敏感性文件 |
| `check_time_conflicts.py` | 检查多时间戳订单是否跨时期 |
| `validate_data_outputs.py` | 验证全部输出和 manifest |
| `run_all.py` | 按正确顺序执行以上完整流程 |

算法实现位于 `src/online_trade/data/`，配置位于 `configs/`。
