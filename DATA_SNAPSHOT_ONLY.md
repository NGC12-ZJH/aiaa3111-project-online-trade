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

- `data/raw/online_retail_II.xlsx`: official source workbook;
- `data/processed/clean_transactions.csv.gz`: complete auditable row-level evidence;
- `data/processed/orders.csv.gz`: order-level input for RFM and evaluation;
- `data/processed/baskets.csv.gz`: basket-level input for future rule evaluation;
- `data/processed/baskets_long.csv.gz`: order–item input for pattern mining;
- all reconciliation, exclusion, conflict, sensitivity, extreme-value and eligibility audit files;
- `data/processed/run_manifest.json`: hashes, row counts and run metadata from the validated generation run.

The manifest preserves the original local run record, so its absolute paths describe the generation environment and are not checkout instructions. Use repository-relative paths shown above.

## Use

Members who need the prepared data should fetch or check out this branch. Code changes continue through the normal feature branches and PRs. Do not open a PR from this snapshot branch and do not merge its data files into `main`.
