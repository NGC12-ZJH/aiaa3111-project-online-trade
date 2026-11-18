"""Extract pinned Git blobs; keep all customer-level inputs ignored locally."""
from pathlib import Path
import csv
import gzip
import hashlib
import io
import json
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / 'data/processed/local/D_validation'


def blob(ref, path):
    return subprocess.check_output(['git', 'show', f'{ref}:{path}'], cwd=ROOT)


def main():
    protocol = json.loads((ROOT / 'configs/validation.json').read_text(encoding='utf-8'))
    LOCAL.mkdir(parents=True, exist_ok=True)
    core = blob(protocol['c_handoff_commit'], 'experiments/c_pattern/runs/2026-11-15_activity_P1-P5/category_P1_P5_handoff/D_validation_core.zip')
    (LOCAL / 'D_validation_core.zip').write_bytes(core)
    with zipfile.ZipFile(io.BytesIO(core)) as archive:
        target = (LOCAL / 'core').resolve()
        for name in archive.namelist():
            if not (target / name).resolve().is_relative_to(target):
                raise ValueError('Unsafe archive member')
        archive.extractall(target)
    ref = protocol['a_snapshot_commit']
    manifest = json.loads(blob(ref, 'data/processed/A_data_preparation/run_manifest.json'))
    baskets = blob(ref, 'data/processed/A_data_preparation/baskets.csv.gz')
    expected = next(x['sha256'] for x in manifest['output_metadata'] if x['filename'] == 'baskets.csv.gz')
    assert hashlib.sha256(baskets).hexdigest() == expected, 'A basket hash mismatch'
    # Only serialize Discovery replay and Validation inputs. No Test features or metrics.
    handles = {}
    writers = {}
    try:
        source = csv.DictReader(io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(baskets)), encoding='utf-8-sig', newline=''))
        for period in ('discovery', 'validation'):
            handle = (LOCAL / f'{period}_baskets.csv').open('w', encoding='utf-8', newline='')
            handles[period] = handle
            writers[period] = csv.DictWriter(handle, source.fieldnames, lineterminator='\n')
            writers[period].writeheader()
        for row in source:
            if row['split'] in writers:
                writers[row['split']].writerow(row)
    finally:
        for handle in handles.values():
            handle.close()
    provenance = {'a_snapshot': ref, 'c_handoff': protocol['c_handoff_commit'], 'source_baskets_sha256': expected,
                  'core_zip_sha256': hashlib.sha256(core).hexdigest(), 'exported_periods': ['discovery', 'validation'], 'test_evaluated': False}
    (LOCAL / 'input_provenance.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    print('Prepared pinned inputs; Test was not exported or evaluated.')


if __name__ == '__main__':
    main()
