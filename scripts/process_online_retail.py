#!/usr/bin/env python3
"""Run the Online Retail data-processing pipeline from the repository root."""

from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from online_trade.data.pipeline import main  # noqa: E402


if __name__ == "__main__":
    main()

