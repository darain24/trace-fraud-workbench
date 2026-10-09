# Trace walkthrough — 4 minutes

A guided tour of the running app against a live local TigerGraph, also used as the script
for the demo video. Everything below is true of the current build.

Before starting, run `./scripts/demo_up.sh` and wait for the green line, then confirm the
header reads **20/20** graph persistence.

The case IDs below are the benchmark's (`TRACE_DATASET=full`). On the synthetic demo
dataset the same beats are DEMO-009 for the shared-device network, DEMO-010 for the
recurring-charge dispute, DEMO-006 for the cleared new phone and DEMO-001 for card testing.
The demo's numbers are its own, not the benchmark results quoted here.

## 0:00–0:35 — The finding

> "An alert is not a verdict. The dataset carries the bank's own fraud model score on every
> transaction, and the first thing I did was check it against the bank's own closed
> cases. It scores ROC-AUC 0.053 — inverted. Every cleared case had scored 0.82 or higher."

> "That model isn't broken. It's the thing that decides which alerts get opened, and the
> ones it shouts loudest about are the customers who bought a new phone or went on a trip.
> So Trace doesn't use it. Trace scores the evidence instead."

Show the case queue and the header: 20 benchmark cases, 20 saved, 20/20 written to
TigerGraph.

## 0:35–1:30 — Follow the network (HHG-014)

Open HHG-014, the analyst request. Show:

- The evidence graph: the flagged transaction, its device profile, and the other cards that
  touched it.
- **Why this probability** — the weighted findings panel. Point at `Shared origin +1.50`
  and say the number is a fitted log-odds weight, not a guess.
- The evidence list: `tigergraph:verified_derivation:` references, and the GraphRAG
  documents including **R6 Shared origin** retrieved from the vector store. The agent
  retrieved the rule it then applied.
- The recommendation: `CREATE_CASE`, `ESCALATE_TO_ANALYST`, `MONITOR_CARD`, `FILE_REPORT`
  (L2), `MONITOR_CONNECTED_CARDS` — and the SAR narrative naming the shared device profile
  as the linking element, not an identified person.

> "One cardholder's answer can't settle whether several cards run through one device
> profile, so this case doesn't ask. R6 sends it to a report and connected-card
> monitoring."

## 1:30–2:25 — Change a decision

Open an uncertain case. Use **What would change this decision?** to show confirmation,
denial and no-reply branches without touching the record — point out `persisted: false`.

Then show a case that actually requested evidence (HHG-002, HHG-017, HHG-019 or HHG-020).
Show `evidence_requests` with the simulated reply **and its stated basis**, then the initial
and final recommendations side by side and `what_changed`.

> "Seven of the twenty asked for evidence. Four changed their recommendation because of it.
> Both versions stay in the answer."

## 2:25–3:00 — Protect the legitimate half

Open a `legitimate` case. Show the counter-evidence: the device marked New, the amount
consistent with baseline, no velocity change.

> "A new device is the strongest counter-indicator in this dataset — twelve percent fraud.
> People buy new phones, and they're exactly the people the model flags. Six of these twenty
> are closed as legitimate with no customer impact."

## 3:00–3:35 — Case memory in the graph

Show the event history replay for one case, then switch to the graph and read the
`Investigation` vertex back:

```
i.verdict "fraud" · i.pattern "undocumented" · i.exposure 672.3
i.actions "CREATE_CASE,ESCALATE_TO_ANALYST,MONITOR_CARD,FILE_REPORT,MONITOR_CONNECTED_CARDS"
```

> "The case is written back with queryable attributes and linked to its transactions, its
> card, the cards it implicated, the device profile it named, and the prior cases it cited.
> The next investigation finds it by traversal."

## 3:35–4:00 — Measurement, honestly

Show the evaluation view.

> "On two hundred October closed cases, the bank's score alone gets 27 right. Trace gets
> 111 of the 139 it's willing to decide. My first hand-tuned version got zero out of forty
> — it was pointed the wrong way. That's the whole lesson: a valid JSON file and a
> good-looking interface tell you nothing about whether the investigation is right."

## Recording checklist

- Hide credentials and unrelated desktop content.
- Use the actual running build. Do not fabricate service status or results.
- Keep resolution high enough to read evidence references and approval badges.
- Say "simulated" out loud wherever a customer reply is shown.
- Three to five minutes.
