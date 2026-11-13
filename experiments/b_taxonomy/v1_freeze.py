"""Freeze the taxonomy_v1 structure (release candidate) before any gold-standard evaluation.

What it does:
- sets version/status in configs/taxonomy/taxonomy_v1.json
- writes data/taxonomy/v1_work/FREEZE_taxonomy_v1.json with SHA-256 hashes of every file that defines the
  structure, the reference-example pool and the gold sample
After this, v1_step3_build.py refuses to overwrite the taxonomy (unless --unfreeze), and llm_tag.py checks the
hashes before each run, so R1-R6 are guaranteed to use exactly this version.

Usage: python v1_freeze.py --by "B (Jinghan ZHAO)" --note "..."
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone

from paths import ROOT, TAXONOMY
from taxonomy_io import GOLD_DIR, TAX_CFG, V1_WORK

FREEZE = V1_WORK / "FREEZE_taxonomy_v1.json"
FILES = [TAX_CFG / "taxonomy_v1.json", TAX_CFG / "taxonomy_v1_decisions.json", V1_WORK / "seed_labels_v1.csv",
         V1_WORK / "definitions_draft_v1.json", TAXONOMY / "item_attributes_v1.csv", GOLD_DIR / "gold_items_v1.csv"]
VERSION = "taxonomy_v1_rc1"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check_freeze(strict=True):
    """Return the freeze record; raise if any frozen file changed (strict) or warn."""
    if not FREEZE.exists():
        return None
    rec = json.loads(FREEZE.read_text())
    bad = [f for f, h in rec["sha256"].items() if not (ROOT / f).exists() or sha(ROOT / f) != h]
    if bad:
        msg = f"frozen files changed since {rec['frozen_at']}: {bad}"
        if strict:
            raise SystemExit(msg + " -- refreeze on purpose (v1_freeze.py) or restore them.")
        print("WARNING:", msg)
    return rec


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--by", required=True)
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    tp = TAX_CFG / "taxonomy_v1.json"
    tax = json.loads(tp.read_text())
    tax["version"] = VERSION
    tax["status"] = ("FROZEN structure (release candidate 1). Subcategories, definitions, examples and seed pool are fixed "
                     "for R1-R6. Final name `taxonomy_v1` only after the gold-standard acceptance rule is met.")
    tax["frozen_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tp.write_text(json.dumps(tax, indent=1, ensure_ascii=False))
    rec = {"version": VERSION, "frozen_at": tax["frozen_at"], "frozen_by": a.by, "note": a.note,
           "n_l2": len(tax["l2"]), "n_l1": len({c["l1"] for c in tax["l2"]}),
           "sha256": {str(p.relative_to(ROOT)): sha(p) for p in FILES}}
    FREEZE.write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    print(json.dumps(rec, indent=1, ensure_ascii=False))
