"""Load the versioned Online Retail data-processing configuration."""

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = PROJECT_ROOT / "configs" / "data_processing.json"

with CONFIG_PATH.open("r", encoding="utf-8") as stream:
    CONFIG = json.load(stream)

INPUT_XLSX = PROJECT_ROOT / CONFIG["input_xlsx"]
OUTPUT_DIR = PROJECT_ROOT / CONFIG["output_dir"]

# Left-closed, right-open date windows. December 2011 is intentionally out of scope.
SPLITS = CONFIG["splits"]

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

