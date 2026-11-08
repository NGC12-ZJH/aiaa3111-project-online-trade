# 步骤 1 交付：数据清洗与四时期切分（A · Qingyang LI）

UCI Online Retail II 经清洗、跨表去重、四时期切分（Profile / Discovery / Validation / Test）后的全部输出。清洗思路与字段说明见 `main` 分支的 `docs/data_processing_guide.md`。

## 主交接文件

| 文件 | 粒度 / 行数 | 使用者 | 大小 / SHA-256 |
|---|---|---|---|
| `clean_transactions.csv.gz` | 一行一个物理来源明细；1,067,371 行 | A：逐行追溯和敏感性 | 26,635,161 B；`01c6a69702b675723d2d9489f5771a45ea047946875eaae699384298afc9599b` |
| `orders.csv.gz` | 一行一个规范订单；53,628 行 | B：RFM；D：评价分母 | 1,266,845 B；`2ff8420a97ed2f89a303c57a6431590e130df35936ad143350adb40a5040d4c2` |
| `baskets.csv.gz` | 一行一个有效订单购物篮；39,516 行 | D：规则命中 | 2,772,853 B；`30aef702f812ab42224271871271daff5b4e37a594696eee82208252198367bf` |
| `baskets_long.csv.gz` | 一行一个订单—商品；992,036 行 | C：FP-Growth | 3,977,938 B；`e95ae6da8b07677bdaf6ed2663c178ee44a6e9a1162a26eaa52cfeb62701f175` |
| `run_manifest.json` | 全部 20 个输出的行数、大小、哈希和运行环境 | A–D | 7,222 B；`fc26e9fe52cf62ca5853b028fc7aab78b06d4cd0d13e1ab01e7412dd4f81554e` |

其余 `.csv` 为审计表：排除原因、跨表对账、重复与零价格敏感性、极端值、订单冲突、时期资格和留存等。

## 生成方式

```bash
python3 scripts/run_all.py   # 最后显示 Validation passed 才可交接
```

处理代码基线 `301875b`，配置 `configs/data_processing.json` v1。

`run_manifest.json` 中的输出文件名相对本文件夹；其中的绝对路径只记录当时的生成环境，不是下载路径。本文件夹内容与快照提交 `ed1c57a` 逐字节相同，2026-11-08 从 `data/processed/` 移入本文件夹。
