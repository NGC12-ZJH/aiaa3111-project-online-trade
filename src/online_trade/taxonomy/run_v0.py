"""Run the original v0 pipeline through the repository's taxonomy entry point."""
import subprocess
import sys

from .paths import ROOT

STEPS = ["prepare_inputs", "explore_item_rules", "explore_baskets", "step1_catalog_cluster",
         "step2_tag", "step3_concept_mining", "step4_checks"]


def main():
    for step in STEPS:
        print(f"\n===== {step} =====", flush=True)
        subprocess.run([sys.executable, str(ROOT / "scripts/run_taxonomy.py"), step],
                       cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
