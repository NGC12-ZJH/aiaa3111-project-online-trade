#!/usr/bin/env python3
"""Validate the outputs produced by process_data.py."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from . import config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=config.OUTPUT_DIR)
    return parser.parse_args()


def open_csv(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def expected_split(date_text: str) -> str:
    if not date_text:
        return "invalid_date"
    value = datetime.fromisoformat(date_text)
    for name, (start, end) in config.SPLITS.items():
        if datetime.fromisoformat(start) <= value < datetime.fromisoformat(end):
            return name
    return "out_of_scope"


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate(output_dir: Path) -> list[str]:
    required_files = [
        "clean_transactions.csv.gz", "orders.csv.gz", "baskets.csv.gz", "baskets_long.csv.gz",
        "audit_summary.csv", "exclusion_summary.csv", "invoice_conflicts.csv",
        "time_conflict_stage_check.csv",
        "special_stock_codes.csv", "extreme_lines.csv", "extreme_orders.csv",
        "audit_order_samples.csv", "duplicate_sensitivity_summary.csv",
        "zero_price_summary.csv", "zero_price_codes.csv", "run_manifest.json",
    ]
    errors: list[str] = []
    for filename in required_files:
        path = output_dir / filename
        require(path.exists() and path.stat().st_size > 0, f"Missing or empty output: {filename}", errors)
    if errors:
        return errors

    source_ids: set[str] = set()
    clean_count = 0
    with open_csv(output_dir / "clean_transactions.csv.gz") as stream:
        for row in csv.DictReader(stream):
            clean_count += 1
            source_id = row["source_row_id"]
            require(source_id not in source_ids, f"Duplicate source_row_id: {source_id}", errors)
            source_ids.add(source_id)
            require(row["split"] == expected_split(row["invoice_datetime"]), f"Wrong split for source row {source_id}", errors)
            if len(errors) >= 100:
                return errors

    order_ids: set[str] = set()
    order_lookup: dict[str, dict] = {}
    with open_csv(output_dir / "orders.csv.gz") as stream:
        for row in csv.DictReader(stream):
            basket_id = row["basket_id"]
            require(basket_id not in order_ids, f"Duplicate order id: {basket_id}", errors)
            order_ids.add(basket_id)
            order_lookup[basket_id] = row
            gross = Decimal(row["gross_purchase_amount"])
            returns = Decimal(row["return_amount"])
            net = Decimal(row["net_amount"])
            require(row["invoice_date"] == row["invoice_datetime"], f"Order date alias mismatch for {basket_id}", errors)
            require(Decimal(row["valid_amount"]) == gross, f"Valid amount alias mismatch for {basket_id}", errors)
            require(gross - returns == net, f"Amount reconciliation failed for {basket_id}", errors)
            gross_with_duplicates = Decimal(row["gross_purchase_amount_with_duplicates"])
            returns_with_duplicates = Decimal(row["return_amount_with_duplicates"])
            net_with_duplicates = Decimal(row["net_amount_with_duplicates"])
            require(
                gross_with_duplicates - returns_with_duplicates == net_with_duplicates,
                f"With-duplicates amount reconciliation failed for {basket_id}",
                errors,
            )
            require(gross <= gross_with_duplicates, f"Main gross exceeds with-duplicates gross for {basket_id}", errors)
            require(row["split"] == expected_split(row["invoice_datetime"]), f"Wrong order split for {basket_id}", errors)
            if row["is_eligible_for_main_comparison"] == "1":
                require(row["is_valid_order"] == "1", f"Eligible order is invalid: {basket_id}", errors)
                require(row["is_valid_rfm_order"] == "1", f"Eligible order has no positive-price product: {basket_id}", errors)
                require(row["is_identified_customer"] == "1", f"Eligible order lacks identified customer: {basket_id}", errors)
                require(row["is_profile_customer"] == "1", f"Eligible order is not a profile customer: {basket_id}", errors)

    basket_ids: set[str] = set()
    expected_long_pairs: set[tuple[str, str]] = set()
    with open_csv(output_dir / "baskets.csv.gz") as stream:
        for row in csv.DictReader(stream):
            basket_id = row["basket_id"]
            require(basket_id not in basket_ids, f"Duplicate basket id: {basket_id}", errors)
            basket_ids.add(basket_id)
            require(basket_id in order_lookup, f"Basket missing from orders: {basket_id}", errors)
            require(row["invoice_date"] == row["invoice_datetime"], f"Basket date alias mismatch for {basket_id}", errors)
            items = json.loads(row["items"])
            require(bool(items), f"Empty basket: {basket_id}", errors)
            require(len(items) == len(set(items)), f"Duplicate item within basket: {basket_id}", errors)
            require(len(items) == int(row["basket_size"]), f"Basket size mismatch: {basket_id}", errors)
            require(not (set(items) & config.NON_PRODUCT_STOCK_CODES), f"Non-product item in basket: {basket_id}", errors)
            expected_long_pairs.update((basket_id, item) for item in items)

    actual_long_pairs: set[tuple[str, str]] = set()
    with open_csv(output_dir / "baskets_long.csv.gz") as stream:
        for row in csv.DictReader(stream):
            pair = (row["basket_id"], row["stock_code"])
            require(row["invoice_date"] == row["invoice_datetime"], f"Basket-long date alias mismatch for {pair}", errors)
            require(pair not in actual_long_pairs, f"Duplicate basket-item pair: {pair}", errors)
            actual_long_pairs.add(pair)
    require(actual_long_pairs == expected_long_pairs, "baskets_long does not match baskets item sets", errors)

    with (output_dir / "run_manifest.json").open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    require(manifest["headline_counts"]["raw_data_rows"] == clean_count, "Manifest raw row count mismatch", errors)
    require(manifest["headline_counts"]["invoice_count"] == len(order_ids), "Manifest invoice count mismatch", errors)
    require(manifest["headline_counts"]["valid_basket_count"] == len(basket_ids), "Manifest basket count mismatch", errors)
    return errors


def main() -> int:
    args = parse_args()
    errors = validate(args.output_dir)
    if errors:
        print("Validation failed:")
        for error in errors[:100]:
            print(f"- {error}")
        return 1
    print("Validation passed: all required files, reconciliations, split boundaries, baskets, and eligibility checks are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

