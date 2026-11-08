#!/usr/bin/env python3
"""运行 B 模块：Profile 期 RFM 分群比较、选择、随机分组与画像。

用法（仓库根目录）：
    python scripts/run_clustering.py
    python scripts/run_clustering.py --bootstrap-repeats 5   # 快速试跑
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from online_trade.clustering.pipeline import run  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--orders", type=Path, default=ROOT / "data/processed/orders.csv.gz",
                        help="A 输出的订单表（默认 data/processed/orders.csv.gz）")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/experiment.json")
    parser.add_argument("--bootstrap-repeats", type=int, default=None,
                        help="覆盖配置中的抽样次数，仅用于快速试跑")
    args = parser.parse_args()

    experiment = json.loads(args.config.read_text(encoding="utf-8"))
    candidates, profile, sensitivity = run(experiment, args.orders, ROOT, args.bootstrap_repeats)
    print("\nCandidates:\n", candidates.to_string(index=False))
    print("\nSelected clustering profile:\n", profile.to_string())
    print("\nSensitivity:\n", sensitivity.to_string(index=False))


if __name__ == "__main__":
    main()
