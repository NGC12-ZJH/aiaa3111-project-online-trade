# 实验与运行记录

| 日期 | 负责人 | 运行 | 配置/代码状态 | 结果 | 验证与限制 |
|---|---|---|---|---|---|
| 2026-11-06 | Qingyang LI | Online Retail II 四时期数据准备基线 | `data_processing.json` v1；Git 基线 `0312759`；`new dataset` 尚未提交 | 1,067,371 物理明细；1,044,848 规范明细；53,628 订单；39,516 购物篮；2,684 profile客户 | 全部自动验证通过；83个多时间订单均未跨阶段；跨表冲突为0；两次独立运行核心文件哈希一致。特殊编码名单在正式建模前仍应由另一成员复核。 |

运行命令：

```bash
python3 "new dataset/scripts/run_all.py"
```

完整输出文件哈希、大小和行数见本地 `data/processed/run_manifest.json`。

