#!/usr/bin/env python3
"""Run the complete Online Retail II processing and validation workflow."""

from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from online_trade.data import config  # noqa: E402
from online_trade.data.pipeline import process  # noqa: E402
from online_trade.data.policy_audit import main as policy_audit_main  # noqa: E402
from online_trade.data.time_conflicts import main as time_conflicts_main  # noqa: E402
from online_trade.data.validation import main as validation_main  # noqa: E402


def main() -> int:
    process(config.INPUT_XLSX, config.OUTPUT_DIR)
    policy_audit_main()
    time_conflicts_main()
    return validation_main()


if __name__ == "__main__":
    sys.exit(main())
