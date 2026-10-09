# Benchmark results

Twenty reference answers produced by Trace on the benchmark case pack, one JSON file per case from `case_pack.csv`.

Promoted here only by `scripts/export_results.py`, which refuses any case that is not
grounded in TigerGraph, not written back with a verified read-back, missing graph or
document evidence, or failing a policy or ID check. Drafts live in `output/draft-cases/`
and are never promoted silently.

Every case in this directory was:

- investigated against a live TigerGraph Community Edition instance through the official
  TigerGraph MCP server,
- verified for graph/local evidence parity over the investigation window,
- grounded with GraphRAG context retrieved from TigerGraph's vector store, and
- written back to the graph as an `Investigation` vertex, linked to its transactions,
  card, connected cards, device profile and cited prior cases.

Customer replies recorded in `evidence_requests` are simulated and labelled `SIMULATED`
with the basis for the assumption. No customer was contacted, no card was blocked, and no
report was filed.

See `docs/VERIFICATION.md` for the recorded run.
