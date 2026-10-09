"""Real TigerGraph MCP adapter. Never reports persistence on unavailable/mock services."""

import hashlib
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from .config import TG_GRAPH, TG_URL


class TigerGraphUnavailable(RuntimeError):
    pass


def credential_headers():
    """Forward local credentials; unset fields can use the server's profile."""
    fields = {
        "TG_HOST": "X-TG-Host",
        "TG_GRAPHNAME": "X-TG-Graphname",
        "TG_API_TOKEN": "X-TG-Api-Token",
        "TG_JWT_TOKEN": "X-TG-Jwt-Token",
        "TG_USERNAME": "X-TG-Username",
        "TG_PASSWORD": "X-TG-Password",
        "TG_SECRET": "X-TG-Secret",
        "TG_RESTPP_PORT": "X-TG-Restpp-Port",
        "TG_GS_PORT": "X-TG-Gs-Port",
        "TG_SSL_PORT": "X-TG-Ssl-Port",
        "TG_PROFILE": "X-TG-Profile",
    }
    return {header: os.environ[key] for key, header in fields.items() if os.getenv(key)}


def transport_error(error):
    """Unwrap SDK task groups without exposing response bodies or credentials."""
    if isinstance(error, BaseExceptionGroup):
        return "; ".join(dict.fromkeys(transport_error(e) for e in error.exceptions))
    if isinstance(error, TigerGraphUnavailable):
        return str(error)
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        hints = {
            400: "Check TG_HOST in .env and the MCP server's profile configuration.",
            401: "Set valid TG_API_TOKEN (or supported credentials) in .env.",
            403: "Check the TigerGraph identity's permissions.",
            404: "Check TG_MCP_URL points to the MCP endpoint.",
        }
        return f"TigerGraph MCP HTTP {status}. {hints.get(status, 'Check the MCP server logs.')}"
    if isinstance(error, httpx.RequestError):
        return "TigerGraph MCP transport unavailable. Check TG_MCP_URL and that the server is running."
    return (
        f"TigerGraph MCP operation failed ({type(error).__name__}); check server logs."
    )


@asynccontextmanager
async def session(timeout=30):
    if not TG_URL:
        raise TigerGraphUnavailable(
            "TG_MCP_URL is not configured. Local analysis is not TigerGraph compliance."
        )
    try:
        async with streamablehttp_client(
            TG_URL, headers=credential_headers(), timeout=timeout
        ) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                yield client
    except Exception as error:
        raise TigerGraphUnavailable(transport_error(error)) from None


FENCE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def decode(text):
    """The MCP server wraps its JSON envelope in markdown fences and repeats
    fragments of it as prose. Parse every fenced block plus the bare text."""
    out = []
    for block in FENCE.findall(text):
        try:
            out.append(json.loads(block))
        except ValueError:
            continue
    if not out:
        try:
            out.append(json.loads(text))
        except ValueError:
            out.append(text)
    return out


def unpack(result):
    if result.isError:
        raise TigerGraphUnavailable("TigerGraph MCP rejected the operation")
    texts = [x.text for x in result.content if getattr(x, "type", "") == "text"]
    values = []
    for t in texts:
        values.extend(decode(t))
    envelopes = [v for v in values if isinstance(v, dict) and "success" in v]
    if not envelopes and not any(isinstance(v, dict) for v in values):
        raise TigerGraphUnavailable(
            "TigerGraph MCP returned no parsable payload: " + str(values)[:200]
        )
    for v in values:
        if isinstance(v, dict) and (
            v.get("error")
            or v.get("success") is False
            or (v.get("data") or {}).get("failed_count", 0)
        ):
            raise TigerGraphUnavailable(
                str(v.get("error") or v.get("summary") or "TigerGraph query failed")[
                    :300
                ]
            )
    return values


async def health():
    """Report what is actually true of the graph right now.

    MCP staying reachable says nothing about whether GSE and GSQL are alive behind it,
    so this runs a real query before calling the graph available.
    """
    if not TG_URL:
        return {
            "configured": False,
            "available": False,
            "verified": False,
            "reason": "Set TG_MCP_URL for the official TigerGraph MCP server. No paid account is configured.",
        }
    try:
        async with session() as client:
            tools = await client.list_tools()
            names = [t.name for t in tools.tools]
            counts = {}
            for kind in ("Transaction", "ClosedCase", "Document", "Investigation"):
                result = await invoke(
                    client,
                    "tigergraph__get_vertex_count",
                    {"graph_name": TG_GRAPH, "vertex_type": kind},
                )
                for v in result:
                    if isinstance(v, dict) and isinstance(v.get("data"), dict):
                        counts[kind] = v["data"].get("count")
                        break
        verified = bool(counts.get("Transaction")) and bool(counts.get("Document"))
        return {
            "configured": True,
            "available": True,
            "verified": verified,
            "graph": TG_GRAPH,
            "counts": counts,
            "tools": names,
            "reason": (
                f"Graph '{TG_GRAPH}' answered: {counts.get('Transaction', 0):,} "
                f"transactions, {counts.get('Document', 0):,} vector documents, "
                f"{counts.get('Investigation', 0):,} cases written back."
                if verified
                else "MCP reachable but the graph is empty; run provision_tigergraph.py."
            ),
        }
    except Exception as e:
        return {
            "configured": True,
            "available": False,
            "verified": False,
            "reason": str(e)[:250],
        }


async def invoke(client, name, arguments, timeout=30):
    listed = await client.list_tools()
    tool = next((t for t in listed.tools if t.name == name), None)
    if not tool:
        raise TigerGraphUnavailable(f"Required tool unavailable: {name}")
    # Validate against the actual server schema before submitting.
    import jsonschema

    jsonschema.validate(arguments, tool.inputSchema)
    return unpack(
        await client.call_tool(
            name, arguments, read_timeout_seconds=timedelta(seconds=timeout)
        )
    )


async def call(name, arguments, timeout=30, client=None):
    """`timeout` is raised for provisioning calls: installing a GSQL query compiles
    native code and routinely runs for minutes. Pass an open `client` from
    `bulk()` to reuse one MCP session across many calls."""
    if client is not None:
        return await invoke(client, name, arguments, timeout)
    async with session(timeout) as fresh:
        return await invoke(fresh, name, arguments, timeout)


@asynccontextmanager
async def bulk(timeout=600):
    """One MCP session for a whole load. Re-handshaking per row makes bulk
    provisioning an order of magnitude slower than the graph writes themselves."""
    async with session(timeout) as client:
        yield client


SAFE = re.compile(r"^[A-Za-z0-9_.:\- ]{1,64}$")


def literal(value):
    """Inline a parameter into interpreted GSQL. Interpreted queries take no
    parameter list, so values are substituted into the text; everything inlined here
    is an identifier or timestamp from the dataset and must match a strict
    allowlist before it reaches the server."""
    text = str(value)
    if not SAFE.match(text):
        raise TigerGraphUnavailable(f"Refusing to inline unsafe GSQL literal: {text!r}")
    return '"' + text + '"'


VECTOR_QUERY = "trace_vector_search"


async def installed(name, client=None):
    """Whether a compiled query is available on this server."""
    try:
        result = await call(
            "tigergraph__is_query_installed",
            {"graph_name": TG_GRAPH, "query_name": name},
            client=client,
        )
    except TigerGraphUnavailable:
        return False
    for v in result:
        if isinstance(v, dict):
            data = v.get("data") or {}
            if isinstance(data, dict) and "is_installed" in data:
                return bool(data["is_installed"])
            if "is_installed" in v:
                return bool(v["is_installed"])
    return False


async def vector_search(vector, k, cutoff, client=None):
    """Top-k over the Document embeddings held in TigerGraph.

    `vectorSearch` takes the query vector as a query parameter, so it only exists
    inside an installed query. Where `trace_vector_search` compiled, this is a
    server-side search. Where it did not -- Community Edition on a small container
    cannot compile a query at all -- the caller falls back to ranking the same
    TigerGraph-held vectors locally. Returns None to signal that fallback.
    """
    if not await installed(VECTOR_QUERY, client):
        return None
    return await call(
        "tigergraph__run_installed_query",
        {
            "graph_name": TG_GRAPH,
            "query_name": VECTOR_QUERY,
            "params": {"query_vector": list(vector), "k": k, "cutoff": cutoff},
        },
        timeout=300,
        client=client,
    )


QUERY_BODIES = {
    # Parity is checked by aggregate plus a bounded sample rather than by pulling
    # every row back. TigerGraph answers the full projection in about four seconds,
    # but the MCP server re-serialises each result into a markdown envelope and
    # repeats it in its summary, so a few hundred rows become a multi-megabyte
    # streamed response that times out. The aggregate covers the whole window and
    # the sample covers the transactions the case actually cites.
    "trace_customer_window": """
  SumAccum<INT> @@n;
  SumAccum<DOUBLE> @@total;
  seeds = {{Customer.*}};
  customers = SELECT c FROM seeds:c WHERE c.id == {customer_id};
  cards = SELECT k FROM customers:c -(OWNS:e)-> Card:k;
  txns = SELECT t FROM cards:k -(MADE:e)-> Transaction:t
    WHERE t.ts <= {cutoff} AND t.ts >= {start_at}
    ACCUM @@n += 1, @@total += t.amount;
  picked = SELECT t FROM txns:t WHERE t.ts >= {sample_from} LIMIT 30;
  PRINT @@n AS window_count, @@total AS window_amount;
  PRINT picked[picked.id, picked.ts, picked.card_id, picked.amount];
""",
    "trace_device_window": """
  SumAccum<INT> @@n;
  SetAccum<STRING> @@cards;
  seeds = {{DeviceProfile.*}};
  devices = SELECT d FROM seeds:d WHERE d.id == {device_id};
  txns = SELECT t FROM devices:d -(DEVICE_TXNS:e)-> Transaction:t
    WHERE t.ts <= {cutoff} AND t.ts >= {start_at}
    ACCUM @@n += 1, @@cards += t.card_id;
  picked = SELECT t FROM txns:t LIMIT 20;
  PRINT @@n AS window_count, @@cards AS cards;
  PRINT picked[picked.id, picked.ts, picked.card_id, picked.amount];
""",
    "trace_documents": """
  seeds = {{Document.*}};
  picked = SELECT d FROM seeds:d WHERE d.id IN ({ids});
  PRINT picked[picked.text, picked.kind, picked.closed_at];
""",
    "trace_case_memory": """
  seeds = {{ClosedCase.*}};
  cases = SELECT h FROM seeds:h
    WHERE h.customer_id == {customer_id} AND h.closed_at < {cutoff} LIMIT 40;
  PRINT cases[cases.id, cases.closed_at, cases.outcome, cases.pattern];
""",
    "trace_prior_investigations": """
  SetAccum<VERTEX<Investigation>> @@found;
  cards = {{Card.*}};
  seedCard = SELECT k FROM cards:k WHERE k.id == {card_id};
  byCard = SELECT i FROM seedCard:k -(CARD_INVESTIGATIONS:e)-> Investigation:i
    WHERE i.opened_at < {cutoff} ACCUM @@found += i;
  linked = SELECT i FROM seedCard:k -(LINKED_INVESTIGATIONS:e)-> Investigation:i
    WHERE i.opened_at < {cutoff} ACCUM @@found += i;
  result = @@found;
  PRINT result;
""",
    "trace_network_bfs": """
  SetAccum<VERTEX> @@visited;
  cards = {{Card.*}};
  frontier = SELECT k FROM cards:k WHERE k.id == {card_id} ACCUM @@visited += k;
  txns = SELECT t FROM frontier:k -(MADE:e)-> Transaction:t
    WHERE t.ts <= {cutoff} AND t.ts >= {start_at} LIMIT 200;
  devices = SELECT d FROM txns:t -(FROM_DEVICE:e)-> DeviceProfile:d LIMIT 20;
  linked = SELECT t FROM devices:d -(DEVICE_TXNS:e)-> Transaction:t
    WHERE t.ts <= {cutoff} AND t.ts >= {start_at} LIMIT 500;
  reached = SELECT k FROM linked:t -(ON_CARD:e)-> Card:k ACCUM @@visited += k LIMIT 200;
  result = @@visited;
  PRINT result;
""",
}


async def query(name, params, client=None):
    """Run one of the reviewed GSQL bodies in `tigergraph/queries.gsql`.

    These are sent as interpreted queries. An installed query compiles to native
    code, and on a Community Edition container that compile is the one step that
    reliably exhausts memory; interpreting runs the same GSQL against the same graph
    without it. `scripts/provision_tigergraph.py --schema` still creates and installs
    them where the host has the headroom, and installed queries are used when present.
    """
    body = QUERY_BODIES[name]
    rendered = {}
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            rendered[key] = ", ".join(literal(v) for v in value)
        else:
            rendered[key] = literal(value)
    text = "INTERPRET QUERY () FOR GRAPH {} {{{}}}".format(
        TG_GRAPH, body.format(**rendered)
    )
    return await call(
        "tigergraph__run_query",
        {"graph_name": TG_GRAPH, "query_text": text},
        timeout=600,
        client=client,
    )


async def persist(answer, trigger=None):
    """Write the case into the graph and prove it landed.

    The payload is archived verbatim, but the attributes that matter for retrieval --
    customer, card, verdict, pattern, exposure, actions -- are written as real
    attributes, and the case is linked to its transactions, its card, the cards it
    connected, the device profile it named and the prior cases it cited. That is what
    makes this case findable by the next investigation rather than an opaque blob.
    """
    case = answer["case"]
    candidate = json.loads(json.dumps(answer))
    candidate["case"]["written_to_graph"] = True
    candidate["case"]["graph_case_id"] = answer["case_id"]
    payload = json.dumps(candidate, sort_keys=True, separators=(",", ":"))
    trigger = trigger or {}
    async with bulk(timeout=900) as client:
        await call(
            "tigergraph__add_node",
            {
                "graph_name": TG_GRAPH,
                "vertex_type": "Investigation",
                "vertex_id": answer["case_id"],
                "attributes": {
                    "customer_id": trigger.get("customer_id", ""),
                    "card_id": trigger.get("card_id", ""),
                    "opened_at": trigger.get("opened_at", ""),
                    "status": case["status"],
                    "verdict": case["verdict"],
                    "pattern": case["pattern"],
                    "fraud_probability": case["fraud_probability"],
                    "exposure": case["exposure_usd"],
                    "actions": ",".join(
                        a["action"] for a in answer["next_best_actions"]["final"]
                    ),
                    "sar_filed": bool(answer["sar"]["file"]),
                    "summary": case["summary"],
                    "payload": payload,
                    "outcome_verified": False,
                },
            },
            client=client,
        )
        read = await call(
            "tigergraph__get_node",
            {
                "graph_name": TG_GRAPH,
                "vertex_type": "Investigation",
                "vertex_id": answer["case_id"],
            },
            client=client,
        )

        def contains(value):
            if value == payload:
                return True
            if isinstance(value, dict):
                return any(contains(v) for v in value.values())
            if isinstance(value, list):
                return any(contains(v) for v in value)
            return False

        if not contains(read):
            raise TigerGraphUnavailable(
                "Read-back did not match the saved case; persistence remains unverified"
            )

        async def link(edge_type, target_type, ids):
            ids = [i for i in dict.fromkeys(ids) if i]
            if not ids:
                return
            await call(
                "tigergraph__add_edges",
                {
                    "graph_name": TG_GRAPH,
                    "edge_type": edge_type,
                    "edges": [
                        {
                            "source_type": "Investigation",
                            "source_id": answer["case_id"],
                            "target_type": target_type,
                            "target_id": i,
                        }
                        for i in ids
                    ],
                },
                client=client,
            )

        await link("FINDING", "Transaction", case["affected_txn_ids"])
        await link("INVESTIGATES", "Card", [trigger.get("card_id", "")])
        await link("CONNECTED_TO", "Card", case["connected_card_ids"])
        await link("CITES", "ClosedCase", case["similar_prior_cases"])
        await link(
            "SEEN_ON",
            "DeviceProfile",
            [
                hashlib.sha256(d.encode()).hexdigest()
                for d in case["connected_device_profiles"]
            ],
        )
    return answer["case_id"]
