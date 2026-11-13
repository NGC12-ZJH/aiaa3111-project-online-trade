"""Regression checks for package migration; no datasets, models or API calls."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from online_trade.taxonomy import run_v0
from online_trade.taxonomy.validate import validate


class TaxonomyLayoutTests(unittest.TestCase):
    def test_entry_point_outside_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/run_taxonomy.py"), "validate"],
                cwd=directory, capture_output=True, text=True, check=True,
            )
        self.assertIn("14 frozen hashes, 4724 unique product labels", result.stdout)

    def test_validation_detects_changed_frozen_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("FREEZE_taxonomy_v1.json", "FREEZE_taxonomy_v1_final.json"):
                relative = Path("data/taxonomy/v1_work") / name
                source = ROOT / relative
                record = json.loads(source.read_text())
                for path in [relative, *map(Path, record["sha256"])]:
                    (root / path).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / path, root / path)
            self.assertIn("Validation passed", validate(root))
            with (root / "data/taxonomy/item_taxonomy_v1.csv").open("a") as stream:
                stream.write("\n")
            with self.assertRaisesRegex(ValueError, "Frozen artifact missing or changed"):
                validate(root)

    def test_v0_steps_use_shared_entry_point_in_order(self):
        with patch.object(run_v0.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()):
            run_v0.main()
        self.assertEqual(len(run.call_args_list), len(run_v0.STEPS))
        for call, step in zip(run.call_args_list, run_v0.STEPS):
            self.assertEqual(call.args[0], [sys.executable, str(ROOT / "scripts/run_taxonomy.py"), step])
            self.assertEqual(call.kwargs, {"cwd": ROOT, "check": True})


if __name__ == "__main__":
    unittest.main()
