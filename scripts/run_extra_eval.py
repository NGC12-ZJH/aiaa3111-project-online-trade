"""Run the registered extra evaluations: python scripts/run_extra_eval.py {e10,e9,e5}."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from online_trade.extra_eval import run  # noqa: E402

if __name__ == "__main__":
    steps = sys.argv[1:] or ["e10", "e9", "e5"]
    for step in steps:
        getattr(run, f"run_{step}")()
