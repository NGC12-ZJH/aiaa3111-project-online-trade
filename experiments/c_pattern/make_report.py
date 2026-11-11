from pathlib import Path
import csv,json
r=Path(__file__).resolve().parent
rows=list(csv.DictReader((r/'results/summary.csv').open()))
m=json.loads((r/'results/manifest.json').read_text())
lines=['Discovery CPU FP-Growth / CPU Apriori 对照实验','',f'数据：{m["n_baskets"]} 个合格购物篮，{m["customers"]} 位历史顾客，{m["items"]} 种商品；含 {m["single_item_baskets"]} 个单商品篮。','时间窗口：2010-06-01（含）至2010-12-01（不含）。','方法：相同稠密布尔输入、相同支持度与最长项集长度；每设置每算法3个独立进程，交替顺序；Apriori low_memory=False。','结果：全部12次成对比较的项集及整数计数完全一致，所有返回项集均已从原矩阵逐条重算核验。','','支持度 | 最大长度 | 算法 | 项集数 | 挖掘中位秒 | 最小-最大秒 | 采样峰值中位MiB']
for z in rows:
 lines.append(f'{float(z["support"]):.0%} | {z["max_len"]} | {z["algorithm"]} | {z["n_itemsets"]} | {float(z["mining_median_s"]):.3f} | {float(z["mining_min_s"]):.3f}-{float(z["mining_max_s"]):.3f} | {float(z["peak_median_mib"]):.1f}')
lines += ['','解释：本机本轮设置下，依据上表比较效率；不代表所有数据和实现的普遍结论。','计时仅含挖掘调用，数据清洗、共同编码、导入、核验和写文件不计入。另有加载已编码矩阵加挖掘时间保存在 runs.csv。','内存为约5ms采样的进程RSS峰值，含Python、输入、算法及输出，并非纯算法额外占用；采样可能漏掉短峰。增量及Windows进程峰值另存 runs.csv。','首次运行与后续运行可能受系统缓存、分页和后台程序影响，保留全部重复，不剔除慢值。','本轮为全局合格Discovery项集算法对照，不是G/L/R未来效果实验，也不为项目选择最终支持度。','未生成或测试关联规则；未查看Validation/Test性能；未上传GitHub。','', '复现：在本目录执行 .\\.venv\\Scripts\\python.exe benchmark.py','数据完整性复核：python audit_data.py','完整口径见 README_benchmark.md；依赖见 requirements-lock.txt。']
(r/'实验结果说明.txt').write_text('\n'.join(lines),encoding='utf-8')
