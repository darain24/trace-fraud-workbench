# Data

The MIT license in `LICENSE` covers this repository's code and documentation only. It does
not cover any dataset.

## Benchmark dataset (`TRACE_DATASET=full`)

Trace was developed against an adaptation of the **IEEE-CIS Fraud Detection** dataset
(Vesta Corporation, via the IEEE Computational Intelligence Society), prepared by
TigerGraph as a benchmark for Hacker House Goa 2026. It adds a 20-case trigger pack
(`case_pack.csv`) and 5,565 closed investigations (`closed_cases_history.csv`) to the
original transaction and identity tables.

- None of it is redistributed here. `scripts/download_data.py` fetches it from its
  published location into `data/raw/`, which is git-ignored.
- The original Kaggle outcome labels are never used to recover answers.
- Use of the data is subject to its original terms.

## Synthetic demo dataset (`TRACE_DATASET=demo`)

A small, seeded, fully synthetic dataset with the same files and columns, generated
locally by `scripts/generate_demo_data.py`. It contains no real transactions and exists
so the whole pipeline can be run without the benchmark files. Numbers measured on it
(holdout accuracy, exposure, and so on) say nothing about real fraud.

## Derived artefacts

`examples/benchmark-results/` holds Trace's own twenty answers on the benchmark trigger
pack. They contain dataset identifiers (transaction, card and case IDs) and amounts that
Trace computed, but no source rows.
