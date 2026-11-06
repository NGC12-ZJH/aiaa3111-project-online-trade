"""Load the versioned Online Retail II four-period configuration."""

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DATASET_ROOT = REPOSITORY_ROOT
CONFIG_PATH = REPOSITORY_ROOT / "configs" / "data_processing.json"
EXPERIMENT_CONFIG_PATH = REPOSITORY_ROOT / "configs" / "experiment.json"
EXPERIMENT_EXAMPLE_PATH = REPOSITORY_ROOT / "configs" / "experiment.example.json"

with CONFIG_PATH.open("r", encoding="utf-8") as stream:
    CONFIG = json.load(stream)
with EXPERIMENT_CONFIG_PATH.open("r", encoding="utf-8") as stream:
    EXPERIMENT_CONFIG = json.load(stream)
with EXPERIMENT_EXAMPLE_PATH.open("r", encoding="utf-8") as stream:
    EXPERIMENT_EXAMPLE = json.load(stream)

INPUT_XLSX = REPOSITORY_ROOT / CONFIG["dataset"]["input_xlsx"]
EXPECTED_INPUT_SHA256 = CONFIG["dataset"]["expected_sha256"]
OUTPUT_DIR = REPOSITORY_ROOT / CONFIG["output_dir"]
WORKSHEETS = CONFIG["worksheets"]
FIELD_MAPPING = CONFIG["field_mapping"]
CROSS_SHEET_POLICY = CONFIG["cross_sheet_policy"]

# Left-closed, right-open date windows. December 2011 is intentionally out of scope.
SPLITS = CONFIG["splits"]


def _experiment_splits(payload: dict) -> dict[str, list[str]]:
    return {
        name: [payload[name]["start"], payload[name]["end_exclusive"]]
        for name in ("profile", "discovery", "validation", "test")
    }


for experiment_path, experiment_payload in [
    (EXPERIMENT_CONFIG_PATH, EXPERIMENT_CONFIG),
    (EXPERIMENT_EXAMPLE_PATH, EXPERIMENT_EXAMPLE),
]:
    if _experiment_splits(experiment_payload) != SPLITS:
        raise ValueError(
            f"Split boundaries disagree between {CONFIG_PATH} and {experiment_path}"
        )

# Administrative/service codes excluded from product baskets and merchandise amounts.
# Review special_stock_codes.csv before freezing the final research protocol.
NON_PRODUCT_STOCK_CODES = set(CONFIG["non_product_stock_codes"])

# Zero-price lines and duplicate candidates remain in the auditable clean table. These
# switches determine whether they enter the main amount and basket views.
INCLUDE_ZERO_PRICE_IN_BASKETS = bool(CONFIG["include_zero_price_in_baskets"])
RETAIN_EXACT_DUPLICATE_CANDIDATES = bool(CONFIG["retain_exact_duplicate_candidates"])

# Deterministic audit sample sizes.
AUDIT_SAMPLE_PER_CATEGORY = int(CONFIG["audit_sample_per_category"])
EXTREME_LINE_LIMIT = int(CONFIG["extreme_line_limit"])
EXTREME_ORDER_LIMIT = int(CONFIG["extreme_order_limit"])

