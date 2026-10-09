# The fraud model that was right about everything except fraud

*Building an agentic fraud investigator on TigerGraph.*

We were given six months of card transactions, 5,565 closed investigations, a fraud
policy, and twenty alerts to investigate. Every transaction carried a risk score from the
bank's detection model. No fraud label anywhere.

The first thing we did was check whether that risk score was any good.

Across all 5,565 closed cases it scores **ROC-AUC 0.053**. Not poor. *Inverted.* Nearly
perfectly. Every single cleared case had scored 0.82 or higher.

## Why an inverted model is not a broken model

The score is not wrong about transactions. It is the thing that decides which alerts get
opened, and the ones it shouts loudest about are the ones where the cardholder turns out
to have bought a new phone, gone on a trip, or made one unusually large purchase. The
confirmed fraud arrives through a different door — customers reporting charges they did
not make — often at scores near zero.

So inside the closed-case record, a high score means "this was investigated and cleared".

That is exploitable. Inverting the score alone scores 93% on a balanced October holdout,
which would have been a very good-looking number to put in a README.

We do not use it. There is a test in the repository asserting that two otherwise identical
cases, one scoring 0.02 and one scoring 0.99, assess identically. The inversion is a
property of the bank's alerting workflow, not of fraud, and the twenty benchmark cases draw
their risk-score triggers from 0.52 to 0.90 — a different sampling frame. Fitting it would
have been fitting the exam's construction rather than the problem.

## What is left when you throw the score away

Behaviour. And it inverts most of the obvious intuitions.

Among high-score alerts — the cases where evidence actually had to decide — a device marked
`New` for the account runs at **12.3% fraud**. It is the strongest counter-indicator in the
data. People buy new phones, and the ones who do are exactly the ones the model flags. A
device the account already knows runs at **93.4%**. Billing regions never seen before are
*more* common among cleared cases than confirmed ones. A purchase far above the customer's
median, with nothing else changed, is 23% fraud.

What does predict fraud is velocity measured against the card's own rhythm, and concurrent
activity in the cardholder's home region — the signature of a card that was cloned rather
than carried.

We fitted a log-odds weight to each of those findings on investigations opened before
October 2016, and held them out on the 278 October alerts of the same kind: **ROC-AUC
0.849, accuracy 0.791, Brier 0.157**. Eleven named findings, each one a sentence an analyst
can check, summed into a probability the interface shows the arithmetic for.

The previous hand-tuned heuristic scored **0 out of 40** on the same holdout and abstained
on 31 of them. It was not slightly miscalibrated. It was pointed the wrong way, because it
encoded the same intuitions everyone has about new devices and unfamiliar regions.

## What TigerGraph does here

The graph is the evidence store and the case memory, and both matter.

`Customer → OWNS → Card → MADE → Transaction`, with transactions attached to device
profiles, billing regions and email domains, and closed cases linked to the transactions
they involved. Every query is cutoff-bounded, so an investigation opened on 22 November
cannot see anything recorded after it — including cases closed later.

The agent does not trust its own local copy. It re-derives every claim through GSQL and
refuses to continue if the graph disagrees: the aggregate over the window has to match, a
sampled set of transactions has to match field by field, and the flagged transaction is
fetched and checked explicitly. A case that fails parity never reaches the answer files —
the exporter refuses it.

Then it writes the case back. Not as a JSON blob on a vertex, but as an `Investigation`
with queryable attributes — verdict, pattern, exposure, actions, whether a report was
filed — linked by `FINDING` to its transactions, `INVESTIGATES` to its card, `CONNECTED_TO`
to the cards it implicated, `SEEN_ON` to the device profile it named, and `CITES` to the
prior cases it drew on. The next investigation can find it by traversal, which is what case
memory is supposed to mean.

GraphRAG runs over a 503-document corpus in TigerGraph's vector store: the policy, the five
documented patterns, the regulatory references, and closed-case narratives. We rank policy
chunks and case narratives *separately*, because pooled, 466 near-identical analyst notes
bury the 37 policy chunks every time — and a recommendation needs a rule to cite. When the
agent investigated the shared-device case, it retrieved R6 Shared Origin. That is the rule
it then applied.

## Running Community Edition on a laptop

Free and complete, but the defaults assume a server. Three things mattered, and all three
cost us hours:

**Kafka Connect is allocated 10 GB out of the box.** On a 3.8 GB Docker VM the kernel's OOM
killer takes the largest process, which is the graph store engine. Right-sizing the service
heaps was the difference between a graph that stayed up and one that did not.

**Do not install queries.** `INSTALL QUERY` compiles GSQL to native code, and that compile
is the single step that reliably exhausts memory on a small container. The queries run
interpreted from the same reviewed bodies, against the same graph.

**Watch the MCP layer, not just the database.** A query that returned 514 rows was taking
159 seconds and taking GSQL down with it. Timed directly inside the container, TigerGraph
answered in four seconds and 143 KB. The MCP server was wrapping the result in a markdown
envelope and repeating it in its summary. We changed verification to compare an aggregate
over the whole window plus a capped sample — which is a *stronger* check than the rows we
had been pulling, because it covers rows the sample never sees.

The worst one took longest to find. `search_top_k_similarity` was costing 116 seconds per
call. It turns out the MCP tool generates and *installs* a fresh GSQL query for every
distinct search — `_vec_search_<hash>` — so every similarity search was compiling native
code. The GSQL log had sixteen orphaned ones in it. Since `vectorSearch` takes the query
vector as a query parameter, it only exists inside an installed query, and this container
cannot compile one. So the vectors stay in TigerGraph and the top-k scan runs client-side
where the server cannot compile, with the winning documents read back out of the graph by
id, and which path ran recorded on every case. Grounding went from 100–150 seconds to 2–6.

## Being agentic about uncertainty

The interesting part of this task is not classification. It is what to do when you are not
sure.

The policy is explicit: on a single weak signal below 0.70, verify before you block. So the
agent records what it would recommend now, raises an evidence request, simulates the
cardholder's reply, states the basis for that assumption in the case file, folds it back in
as evidence, and recommends again. Both recommendations survive in the answer, with what
changed between them.

Two places where that needed judgement:

A customer report *is* a denial. Asking a cardholder to validate a transaction they just
reported is not evidence gathering, so those cases skip the request and go straight to R2.

A shared-origin cluster cannot be settled by one cardholder. When several cards of
different customers run through one device profile, asking one of them what they bought
answers nothing. R6 routes that to a report and connected-card monitoring instead.

Across the twenty cases: eleven fraud, six legitimate, three uncertain. Seven evidence
requests, four of which changed the recommendation. Two suspicious activity reports — the
policy says most cases never need one, and we read R9's reporting condition to require the
coordinated, cross-customer abuse it actually describes rather than any unmatched pattern.

## What we would do with more time

Calibration is the honest gap. The weights are fitted on investigated alerts, which are not
the general transaction population, and the probabilities are calibrated for that frame. We
would want a proper reliability curve on a held-out period and a genuine cost model behind
the thresholds rather than symmetric ones.

We would also push harder on the undocumented pattern. Four of the twenty cases fit none of
the five documented typologies, and describing them in our own words is the part we are
least able to check.

And we would give the agent the ability to open its own cases outside the twenty. The graph
already supports it — the discovery view surfaces candidate device-profile clusters — but
investigating them properly is a different problem from investigating an alert someone
handed you.

## The thing worth keeping

An interface that renders beautifully and passes every schema check tells you nothing about
whether the investigation is any good. Our first version produced twenty perfectly valid
JSON files and scored zero out of forty on the only holdout we had.

What fixed it was not better prompting. It was checking whether each signal pointed the
direction we assumed, against the bank's own record of what turned out to be true.
