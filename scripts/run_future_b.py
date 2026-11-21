"""Future work B pre-check (registered in configs/future_B/precheck.json): python scripts/run_future_b.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from online_trade.future_b import precheck  # noqa: E402

if __name__ == "__main__":
    precheck.run()
