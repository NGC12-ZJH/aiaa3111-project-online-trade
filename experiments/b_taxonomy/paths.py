"""Shared paths and pinned input versions for the taxonomy_v0 experiment."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "b_taxonomy"

# Pinned upstream inputs (read with `git show <commit>:<path>`; nothing is re-cleaned here).
SNAPSHOT_COMMIT = "2ae672b7ea6edb7f5e1561b6a64823004dea833e"  # origin/a/online-retail-ii-data-snapshot
C_PATTERN_COMMIT = "fb734c4a654d9d473a57fca33f7e1266b4bc3260"  # origin/c/pattern-mining
SNAPSHOT_FILES = {
    "clean_transactions.csv.gz": "data/processed/A_data_preparation/clean_transactions.csv.gz",
    "baskets_long.csv.gz": "data/processed/A_data_preparation/baskets_long.csv.gz",
    "customer_clusters.csv": "data/processed/B_customer_clustering/customer_clusters.csv",
    "random_groups.csv": "data/processed/B_customer_clustering/random_groups.csv",
}
C_FILES = {
    "rule_evidence.csv.gz": "experiments/c_pattern/patterns/rule_evidence.csv.gz",
    "product_names.csv": "experiments/c_pattern/pattern_analysis/product_names.csv",
}

# Local-only inputs and caches (git-ignored: data/processed/local/).
INPUT = ROOT / "data" / "processed" / "local" / "b_taxonomy_inputs"
CACHE = ROOT / "data" / "processed" / "local" / "b_taxonomy_cache"

# Committed outputs (no customer identifiers).
TAXONOMY = ROOT / "data" / "taxonomy"
RESULTS = EXP / "results"

# Text-embedding model used only to propose clusters (pinned Hugging Face revision).
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"

# Schema items: codes first seen before Validation starts.
SCHEMA_CUTOFF = "2010-12-01"
N_CLUSTERS = 120
SEED = 42

# Rule thresholds copied from C's development config (discovery_dev_v1).
THRESHOLDS = dict(min_support=0.01, min_joint=20, min_ante=20, min_conf=0.2, min_lift=1.0)
BUDGET50_ALLOCATION = {"0": 5, "1": 15, "2": 30}  # C's largest-remainder split of budget 50

for p in (INPUT, CACHE, TAXONOMY, RESULTS):
    p.mkdir(parents=True, exist_ok=True)
