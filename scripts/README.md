# scripts

数据处理模块已提供以下运行入口，应从仓库根目录依次执行：

```bash
python3 scripts/process_online_retail.py
python3 scripts/inspect_data_policy.py
python3 scripts/check_time_conflicts.py
python3 scripts/validate_data_outputs.py
```

核心逻辑位于 `src/online_trade/data/`，配置位于 `configs/data_processing.json`。其他模块稳定后继续在本目录添加统一入口。
