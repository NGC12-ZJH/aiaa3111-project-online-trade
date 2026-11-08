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
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from . import config


REQUIRED_FILES = [
    "clean_transactions.csv.gz", "orders.csv.gz", "baskets.csv.gz", "baskets_long.csv.gz",
    "audit_summary.csv", "exclusion_summary.csv", "invoice_conflicts.csv",
    "time_conflict_stage_check.csv", "special_stock_codes.csv", "extreme_lines.csv",
    "extreme_orders.csv", "audit_order_samples.csv", "duplicate_sensitivity_summary.csv",
    "zero_price_summary.csv", "zero_price_codes.csv", "run_manifest.json",
    "sheet_reconciliation_summary.csv", "cross_sheet_overlap_exclusions.csv",
    "cross_sheet_invoice_conflicts.csv", "four_period_retention_summary.csv",
    "period_eligibility_summary.csv",
]


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
    errors: list[str] = []
    for filename in REQUIRED_FILES:
        path = output_dir / filename
        require(path.exists() and path.stat().st_size > 0, f"Missing or empty output: {filename}", errors)
    if errors:
        return errors

    clean_count = 0
    canonical_count = 0
    cross_sheet_overlap_excluded_count = 0
    duplicate_hashes: set[bytes] = set()
    clean_orders: dict[str, dict] = {}

    def new_order() -> dict:
        return {
            "customer_ids": set(), "countries": set(), "datetimes": set(), "items": set(),
            "gross": Decimal("0"), "returns": Decimal("0"),
            "gross_with_duplicates": Decimal("0"), "returns_with_duplicates": Decimal("0"),
            "line_count": 0, "valid_basket_line_count": 0, "valid_amount_line_count": 0,
            "duplicate_candidate_count": 0, "cancelled_line_count": 0, "non_product_line_count": 0,
        }

    def money(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    with open_csv(output_dir / "clean_transactions.csv.gz") as stream:
        for row in csv.DictReader(stream):
            clean_count += 1
            source_id = row["source_row_id"]
            require(source_id == str(clean_count), f"Non-contiguous source_row_id at row {clean_count}: {source_id}", errors)
            require(row["split"] == expected_split(row["invoice_datetime"]), f"Wrong split for source row {source_id}", errors)
            expected_canonical = expected_canonical_source(row["source_sheet"], row["invoice_datetime"])
            is_canonical = row["is_canonical_source_row"] == "1"
            is_overlap_excluded = row["is_cross_sheet_overlap_excluded"] == "1"
            require(is_canonical == expected_canonical, f"Wrong canonical-source flag for source row {source_id}", errors)

            invoice_id = row["invoice_id"]
            stock_code = row["stock_code"]
            description = row["description"]
            quantity = int(row["quantity"]) if row["quantity"] else None
            invoice_datetime = datetime.fromisoformat(row["invoice_datetime"]) if row["invoice_datetime"] else None
            unit_price = Decimal(row["unit_price"]) if row["unit_price"] else None
            customer_id = row["customer_id"]
            country = row["country"]
            raw_amount = Decimal(quantity) * unit_price if quantity is not None and unit_price is not None else Decimal("0")
            require(Decimal(row["line_amount"]) == money(raw_amount), f"Wrong line_amount for source row {source_id}", errors)

            is_cancelled = invoice_id.upper().startswith("C")
            is_negative_quantity = quantity is not None and quantity < 0
            is_zero_quantity = quantity == 0
            is_zero_price = unit_price == 0
            is_negative_price = unit_price is not None and unit_price < 0
            is_non_product = stock_code.upper() in config.NON_PRODUCT_STOCK_CODES
            expected_flags = {
                "is_cancelled_invoice": is_cancelled,
                "is_negative_quantity": is_negative_quantity,
                "is_zero_quantity": is_zero_quantity,
                "is_zero_price": is_zero_price,
                "is_negative_price": is_negative_price,
                "is_missing_customer": customer_id == "",
                "is_missing_description": description == "",
                "is_non_product": is_non_product,
            }
            for field, expected in expected_flags.items():
                require((row[field] == "1") == expected, f"Wrong {field} for source row {source_id}", errors)

            duplicate_values = (
                invoice_id, stock_code, description, quantity, invoice_datetime,
                unit_price, customer_id, country,
            )
            duplicate_text = "\x1f".join("" if value is None else str(value) for value in duplicate_values)
            duplicate_digest = hashlib.blake2b(duplicate_text.encode("utf-8"), digest_size=16).digest()
            expected_duplicate = is_canonical and duplicate_digest in duplicate_hashes
            if is_canonical:
                duplicate_hashes.add(duplicate_digest)
            require(
                (row["is_exact_duplicate_candidate"] == "1") == expected_duplicate,
                f"Wrong duplicate-candidate flag for source row {source_id}",
                errors,
            )

            base_valid_common = (
                invoice_id != "" and stock_code != "" and invoice_datetime is not None
                and quantity is not None and unit_price is not None and is_canonical
                and not is_cancelled and quantity > 0 and unit_price >= 0 and not is_non_product
            )
            valid_common = base_valid_common and (
                config.RETAIN_EXACT_DUPLICATE_CANDIDATES or not expected_duplicate
            )
            expected_valid_basket = valid_common and (
                config.INCLUDE_ZERO_PRICE_IN_BASKETS or unit_price > 0
            )
            expected_valid_amount = valid_common and unit_price > 0
            require(
                (row["is_valid_basket_item"] == "1") == expected_valid_basket,
                f"Wrong basket-valid flag for source row {source_id}", errors,
            )
            require(
                (row["is_valid_amount_line"] == "1") == expected_valid_amount,
                f"Wrong amount-valid flag for source row {source_id}", errors,
            )

            exclusion_checks = [
                (invoice_id == "", "missing_invoice"),
                (invoice_datetime is None, "invalid_date"),
                (not is_canonical, "noncanonical_source_row"),
                (stock_code == "", "missing_stock_code"),
                (quantity is None, "invalid_quantity"),
                (unit_price is None, "invalid_unit_price"),
                (is_cancelled, "cancelled_invoice"),
                (is_negative_quantity, "negative_quantity"),
                (is_zero_quantity, "zero_quantity"),
                (is_negative_price, "negative_price"),
                (is_non_product, "non_product"),
                (expected_duplicate and not config.RETAIN_EXACT_DUPLICATE_CANDIDATES, "duplicate_candidate"),
                (is_zero_price and not config.INCLUDE_ZERO_PRICE_IN_BASKETS, "zero_price"),
            ]
            expected_exclusion = next((reason for condition, reason in exclusion_checks if condition), "")
            require(
                row["primary_exclusion_reason"] == expected_exclusion,
                f"Wrong primary exclusion for source row {source_id}", errors,
            )

            if is_canonical:
                canonical_count += 1
            else:
                require(row["is_valid_basket_item"] == "0", f"Noncanonical row entered basket: {source_id}", errors)
                require(row["is_valid_amount_line"] == "0", f"Noncanonical row entered amount: {source_id}", errors)
                require(row["is_exact_duplicate_candidate"] == "0", f"Noncanonical row entered duplicate policy: {source_id}", errors)
            if is_overlap_excluded:
                cross_sheet_overlap_excluded_count += 1
                require(not is_canonical, f"Overlap-excluded row is canonical: {source_id}", errors)

            if is_canonical and invoice_id:
                order = clean_orders.setdefault(invoice_id, new_order())
                order["line_count"] += 1
                if customer_id:
                    order["customer_ids"].add(customer_id)
                if country:
                    order["countries"].add(country)
                if invoice_datetime:
                    order["datetimes"].add(invoice_datetime)
                if expected_duplicate:
                    order["duplicate_candidate_count"] += 1
                if is_cancelled:
                    order["cancelled_line_count"] += 1
                if is_non_product:
                    order["non_product_line_count"] += 1
                if expected_valid_basket:
                    order["items"].add(stock_code)
                    order["valid_basket_line_count"] += 1
                if expected_valid_amount:
                    order["gross"] += raw_amount
                    order["valid_amount_line_count"] += 1
                if base_valid_common and unit_price > 0:
                    order["gross_with_duplicates"] += raw_amount
                is_return_line = (
                    quantity is not None and unit_price is not None and unit_price >= 0
                    and bool(stock_code) and not is_non_product and (is_cancelled or quantity < 0)
                )
                if is_return_line:
                    order["returns_with_duplicates"] += abs(raw_amount)
                    if config.RETAIN_EXACT_DUPLICATE_CANDIDATES or not expected_duplicate:
                        order["returns"] += abs(raw_amount)
            if len(errors) >= 100:
                return errors

    profile_customers = {
        next(iter(order["customer_ids"]))
        for order in clean_orders.values()
        if len(order["customer_ids"]) == 1
        and order["items"]
        and expected_split(min(order["datetimes"]).isoformat(sep=" ") if order["datetimes"] else "") == "profile"
    }

    order_ids: set[str] = set()
    order_lookup: dict[str, dict] = {}
    with open_csv(output_dir / "orders.csv.gz") as stream:
        for row in csv.DictReader(stream):
            basket_id = row["basket_id"]
            require(basket_id not in order_ids, f"Duplicate order id: {basket_id}", errors)
            require(basket_id in clean_orders, f"Order missing from clean canonical lines: {basket_id}", errors)
            order_ids.add(basket_id)
            order_lookup[basket_id] = row
            if basket_id not in clean_orders:
                continue
            expected = clean_orders[basket_id]
            expected_customer = next(iter(expected["customer_ids"])) if len(expected["customer_ids"]) == 1 else ""
            expected_country = next(iter(expected["countries"])) if len(expected["countries"]) == 1 else ""
            first_datetime = min(expected["datetimes"]) if expected["datetimes"] else None
            first_datetime_text = first_datetime.isoformat(sep=" ") if first_datetime else ""
            expected_order_split = expected_split(first_datetime_text)
            has_customer_conflict = len(expected["customer_ids"]) > 1
            has_country_conflict = len(expected["countries"]) > 1
            has_datetime_conflict = len(expected["datetimes"]) > 1
            datetime_span = int((max(expected["datetimes"]) - min(expected["datetimes"])).total_seconds()) if has_datetime_conflict else 0
            is_valid_order = bool(expected["items"])
            is_valid_rfm_order = expected["valid_amount_line_count"] > 0
            is_identified = bool(expected_customer) and not has_customer_conflict
            is_profile_customer = is_identified and expected_customer in profile_customers
            is_eligible = is_valid_order and is_profile_customer and expected_order_split in config.SPLITS

            exact_fields = {
                "customer_id": expected_customer,
                "invoice_date": first_datetime_text,
                "invoice_datetime": first_datetime_text,
                "country": expected_country,
                "basket_size": str(len(expected["items"])),
                "line_count": str(expected["line_count"]),
                "valid_basket_line_count": str(expected["valid_basket_line_count"]),
                "valid_amount_line_count": str(expected["valid_amount_line_count"]),
                "split": expected_order_split,
                "is_valid_order": str(int(is_valid_order)),
                "is_valid_rfm_order": str(int(is_valid_rfm_order)),
                "is_identified_customer": str(int(is_identified)),
                "is_profile_customer": str(int(is_profile_customer)),
                "is_eligible_for_main_comparison": str(int(is_eligible)),
                "has_customer_conflict": str(int(has_customer_conflict)),
                "has_country_conflict": str(int(has_country_conflict)),
                "has_datetime_conflict": str(int(has_datetime_conflict)),
                "datetime_span_seconds": str(datetime_span),
                "duplicate_candidate_count": str(expected["duplicate_candidate_count"]),
                "cancelled_line_count": str(expected["cancelled_line_count"]),
                "non_product_line_count": str(expected["non_product_line_count"]),
            }
            for field, expected_value in exact_fields.items():
                require(row[field] == expected_value, f"Order {field} mismatch for {basket_id}", errors)

            gross = Decimal(row["gross_purchase_amount"])
            returns = Decimal(row["return_amount"])
            net = Decimal(row["net_amount"])
            require(gross == money(expected["gross"]), f"Order gross mismatch from clean lines for {basket_id}", errors)
            require(returns == money(expected["returns"]), f"Order returns mismatch from clean lines for {basket_id}", errors)
            require(row["invoice_date"] == row["invoice_datetime"], f"Order date alias mismatch for {basket_id}", errors)
            require(Decimal(row["valid_amount"]) == gross, f"Valid amount alias mismatch for {basket_id}", errors)
            require(gross - returns == net, f"Amount reconciliation failed for {basket_id}", errors)
            gross_with_duplicates = Decimal(row["gross_purchase_amount_with_duplicates"])
            returns_with_duplicates = Decimal(row["return_amount_with_duplicates"])
            net_with_duplicates = Decimal(row["net_amount_with_duplicates"])
            require(
                gross_with_duplicates == money(expected["gross_with_duplicates"]),
                f"Order gross-with-duplicates mismatch for {basket_id}", errors,
            )
            require(
                returns_with_duplicates == money(expected["returns_with_duplicates"]),
                f"Order returns-with-duplicates mismatch for {basket_id}", errors,
            )
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
            if len(errors) >= 100:
                return errors

    require(order_ids == set(clean_orders), "orders does not exactly match canonical non-empty invoice IDs", errors)

    basket_ids: set[str] = set()
    basket_lookup: dict[str, tuple[dict, set[str]]] = {}
    expected_long_count = 0
    with open_csv(output_dir / "baskets.csv.gz") as stream:
        for row in csv.DictReader(stream):
            basket_id = row["basket_id"]
            require(basket_id not in basket_ids, f"Duplicate basket id: {basket_id}", errors)
            basket_ids.add(basket_id)
            require(basket_id in order_lookup, f"Basket missing from orders: {basket_id}", errors)
            if basket_id not in order_lookup:
                continue
            order_row = order_lookup[basket_id]
            require(row["invoice_date"] == row["invoice_datetime"], f"Basket date alias mismatch for {basket_id}", errors)
            items = json.loads(row["items"])
            require(bool(items), f"Empty basket: {basket_id}", errors)
            require(len(items) == len(set(items)), f"Duplicate item within basket: {basket_id}", errors)
            require(items == sorted(items), f"Basket items are not deterministically sorted: {basket_id}", errors)
            require(len(items) == int(row["basket_size"]), f"Basket size mismatch: {basket_id}", errors)
            require(not (set(items) & config.NON_PRODUCT_STOCK_CODES), f"Non-product item in basket: {basket_id}", errors)
            require(set(items) == clean_orders[basket_id]["items"], f"Basket items mismatch clean lines: {basket_id}", errors)
            for field in [
                "customer_id", "invoice_date", "invoice_datetime", "country", "basket_size",
                "gross_purchase_amount", "split", "is_profile_customer", "is_eligible_for_main_comparison",
            ]:
                require(row[field] == order_row[field], f"Basket {field} mismatch order: {basket_id}", errors)
            item_set = set(items)
            basket_lookup[basket_id] = (row, item_set)
            expected_long_count += len(item_set)

    expected_basket_ids = {basket_id for basket_id, row in order_lookup.items() if row["is_valid_order"] == "1"}
    require(basket_ids == expected_basket_ids, "baskets does not exactly match valid orders", errors)

    actual_long_pairs: set[tuple[str, str]] = set()
    with open_csv(output_dir / "baskets_long.csv.gz") as stream:
        for row in csv.DictReader(stream):
            pair = (row["basket_id"], row["stock_code"])
            require(row["invoice_date"] == row["invoice_datetime"], f"Basket-long date alias mismatch for {pair}", errors)
            require(pair not in actual_long_pairs, f"Duplicate basket-item pair: {pair}", errors)
            require(row["basket_id"] in basket_lookup, f"Basket-long row missing basket parent: {pair}", errors)
            if row["basket_id"] in basket_lookup:
                basket_row, item_set = basket_lookup[row["basket_id"]]
                require(row["stock_code"] in item_set, f"Basket-long item missing from parent basket: {pair}", errors)
                for field in [
                    "customer_id", "invoice_date", "invoice_datetime", "split", "is_eligible_for_main_comparison",
                ]:
                    require(row[field] == basket_row[field], f"Basket-long {field} mismatch parent: {pair}", errors)
            actual_long_pairs.add(pair)
            if len(errors) >= 100:
                return errors
    require(len(actual_long_pairs) == expected_long_count, "baskets_long does not exactly cover basket item sets", errors)

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
    require(manifest["input_sha256"] == config.EXPECTED_INPUT_SHA256, "Manifest input SHA-256 mismatch", errors)
    require(manifest["configuration"]["splits"] == config.SPLITS, "Manifest split configuration mismatch", errors)
    require(manifest["configuration"]["worksheets"] == config.WORKSHEETS, "Manifest worksheet configuration mismatch", errors)
    require(manifest["headline_counts"]["raw_data_rows"] == clean_count, "Manifest raw row count mismatch", errors)
    require(manifest["headline_counts"]["canonical_source_rows"] == canonical_count, "Manifest canonical row count mismatch", errors)
    require(
        manifest["headline_counts"]["cross_sheet_overlap_excluded_rows"] == cross_sheet_overlap_excluded_count,
        "Manifest overlap-excluded row count mismatch",
        errors,
    )
    require(manifest["headline_counts"]["invoice_count"] == len(order_ids), "Manifest invoice count mismatch", errors)
    require(manifest["headline_counts"]["valid_basket_count"] == len(basket_ids), "Manifest basket count mismatch", errors)
    if "output_metadata" in manifest:
        metadata = {entry["filename"]: entry for entry in manifest["output_metadata"]}
        expected_metadata_files = set(REQUIRED_FILES) - {"run_manifest.json"}
        require(set(metadata) == expected_metadata_files, "Manifest output metadata file set mismatch", errors)
        for filename, entry in metadata.items():
            path = output_dir / filename
            require(path.stat().st_size == entry["size_bytes"], f"Manifest size mismatch for {filename}", errors)
            require(file_sha256(path) == entry["sha256"], f"Manifest SHA-256 mismatch for {filename}", errors)
    return errors


def finalize_manifest(output_dir: Path) -> None:
    manifest_path = output_dir / "run_manifest.json"
    with manifest_path.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    metadata = []
    for filename in sorted(REQUIRED_FILES):
        if filename == "run_manifest.json":
            continue
        path = output_dir / filename
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

