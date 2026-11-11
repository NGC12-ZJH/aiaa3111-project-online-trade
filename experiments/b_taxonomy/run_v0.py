"""Run the whole taxonomy_v0 experiment in order. Usage: python experiments/b_taxonomy/run_v0.py"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = ["prepare_inputs.py", "explore_item_rules.py", "explore_baskets.py", "step1_catalog_cluster.py",
         "step2_tag.py", "step3_concept_mining.py", "step4_checks.py"]

for step in STEPS:
    print(f"\n===== {step} =====", flush=True)
    subprocess.run([sys.executable, str(HERE / step)], cwd=HERE, check=True)
