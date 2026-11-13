#!/usr/bin/env python3
"""Run a taxonomy workflow step from any working directory.

Examples:
  python scripts/run_taxonomy.py validate
  python scripts/run_taxonomy.py run_v0
  python scripts/run_taxonomy.py llm_tag --run R2 --offline

Step arguments are forwarded unchanged. Use <step> --help for steps with a CLI.
Reproduction steps write outputs; validate only reads committed artifacts.
"""
import argparse
from pathlib import Path
import runpy
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

STEPS = (
    "validate", "run_v0", "prepare_inputs", "explore_item_rules", "explore_baskets",
    "step1_catalog_cluster", "step2_tag", "step3_concept_mining", "step4_checks",
    "v1_step1_stats", "v1_step2_propose", "v1_step3_build", "v1_review_sheet",
    "v1_freeze", "gold_sample", "make_annotation_guide", "gold_agreement",
    "gold_finalize", "llm_client", "llm_tag", "compare_runs", "evaluate_gold",
    "v1_finalize_labels", "make_review_sheet",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=STEPS)
    parser.add_argument("step_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    sys.argv = [args.step, *args.step_args]
    runpy.run_module(f"online_trade.taxonomy.{args.step}", run_name="__main__")


if __name__ == "__main__":
    main()
