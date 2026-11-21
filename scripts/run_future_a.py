"""Future work A (registered in configs/future_A/): python scripts/run_future_a.py {precheck,round2,p5}"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

STEPS = {"precheck": "online_trade.future_a.precheck", "round2": "online_trade.future_a.round2",
         "p5": "online_trade.future_a.hmm"}

if __name__ == "__main__":
    for step in sys.argv[1:] or ["precheck"]:
        if step not in STEPS:
            raise SystemExit(f"unknown step {step}; choose from {sorted(STEPS)}")
        importlib.import_module(STEPS[step]).run()
