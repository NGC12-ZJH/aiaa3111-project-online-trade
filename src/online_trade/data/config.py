"""Configuration for the Online Retail data-processing pipeline."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
INPUT_XLSX = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

# Left-closed, right-open date windows. December 2011 is intentionally out of scope.
SPLITS = {
    "profile": ("2010-12-01T00:00:00", "2011-04-01T00:00:00"),
    "discovery": ("2011-04-01T00:00:00", "2011-07-01T00:00:00"),
    "validation": ("2011-07-01T00:00:00", "2011-09-01T00:00:00"),
    "test": ("2011-09-01T00:00:00", "2011-12-01T00:00:00"),
}

# Administrative/service codes excluded from product baskets and merchandise amounts.
# Review special_stock_codes.csv before freezing the final research protocol.
NON_PRODUCT_STOCK_CODES = {
    "AMAZONFEE",
    "B",
    "BANK CHARGES",
    "C2",
    "CRUK",
    "D",
    "DOT",
    "DCGS0055",
    "DCGS0057",
    "DCGS0066P",
    "DCGS0067",
    "DCGS0068",
    "DCGS0071",
    "DCGS0072",
    "DCGS0073",
    "DCGS0074",
    "GIFT_0001_10",
    "GIFT_0001_20",
    "GIFT_0001_30",
    "GIFT_0001_40",
    "GIFT_0001_50",
    "M",
    "PADS",
    "POST",
    "S",
}

# Main protocol: zero-price items remain available for audit and sensitivity analysis,
# but do not enter the main baskets or define an RFM-valid order.
INCLUDE_ZERO_PRICE_IN_BASKETS = False

# Main protocol removes subsequent exact duplicate candidates. The raw row and flag
# remain in clean_transactions, and orders retains the with-duplicates amounts.
RETAIN_EXACT_DUPLICATE_CANDIDATES = False

# Deterministic audit sample sizes.
AUDIT_SAMPLE_PER_CATEGORY = 5
EXTREME_LINE_LIMIT = 50
EXTREME_ORDER_LIMIT = 50

