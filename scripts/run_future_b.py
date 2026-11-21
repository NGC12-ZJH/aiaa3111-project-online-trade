"""Future work B (configs/future_B/): python scripts/run_future_b.py [precheck|experiment]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from online_trade.future_b import comparisons, experiment, precheck  # noqa: E402

if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "precheck"
    {"precheck": precheck.run, "experiment": experiment.run, "comparisons": comparisons.run}[step]()
