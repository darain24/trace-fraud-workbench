# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this is

**Trace** is an agentic fraud-investigation workbench. A trigger (a risk score, a customer report or an analyst request) starts an investigation. Trace then works through these steps:

1. Collects a bounded evidence packet (`backend/tracework/analysis.py`).
2. Re-derives that evidence in TigerGraph through GSQL over the official TigerGraph MCP server, and refuses to continue if the graph disagrees (`retrieval.py`, `tigergraph.py`).
3. Retrieves policy and case context by vector search in TigerGraph (GraphRAG).
4. Scores fitted log-odds evidence weights.
5. Applies a deterministic bank policy (`policy.py`).
6. Requests more evidence when it can't decide.
7. Writes the case back into the graph and reads it back to confirm.

The orchestration lives in `engine.py`, the API is FastAPI (`api.py`), and the UI is React + Vite (`frontend/`). All inference is local through Ollama. There are no paid APIs.

The project began as a solo hackathon entry (TigerGraph Hacker House Goa 2026, Task 4). It is now being turned into a standalone **portfolio project**. See "Roadmap" below.

## Commands

```bash
uv sync --all-extras --dev           # Python deps (Python >= 3.11)
npm ci --prefix frontend             # frontend deps
uv run pytest -q                     # backend tests (never touch a live graph; see backend/tests/conftest.py)
uv run ruff check .                  # lint
npm run build --prefix frontend      # tsc + vite build
./scripts/dev.sh                     # API on :8000 + UI on :5173
./scripts/demo_up.sh                 # full stack: TigerGraph container, Ollama, MCP on :9001, API, UI
```

Data pipeline, in order:
1. `scripts/download_data.py`
2. `scripts/ingest.py`, which writes SQLite to `data/trace.db`
3. `scripts/provision_tigergraph.py --schema/--data/--documents`
4. `scripts/verify_tigergraph.py`
5. `scripts/fit_evidence_model.py`
6. `scripts/run_benchmark.py --require-graph`
7. `scripts/export_results.py`

## Hard rules: do not break these

- **The risk score is never evidence.** It carries zero weight. A test asserts that two cases that differ only in their risk score (0.02 vs 0.99) assess identically. Don't fit it, invert it or use it as a feature.
- **TigerGraph is the source of record.** SQLite is a local projection. An answer is `verified` only if it is graph-grounded, written back, read back, and has both graph and document evidence. `export_results.py` and `?verified=true` must keep refusing anything less.
- **Temporal honesty.** Prior cases and retrieved documents are only admissible if `closed_at` falls before the investigation cutoff.
- **Data semantics.**
  - `addr1` is an anonymised billing region, not a location, so make no impossible-travel claims.
  - V/C/D/M/`id_` columns are unnamed features, so never invent meanings for them.
  - A shared DeviceProfile is a lead, not an identity.
  - Card IDs are propagated only from unambiguous anchors.
- **Simulated means labelled.** Customer replies are simulated and marked `SIMULATED` with their basis. No real banking or regulatory action is ever taken.
- **No data redistribution.** `data/` and `output/` are git-ignored, and real benchmark rows must never be committed. See `DATA.md`.
- **No paid or cloud fallbacks** for model or embedding calls.
- Don't commit `.env`. `.env.example` holds only Community Edition loopback defaults.

## Conventions

- Match the surrounding style: terse, precise comments that explain *why*, and no filler. Python is formatted and linted with ruff (`select = E4,E7,E9,F,I`). The TypeScript is strict.
- Keep behaviour unchanged during refactors. This roadmap is polish and packaging with **no new product features**.
- The terminology is "benchmark", "source dataset", "verified export" and "the bank's policy". Avoid hackathon wording such as "organizer", "submission" or "judges". The only exceptions are the README's **Origin** section and the attribution in `DATA.md`.
- Use small, focused commits with one PR per roadmap phase. End commit messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Ask the user before** any of these: pushing, opening PRs, renaming the GitHub repo, changing repo settings, or publishing anything (blog, video, social).

## Roadmap

Phase 1 (identity and cleanup) is **done** on the branch `portfolio/phase1-identity`. That covered the hackathon wording, the `submission_ready` → `verified` rename, the move of `cases/` to `examples/benchmark-results/`, `LICENSE` (MIT), `DATA.md`, and version 1.0.0. Build the remaining phases on top of that branch.

### Phase 2: Make it runnable by anyone

1. **`scripts/generate_demo_data.py`**: a seeded, deterministic, fully synthetic dataset written to `data/raw/`. It must satisfy `scripts/ingest.py` exactly.
   - **`transactions.csv`**: the original IEEE-CIS columns (`TransactionID, TransactionDT, TransactionAmt, ProductCD, card1..card6, addr1, addr2, dist1, dist2, P_emaildomain, R_emaildomain, C1..C14, D1..D15, M1..M9, V1..V339`) followed by `customer_id, ts, channel, risk_score`. That is 397 columns. Unused V/C/D columns may be blank.
   - **`identity.csv`**: `TransactionID, id_01..id_38, DeviceType, DeviceInfo`. Ingest reads `DeviceInfo`, `id_30`, `id_31` and `id_33` as the device profile, `id_15` as the new/found device flag, and `id_23` as the proxy flag.
   - **`case_pack.csv`**: `case_id, opened_at, trigger_type, trigger_text, flagged_txn_id, card_id, customer_id, risk_score`.
     - Exactly **20** cases, because `export_results.py` expects 20. Use IDs `DEMO-001..DEMO-020`, not `HHG-`.
     - `trigger_type` is one of `risk_score`, `customer_report` or `analyst_request`.
     - Each flagged transaction must exist, with a matching `customer_id`. Its `card_id` must be anchored, or ingest raises a "Case anchor mismatch" error.
   - **`closed_cases_history.csv`**: `case_id, customer_id, card_id, opened_at, closed_at, outcome, pattern, first_fraud_txn_id, txn_ids, n_txns, exposure_usd, connected_card_ids, actions_taken, report_filed, analyst_notes`.
     - `outcome` ∈ {`confirmed_fraud`, `cleared`}.
     - `pattern` ∈ {`account_takeover`, `card_not_present_fraud`, `card_not_present_new_device`, `card_testing`, `out_of_region_use`, `undocumented`, `none`}.
     - `txn_ids` is pipe-separated.
     - Cases must span dates both before and after **2016-10-01**, with flagged scores ≥ **0.82**, so `fit_evidence_model.py` (`SPLIT`, `ALERT_SCORE`) has both a training set and a holdout.
   - **`README.md`**: must contain the headings `# Fraud Policy`, `# Answer Format`, `## The five known fraud patterns`, `## Regulatory references`, `## Things to know` and `## Rules`, in that order. `provision_tigergraph.py` (`corpus()`) and `api.py` (`/api/policy`) slice text between them. Write original synthetic policy text consistent with the rules R1–R6 in `policy.py`. **Do not copy the benchmark README.**
   - Plant recognisable patterns: card testing, a takeover on a known device, a multi-day run in a new region, a velocity burst against the card's own rhythm, concurrent home-region activity, and cleared "new phone / trip / one big purchase" cases.
   - Keep it about 1–2% of full size so ingest, provisioning and fitting each take minutes.
   - Select the dataset with `TRACE_DATASET=demo|full` in `config.py` and `.env.example`. `full` keeps `download_data.py` exactly as it is.
   - Before writing the generator, read `scripts/ingest.py`, `scripts/fit_evidence_model.py`, `scripts/provision_tigergraph.py` and `backend/tracework/analysis.py` in full.
2. **`docker-compose.yml`**: run `tigergraph/community:4.2.5` with the ulimits and ports from `.env.example`, plus the TigerGraph MCP server on :9001. Ollama stays on the host; document `ollama pull` for `qwen3:4b` and `all-minilm`.
3. **`Makefile`**: add the targets `setup`, `demo-data`, `ingest`, `graph` (provision and verify), `fit`, `up` (wrapping `scripts/demo_up.sh`), `test` and `lint`. Wrap the existing scripts; don't reimplement them.
4. **Optional `TRACE_GRAPH=off`**: an explicit opt-in to run on SQLite only, with a visible "not graph-grounded" banner. The default stays as it is: refuse without `TG_MCP_URL` (`tigergraph.py`). Skip this if it needs more than a flag check in the engine.

### Phase 3: Code quality

5. Split `frontend/src/App.tsx` (about 1,500 lines) into `components/`, `api.ts` and `types.ts`. Make it a pure move with no behaviour change.
6. Frontend:
   - Add eslint and a `lint` script.
   - Add a `format` script using the prettier that is already installed.
   - Add Vitest + Testing Library tests for the findings arithmetic and the approval-route display.
7. Backend:
   - Add `ruff format` (format-only commit).
   - Add tests for the generator (schema contract and determinism).
   - Add `pytest-cov`.
   - Leave `engine.py` alone except where Phase 2 needs a change.
8. Add `.github/workflows/ci.yml`. It runs `uv sync`, then ruff check and format check, then pytest, then `npm ci`, the build, the tests and lint.
9. Add `.editorconfig`, `.pre-commit-config.yaml` (ruff and prettier) and a short `CONTRIBUTING.md`.

### Phase 4: Presentation

10. Rewrite the README so it can be skimmed in 30 seconds:
    - pitch and badges
    - hero screenshot or GIF
    - the risk-score finding (ROC-AUC 0.053) and the signal table
    - results (holdout ROC-AUC 0.849, Brier 0.157, episode Jaccard 0.595)
    - the mermaid architecture diagram
    - quickstart with `make` and demo data
    - limitations
    - Origin
    - license and data

    Move the long engineering notes (laptop tuning, MCP payload sizes, vector-search fallback) to `docs/ENGINEERING_NOTES.md`.
11. Screenshots go in `docs/images/`. The user records the video and publishes the blog (`docs/BLOG_DRAFT.md`, written in first person singular). Help prepare these, but don't publish them.

### Phase 5: GitHub and resume (needs user approval)

12. Rename the repo to something like `trace-fraud-workbench`. Add a description and topics (`fraud-detection`, `tigergraph`, `graphrag`, `llm-agents`, `fastapi`, `react`, `ollama`, `mcp`), a social preview image and a pin. Write the profile README `darain24/darain24`. Tag `v1.0.0`.

## Definition of done

- Starting from a fresh clone with no `data/`, this sequence brings up the UI at :5173 and runs one investigation end to end:
  ```bash
  make setup && make demo-data && make ingest && make graph && make fit && make up
  ```
- `make test` and `make lint` pass, and CI is green.
- `grep -rniE 'organi[sz]er|submission|judge|team lead|deadline'` (excluding `data/`, `node_modules/` and the lockfiles) matches only the Origin section and the `DATA.md` attribution.
- `TRACE_DATASET=full` still ingests and reproduces `examples/benchmark-results/`.
