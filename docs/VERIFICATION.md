# Verification report

Recorded against TigerGraph Community Edition 4.2.5 running locally in Docker, reached
through the official TigerGraph MCP server, on an Apple M3 with 8 GB of memory.

## TigerGraph

| | |
|---|---|
| Graph | `Trace`, created from `tigergraph/schema.gsql` |
| Transaction vertices | 42,566 |
| Closed cases | 5,565 |
| Cards / customers / device profiles | 2,203 / 2,153 / 2,651 |
| Billing regions / email domains | 118 / 54 |
| Vector documents | 503, 384-dimension `all-minilm`, COSINE |
| Investigation vertices written by the agent | 20 |
| Data edges | `MADE` 42,566 · `NEXT` 40,363 · `PURCHASER_EMAIL` 37,319 · `BILLED_IN` 26,188 · `FROM_DEVICE` 20,738 · `INVOLVES` 14,955 · `CASE_ON_CARD` 5,565 · `OWNS` 2,203 |
| Case-memory edges | `CITES` 91 · `FINDING` 41 · `INVESTIGATES` 20 · `CONNECTED_TO` 2 · `SEEN_ON` 1 |

- Graph/local evidence parity verified for all 20 cases: 1,868 transactions checked by
  window aggregate, plus a capped per-row sample and an explicit fetch of each flagged
  transaction.
- Vector context retrieved for all 20 cases (6 documents each, policy and case narratives
  ranked separately), filtered so no investigation reads a case closed after its alert.
- Case write and read-back verified for all 20. Read-back compares the archived payload
  byte for byte before persistence is claimed.
- 0 TigerGraph errors and 0 local-model errors on the recorded run.

## Benchmark output

| | |
|---|---|
| Cases | 20 / 20 graph-backed and verified |
| Verdicts | 11 fraud · 6 legitimate · 3 uncertain |
| Patterns | 4 `card_not_present_new_device` · 4 `card_not_present_fraud` · 4 `undocumented` · 1 `account_takeover` · 7 `none` |
| Statuses | 7 `closed_fraud` · 6 `closed_legitimate` · 7 `escalated` |
| Evidence items | 231 total, 9–15 per case: 151 `graph`, 60 `document`, 20 `customer` |
| Prior cases cited | 91 |
| Evidence requests | 7, of which 4 changed the recommendation |
| Suspicious activity reports | 1 |
| Episode sizes | nine of two transactions, four of one, one of five, six empty (legitimate) |
| Graph and retrieval calls | 411 (20.6 per case) |
| Local-model tokens | 21,122 (`qwen3:4b`, local, cached on rerun) |

Independent audit of all 20 answers against the benchmark's answer format passes: field
sets, enum values, ID existence against the dataset, exposure arithmetic against the named
transactions, SAR/action agreement, empty-SAR field discipline, narrative length 6–12
sentences, summary length 2–6 sentences, and recommendation changes only where an evidence
request was recorded.

## Assessment model

Fitted on closed investigations opened before October 2016 whose flagged transaction scored
at or above 0.82 — the alerts where the evidence, not the alert, had to decide. Reproduce
with `scripts/fit_evidence_model.py`, which writes `output/evidence-model.json`.

| | Train | Holdout |
|---|---|---|
| Split | opened before 2016-10-01 | opened on or after |
| Cases | 1,168 | 278 |
| Fraud rate | 37.5% | 48.2% |
| ROC-AUC | — | **0.849** |
| Accuracy | — | **0.791** |
| Brier | — | **0.157** |

The bank's risk score is excluded. Across all 5,565 closed cases it scores ROC-AUC 0.053 —
near-perfectly inverted — because it selects which alerts are opened rather than which
activity is fraud. `test_score_alone_cannot_move_the_assessment` asserts that two cases
differing only in score assess identically.

Episode scope validated against the same 250 October confirmed-fraud episodes. The shipped
rule — same card, same channel, within six hours of the flagged transaction, capped at two —
scores precision 0.78, recall 0.72, Jaccard 0.595, and a median relative exposure error of
0.34.

| Window | Jaccard | Median exposure error | Mean exposure error |
|---|---|---|---|
| ±6h, cap 1 | — | 0.36 | 0.35 |
| **±6h, cap 2** | **0.595** | **0.34** | **0.63** |
| ±6h, cap 4 | 0.555 | 0.38 | 1.13 |
| ±48h, cap 4 | 0.488 | — | — |

Wider or larger windows trade more precision than they gain in recall, and over-scoping
inflates exposure, which is what drives the reporting threshold and the approval route.
Real episodes are small: the median confirmed episode is one transaction. Agreement with
the $1,000 reporting threshold sits at 0.90 across every cap tested, so no scoping choice
fixes cases that land near it — HHG-006 assesses at $970.16 and gets a case without a
report on that basis.

## Diagnostic on 200 October closed cases

| Strategy | Correct | Abstained | Brier |
|---|---|---|---|
| Bank risk score alone (≥0.7 ⇒ fraud) | 27 / 200 | 0 | 0.560 |
| Trace | **111 / 200** | 61 | **0.189** |
| Trace with case memory withheld | 111 / 200 | 61 | 0.189 |

Of the 139 cases Trace decided, 111 were correct — 79.9%. The previous hand-tuned heuristic
scored 0 of 40 on the same holdout and abstained on 31 of them.

**Case memory shows no measured effect on this sample and none is claimed.** Withholding
prior cases leaves the probability unchanged here, because the network finding that depends
on them requires two or more corroborated connected cards, which does not occur in this
selection. Memory does change what the case file cites, and it drives the shared-origin
finding in HHG-014.

## Engineering checks

- 39 backend tests pass. The suite is isolated from any live graph: `conftest.offline_graph`
  clears `TG_URL`, because without it the fixture cases were being written into the real
  workspace.
- Production frontend build passes. Ruff passes.
- `scripts/check_outputs.py`: 20 cases, 20 valid, 20 verified, 0 errors.
- The exporter refuses any case that is not grounded, not written back with a verified
  read-back, or missing graph or document evidence. It caught a real instance of this
  during development, where a case persisted while its evidence was local-only.

## Limitations

The holdout is October alerts from the investigated population, which is not the general
transaction population and not the hidden benchmark. Twenty valid graph-backed answers is a
completeness result, not an accuracy one. The gradient-boosted model in
`scripts/train_assessment.py` scores ROC-AUC 0.966 on October but saturates at 0.99 on 19 of
the 20 benchmark cases; it stays advisory and never drives a verdict. Customer replies are
simulated and labelled. No customer, card, or regulator is contacted.

Vector similarity currently ranks client-side over the vectors held in TigerGraph, because
`vectorSearch` exists only inside an installed query and this container cannot compile one.
Which path ran is recorded on every case, and the retrieved documents are read back out of
the graph by id.
