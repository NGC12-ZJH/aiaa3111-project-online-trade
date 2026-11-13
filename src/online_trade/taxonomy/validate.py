"""Read-only verification of frozen taxonomy artifacts; standard library only."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def validate(root=ROOT):
    errors = []
    checked = 0
    for name in ("FREEZE_taxonomy_v1.json", "FREEZE_taxonomy_v1_final.json"):
        record = json.loads((root / "data/taxonomy/v1_work" / name).read_text())
        for relative, expected in record["sha256"].items():
            path = root / relative
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                errors.append(f"Frozen artifact missing or changed: {relative}")
            checked += 1
    tax = json.loads((root / "configs/taxonomy/taxonomy_v1.json").read_text())
    parent = {entry["id"]: entry["l1"] for entry in tax["l2"]} | {"other": "other"}
    with (root / "data/taxonomy/item_taxonomy_v1.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    codes = [r["stock_code"] for r in rows]
    if not codes or any(not code for code in codes) or len(codes) != len(set(codes)):
        errors.append("Missing, empty or duplicate stock codes")
    for row in rows:
        if row["l2_id"] not in parent or parent.get(row["l2_id"]) != row["l1_id"]:
            errors.append(f"Invalid category hierarchy: {row['stock_code']}")
        if row["taxonomy_version"] != "taxonomy_v1":
            errors.append(f"Unexpected taxonomy version: {row['stock_code']}")
    if errors:
        raise ValueError("\n".join(errors))
    return f"Validation passed: {checked} frozen hashes, {len(rows)} unique product labels and category hierarchy."


if __name__ == "__main__":
    print(validate())
