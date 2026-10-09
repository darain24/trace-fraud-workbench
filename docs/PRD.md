# Trace product requirements

## Product promise

An investigator should be able to explain what happened, what is uncertain, what additional evidence matters, and which action the supplied bank policy permits. A useful investigation combines accurate graph evidence with visible decision changes and complete audit records.

Primary audience: fraud analysts and investigation leads. Constraints: no paid services; runs on a laptop (developed on an M3 with 8 GB); TigerGraph is the source of record.

## Quality goals

| Goal | Implementation |
|---|---|
| Investigation accuracy | Weighted evidence findings fitted on the bank's closed cases and held out (ROC-AUC 0.849); episode scope validated against 250 confirmed episodes; the bank's risk score excluded as a selection artefact |
| Next best action | Policy-controlled actions, initial/final recommendations, explicit verification and escalation |
| Explainability | Provenance, evidence graph, supporting/contradicting findings, short case summaries |
| Agentic engineering | Stateful workflow, bounded local-model tool selection, durable events, idempotent evidence/approval operations |
| Innovation | Decision-changing evidence scenarios, undocumented-pattern corroboration, candidate discovery, replay |
| Reproducibility | Real-data workbench against a live local TigerGraph, reproducible exports, recorded verification |

## Required workflow

Trigger → retrieve → compare explanations → assess → apply policy → request evidence if needed → reassess → stop or escalate → persist → export.

The state includes immutable initial actions, current actions, exposure, verdict, pattern, evidence, prior-case references, simulation assumptions, decision revision, approvals, graph-persistence status, tool counts, tokens, and latency.

## Functional requirements

1. All 20 benchmark cases load into a searchable queue and can be investigated independently.
2. Transaction, customer, card, device-profile, and region data are traceable to actual source rows.
3. Card IDs are anchored and ambiguity is explicit; unnamed model features retain unnamed semantics.
4. Existing confirmed and cleared historical cases inform evidence; new predictions never masquerade as confirmed outcomes.
5. Device sharing needs behavioral corroboration. Graph links alone do not imply guilt.
6. The documented patterns are investigated; supported coordinated abuse may remain `undocumented` rather than being forced into a category.
7. Every next action obeys the supplied policy and approval route. Missing settlement data prevents a claim that a purchase cleared.
8. An original customer denial is distinguished from a simulated response. Scenario exploration is non-mutating; recorded simulated responses are visibly labeled.
9. The interface supports evidence selection, graph inspection, timeline review, action history, approval simulation, SAR preview, export, and recorded replay.
10. Graph records and vector grounding are required for a verified export. Local-mode drafts cannot be silently promoted.
11. Candidate discovery stays outside the benchmark folder. Evaluation reports actual measurements and limitations.
12. Local model and embedding calls cannot fall back to paid endpoints.

## Acceptance and operational quality

- Exact answer schema and dataset-ID checks; exposure is computed from selected transactions.
- SAR fields agree with final actions; legitimate verdicts carry no affected fraud transactions or exposure.
- No restricted action runs without matching approval, and this demo never performs actual financial operations.
- Duplicate responses and approvals are idempotent; stale-revision approvals fail.
- All evidence retrieval respects the investigation cutoff.
- Service failures are visible. A failed query is never interpreted as an absence of suspicious activity.
- Graph writes are independently read back before persistence is claimed.
- Desktop and narrow-screen workflows remain usable; fonts are bundled locally.

## Deliverables

A working application, a reproducible repository, twenty verified reference answers in `examples/benchmark-results/`, and a recorded verification run (`docs/VERIFICATION.md`).

## Current status

The full pipeline runs against a live local TigerGraph: graph and vector loading, grounding with parity checks, case write-back with read-back, and guarded export. Historical scoring stays advisory because its training cohort differs from the benchmark cases. No claim of hidden-key accuracy is made.
