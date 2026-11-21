"""Future work A pre-check (registered in configs/future_A/precheck.json): python scripts/run_future_a.py precheck"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from online_trade.future_a import precheck  # noqa: E402

if __name__ == "__main__":
    steps = sys.argv[1:] or ["precheck"]
    for step in steps:
        if step != "precheck":
            raise SystemExit(f"unknown step {step}")
        precheck.run()
