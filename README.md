# Trace

**Evidence before action.** An agentic fraud-investigation workbench built on TigerGraph.

A fraud alert is not a verdict. Trace takes one of the twenty benchmark triggers, gathers evidence from a TigerGraph knowledge graph and vector store, weighs it against the shapes the bank's own closed cases actually took, decides whether it can act, asks for more evidence when it cannot, recommends actions under the supplied policy with their approval routes, and writes the case back into the graph so the next investigation can find it.

Everything runs locally: TigerGraph Community Edition in Docker, the official TigerGraph MCP server, and Ollama for reasoning and embeddings. No cloud account, no API key, no billing.

---

## The finding that shaped the agent

The bank's risk score is **anti-correlated with confirmed fraud** inside the closed-case record. Across all 5,565 closed investigations it scores ROC-AUC **0.053** — near-perfectly inverted. Every single cleared case scored 0.82 or higher.

That is not a model that is wrong. It is a model doing its job: it decides which alerts get opened, and the alerts it screams loudest about are the ones where the cardholder turns out to have bought a new phone, taken a trip, or made one unusually large purchase. Confirmed fraud arrives mostly through customer reports, at scores that are often low.

It would be easy to exploit. Inverting the score alone scores 93% on a balanced October holdout. **Trace does not use it**, and there is a test asserting that two otherwise identical cases scoring 0.02 and 0.99 assess identically. The inversion is a property of which alerts the bank chose to close, not of fraud, and the benchmark draws its risk-score triggers from 0.52 to 0.90 — a different sampling frame entirely. Fitting it would be fitting the exam's construction.

What survives when the score is removed is behaviour, and it inverts the obvious intuitions:

| Signal | Naive reading | What the closed cases show |
|---|---|---|
| Device marked `New` for the account | suspicious | **strongest counter-indicator** — 12.3% fraud among high-score alerts |
| Device already known (`Found`) | reassuring | **93.4% fraud** |
| Billing region never seen before | suspicious | more common in *cleared* cases |
| Amount far above the customer's median | suspicious | 23.0% fraud when nothing else changed |
| Velocity against the card's own 30-day rhythm | — | the real signal |
| Concurrent activity in the home region | — | the card was cloned, not carried |

## Assessment model

Each finding carries a log-odds weight fitted on the bank's own closed cases — investigations opened before October 2016 whose flagged transaction scored 0.82 or above, because those are the alerts where evidence rather than the alert had to decide. That subpopulation is 37.5% fraud, close to the benchmark's stated mix.

**Held out on the 278 October alerts of the same kind (48.2% fraud): ROC-AUC 0.849, accuracy 0.791, Brier 0.157.**

The probability is the sum of named contributions, and the workbench shows the arithmetic:

```
prior                                              +0.92
+ device already known to the account              +1.38
+ multi-day run in a billing region not in baseline+1.26
+ velocity burst against the card's own rhythm     +0.35
- card-present with no identity record             -0.30
                                                   -----
                                            log-odds 3.61  ->  p = 0.97
```

Card testing is applied as policy rule R5 with a fixed weight rather than a fitted one: it appears in 16 of 5,565 closed cases, too few to fit honestly.

Episode scope was validated the same way, against 250 October confirmed-fraud episodes: same card, same channel, within six hours of the flagged transaction, capped at two. Precision 0.78, recall 0.72, Jaccard 0.595, median relative exposure error 0.34 — against Jaccard 0.555 at a cap of four and 0.488 at ±48 hours. Real episodes are small; the median confirmed episode is one transaction, and over-scoping inflates the exposure that decides the reporting threshold and the approval route.

## What the agent does

1. **Trigger** — a risk score, a customer report, or an analyst request from `case_pack.csv`.
2. **Investigate** — `analysis.collect` assembles a bounded evidence packet: customer baseline, the card's 48-hour window against its own 30-day rhythm, device-profile neighbours, concurrent home-region activity, and closed cases admissible before the alert.
3. **Ground in the graph** — `retrieval.ground` re-derives all of it through GSQL over TigerGraph MCP and **refuses to continue if the graph disagrees**. Local SQLite is a convenience projection, never the source of record.
4. **Retrieve context** — vector search over 503 embedded documents held in TigerGraph: the fraud policy, the five documented patterns, the regulatory reference list, and closed-case analyst narratives. Ranked separately by kind so the policy is never buried under case notes, and filtered by `closed_at` so no investigation can read a case closed after its own alert.
5. **Assess** — weighted findings produce a probability, a verdict, a pattern and an episode.
6. **Decide whether it can act** — under R1 a weak or single-signal case is verified before anything with customer impact.
7. **Request evidence** — the agent raises a request, simulates the reply, and records the assumption and its basis. A corroborated shared-origin cluster skips this: one cardholder's answer cannot settle whether several cards run through one device profile, and R6 routes it to a report instead.
8. **Recommend again** — `next_best_actions.initial` and `.final` with routes, plus `what_changed`.
9. **Explain and stop** — `stop_reason` cites the policy clause and says what further work would not change.
10. **Write case memory** — the case is written to the graph with queryable attributes and linked to its transactions, card, connected cards, device profile and cited prior cases.

Only `auto` actions are ever executed. `L1` and `L2` are recommended with the route stated and wait for a human. No customer is contacted, no card is blocked, no report is filed.

## Run it

Prerequisites: Docker, Python 3.11+, Node 22+, uv, Ollama. Tested on an Apple M3 with 8 GB of memory.

```bash
uv sync --extra dev
npm ci --prefix frontend
uv run python scripts/download_data.py
uv run python scripts/ingest.py
ollama pull qwen3:4b && ollama pull all-minilm
```

### TigerGraph Community Edition

Free for production, research and educational use. The image is amd64 and runs emulated on Apple Silicon.

```bash
docker run -d --platform linux/amd64 --name tigergraph \
  --ulimit nofile=1000000:1000000 \
  -p 14022:22 -p 9000:9000 -p 14240:14240 \
  tigergraph/community:4.2.5
```

Services take a few minutes to warm up. Watch `docker exec -u tigergraph tigergraph /home/tigergraph/tigergraph/app/cmd/gadmin status` until nothing reads `Warmup`.

The image is configured for a much larger host than a laptop VM. Right-size it once:

```bash
docker exec -u tigergraph tigergraph bash -lc '
G=/home/tigergraph/tigergraph/app/cmd/gadmin
$G config set KafkaConnect.MaxMemorySizeMB 512
$G config set KafkaStreamLL.MaxMemorySizeMB 256
$G config set ZK.BasicConfig.Env "ZK_SERVER_HEAP=256;"
$G config set Kafka.BasicConfig.Env "KAFKA_HEAP_OPTS=-Xms128M -Xmx512M;"
$G config apply -y && $G restart all -y'
```

Without this, Kafka Connect alone is allocated 10 GB and GSQL is killed by the kernel under query load.

Then start the official MCP server and provision:

```bash
cp .env.example .env          # already points at the local container
uv run tigergraph-mcp --env-file .env --transport streamable-http --host 127.0.0.1 --port 9001

uv run python scripts/provision_tigergraph.py --schema
uv run python scripts/provision_tigergraph.py --data
uv run python scripts/provision_tigergraph.py --documents
uv run python scripts/verify_tigergraph.py
```

`--data` loads the benchmark subgraph: the complete history of the twenty benchmark customers, every transaction sharing a flagged device profile or billing region inside the alert's lookback, and every transaction named by a closed case — **42,566 transactions, 2,203 cards, 2,651 device profiles and all 5,565 closed cases**. Everything outside that set is unreachable from the twenty triggers. `--full` loads all 590,742 rows if you have the time and the RAM.

### Investigate

```bash
uv run python scripts/train_assessment.py          # optional advisory model
uv run python scripts/run_benchmark.py --require-graph
uv run python scripts/export_results.py
./scripts/dev.sh
```

Open http://127.0.0.1:5173. API docs at http://127.0.0.1:8000/docs.

`--require-graph` re-runs any case that did not end up graph-backed. Community Edition on a small container drops a service under load often enough that one pass is not a reliable result. `export_results.py` refuses to promote a case into `examples/benchmark-results/` unless it is grounded in the graph, written back with a verified read-back, carries both graph and document evidence, and passes every policy and ID check.

## Verify

```bash
uv run pytest -q
npm run build --prefix frontend
uv run python scripts/check_outputs.py
uv run ruff check .

uv run python scripts/verify_tigergraph.py      # graph + vector grounding
uv run python scripts/fit_evidence_model.py     # refit and re-verify the weights
```

Tests cover policy thresholds and approval routes, the ban on the risk score contributing weight, non-mutating scenario exploration, evidence-request supersession, preserved initial recommendations, fabricated IDs, persistence that cannot be claimed without a verified read-back, and the verified-export guards.

## How TigerGraph is used

**Schema** (`tigergraph/schema.gsql`). Customers own cards, cards make transactions, transactions attach to device profiles, billing regions and email domains, and run in `NEXT` sequence. Closed cases link to their transactions and cards. `Investigation` is the agent's own case memory, with queryable attributes rather than an opaque blob, linked by `FINDING`, `INVESTIGATES`, `CONNECTED_TO`, `SEEN_ON` and `CITES`.

**Queries** (`tigergraph/queries.gsql`). Customer window, device window, case memory, prior investigations, and a bounded network expansion over shared device profiles. All are cutoff-bounded: an investigation can never see activity recorded after its own alert opened.

They run **interpreted**. `INSTALL QUERY` compiles to native code, and on a Community Edition container that compile is the one step that reliably exhausts memory. Interpreting runs the same GSQL against the same graph without it. The provisioning script still installs them where the host has headroom.

Parity is checked by **aggregate plus bounded sample** rather than by pulling every row back. TigerGraph answers a 514-row projection in four seconds, but the MCP server re-serialises each result into a markdown envelope and repeats it in its summary, so a few hundred rows become a multi-megabyte streamed response that times out. The aggregate covers the whole window; the sample and an explicit fetch cover the rows the case cites.

**Vector store.** `Document` carries a 384-dimension `all-minilm` embedding, added through MCP with `add_vector_attribute` and filled with `upsert_vectors`. Retrieval is filtered by `closed_at`, so GraphRAG obeys the same time boundary as the graph traversal, and the policy chunks and case narratives are ranked separately so a recommendation always has a rule to cite.

The corpus is 503 documents, not 5,565. The historical analyst notes collapse to about 370 distinct templates once identifiers, dates and amounts are masked; embedding all of them adds no retrievable meaning and buries the 37 policy chunks under a thousand near-identical sentences. Every case belonging to a benchmark customer or card is kept in full.

**On the similarity search.** MCP's `search_top_k_similarity` generates and *installs* a fresh GSQL query for every distinct search — `_vec_search_<hash>` — so each call compiles native code. That took 116 seconds per search here and was what kept killing GSQL. `vectorSearch` itself takes the query vector as a query parameter, so it only exists inside an installed query, and this container cannot compile one at all. So: where `trace_vector_search` is installed, the search runs server-side; where it is not, the top-k scan runs client-side over the same TigerGraph-held vectors and the winning documents are read back out of the graph by id. Which path ran is recorded on every case. Grounding went from 100–150 seconds to 2–6.

## Building the graph on a laptop

Community Edition is free and complete, but its defaults assume a server. Three things mattered:

- **Right-size the services.** Kafka Connect is allocated 10 GB out of the box. On a 3.8 GB Docker VM the kernel's OOM killer takes the largest process, which is the graph store engine.
- **Do not install queries.** `INSTALL QUERY` compiles to native code and is the single step that reliably exhausts memory. The queries run interpreted from the same reviewed bodies.
- **Keep MCP payloads small.** TigerGraph returns a 514-row projection in four seconds; the MCP server then wraps it in a markdown envelope and repeats it in its summary, turning a few hundred rows into a multi-megabyte streamed response that times out. Verification therefore compares an aggregate over the whole window plus a capped sample, which is a stronger check than the rows we would otherwise have pulled.

## Data semantics we hold to

- A risk score starts an investigation. It is never evidence, and it carries no weight.
- A DeviceProfile is DeviceInfo, OS, browser and screen combined. Common handsets collide. Sharing one is a lead, not an identity.
- `addr1` is an anonymised billing-region code, not a geolocation. No impossible-travel claims.
- The V, C, D, M and numeric `id_` columns are unnamed Vesta features. They are used as signals and described as such, never given invented meanings.
- Merchant identity and authorisation settlement status are not in the dataset, so recurring-charge findings are stated as hypotheses.
- Card IDs are propagated from benchmark anchors only where the six-field card signature maps unambiguously. Unresolved cards keep internal IDs and never appear in an exported answer.
- Prior cases are retrieved only if closed before the investigation's cutoff.
- Customer replies are simulated, labelled `SIMULATED`, and recorded in `evidence_requests` with the basis for the assumption.
- No original Kaggle files are used to recover outcomes.

## Repository map

- `backend/tracework/` — `analysis` (evidence and weighted findings), `retrieval` (GraphRAG and parity), `tigergraph` (MCP adapter, GSQL bodies, case persistence), `policy` (the supplied rules), `engine` (orchestration, SAR, recommendations), `api`, `llm`, `scoring`, `evaluation`, `store`.
- `frontend/` — React workbench: timeline, relationship graph, weighted findings breakdown, scenario explorer, approvals, event history.
- `tigergraph/` — schema and query definitions.
- `scripts/` — download, ingest, provision, verify, train, benchmark, review, export.
- `docs/` — architecture, PRD, walkthrough, blog draft, verification report.
- `examples/benchmark-results/` — twenty reference answers, promoted only by the guarded exporter.
- `output/draft-cases/` — drafts from the most recent run (git-ignored).

## Limitations

The assessment is fitted on investigated alerts, which are not the general transaction population; its probabilities are calibrated for that frame. Holdout accuracy on October alerts is not benchmark accuracy, and the benchmark answer key is hidden. The historical gradient-boosted model in `scripts/train_assessment.py` scores ROC-AUC 0.966 on October but saturates at 0.99 on 19 of the 20 benchmark cases — a plain distribution mismatch — so it stays advisory and never drives a verdict. Approvals in the UI are demo controls, not role-based authentication. Every banking and regulatory action is simulated.

## Origin

Trace started as my solo entry for TigerGraph's Hacker House Goa 2026 (Task 4), and has since been extended into a standalone project.

## License and data

Code is MIT-licensed (see `LICENSE`). The benchmark data is an adaptation of the IEEE-CIS Fraud Detection dataset (Vesta Corporation, via the IEEE Computational Intelligence Society), prepared by TigerGraph. None of it is redistributed in this repository. See `DATA.md`.
