"""Extract pinned A/B snapshot files and C rule evidence into data/processed/local/b_taxonomy_inputs/."""
import hashlib
import subprocess

from paths import C_FILES, C_PATTERN_COMMIT, INPUT, ROOT, SNAPSHOT_COMMIT, SNAPSHOT_FILES


def extract(commit, files):
    for name, path in files.items():
        data = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{path}"],
                              check=True, capture_output=True).stdout
        (INPUT / name).write_bytes(data)
        print(f"{name:28s} {len(data):>11,d} bytes  sha256={hashlib.sha256(data).hexdigest()[:16]}")


if __name__ == "__main__":
    subprocess.run(["git", "-C", str(ROOT), "fetch", "-q", "origin"], check=False)
    extract(SNAPSHOT_COMMIT, SNAPSHOT_FILES)
    extract(C_PATTERN_COMMIT, C_FILES)
