# Engineering notes

The README keeps to what Trace is and how to run it. This is the rest: the
assessment arithmetic, how TigerGraph is used and why, running Community Edition
on a laptop, the manual path for the full benchmark, and the data semantics the
code holds to.

## Assessment model

Each finding carries a log-odds weight fitted on the bank's own closed cases —
investigations opened before October 2016 whose flagged transaction scored 0.82 or
above, because those are the alerts where evidence rather than the alert had to
decide. That subpopulation is 37.5% fraud, close to the benchmark's stated mix.
Held out on the 278 October alerts of the same kind (48.2% fraud): ROC-AUC 0.849,
accuracy 0.791, Brier 0.157. `scripts/fit_evidence_model.py` refits and re-verifies
the weights.

The probability is the sum of named contributions, and the workbench shows the
arithmetic:

```
prior                                              +0.92
+ device already known to the account              +1.38
+ multi-day run in a billing region not in baseline+1.26
+ velocity burst against the card's own rhythm     +0.35
- card-present with no identity record             -0.30
                                                   -----
                                            log-odds 3.61  ->  p = 0.97
```

Card testing is applied as policy rule R5 with a fixed weight rather than a fitted
one: it appears in 16 of 5,565 closed cases, too few to fit honestly.

Episode scope was validated the same way, against 250 October confirmed-fraud
episodes: same card, same channel, within six hours of the flagged transaction,
capped at two. Precision 0.78, recall 0.72, Jaccard 0.595, median relative exposure
error 0.34 — against Jaccard 0.555 at a cap of four and 0.488 at ±48 hours. Real
episodes are small; the median confirmed episode is one transaction, and
over-scoping inflates the exposure that decides the reporting threshold and the
approval route.

The historical gradient-boosted model in `scripts/train_assessment.py` scores
ROC-AUC 0.966 on October but saturates at 0.99 on 19 of the 20 benchmark cases — a
plain distribution mismatch — so it stays advisory and never drives a verdict.

## The agent loop in detail

1. **Trigger** — a risk score, a customer report, or an analyst request from
   `case_pack.csv`.
2. **Investigate** — `analysis.collect` assembles a bounded evidence packet:
   customer baseline, the card's 48-hour window against its own 30-day rhythm,
   device-profile neighbours, concurrent home-region activity, and closed cases
   admissible before the alert.
3. **Ground in the graph** — `retrieval.ground` re-derives all of it through GSQL
   over TigerGraph MCP and **refuses to continue if the graph disagrees**. Local
   SQLite is a convenience projection, never the source of record.
4. **Retrieve context** — vector search over the embedded documents held in
   TigerGraph: the fraud policy, the five documented patterns, the regulatory
   reference list, and closed-case analyst narratives. Ranked separately by kind so
   the policy is never buried under case notes, and filtered by `closed_at` so no
   investigation can read a case closed after its own alert.
5. **Assess** — weighted findings produce a probability, a verdict, a pattern and
   an episode.
6. **Decide whether it can act** — under R1 a weak or single-signal case is
   verified before anything with customer impact.
7. **Request evidence** — the agent raises a request, simulates the reply, and
   records the assumption and its basis. A corroborated shared-origin cluster skips
   this: one cardholder's answer cannot settle whether several cards run through
   one device profile, and R6 routes it to a report instead.
8. **Recommend again** — `next_best_actions.initial` and `.final` with routes, plus
   `what_changed`.
9. **Explain and stop** — `stop_reason` cites the policy clause and says what
   further work would not change.
10. **Write case memory** — the case is written to the graph with queryable
    attributes and linked to its transactions, card, connected cards, device
    profile and cited prior cases.

Only `auto` actions are ever executed. `L1` and `L2` are recommended with the route
stated and wait for a human. No customer is contacted, no card is blocked, no
report is filed.

## How TigerGraph is used

**Schema** (`tigergraph/schema.gsql`). Customers own cards, cards make
transactions, transactions attach to device profiles, billing regions and email
domains, and run in `NEXT` sequence. Closed cases link to their transactions and
cards. `Investigation` is the agent's own case memory, with queryable attributes
rather than an opaque blob, linked by `FINDING`, `INVESTIGATES`, `CONNECTED_TO`,
`SEEN_ON` and `CITES`.

**Queries** (`tigergraph/queries.gsql`). Customer window, device window, case
memory, prior investigations, and a bounded network expansion over shared device
profiles. All are cutoff-bounded: an investigation can never see activity recorded
after its own alert opened.

They run **interpreted**. `INSTALL QUERY` compiles to native code, and on a
Community Edition container that compile is the one step that reliably exhausts
memory. Interpreting runs the same GSQL against the same graph without it. The
provisioning script still installs them where the host has headroom.

Parity is checked by **aggregate plus bounded sample** rather than by pulling every
row back. TigerGraph answers a 514-row projection in four seconds, but the MCP
server re-serialises each result into a markdown envelope and repeats it in its
summary, so a few hundred rows become a multi-megabyte streamed response that times
out. The aggregate covers the whole window; the sample and an explicit fetch cover
the rows the case cites.

**Vector store.** `Document` carries a 384-dimension `all-minilm` embedding, added
through MCP with `add_vector_attribute` and filled with `upsert_vectors`. Retrieval
is filtered by `closed_at`, so GraphRAG obeys the same time boundary as the graph
traversal, and the policy chunks and case narratives are ranked separately so a
recommendation always has a rule to cite.

On the benchmark the corpus is 503 documents, not 5,565. The historical analyst
notes collapse to about 370 distinct templates once identifiers, dates and amounts
are masked; embedding all of them adds no retrievable meaning and buries the 37
policy chunks under a thousand near-identical sentences. Every case belonging to a
benchmark customer or card is kept in full.

**On the similarity search.** MCP's `search_top_k_similarity` generates and
_installs_ a fresh GSQL query for every distinct search — `_vec_search_<hash>` — so
each call compiles native code. That took 116 seconds per search here and was what
kept killing GSQL. `vectorSearch` itself takes the query vector as a query
parameter, so it only exists inside an installed query, and this container cannot
compile one at all. So: where `trace_vector_search` is installed, the search runs
server-side; where it is not, the top-k scan runs client-side over the same
TigerGraph-held vectors and the winning documents are read back out of the graph by
id. Which path ran is recorded on every case. Grounding went from 100–150 seconds
to 2–6.

## Running Community Edition on a laptop

Community Edition is free and complete, but its defaults assume a server. Tested on
an Apple M3 with 8 GB of memory; the image is amd64 and runs emulated on Apple
Silicon, so expect it to be slow and to warm the machine.

- **Right-size the services** (`make graph-tune`). Kafka Connect is allocated 10 GB
  out of the box. On a 3.8 GB Docker VM the kernel's OOM killer takes the largest
  process, which is the graph store engine. The same target lifts RESTPP's 16 s
  default query timeout, which the first data loads into a fresh emulated container
  exceed.
- **Do not depend on installed queries.** `INSTALL QUERY` compiles to native code
  and is the single step that reliably exhausts memory. The queries run interpreted
  from the same reviewed bodies.
- **Keep MCP payloads small.** See parity above.
- **A fresh container has no schema**, and GSE and GPE stay in `Warmup` until one
  exists. `scripts/demo_up.sh` treats that state as ready enough to install the
  schema, rather than waiting for services that cannot come up yet.
- **The MCP server must see TigerGraph on its own loopback.** The workbench
  forwards its `TG_HOST` (`http://127.0.0.1`) with every MCP call, overriding the
  server's own profile. On the host that is right; in `docker-compose.yml` the MCP
  container shares TigerGraph's network namespace so it stays right.
- **Expect the occasional dropped service under load.** Grounding queries, the
  local model and case write-back arriving back to back can saturate an emulated
  container, and a write-back that times out leaves the case unverified rather than
  claiming it. `scripts/run_benchmark.py --require-graph` re-runs exactly those
  cases.

## Full benchmark, step by step

`make full-data` and the README's quickstart cover this; the manual path is below
for when something needs to be done by hand. Set `TRACE_DATASET=full` in `.env`
first.

```bash
uv sync --extra dev
npm ci --prefix frontend
uv run python scripts/download_data.py
uv run python scripts/ingest.py
ollama pull qwen3:4b && ollama pull all-minilm
```

Start Community Edition (`docker compose up -d` does the same, bound to loopback):

```bash
docker run -d --platform linux/amd64 --name tigergraph \
  --ulimit nofile=1000000:1000000 \
  -p 14022:22 -p 9000:9000 -p 14240:14240 \
  tigergraph/community:4.2.5
```

Services take a few minutes to warm up. Watch
`docker exec -u tigergraph tigergraph /home/tigergraph/tigergraph/app/cmd/gadmin status`
until nothing reads `Warmup` (on a fresh container GSE and GPE wait for the schema).
Right-size it once with `make graph-tune`. Then start the official MCP server and
provision:

```bash
cp .env.example .env          # already points at the local container
uv run tigergraph-mcp --env-file .env --transport streamable-http --host 127.0.0.1 --port 9001

uv run python scripts/provision_tigergraph.py --schema
uv run python scripts/provision_tigergraph.py --data
uv run python scripts/provision_tigergraph.py --documents
uv run python scripts/verify_tigergraph.py
```

`--data` loads the benchmark subgraph: the complete history of the twenty benchmark
customers, every transaction sharing a flagged device profile or billing region
inside the alert's lookback, and every transaction named by a closed case —
**42,566 transactions, 2,203 cards, 2,651 device profiles and all 5,565 closed
cases**. Everything outside that set is unreachable from the twenty triggers.
`--full` loads all 590,742 rows if you have the time and the RAM.

Then investigate:

```bash
uv run python scripts/train_assessment.py          # optional advisory model
uv run python scripts/run_benchmark.py --require-graph
uv run python scripts/export_results.py
./scripts/dev.sh
```

`--require-graph` re-runs any case that did not end up graph-backed.
`export_results.py` refuses to promote a case into `examples/benchmark-results/`
unless it is grounded in the graph, written back with a verified read-back, carries
both graph and document evidence, and passes every policy and ID check. With
`TRACE_DATASET=demo` it writes to `output/demo-results/` instead.

## Verification commands

```bash
make test lint                                  # both suites, coverage, all linters
uv run python scripts/check_outputs.py          # every saved answer validates
uv run python scripts/verify_tigergraph.py      # graph + vector grounding
uv run python scripts/fit_evidence_model.py     # refit and re-verify the weights
```

Tests cover policy thresholds and approval routes, the ban on the risk score
contributing weight, non-mutating scenario exploration, evidence-request
supersession, preserved initial recommendations, fabricated IDs, persistence that
cannot be claimed without a verified read-back, the verified-export guards, the
demo dataset's contract and determinism, and the workbench's findings and approval
displays.

## Data semantics we hold to

- A risk score starts an investigation. It is never evidence, and it carries no
  weight.
- A DeviceProfile is DeviceInfo, OS, browser and screen combined. Common handsets
  collide. Sharing one is a lead, not an identity.
- `addr1` is an anonymised billing-region code, not a geolocation. No
  impossible-travel claims.
- The V, C, D, M and numeric `id_` columns are unnamed Vesta features. They are
  used as signals and described as such, never given invented meanings.
- Merchant identity and authorisation settlement status are not in the dataset, so
  recurring-charge findings are stated as hypotheses.
- Card IDs are propagated from benchmark anchors only where the six-field card
  signature maps unambiguously. Unresolved cards keep internal IDs and never appear
  in an exported answer.
- Prior cases are retrieved only if closed before the investigation's cutoff.
- Customer replies are simulated, labelled `SIMULATED`, and recorded in
  `evidence_requests` with the basis for the assumption.
- No original Kaggle files are used to recover outcomes.

## The demo dataset

`scripts/generate_demo_data.py` writes a seeded, fully synthetic dataset in the
benchmark's column layout at about 1.5% of its size: about 150 customers, about 9,300
transactions, 244 closed cases and twenty open cases, `DEMO-001` to `DEMO-020`. It
plants the shapes the assessment is built to separate — card testing, takeover
from a known device, multi-day new-region runs, velocity bursts, concurrent home
activity, a device ring shared across customers, a recurring-charge dispute, and
the cleared new-phone, trip and big-purchase alerts — and draws the risk score
independently of the outcome. The same seed always writes the same bytes. Numbers
fitted on it describe the synthetic data, not the benchmark.
