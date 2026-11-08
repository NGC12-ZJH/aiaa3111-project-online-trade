#!/usr/bin/env python3
"""Check whether Online Retail II orders with multiple timestamps cross time splits."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime

from . import config


def assign_split(value: datetime) -> str:
    for name, (start_text, end_text) in config.SPLITS.items():
        if datetime.fromisoformat(start_text) <= value < datetime.fromisoformat(end_text):
            return name
    return "out_of_scope"


def main() -> None:
    input_path = config.OUTPUT_DIR / "invoice_conflicts.csv"
    output_path = config.OUTPUT_DIR / "time_conflict_stage_check.csv"
    output_rows: list[dict] = []
    stage_patterns = Counter()

    with input_path.open("r", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            timestamps = [datetime.fromisoformat(value) for value in json.loads(row["datetimes"])]
            splits = [assign_split(value) for value in timestamps]
            distinct_splits = sorted(set(splits))
            stage_patterns[" + ".join(distinct_splits)] += 1
            output_rows.append({
                "basket_id": row["basket_id"],
                "earliest_datetime": min(timestamps).isoformat(sep=" "),
                "latest_datetime": max(timestamps).isoformat(sep=" "),
                "datetime_count": len(timestamps),
                "datetime_span_seconds": int((max(timestamps) - min(timestamps)).total_seconds()),
                "same_calendar_day": int(min(timestamps).date() == max(timestamps).date()),
                "assigned_splits": json.dumps(distinct_splits, ensure_ascii=False),
                "crosses_split_boundary": int(len(distinct_splits) > 1),
                "all_datetimes": json.dumps([value.isoformat(sep=" ") for value in sorted(timestamps)], ensure_ascii=False),
            })

    fieldnames = [
        "basket_id", "earliest_datetime", "latest_datetime", "datetime_count",
        "datetime_span_seconds", "same_calendar_day", "assigned_splits",
        "crosses_split_boundary", "all_datetimes",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    crossing = [row for row in output_rows if row["crosses_split_boundary"]]
    longest = max(output_rows, key=lambda row: row["datetime_span_seconds"], default=None)
    summary = {
        "orders_checked": len(output_rows),
        "orders_crossing_split_boundary": len(crossing),
        "orders_within_one_calendar_day": sum(row["same_calendar_day"] for row in output_rows),
        "stage_patterns": dict(stage_patterns),
        "maximum_span_seconds": longest["datetime_span_seconds"] if longest else 0,
        "maximum_span_order": longest["basket_id"] if longest else None,
        "output": str(output_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if crossing:
        print("Cross-stage orders:")
        for row in crossing:
            print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
