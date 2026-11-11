# Discovery CPU pattern-mining benchmark

Only local files are created. No GitHub upload is performed.

Run in PowerShell from this directory:

    .\.venv\Scripts\python.exe benchmark.py

Data preparation uses the unchanged project source:

    python benchmark_source/scripts/process_online_retail_ii.py --input online_retail_II.xlsx --output-dir processed

Scope: all eligible Discovery baskets (2010-06-01 inclusive to 2010-12-01 exclusive), including single-item baskets. Eligibility comes from the project's frozen Profile customer population. Validation/Test performance is not inspected.

Protocol: mlxtend FP-Growth versus default Apriori (low_memory=False), dense boolean input, supports 0.02 and 0.01, maximum itemset lengths 2 and 3, three fresh-process repetitions per setting, alternating algorithm order. These are computational benchmark settings, not selected final research thresholds. CPU numerical-library threads are limited to one. No warm-up is discarded; results describe fresh-process runs after imports.

Timing: mining_s measures only the algorithm call. load_encode_mine_s measures loading the pre-encoded matrix, DataFrame wrapping and mining; despite its legacy field name, encoding and source CSV preparation are excluded. Imports, subprocess startup, result verification and serialization are excluded from both. Full raw-data end-to-end time is not measured.

Memory: sampled_peak_mib is process RSS sampled at approximately 5 ms during matrix loading and mining, including Python/import baseline, input and output. sampled_increment_mib subtracts the post-import baseline; it is not algorithm-exclusive memory. Sampling may miss short peaks. process_peak_mib is the Windows process lifetime high-water mark read immediately after mining (before verification); it includes import/startup peaks and must not be interpreted as mining-only memory. No memory-profiler instrumentation of Python allocations is used.

Correctness: compares exact normalized itemset-to-integer-count mappings across algorithms and repetitions, and independently recounts EVERY returned itemset against the input matrix. Singletons are included. This benchmark tests frequent itemsets, not budget selection or future rule quality. Equal itemsets imply the same rules under identical deterministic rule generation, but rule generation is not benchmarked here.

Outputs: results/manifest.json records data hashes, source commit, environment and settings; runs.csv contains per-run observations; consistency.csv contains exact checks; summary.csv contains median/min/max times and median sampled memory; each run JSON retains all itemset counts (integer column IDs map through items.json); comparison.png plots the medians.

Limitations: results are specific to this computer, these settings and mlxtend implementations. Background processes affect timing. No claim of universal algorithm superiority or GPU speed is supported. Keep customer-level files and the environment local when preparing a future GitHub change.
