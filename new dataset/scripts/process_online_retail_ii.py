#!/usr/bin/env python3
"""Run the Online Retail II four-period data-processing pipeline."""

from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from online_retail_ii.pipeline import main  # noqa: E402


if __name__ == "__main__":
    main()

