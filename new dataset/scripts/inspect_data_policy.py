#!/usr/bin/env python3
"""Generate duplicate and zero-price policy sensitivity summaries."""

from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from online_retail_ii.policy_audit import main  # noqa: E402


if __name__ == "__main__":
    main()

