#!/usr/bin/env python3
"""Validate Online Retail II four-period outputs in the main repository layout."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
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


def expected_canonical_source(sheet_name: str, date_text: str) -> bool:
    if not date_text or sheet_name not in config.WORKSHEETS:
        return False
    value = datetime.fromisoformat(date_text)
    policy = config.WORKSHEETS[sheet_name]
    return (
        datetime.fromisoformat(policy["canonical_start"])
        <= value
        < datetime.fromisoformat(policy["canonical_end_exclusive"])
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
        "sheet_reconciliation_summary.csv", "cross_sheet_overlap_exclusions.csv",
        "cross_sheet_invoice_conflicts.csv", "four_period_retention_summary.csv",
        "period_eligibility_summary.csv",
    ]
    errors: list[str] = []
    for filename in required_files:
        path = output_dir / filename
        require(path.exists() and path.stat().st_size > 0, f"Missing or empty output: {filename}", errors)
    if errors:
        return errors

    source_ids: set[str] = set()
    clean_count = 0
    canonical_count = 0
    cross_sheet_overlap_excluded_count = 0
    with open_csv(output_dir / "clean_transactions.csv.gz") as stream:
        for row in csv.DictReader(stream):
            clean_count += 1
            source_id = row["source_row_id"]
            require(source_id not in source_ids, f"Duplicate source_row_id: {source_id}", errors)
            source_ids.add(source_id)
            require(row["split"] == expected_split(row["invoice_datetime"]), f"Wrong split for source row {source_id}", errors)
            expected_canonical = expected_canonical_source(row["source_sheet"], row["invoice_datetime"])
            is_canonical = row["is_canonical_source_row"] == "1"
            is_overlap_excluded = row["is_cross_sheet_overlap_excluded"] == "1"
            require(is_canonical == expected_canonical, f"Wrong canonical-source flag for source row {source_id}", errors)
            if is_canonical:
                canonical_count += 1
            else:
                require(row["is_valid_basket_item"] == "0", f"Noncanonical row entered basket: {source_id}", errors)
                require(row["is_valid_amount_line"] == "0", f"Noncanonical row entered amount: {source_id}", errors)
                require(row["is_exact_duplicate_candidate"] == "0", f"Noncanonical row entered duplicate policy: {source_id}", errors)
            if is_overlap_excluded:
                cross_sheet_overlap_excluded_count += 1
                require(not is_canonical, f"Overlap-excluded row is canonical: {source_id}", errors)
            if len(errors) >= 100:
                return errors
    require(source_ids == {str(value) for value in range(1, clean_count + 1)}, "source_row_id values are not contiguous from 1", errors)

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

    with (output_dir / "sheet_reconciliation_summary.csv").open("r", encoding="utf-8", newline="") as stream:
        reconciliation = {row["name"]: row for row in csv.DictReader(stream)}
    require(
        int(reconciliation["only_first_sheet_rows"]["physical_rows"]) == 0,
        "Overlap contains rows unique to first worksheet",
        errors,
    )
    require(
        int(reconciliation["only_second_sheet_rows"]["physical_rows"]) == 0,
        "Overlap contains rows unique to second worksheet",
        errors,
    )
    require(
        int(reconciliation["differing_invoice_multisets"]["physical_rows"]) == 0,
        "Overlap contains differing invoice contents",
        errors,
    )
    with (output_dir / "cross_sheet_invoice_conflicts.csv").open("r", encoding="utf-8", newline="") as stream:
        require(sum(1 for _ in csv.DictReader(stream)) == 0, "Cross-sheet conflict file contains invoices", errors)

    with (output_dir / "run_manifest.json").open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    require(manifest["headline_counts"]["raw_data_rows"] == clean_count, "Manifest raw row count mismatch", errors)
    require(manifest["headline_counts"]["canonical_source_rows"] == canonical_count, "Manifest canonical row count mismatch", errors)
    require(
        manifest["headline_counts"]["cross_sheet_overlap_excluded_rows"] == cross_sheet_overlap_excluded_count,
        "Manifest overlap-excluded row count mismatch",
        errors,
    )
    require(manifest["headline_counts"]["invoice_count"] == len(order_ids), "Manifest invoice count mismatch", errors)
    require(manifest["headline_counts"]["valid_basket_count"] == len(basket_ids), "Manifest basket count mismatch", errors)
    return errors


def finalize_manifest(output_dir: Path) -> None:
    manifest_path = output_dir / "run_manifest.json"
    with manifest_path.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    metadata = []
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.name == "run_manifest.json":
            continue
        entry = {
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        if path.name.endswith(".csv") or path.name.endswith(".csv.gz"):
            with open_csv(path) as stream:
                entry["data_rows"] = sum(1 for _ in csv.DictReader(stream))
        metadata.append(entry)
    manifest["outputs"] = [entry["filename"] for entry in metadata]
    manifest["output_metadata"] = metadata
    with manifest_path.open("w", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main() -> int:
    args = parse_args()
    errors = validate(args.output_dir)
    if errors:
        print("Validation failed:")
        for error in errors[:100]:
            print(f"- {error}")
        return 1
    finalize_manifest(args.output_dir)
    print("Validation passed: all required files, reconciliations, split boundaries, baskets, and eligibility checks are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

