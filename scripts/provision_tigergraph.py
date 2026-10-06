"""Install and load ONLY an already-authorized, no-charge TigerGraph workspace.
No account creation, billing, instance provisioning, or destructive DDL.
"""

import argparse
import asyncio
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from tracework import retrieval, store, tigergraph
from tracework.config import DATA, ROOT, TG_GRAPH

INSTALL_TIMEOUT = 3600
BATCH = 500
VECTOR_BATCH = 100
QUERIES = [
    "trace_customer_window",
    "trace_device_window",
    "trace_case_memory",
    "trace_prior_investigations",
    "trace_network_bfs",
]


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


async def nodes(client, kind, values):
    if values:
        await tigergraph.call(
            "tigergraph__add_nodes",
            {"graph_name": TG_GRAPH, "vertex_type": kind, "vertices": values},
            client=client,
        )


async def edges(client, kind, source, target, values):
    if values:
        await tigergraph.call(
            "tigergraph__add_edges",
            {
                "graph_name": TG_GRAPH,
                "edge_type": kind,
                "edges": [
                    {
                        "source_type": source,
                        "source_id": s,
                        "target_type": target,
                        "target_id": t,
                    }
                    for s, t in values
                ],
            },
            client=client,
        )


def scope(c, full):
    """Transaction ids to load. `full` loads all 590k rows; the default loads the
    subgraph every benchmark answer can be grounded in: the complete history of the
    twenty benchmark customers, every transaction sharing a flagged device profile or
    billing region inside the alert's lookback, and every transaction named by a
    closed case. Anything outside this set is unreachable from the twenty triggers,
    so loading it would only lengthen the upload."""
    if full:
        return [r[0] for r in c.execute("SELECT id FROM transactions ORDER BY id")]
    triggers = [json.loads(r[0]) for r in c.execute("SELECT trigger_json FROM cases")]
    flagged = []
    for t in triggers:
        row = c.execute(
            "SELECT * FROM transactions WHERE id=?", (t["flagged_txn_id"],)
        ).fetchone()
        if row:
            flagged.append((dict(row), t["opened_at"]))
    customers = sorted({f["customer_id"] for f, _ in flagged})
    keep = {
        r[0]
        for r in c.execute(
            "SELECT id FROM transactions WHERE customer_id IN (%s)"
            % ",".join("?" * len(customers)),
            customers,
        )
    }
    for f, cutoff in flagged:
        when = datetime.fromisoformat(f["ts"])
        if f["device"]:
            keep |= {
                r[0]
                for r in c.execute(
                    "SELECT id FROM transactions WHERE device=? AND ts BETWEEN ? AND ?",
                    (
                        f["device"],
                        (when - timedelta(days=30)).isoformat(sep=" "),
                        cutoff,
                    ),
                )
            }
        if f["channel"] == "in_person" and f["region"]:
            keep |= {
                r[0]
                for r in c.execute(
                    "SELECT id FROM transactions WHERE region=? AND ts BETWEEN ? AND ?",
                    (
                        f["region"],
                        (when - timedelta(hours=24)).isoformat(sep=" "),
                        cutoff,
                    ),
                )
            }
    named = set()
    for row in c.execute("SELECT txn_ids FROM history"):
        named |= set(row[0].split("|"))
    keep |= named
    ordered = sorted(keep)
    present = []
    for i in range(0, len(ordered), 900):
        part = ordered[i : i + 900]
        present += [
            r[0]
            for r in c.execute(
                "SELECT id FROM transactions WHERE id IN (%s)" % ",".join("?" * len(part)),
                part,
            )
        ]
    return sorted(present)


async def load(full=False):
    with store.connect() as c:
        wanted = scope(c, full)
        total = len(wanted)
        print(f"Loading {total:,} transactions into {TG_GRAPH}", flush=True)
        done = 0
        loaded = set()
        async with tigergraph.bulk() as client:
            for offset in range(0, total, BATCH):
                chunk = wanted[offset : offset + BATCH]
                batch = [
                    dict(r)
                    for r in c.execute(
                        "SELECT * FROM transactions WHERE id IN (%s)"
                        % ",".join("?" * len(chunk)),
                        chunk,
                    )
                ]
                await nodes(
                    client,
                    "Customer",
                    [{"id": v} for v in sorted({t["customer_id"] for t in batch})],
                )
                cards = {
                    t["card_id"]: (t["customer_id"], bool(t["card_verified"]))
                    for t in batch
                }
                await nodes(
                    client,
                    "Card",
                    [
                        {"id": k, "customer_id": v[0], "verified": v[1]}
                        for k, v in cards.items()
                    ],
                )
                await nodes(
                    client,
                    "Transaction",
                    [
                        {
                            ("proxy_rating" if k == "proxy" else k): v
                            for k, v in t.items()
                            if k != "signature"
                        }
                        for t in batch
                    ],
                )
                await nodes(
                    client,
                    "DeviceProfile",
                    [
                        {"id": digest(v), "description": v}
                        for v in sorted({t["device"] for t in batch if t["device"]})
                    ],
                )
                await nodes(
                    client,
                    "BillingRegion",
                    [{"id": v} for v in sorted({t["region"] for t in batch if t["region"]})],
                )
                await nodes(
                    client,
                    "EmailDomain",
                    [{"id": v} for v in sorted({t["email"] for t in batch if t["email"]})],
                )
                await edges(
                    client,
                    "OWNS",
                    "Customer",
                    "Card",
                    list({(t["customer_id"], t["card_id"]) for t in batch}),
                )
                await edges(
                    client,
                    "MADE",
                    "Card",
                    "Transaction",
                    [(t["card_id"], t["id"]) for t in batch],
                )
                await edges(
                    client,
                    "FROM_DEVICE",
                    "Transaction",
                    "DeviceProfile",
                    [(t["id"], digest(t["device"])) for t in batch if t["device"]],
                )
                await edges(
                    client,
                    "BILLED_IN",
                    "Transaction",
                    "BillingRegion",
                    [(t["id"], t["region"]) for t in batch if t["region"]],
                )
                await edges(
                    client,
                    "PURCHASER_EMAIL",
                    "Transaction",
                    "EmailDomain",
                    [(t["id"], t["email"]) for t in batch if t["email"]],
                )
                loaded.update(t["id"] for t in batch)
                done += len(batch)
                print(f"Uploaded {done:,}/{total:,}", flush=True)
            # Closed cases, but only their edges to transactions actually loaded.
            history = [dict(r) for r in c.execute("SELECT * FROM history")]
            for offset in range(0, len(history), 100):
                part = history[offset : offset + 100]
                await nodes(
                    client,
                    "ClosedCase",
                    [{k: v for k, v in h.items() if k != "raw_json"} for h in part],
                )
                await edges(
                    client,
                    "INVOLVES",
                    "ClosedCase",
                    "Transaction",
                    [
                        (h["id"], tid)
                        for h in part
                        for tid in h["txn_ids"].split("|")
                        if tid in loaded
                    ],
                )
                await edges(
                    client,
                    "CASE_ON_CARD",
                    "ClosedCase",
                    "Card",
                    [(h["id"], h["card_id"]) for h in part if h["card_id"]],
                )
            print(f"Loaded {len(history):,} closed cases", flush=True)
            previous = {}
            sequence = []
            for r in c.execute(
                "SELECT id,card_id FROM transactions ORDER BY card_id,ts,id"
            ):
                if r["id"] not in loaded:
                    continue
                if r["card_id"] in previous:
                    sequence.append((previous[r["card_id"]], r["id"]))
                previous[r["card_id"]] = r["id"]
                if len(sequence) >= 1000:
                    await edges(
                        client, "NEXT", "Transaction", "Transaction", sequence
                    )
                    sequence = []
            await edges(client, "NEXT", "Transaction", "Transaction", sequence)
            print("NEXT sequence edges written", flush=True)


def corpus():
    """The GraphRAG corpus: the fraud policy, the documented patterns, the regulatory
    reference list, and closed-case narratives.

    The narratives are deduplicated by shape. The 5,565 historical analyst notes
    reduce to about 370 distinct templates once identifiers, dates and amounts are
    masked, so embedding all of them adds no retrievable meaning -- it just buries the
    policy text under a thousand near-identical sentences and makes every similarity
    search scan a corpus an order of magnitude larger than it needs to be. Cases
    reachable from a benchmark customer or a flagged device profile are always kept,
    because those are the ones an investigation actually cites.
    """
    readme = (DATA / "raw" / "README.md").read_text()

    def section(start, end):
        return readme.split(start, 1)[1].split(end, 1)[0]

    text = "\n\n".join(
        [
            section("# Fraud Policy", "# Answer Format"),
            section("## The five known fraud patterns", "## Regulatory references"),
            section("## Regulatory references", "## Things to know"),
            section("## Things to know", "## Rules"),
        ]
    )
    docs = [
        {
            "id": "POLICY-" + str(i),
            "text": chunk[:6000],
            "kind": "policy_or_pattern",
            "closed_at": "",
        }
        for i, chunk in enumerate(text.split("\n\n"))
        if len(chunk.strip()) > 50
    ]
    shape = re.compile(r"[0-9][0-9,.]*")
    with store.connect() as c:
        triggers = [
            json.loads(r[0]) for r in c.execute("SELECT trigger_json FROM cases")
        ]
        customers = {t["customer_id"] for t in triggers}
        cards = {t["card_id"] for t in triggers}
        history = [dict(r) for r in c.execute("SELECT * FROM history ORDER BY closed_at")]
    seen = set()
    for h in history:
        essential = h["customer_id"] in customers or h["card_id"] in cards
        key = shape.sub("N", h["notes"])
        if not essential and key in seen:
            continue
        seen.add(key)
        docs.append(
            {
                "id": h["id"],
                "text": h["notes"],
                "kind": "historical_case",
                "closed_at": h["closed_at"],
            }
        )
    return docs


async def documents(reset=False):
    docs = corpus()
    kinds = Counter(d["kind"] for d in docs)
    print(f"Embedding {len(docs)} documents ({dict(kinds)})", flush=True)
    async with tigergraph.bulk() as client:
        if reset:
            await tigergraph.call(
                "tigergraph__run_query",
                {
                    "graph_name": TG_GRAPH,
                    "query_text": (
                        f"INTERPRET QUERY () FOR GRAPH {TG_GRAPH} "
                        "{ s = {Document.*}; d = SELECT x FROM s:x "
                        "POST-ACCUM DELETE(x); }"
                    ),
                },
                client=client,
                timeout=600,
            )
            print("Cleared the existing Document corpus", flush=True)
        for offset in range(0, len(docs), VECTOR_BATCH):
            part = docs[offset : offset + VECTOR_BATCH]
            vectors = [
                {
                    "vertex_id": d["id"],
                    "vector": await retrieval.embed(d["text"]),
                    "attributes": {k: v for k, v in d.items() if k != "id"},
                }
                for d in part
            ]
            await tigergraph.call(
                "tigergraph__upsert_vectors",
                {
                    "graph_name": TG_GRAPH,
                    "vertex_type": "Document",
                    "vector_attribute": "embedding",
                    "vectors": vectors,
                },
                client=client,
            )
            print(f"Embedded {offset + len(part)}/{len(docs)} documents", flush=True)


async def main(args):
    store.init()
    if TG_GRAPH != "Trace":
        raise SystemExit("Schema currently names Trace; use TG_GRAPH=Trace.")
    if args.schema:
        await tigergraph.call(
            "tigergraph__gsql",
            {"command": (ROOT / "tigergraph/schema.gsql").read_text()},
            timeout=INSTALL_TIMEOUT,
        )
        await tigergraph.call(
            "tigergraph__gsql",
            {
                "command": (ROOT / "tigergraph/queries.gsql").read_text(),
                "graph_name": TG_GRAPH,
            },
            timeout=INSTALL_TIMEOUT,
        )
        # One INSTALL per query. A combined install compiles them in a single job and
        # exhausts memory on a small Community Edition container.
        for name in QUERIES:
            print(f"Installing {name} (compiles native code; minutes each)", flush=True)
            await tigergraph.call(
                "tigergraph__gsql",
                {
                    "command": f"USE GRAPH {TG_GRAPH}\nINSTALL QUERY {name}",
                    "graph_name": TG_GRAPH,
                },
                timeout=INSTALL_TIMEOUT,
            )
        await tigergraph.call(
            "tigergraph__add_vector_attribute",
            {
                "graph_name": TG_GRAPH,
                "vertex_type": "Document",
                "vector_name": "embedding",
                "dimension": 384,
                "metric": "COSINE",
            },
        )
    if args.data:
        await load(args.full)
    if args.documents:
        await documents(args.reset_documents)
    print(
        "Provisioning operations finished. Run integration verification; do not assume compliance from upload success."
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--schema", action="store_true")
    p.add_argument("--data", action="store_true")
    p.add_argument("--documents", action="store_true")
    p.add_argument(
        "--reset-documents",
        action="store_true",
        help="clear the existing Document corpus before embedding",
    )
    p.add_argument(
        "--full",
        action="store_true",
        help="load all 590k transactions instead of the benchmark subgraph",
    )
    args = p.parse_args()
    try:
        asyncio.run(main(args))
    except tigergraph.TigerGraphUnavailable as error:
        raise SystemExit(str(error)) from None
