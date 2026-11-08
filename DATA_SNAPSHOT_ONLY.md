# Online Retail II data snapshot — do not merge

This branch is a data-sharing snapshot for project members. It must not be merged into `main` or used as a pull-request source.

## Snapshot identity

- Branch: `a/online-retail-ii-data-snapshot`
- Created: 2026-11-06
- Processing-code base: `301875b`
- Dataset: UCI Online Retail II, ID 502
- License: CC BY 4.0
- Raw workbook SHA-256: `bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980`

## Included data

Deliverables are grouped by workflow step under `data/processed/`; each folder has a README with file list, row counts, SHA-256, generation command and code version. See `data/processed/README.md` for the index and download commands.

- `data/raw/online_retail_II.xlsx`: official source workbook;
- `data/processed/A_data_preparation/` (step 1, A): `clean_transactions.csv.gz`, `orders.csv.gz`, `baskets.csv.gz`, `baskets_long.csv.gz`, all reconciliation, exclusion, conflict, sensitivity, extreme-value and eligibility audit files, and `run_manifest.json`. Byte-identical to snapshot commit `ed1c57a`; moved into this folder on 2026-11-08;
- `data/processed/B_customer_clustering/` (step 2, B, added 2026-11-08): frozen customer cluster labels (K-means, k = 3), 20 size-matched customer-level random groups, and the selection summary.

The manifest preserves the original local run record: its output file names are relative to `A_data_preparation/`, and its absolute paths describe the generation environment rather than checkout instructions.

## Use

Members who need the prepared data should fetch or check out this branch. Code changes continue through the normal feature branches and PRs. Do not open a PR from this snapshot branch and do not merge its data files into `main`.
