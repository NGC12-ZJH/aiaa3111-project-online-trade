#!/usr/bin/env python3
"""Process Online Retail.xlsx into auditable transaction, order, and basket tables.

This implementation uses only the Python standard library. It streams the XLSX XML,
keeps the source workbook unchanged, and writes deterministic compressed CSV outputs.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import heapq
import json
import platform
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Iterator
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from . import config


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = {"x": MAIN_NS}
EXPECTED_COLUMNS = [
    "InvoiceNo",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "UnitPrice",
    "CustomerID",
    "Country",
]
NORMAL_STOCK_PATTERN = re.compile(r"^[0-9]{5}[A-Za-z]?$|^[0-9]{4}[A-Za-z]$")
MONEY_QUANT = Decimal("0.01")


@dataclass
class OrderAggregate:
    invoice_id: str
    customer_ids: set[str] = field(default_factory=set)
    countries: set[str] = field(default_factory=set)
    datetimes: set[datetime] = field(default_factory=set)
    items: set[str] = field(default_factory=set)
    gross_purchase_amount: Decimal = Decimal("0")
    return_amount: Decimal = Decimal("0")
    gross_purchase_amount_with_duplicates: Decimal = Decimal("0")
    return_amount_with_duplicates: Decimal = Decimal("0")
    line_count: int = 0
    valid_basket_line_count: int = 0
    valid_amount_line_count: int = 0
    duplicate_candidate_count: int = 0
    cancelled_line_count: int = 0
    non_product_line_count: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=config.INPUT_XLSX)
    parser.add_argument("--output-dir", type=Path, default=config.OUTPUT_DIR)
    return parser.parse_args()


def normalize_space(value: str) -> str:
    return " ".join(value.strip().split())


def normalize_identifier(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        candidate = text[:-2]
        if candidate.lstrip("-").isdigit():
            return candidate
    return text


def parse_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    if number != number.to_integral_value():
        return None
    return int(number)


def parse_decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def excel_serial_to_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    try:
        serial = float(value)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None
    return datetime(1899, 12, 30) + timedelta(days=serial)


def money_text(value: Decimal) -> str:
    return str(value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def iso_text(value: datetime | None) -> str:
    return value.isoformat(sep=" ") if value else ""


def assign_split(value: datetime | None) -> str:
    if value is None:
        return "invalid_date"
    for name, (start_text, end_text) in config.SPLITS.items():
        if datetime.fromisoformat(start_text) <= value < datetime.fromisoformat(end_text):
            return name
    return "out_of_scope"


def load_shared_strings(archive: ZipFile) -> list[str]:
    values: list[str] = []
    with archive.open("xl/sharedStrings.xml") as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if element.tag == f"{{{MAIN_NS}}}si":
                values.append("".join(node.text or "" for node in element.findall(".//x:t", NS)))
                element.clear()
    return values


def column_index(cell_reference: str) -> int:
    letters = "".join(character for character in cell_reference if character.isalpha())
    result = 0
    for character in letters:
        result = result * 26 + ord(character.upper()) - ord("A") + 1
    return result - 1


def cell_value(cell: ET.Element, shared_strings: list[str]) -> object:
    cell_type = cell.attrib.get("t")
    value_node = cell.find("x:v", NS)
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//x:t", NS))
    if value_node is None or value_node.text is None:
        return None
    raw = value_node.text
    if cell_type == "s":
        return shared_strings[int(raw)]
    if cell_type == "b":
        return raw == "1"
    return raw


def iter_xlsx_rows(path: Path) -> Iterator[tuple[int, list[object]]]:
    with ZipFile(path) as archive:
        shared_strings = load_shared_strings(archive)
        with archive.open("xl/worksheets/sheet1.xml") as stream:
            for _, row in ET.iterparse(stream, events=("end",)):
                if row.tag != f"{{{MAIN_NS}}}row":
                    continue
                row_number = int(row.attrib.get("r", "0"))
                values: list[object] = [None] * len(EXPECTED_COLUMNS)
                for cell in row.findall("x:c", NS):
                    index = column_index(cell.attrib.get("r", ""))
                    if 0 <= index < len(values):
                        values[index] = cell_value(cell, shared_strings)
                yield row_number, values
                row.clear()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def duplicate_digest(values: Iterable[object]) -> bytes:
    text = "\x1f".join("" if value is None else str(value) for value in values)
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).digest()


def push_top(heap: list, score: Decimal | int, row_id: int, record: dict, limit: int) -> None:
    entry = (score, row_id, record)
    if len(heap) < limit:
        heapq.heappush(heap, entry)
    elif entry[:2] > heap[0][:2]:
        heapq.heapreplace(heap, entry)


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def process(input_path: Path, output_dir: Path) -> dict:
    if not input_path.exists():
        raise FileNotFoundError(f"Input workbook not found: {input_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    clean_path = output_dir / "clean_transactions.csv.gz"
    orders: dict[str, OrderAggregate] = {}
    counters = Counter()
    split_line_counts = Counter()
    primary_exclusions = Counter()
    suspicious_codes: dict[str, dict] = defaultdict(lambda: {"count": 0, "descriptions": Counter()})
    duplicate_hashes: set[bytes] = set()
    quantity_heap: list = []
    amount_heap: list = []

    clean_fields = [
        "source_row_id", "invoice_id", "stock_code_raw", "stock_code", "description", "quantity",
        "invoice_datetime", "unit_price", "line_amount", "customer_id", "country", "split",
        "is_cancelled_invoice", "is_negative_quantity", "is_zero_quantity",
        "is_zero_price", "is_negative_price", "is_missing_customer", "is_missing_description",
        "is_non_product", "is_exact_duplicate_candidate", "is_valid_basket_item",
        "is_valid_amount_line", "primary_exclusion_reason",
    ]

    with gzip.open(clean_path, "wt", encoding="utf-8", newline="") as clean_stream:
        writer = csv.DictWriter(clean_stream, fieldnames=clean_fields)
        writer.writeheader()
        row_iterator = iter_xlsx_rows(input_path)
        header_row_number, header = next(row_iterator)
        if header_row_number != 1 or header != EXPECTED_COLUMNS:
            raise ValueError(f"Unexpected workbook schema: {header!r}")

        for excel_row_number, raw in row_iterator:
            counters["raw_data_rows"] += 1
            source_row_id = excel_row_number - 1
            invoice_id = normalize_identifier(raw[0])
            stock_code_raw = normalize_identifier(raw[1])
            # Preserve the source value but use an uppercase canonical product key.
            stock_code = stock_code_raw.upper()
            description = normalize_space(str(raw[2])) if raw[2] is not None else ""
            quantity = parse_int(raw[3])
            invoice_datetime = excel_serial_to_datetime(raw[4])
            unit_price = parse_decimal(raw[5])
            customer_id = normalize_identifier(raw[6])
            country = normalize_space(str(raw[7])) if raw[7] is not None else ""
            split = assign_split(invoice_datetime)

            line_amount = (
                Decimal(quantity) * unit_price
                if quantity is not None and unit_price is not None
                else Decimal("0")
            )
            is_cancelled = invoice_id.upper().startswith("C")
            is_negative_quantity = quantity is not None and quantity < 0
            is_zero_quantity = quantity == 0
            is_zero_price = unit_price == 0
            is_negative_price = unit_price is not None and unit_price < 0
            is_missing_customer = customer_id == ""
            is_missing_description = description == ""
            is_non_product = stock_code.upper() in config.NON_PRODUCT_STOCK_CODES
            digest = duplicate_digest((invoice_id, stock_code, description, quantity, invoice_datetime, unit_price, customer_id, country))
            is_duplicate_candidate = digest in duplicate_hashes
            duplicate_hashes.add(digest)

            base_valid_common = (
                invoice_id != ""
                and stock_code != ""
                and invoice_datetime is not None
                and quantity is not None
                and unit_price is not None
                and not is_cancelled
                and quantity > 0
                and unit_price >= 0
                and not is_non_product
            )
            valid_common = base_valid_common
            if not config.RETAIN_EXACT_DUPLICATE_CANDIDATES and is_duplicate_candidate:
                valid_common = False
            is_valid_basket_item = valid_common and (config.INCLUDE_ZERO_PRICE_IN_BASKETS or unit_price > 0)
            is_valid_amount_line = valid_common and unit_price > 0

            exclusion_checks = [
                (invoice_id == "", "missing_invoice"),
                (invoice_datetime is None, "invalid_date"),
                (stock_code == "", "missing_stock_code"),
                (quantity is None, "invalid_quantity"),
                (unit_price is None, "invalid_unit_price"),
                (is_cancelled, "cancelled_invoice"),
                (is_negative_quantity, "negative_quantity"),
                (is_zero_quantity, "zero_quantity"),
                (is_negative_price, "negative_price"),
                (is_non_product, "non_product"),
                (is_duplicate_candidate and not config.RETAIN_EXACT_DUPLICATE_CANDIDATES, "duplicate_candidate"),
                (is_zero_price and not config.INCLUDE_ZERO_PRICE_IN_BASKETS, "zero_price"),
            ]
            primary_exclusion_reason = next((reason for condition, reason in exclusion_checks if condition), "")
            if primary_exclusion_reason:
                primary_exclusions[primary_exclusion_reason] += 1

            flags = {
                "cancelled_line_rows": is_cancelled,
                "negative_quantity_rows": is_negative_quantity,
                "zero_quantity_rows": is_zero_quantity,
                "zero_price_rows": is_zero_price,
                "negative_price_rows": is_negative_price,
                "missing_customer_rows": is_missing_customer,
                "missing_description_rows": is_missing_description,
                "non_product_rows": is_non_product,
                "exact_duplicate_candidate_rows": is_duplicate_candidate,
                "valid_basket_item_rows": is_valid_basket_item,
                "valid_amount_rows": is_valid_amount_line,
            }
            for name, condition in flags.items():
                if condition:
                    counters[name] += 1
            split_line_counts[split] += 1

            if stock_code and (is_non_product or not NORMAL_STOCK_PATTERN.fullmatch(stock_code)):
                suspicious_codes[stock_code]["count"] += 1
                if description:
                    suspicious_codes[stock_code]["descriptions"][description] += 1

            record = {
                "source_row_id": source_row_id,
                "invoice_id": invoice_id,
                "stock_code_raw": stock_code_raw,
                "stock_code": stock_code,
                "description": description,
                "quantity": "" if quantity is None else quantity,
                "invoice_datetime": iso_text(invoice_datetime),
                "unit_price": "" if unit_price is None else str(unit_price),
                "line_amount": money_text(line_amount),
                "customer_id": customer_id,
                "country": country,
                "split": split,
                "is_cancelled_invoice": int(is_cancelled),
                "is_negative_quantity": int(is_negative_quantity),
                "is_zero_quantity": int(is_zero_quantity),
                "is_zero_price": int(is_zero_price),
                "is_negative_price": int(is_negative_price),
                "is_missing_customer": int(is_missing_customer),
                "is_missing_description": int(is_missing_description),
                "is_non_product": int(is_non_product),
                "is_exact_duplicate_candidate": int(is_duplicate_candidate),
                "is_valid_basket_item": int(is_valid_basket_item),
                "is_valid_amount_line": int(is_valid_amount_line),
                "primary_exclusion_reason": primary_exclusion_reason,
            }
            writer.writerow(record)

            if quantity is not None:
                push_top(quantity_heap, abs(quantity), source_row_id, record, config.EXTREME_LINE_LIMIT)
            push_top(amount_heap, abs(line_amount), source_row_id, record, config.EXTREME_LINE_LIMIT)

            if invoice_id:
                order = orders.setdefault(invoice_id, OrderAggregate(invoice_id=invoice_id))
                order.line_count += 1
                if customer_id:
                    order.customer_ids.add(customer_id)
                if country:
                    order.countries.add(country)
                if invoice_datetime:
                    order.datetimes.add(invoice_datetime)
                if is_duplicate_candidate:
                    order.duplicate_candidate_count += 1
                if is_cancelled:
                    order.cancelled_line_count += 1
                if is_non_product:
                    order.non_product_line_count += 1
                if is_valid_basket_item:
                    order.items.add(stock_code)
                    order.valid_basket_line_count += 1
                if is_valid_amount_line:
                    order.gross_purchase_amount += line_amount
                    order.valid_amount_line_count += 1
                if base_valid_common and unit_price > 0:
                    order.gross_purchase_amount_with_duplicates += line_amount
                is_return_line = (
                    quantity is not None and unit_price is not None and unit_price >= 0
                    and stock_code and not is_non_product and (is_cancelled or quantity < 0)
                )
                if is_return_line:
                    order.return_amount_with_duplicates += abs(line_amount)
                if is_return_line and (config.RETAIN_EXACT_DUPLICATE_CANDIDATES or not is_duplicate_candidate):
                    order.return_amount += abs(line_amount)

    profile_customers = {
        next(iter(order.customer_ids))
        for order in orders.values()
        if len(order.customer_ids) == 1
        and order.items
        and assign_split(min(order.datetimes) if order.datetimes else None) == "profile"
    }

    order_fields = [
        "basket_id", "customer_id", "invoice_date", "invoice_datetime", "country", "valid_amount", "gross_purchase_amount",
        "return_amount", "net_amount", "gross_purchase_amount_with_duplicates",
        "return_amount_with_duplicates", "net_amount_with_duplicates",
        "basket_size", "line_count", "valid_basket_line_count",
        "valid_amount_line_count", "split", "is_valid_order", "is_valid_rfm_order", "is_identified_customer",
        "is_profile_customer", "is_eligible_for_main_comparison", "has_customer_conflict",
        "has_country_conflict", "has_datetime_conflict", "datetime_span_seconds",
        "duplicate_candidate_count", "cancelled_line_count", "non_product_line_count",
    ]
    basket_fields = [
        "basket_id", "customer_id", "invoice_date", "invoice_datetime", "country", "items", "basket_size",
        "gross_purchase_amount", "split", "is_profile_customer", "is_eligible_for_main_comparison",
    ]
    basket_long_fields = ["basket_id", "customer_id", "invoice_date", "invoice_datetime", "stock_code", "split", "is_eligible_for_main_comparison"]
    conflict_fields = [
        "basket_id", "customer_ids", "countries", "datetimes", "has_customer_conflict",
        "has_country_conflict", "has_datetime_conflict", "datetime_span_seconds",
    ]

    order_rows: list[dict] = []
    basket_rows: list[dict] = []
    basket_long_rows: list[dict] = []
    conflict_rows: list[dict] = []
    split_order_counts = Counter()
    split_customer_sets: dict[str, set[str]] = defaultdict(set)
    split_item_sets: dict[str, set[str]] = defaultdict(set)
    split_known_order_counts = Counter()
    basket_size_counts = Counter()
    order_amount_heap: list = []

    def order_sort_key(item: OrderAggregate) -> tuple:
        return (min(item.datetimes) if item.datetimes else datetime.max, item.invoice_id)

    for order in sorted(orders.values(), key=order_sort_key):
        customer_id = next(iter(order.customer_ids)) if len(order.customer_ids) == 1 else ""
        country = next(iter(order.countries)) if len(order.countries) == 1 else ""
        first_datetime = min(order.datetimes) if order.datetimes else None
        split = assign_split(first_datetime)
        has_customer_conflict = len(order.customer_ids) > 1
        has_country_conflict = len(order.countries) > 1
        has_datetime_conflict = len(order.datetimes) > 1
        datetime_span_seconds = (
            int((max(order.datetimes) - min(order.datetimes)).total_seconds())
            if len(order.datetimes) > 1 else 0
        )
        is_valid_order = bool(order.items)
        is_valid_rfm_order = order.valid_amount_line_count > 0
        is_identified = bool(customer_id) and not has_customer_conflict
        is_profile_customer = is_identified and customer_id in profile_customers
        is_eligible = is_valid_order and is_profile_customer and split in config.SPLITS
        net_amount = order.gross_purchase_amount - order.return_amount
        net_amount_with_duplicates = (
            order.gross_purchase_amount_with_duplicates - order.return_amount_with_duplicates
        )

        row = {
            "basket_id": order.invoice_id,
            "customer_id": customer_id,
            "invoice_date": iso_text(first_datetime),
            "invoice_datetime": iso_text(first_datetime),
            "country": country,
            "valid_amount": money_text(order.gross_purchase_amount),
            "gross_purchase_amount": money_text(order.gross_purchase_amount),
            "return_amount": money_text(order.return_amount),
            "net_amount": money_text(net_amount),
            "gross_purchase_amount_with_duplicates": money_text(order.gross_purchase_amount_with_duplicates),
            "return_amount_with_duplicates": money_text(order.return_amount_with_duplicates),
            "net_amount_with_duplicates": money_text(net_amount_with_duplicates),
            "basket_size": len(order.items),
            "line_count": order.line_count,
            "valid_basket_line_count": order.valid_basket_line_count,
            "valid_amount_line_count": order.valid_amount_line_count,
            "split": split,
            "is_valid_order": int(is_valid_order),
            "is_valid_rfm_order": int(is_valid_rfm_order),
            "is_identified_customer": int(is_identified),
            "is_profile_customer": int(is_profile_customer),
            "is_eligible_for_main_comparison": int(is_eligible),
            "has_customer_conflict": int(has_customer_conflict),
            "has_country_conflict": int(has_country_conflict),
            "has_datetime_conflict": int(has_datetime_conflict),
            "datetime_span_seconds": datetime_span_seconds,
            "duplicate_candidate_count": order.duplicate_candidate_count,
            "cancelled_line_count": order.cancelled_line_count,
            "non_product_line_count": order.non_product_line_count,
        }
        order_rows.append(row)
        push_top(order_amount_heap, abs(order.gross_purchase_amount), len(order_rows), row, config.EXTREME_ORDER_LIMIT)

        if has_customer_conflict or has_country_conflict or has_datetime_conflict:
            conflict_rows.append({
                "basket_id": order.invoice_id,
                "customer_ids": json.dumps(sorted(order.customer_ids), ensure_ascii=False),
                "countries": json.dumps(sorted(order.countries), ensure_ascii=False),
                "datetimes": json.dumps([iso_text(value) for value in sorted(order.datetimes)], ensure_ascii=False),
                "has_customer_conflict": int(has_customer_conflict),
                "has_country_conflict": int(has_country_conflict),
                "has_datetime_conflict": int(has_datetime_conflict),
                "datetime_span_seconds": datetime_span_seconds,
            })

        if is_valid_order:
            sorted_items = sorted(order.items)
            basket_rows.append({
                "basket_id": order.invoice_id,
                "customer_id": customer_id,
                "invoice_date": iso_text(first_datetime),
                "invoice_datetime": iso_text(first_datetime),
                "country": country,
                "items": json.dumps(sorted_items, ensure_ascii=False),
                "basket_size": len(sorted_items),
                "gross_purchase_amount": money_text(order.gross_purchase_amount),
                "split": split,
                "is_profile_customer": int(is_profile_customer),
                "is_eligible_for_main_comparison": int(is_eligible),
            })
            for stock_code in sorted_items:
                basket_long_rows.append({
                    "basket_id": order.invoice_id,
                    "customer_id": customer_id,
                    "invoice_date": iso_text(first_datetime),
                    "invoice_datetime": iso_text(first_datetime),
                    "stock_code": stock_code,
                    "split": split,
                    "is_eligible_for_main_comparison": int(is_eligible),
                })
            split_order_counts[split] += 1
            basket_size_counts[len(sorted_items)] += 1
            if customer_id:
                split_customer_sets[split].add(customer_id)
            split_item_sets[split].update(sorted_items)
            if is_eligible:
                split_known_order_counts[split] += 1

    with gzip.open(output_dir / "orders.csv.gz", "wt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=order_fields)
        writer.writeheader()
        writer.writerows(order_rows)
    with gzip.open(output_dir / "baskets.csv.gz", "wt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=basket_fields)
        writer.writeheader()
        writer.writerows(basket_rows)
    with gzip.open(output_dir / "baskets_long.csv.gz", "wt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=basket_long_fields)
        writer.writeheader()
        writer.writerows(basket_long_rows)
    write_csv(output_dir / "invoice_conflicts.csv", conflict_fields, conflict_rows)

    suspicious_rows = []
    for code, details in sorted(suspicious_codes.items(), key=lambda item: (-item[1]["count"], item[0])):
        descriptions = details["descriptions"].most_common(5)
        suspicious_rows.append({
            "stock_code": code,
            "line_count": details["count"],
            "configured_as_non_product": int(code.upper() in config.NON_PRODUCT_STOCK_CODES),
            "top_descriptions": json.dumps(descriptions, ensure_ascii=False),
        })
    write_csv(
        output_dir / "special_stock_codes.csv",
        ["stock_code", "line_count", "configured_as_non_product", "top_descriptions"],
        suspicious_rows,
    )

    extreme_records: dict[tuple[str, int], dict] = {}
    for category, heap in (("absolute_quantity", quantity_heap), ("absolute_line_amount", amount_heap)):
        for score, row_id, record in sorted(heap, reverse=True):
            extreme_records[(category, row_id)] = {"extreme_category": category, "absolute_value": str(score), **record}
    write_csv(
        output_dir / "extreme_lines.csv",
        ["extreme_category", "absolute_value", *clean_fields],
        extreme_records.values(),
    )
    extreme_order_rows = [
        {"absolute_gross_amount": str(score), **row}
        for score, _, row in sorted(order_amount_heap, reverse=True)
    ]
    write_csv(output_dir / "extreme_orders.csv", ["absolute_gross_amount", *order_fields], extreme_order_rows)

    sample_categories: dict[str, list[dict]] = defaultdict(list)
    for row in order_rows:
        if len(sample_categories["single_item"]) < config.AUDIT_SAMPLE_PER_CATEGORY and row["is_valid_order"] and row["basket_size"] == 1:
            sample_categories["single_item"].append(row)
        if len(sample_categories["multi_item"]) < config.AUDIT_SAMPLE_PER_CATEGORY and row["is_valid_order"] and row["basket_size"] > 1:
            sample_categories["multi_item"].append(row)
        if len(sample_categories["anonymous"]) < config.AUDIT_SAMPLE_PER_CATEGORY and row["is_valid_order"] and not row["customer_id"]:
            sample_categories["anonymous"].append(row)
        if len(sample_categories["cancelled"]) < config.AUDIT_SAMPLE_PER_CATEGORY and row["cancelled_line_count"]:
            sample_categories["cancelled"].append(row)
        if len(sample_categories["non_product"]) < config.AUDIT_SAMPLE_PER_CATEGORY and row["non_product_line_count"]:
            sample_categories["non_product"].append(row)
    audit_samples = [
        {"sample_category": category, **row}
        for category, rows in sorted(sample_categories.items())
        for row in rows
    ]
    write_csv(output_dir / "audit_order_samples.csv", ["sample_category", *order_fields], audit_samples)

    audit_rows = []
    def add_metric(section: str, metric: str, value: object, description: str) -> None:
        audit_rows.append({"section": section, "metric": metric, "value": value, "description": description})

    for metric in sorted(counters):
        add_metric("line_audit", metric, counters[metric], "Number of source data rows")
    add_metric("order_audit", "invoice_count", len(order_rows), "Distinct non-empty InvoiceNo values")
    add_metric("order_audit", "valid_basket_count", len(basket_rows), "Orders containing at least one valid product")
    add_metric("order_audit", "basket_long_rows", len(basket_long_rows), "Distinct basket-product pairs")
    add_metric("order_audit", "profile_customer_count", len(profile_customers), "Identified customers with a valid profile-period basket")
    add_metric("order_audit", "single_item_basket_count", basket_size_counts[1], "Valid baskets containing one distinct product")
    add_metric("order_audit", "multi_item_basket_count", sum(count for size, count in basket_size_counts.items() if size > 1), "Valid baskets containing more than one distinct product")
    for split in [*config.SPLITS, "out_of_scope", "invalid_date"]:
        add_metric("split_lines", f"{split}_line_rows", split_line_counts[split], "Source rows assigned to split")
        add_metric("split_orders", f"{split}_valid_baskets", split_order_counts[split], "Valid baskets assigned to split")
        add_metric("split_customers", f"{split}_identified_customers", len(split_customer_sets[split]), "Identified customers with a valid basket")
        add_metric("split_items", f"{split}_distinct_items", len(split_item_sets[split]), "Distinct valid product codes")
        add_metric("split_eligibility", f"{split}_eligible_baskets", split_known_order_counts[split], "Valid baskets belonging to profile customers")
    write_csv(output_dir / "audit_summary.csv", ["section", "metric", "value", "description"], audit_rows)
    write_csv(
        output_dir / "exclusion_summary.csv",
        ["primary_exclusion_reason", "line_count"],
        ({"primary_exclusion_reason": reason, "line_count": count} for reason, count in sorted(primary_exclusions.items())),
    )

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "input_path": str(input_path.resolve()),
        "input_sha256": file_sha256(input_path),
        "output_directory": str(output_dir.resolve()),
        "configuration": {
            "config_path": str(config.CONFIG_PATH.resolve()),
            "schema_version": config.CONFIG["schema_version"],
            "splits": config.SPLITS,
            "non_product_stock_codes": sorted(config.NON_PRODUCT_STOCK_CODES),
            "include_zero_price_in_baskets": config.INCLUDE_ZERO_PRICE_IN_BASKETS,
            "retain_exact_duplicate_candidates": config.RETAIN_EXACT_DUPLICATE_CANDIDATES,
        },
        "headline_counts": {
            "raw_data_rows": counters["raw_data_rows"],
            "invoice_count": len(order_rows),
            "valid_basket_count": len(basket_rows),
            "profile_customer_count": len(profile_customers),
        },
        "outputs": sorted(path.name for path in output_dir.iterdir() if path.is_file()),
    }
    with (output_dir / "run_manifest.json").open("w", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return manifest


def main() -> int:
    args = parse_args()
    manifest = process(args.input, args.output_dir)
    print(json.dumps(manifest["headline_counts"], ensure_ascii=False, indent=2))
    print(f"Outputs written to: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

