"""TigerGraph graph/vector grounding and local, cached embeddings."""

import hashlib
import json
from datetime import timedelta

import httpx

from . import analysis, store, tigergraph
from .config import OLLAMA, TG_GRAPH

EMBED_MODEL = "all-minilm"


async def embed(text):
    key = "embed:" + hashlib.sha256((EMBED_MODEL + text).encode()).hexdigest()
    with store.connect() as c:
        r = c.execute("SELECT value FROM llm_cache WHERE key=?", (key,)).fetchone()
    if r:
        return json.loads(r[0])
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            OLLAMA + "/api/embed", json={"model": EMBED_MODEL, "input": text[:6000]}
        )
        r.raise_for_status()
        vector = r.json()["embeddings"][0]
    with store.connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO llm_cache VALUES(?,?)", (key, json.dumps(vector))
        )
    return vector


def attributes(value, vertex_type):
    found = []

    def walk(v):
        if isinstance(v, dict):
            if v.get("v_type") == vertex_type and "attributes" in v:
                # A projected PRINT (`PRINT txns[txns.id, ...]`) prefixes every
                # attribute key with the set alias; strip it so callers see plain
                # attribute names either way.
                flat = {k.split(".")[-1]: val for k, val in v["attributes"].items()}
                found.append({**flat, "id": str(v.get("v_id", flat.get("id", "")))})
            else:
                for child in v.values():
                    walk(child)
        elif isinstance(v, list):
            for child in v:
                walk(child)

    walk(value)
    return found


def scalar(raw, key):
    """Pull a named aggregate out of the interpreted-query result envelope."""
    found = []

    def walk(v):
        if isinstance(v, dict):
            if key in v:
                found.append(v[key])
            for child in v.values():
                walk(child)
        elif isinstance(v, list):
            for child in v:
                walk(child)

    walk(raw)
    return found[0] if found else None


CORPUS_KEY = "graphrag_corpus"


def corpus_documents():
    """Rebuild the same corpus definition the provisioner uploaded."""
    from importlib import util

    from .config import ROOT

    spec = util.spec_from_file_location(
        "_provision", ROOT / "scripts" / "provision_tigergraph.py"
    )
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.corpus()


async def local_rank(vector, k, cutoff, client):
    """Rank TigerGraph's Document corpus locally, then read the winners back out of
    the graph.

    Used only when `trace_vector_search` is not installed. The embeddings are the
    same ones stored on the Document vertices; what happens off-server is the
    top-k scan, because `vectorSearch` only exists inside a compiled query and this
    container cannot compile one. The text the agent reads still comes from
    TigerGraph, fetched by id.
    """
    index = store.meta(CORPUS_KEY)
    if not index:
        docs = corpus_documents()
        index = {
            "ids": [d["id"] for d in docs],
            "closed_at": [d["closed_at"] for d in docs],
            "kinds": [d["kind"] for d in docs],
            "vectors": [await embed(d["text"]) for d in docs],
        }
        with store.connect() as c:
            c.execute(
                "INSERT OR REPLACE INTO metadata VALUES(?,?)",
                (CORPUS_KEY, json.dumps(index)),
            )
    # Rank the policy text and the prior narratives separately and take from both.
    # Pooled, the 466 case notes always crowd out the 37 policy chunks, and the
    # recommendation has to cite a rule, not another analyst's sentence.
    by_kind = {}
    for i, doc_id in enumerate(index["ids"]):
        closed = index["closed_at"][i]
        if closed and closed >= cutoff:
            continue
        score = sum(a * b for a, b in zip(vector, index["vectors"][i]))
        by_kind.setdefault(index["kinds"][i], []).append((score, doc_id))
    top = []
    half = max(1, k // 2)
    for kind in ("policy_or_pattern", "historical_case"):
        ranked = sorted(by_kind.get(kind, []), reverse=True)
        top += [doc_id for _, doc_id in ranked[:half]]
    if not top:
        return []
    raw = await tigergraph.query("trace_documents", {"ids": top}, client)
    return attributes(raw, "Document")


async def ground(packet, trigger):
    """Re-derive the evidence from TigerGraph and refuse to proceed if it disagrees.

    Local SQLite is a projection of the same source CSVs and exists so the
    workbench stays usable when the graph is down. It is not the source of record: a
    case is only marked graph-backed once the graph agrees on the aggregate over the
    window under investigation, agrees transaction by transaction on the sample the
    case cites, returns the same admissible closed cases, and returns vector context.
    """
    f = packet["flagged"]
    calls = 0
    window_start = (analysis.dt(trigger["opened_at"]) - timedelta(days=14)).isoformat(
        sep=" "
    )
    sample_from = (analysis.dt(f["ts"]) - timedelta(hours=48)).isoformat(sep=" ")
    # Count the window straight from the projection. Deriving it from the evidence
    # packet compares different sets: `baseline` is capped at its 300 most recent
    # rows, so a high-volume customer legitimately has more transactions in the window
    # than the packet carries, and the aggregate would disagree every time.
    with store.connect() as c:
        row = c.execute(
            "SELECT count(*) n, coalesce(sum(amount), 0) total FROM transactions "
            "WHERE customer_id=? AND ts<=? AND ts>=?",
            (trigger["customer_id"], trigger["opened_at"], window_start),
        ).fetchone()
    local_count, local_total = row["n"], row["total"]
    local = [
        t
        for t in {x["id"]: x for x in packet["baseline"] + packet["timeline"]}.values()
        if t["ts"] >= window_start
    ]
    async with tigergraph.bulk(timeout=600) as client:
        raw = await tigergraph.query(
            "trace_customer_window",
            {
                "customer_id": trigger["customer_id"],
                "cutoff": trigger["opened_at"],
                "start_at": window_start,
                "sample_from": sample_from,
            },
            client=client,
        )
        calls += 1
        count = scalar(raw, "window_count")
        total = scalar(raw, "window_amount")
        if count is None:
            raise tigergraph.TigerGraphUnavailable(
                "Customer window query returned no aggregate; evidence unverified"
            )
        if int(count) != local_count:
            raise tigergraph.TigerGraphUnavailable(
                f"Graph holds {count} transactions in the window, local projection "
                f"holds {local_count}"
            )
        if abs(float(total) - float(local_total)) > 0.05:
            raise tigergraph.TigerGraphUnavailable(
                f"Graph window total {float(total):.2f} does not match the local "
                f"projection's {float(local_total):.2f}"
            )
        lookup = {t["id"]: t for t in local}
        sample = attributes(raw, "Transaction")
        if not sample:
            raise tigergraph.TigerGraphUnavailable(
                "Customer window query returned no sampled transactions"
            )
        for t in sample:
            mine = lookup.get(t["id"])
            if not mine:
                raise tigergraph.TigerGraphUnavailable(
                    "Graph returned a transaction outside the local window: " + t["id"]
                )
            if str(t["ts"]) != mine["ts"] or str(t["card_id"]) != mine["card_id"]:
                raise tigergraph.TigerGraphUnavailable(
                    "Graph/local evidence mismatch on " + t["id"]
                )
            if abs(float(t["amount"]) - mine["amount"]) > 0.001:
                raise tigergraph.TigerGraphUnavailable(
                    "Graph/local amount mismatch on " + t["id"]
                )
        # The flagged transaction is verified explicitly rather than left to the
        # sample: on a high-volume card the capped sample need not contain it, and
        # every claim in the answer rests on this row.
        if f["id"] not in {t["id"] for t in sample}:
            node = attributes(
                await tigergraph.call(
                    "tigergraph__get_node",
                    {
                        "graph_name": TG_GRAPH,
                        "vertex_type": "Transaction",
                        "vertex_id": f["id"],
                    },
                    client=client,
                ),
                "Transaction",
            )
            calls += 1
            if not node:
                raise tigergraph.TigerGraphUnavailable(
                    "Flagged transaction is missing from the graph: " + f["id"]
                )
            got = node[0]
            if (
                str(got["ts"]) != f["ts"]
                or str(got["card_id"]) != f["card_id"]
                or abs(float(got["amount"]) - f["amount"]) > 0.001
            ):
                raise tigergraph.TigerGraphUnavailable(
                    "Graph/local mismatch on the flagged transaction " + f["id"]
                )
        if f["device"]:
            raw = await tigergraph.query(
                "trace_device_window",
                {
                    "device_id": hashlib.sha256(f["device"].encode()).hexdigest(),
                    "cutoff": trigger["opened_at"],
                    "start_at": (analysis.dt(f["ts"]) - timedelta(days=30)).isoformat(
                        sep=" "
                    ),
                },
                client=client,
            )
            calls += 1
            device_count = scalar(raw, "window_count")
            if device_count is None or int(device_count) == 0:
                raise tigergraph.TigerGraphUnavailable(
                    "Device profile query returned nothing for a device-bearing case"
                )
            device_ids = {t["id"] for t in packet["neighbors"]} | {f["id"]}
            for t in attributes(raw, "Transaction"):
                if t["id"] in device_ids:
                    mine = ({x["id"]: x for x in packet["neighbors"]} | {f["id"]: f})[
                        t["id"]
                    ]
                    if abs(float(t["amount"]) - mine["amount"]) > 0.001:
                        raise tigergraph.TigerGraphUnavailable(
                            "Device query failed evidence parity on " + t["id"]
                        )
            packet["graph_device_transactions"] = int(device_count)
        raw = await tigergraph.query(
            "trace_case_memory",
            {"customer_id": trigger["customer_id"], "cutoff": trigger["opened_at"]},
            client=client,
        )
        calls += 1
        graph_cases = {c["id"]: c for c in attributes(raw, "ClosedCase")}
        for h in packet["history"]:
            node = graph_cases.get(h["id"])
            if node is None:
                node_raw = await tigergraph.call(
                    "tigergraph__get_node",
                    {
                        "graph_name": TG_GRAPH,
                        "vertex_type": "ClosedCase",
                        "vertex_id": h["id"],
                    },
                    client=client,
                )
                calls += 1
                found = attributes(node_raw, "ClosedCase")
                node = found[0] if found else None
            if not node:
                raise tigergraph.TigerGraphUnavailable(
                    "Historical case missing from the graph: " + h["id"]
                )
            if node["closed_at"] >= trigger["opened_at"]:
                raise tigergraph.TigerGraphUnavailable(
                    "Retrieved a case closed after this alert: " + h["id"]
                )
        # Case memory this agent wrote earlier, read back from the graph.
        try:
            raw = await tigergraph.query(
                "trace_prior_investigations",
                {"card_id": trigger["card_id"], "cutoff": trigger["opened_at"]},
                client=client,
            )
            calls += 1
            prior = attributes(raw, "Investigation")
        except tigergraph.TigerGraphUnavailable:
            prior = []
        # Policy, pattern and prior-narrative context from the TigerGraph vector index.
        vector = await embed(
            trigger.get("trigger_text", "")
            + " "
            + packet["flagged"]["channel"]
            + " "
            + trigger.get("trigger_type", "")
        )
        raw = await tigergraph.vector_search(vector, 6, trigger["opened_at"], client)
        if raw is None:
            found = await local_rank(vector, 6, trigger["opened_at"], client)
            packet["vector_search"] = "client-side rank over TigerGraph-held vectors"
        else:
            found = attributes(raw, "Document")
            packet["vector_search"] = "TigerGraph trace_vector_search"
        calls += 1
        seen = set()
        docs = []
        for d in found:
            key = d.get("id") or d.get("text", "")[:60]
            if key in seen:
                continue
            seen.add(key)
            # An investigation may not read a case closed after its own alert.
            if d.get("closed_at") and d["closed_at"] >= trigger["opened_at"]:
                continue
            docs.append(d)
        if not docs:
            raise tigergraph.TigerGraphUnavailable(
                "No admissible vector context returned; GraphRAG is not verified"
            )
        raw = await tigergraph.query(
            "trace_network_bfs",
            {
                "card_id": trigger["card_id"],
                "cutoff": trigger["opened_at"],
                "start_at": (analysis.dt(f["ts"]) - timedelta(days=30)).isoformat(
                    sep=" "
                ),
            },
            client=client,
        )
        calls += 1
        packet["graph_network"] = sorted(
            {c["id"] for c in attributes(raw, "Card")} - {trigger["card_id"]}
        )
    packet["graph_documents"] = docs
    packet["graph_prior_investigations"] = prior
    packet["graph_verified_transactions"] = local_count
    packet["graph_window_total"] = round(float(total), 2)
    packet["source"] = "tigergraph"
    packet["tool_calls"] += calls
    return packet
