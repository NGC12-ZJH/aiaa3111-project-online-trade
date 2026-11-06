#!/usr/bin/env python3
"""Create decision-support summaries for duplicates and zero-price lines."""

from __future__ import annotations

import csv
import gzip
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from . import config


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    output_dir = config.OUTPUT_DIR
    duplicate_rows = 0
    duplicate_invoices: set[str] = set()
    duplicate_customers: set[str] = set()
    duplicate_amount = Decimal("0")
    duplicate_positive_amount = Decimal("0")
    duplicate_return_amount = Decimal("0")
    duplicate_by_split = Counter()
    zero_rows = 0
    zero_invoices: set[str] = set()
    zero_customers: set[str] = set()
    zero_by_split = Counter()
    zero_codes = Counter()
    zero_descriptions: dict[str, Counter] = defaultdict(Counter)

    with gzip.open(output_dir / "clean_transactions.csv.gz", "rt", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["is_canonical_source_row"] != "1":
                continue
            if row["is_exact_duplicate_candidate"] == "1":
                duplicate_rows += 1
                duplicate_invoices.add(row["invoice_id"])
                if row["customer_id"]:
                    duplicate_customers.add(row["customer_id"])
                amount = Decimal(row["line_amount"])
                duplicate_amount += amount
                if amount > 0 and row["is_cancelled_invoice"] == "0":
                    duplicate_positive_amount += amount
                if amount < 0 or row["is_cancelled_invoice"] == "1":
                    duplicate_return_amount += abs(amount)
                duplicate_by_split[row["split"]] += 1
            if row["is_zero_price"] == "1":
                zero_rows += 1
                zero_invoices.add(row["invoice_id"])
                if row["customer_id"]:
                    zero_customers.add(row["customer_id"])
                zero_by_split[row["split"]] += 1
                zero_codes[row["stock_code"]] += 1
                if row["description"]:
                    zero_descriptions[row["stock_code"]][row["description"]] += 1

    duplicate_summary = [
        {"metric": "duplicate_candidate_extra_rows", "value": duplicate_rows},
        {"metric": "affected_invoices", "value": len(duplicate_invoices)},
        {"metric": "affected_identified_customers", "value": len(duplicate_customers)},
        {"metric": "all_duplicate_candidate_line_amount", "value": str(duplicate_amount.quantize(Decimal("0.01")))},
        {"metric": "positive_purchase_amount_if_removed", "value": str(duplicate_positive_amount.quantize(Decimal("0.01")))},
        {"metric": "return_amount_if_removed", "value": str(duplicate_return_amount.quantize(Decimal("0.01")))},
        *({"metric": f"rows_in_{split}", "value": count} for split, count in sorted(duplicate_by_split.items())),
    ]
    write_csv(output_dir / "duplicate_sensitivity_summary.csv", ["metric", "value"], duplicate_summary)

    zero_summary = [
        {"metric": "zero_price_rows", "value": zero_rows},
        {"metric": "affected_invoices", "value": len(zero_invoices)},
        {"metric": "affected_identified_customers", "value": len(zero_customers)},
        *({"metric": f"rows_in_{split}", "value": count} for split, count in sorted(zero_by_split.items())),
    ]
    write_csv(output_dir / "zero_price_summary.csv", ["metric", "value"], zero_summary)
    zero_code_rows = [
        {
            "stock_code": code,
            "line_count": count,
            "top_descriptions": json.dumps(zero_descriptions[code].most_common(5), ensure_ascii=False),
        }
        for code, count in zero_codes.most_common()
    ]
    write_csv(output_dir / "zero_price_codes.csv", ["stock_code", "line_count", "top_descriptions"], zero_code_rows)
    print(json.dumps({
        "duplicate_candidate_rows": duplicate_rows,
        "duplicate_affected_invoices": len(duplicate_invoices),
        "duplicate_positive_amount_if_removed": str(duplicate_positive_amount.quantize(Decimal("0.01"))),
        "zero_price_rows": zero_rows,
        "zero_price_affected_invoices": len(zero_invoices),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
