#!/usr/bin/env python3
"""Run task B: compare, select and profile RFM clusterings and build random control groups.

Usage (from the repository root):
    python scripts/run_clustering.py
    python scripts/run_clustering.py --bootstrap-repeats 5   # quick trial run
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
                        help="orders table produced by task A")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/experiment.json")
    parser.add_argument("--bootstrap-repeats", type=int, default=None,
                        help="override the configured bootstrap repeats (quick trials only)")
    args = parser.parse_args()

    experiment = json.loads(args.config.read_text(encoding="utf-8"))
    candidates, profile, sensitivity = run(experiment, args.orders, ROOT, args.bootstrap_repeats)
    print("\nCandidates:\n", candidates.to_string(index=False))
    print("\nSelected clustering profile:\n", profile.to_string())
    print("\nSensitivity:\n", sensitivity.to_string(index=False))


if __name__ == "__main__":
    main()
