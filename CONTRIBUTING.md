# Contributing

## Setup

```bash
make setup               # uv sync, npm ci, and .env from .env.example
make demo-data ingest    # synthetic dataset; no download needed
uvx pre-commit install   # optional: ruff and prettier on every commit
```

Python 3.11+, Node 22, and `uv`. The full stack also needs Docker and Ollama;
see the README.

## Before you open a pull request

```bash
make test    # pytest with coverage, then Vitest
make lint    # ruff check and format, ESLint, Prettier
```

CI runs the same checks. Neither suite touches a live graph or model.

## Rules that are not negotiable

These carry the project's claims. A change that breaks one is a bug, even if
every test passes.

- **The risk score is never evidence.** It carries zero weight and is never a
  feature; a test pins it.
- **TigerGraph is the source of record.** An answer is `verified` only if it is
  graph-grounded, written back, read back, and carries graph and document
  evidence.
- **Temporal honesty.** Prior cases and documents count only if they closed
  before the investigation's cutoff.
- **Data semantics.** `addr1` is an anonymised region, not a location. The V,
  C, D, M and `id_` columns are unnamed. A shared device profile is a lead, not
  an identity.
- **Simulated means labelled.** Customer replies are simulated and say so. No
  real banking or regulatory action is ever taken.
- **No paid or cloud fallbacks** for model or embedding calls.
- **No data redistribution.** Never commit rows from the benchmark dataset;
  see [DATA.md](DATA.md). The synthetic demo data is regenerated, not
  committed.

## Style

Ruff and Prettier own formatting. Comments explain _why_, briefly. Keep
commits small and focused, with an imperative subject line.
