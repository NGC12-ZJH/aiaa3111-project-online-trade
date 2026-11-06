# Scripts

从仓库根目录运行完整流程：

```bash
python3 "new dataset/scripts/run_all.py"
```

也可以依次运行：

```text
process_online_retail_ii.py
inspect_data_policy.py
check_time_conflicts.py
validate_data_outputs.py
```

核心逻辑放在相邻的 `src/`，脚本只负责读取配置和调用模块。

