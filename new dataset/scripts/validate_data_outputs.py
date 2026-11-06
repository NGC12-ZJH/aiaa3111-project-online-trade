#!/usr/bin/env python3
"""Validate all generated Online Retail data outputs."""

from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from online_retail_ii.validation import main  # noqa: E402


if __name__ == "__main__":
    main()

