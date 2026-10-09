"""Run every benchmark trigger and write the draft answers.

A case that could not be grounded in and written to TigerGraph is not a finished
answer, so `--require-graph` re-runs those rather than accepting the local-only
fallback. Community Edition on a small container drops a service under load often
enough that a single pass is not a reliable result.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from tracework import engine, store, tigergraph
from tracework.config import ROOT, TG_GRAPH, TG_URL


def reset(case_id):
    with store.connect() as c:
        c.execute(
            "UPDATE cases SET result_json=NULL,detail_json=NULL,state='queued' WHERE id=?",
            (case_id,),
        )


# Set to "" to disable. Community Edition sized for a laptop VM has no headroom, and
# the kernel takes GSE or GSQL down under query load; this restarts that one local
# container between cases. It is a local-development affordance, not something the
# agent does to a workspace it does not own.
LOCAL_CONTAINER = os.getenv("TG_LOCAL_CONTAINER", "tigergraph")
GADMIN = "/home/tigergraph/tigergraph/app/cmd/gadmin"


async def healthy():
    """Actually run a query. MCP staying reachable says nothing about whether GSE
    and GSQL are alive behind it, and that is exactly how a run stalls."""
    if not TG_URL:
        return False
    try:
        await tigergraph.call(
            "tigergraph__run_query",
            {
                "graph_name": TG_GRAPH,
                "query_text": (
                    f"INTERPRET QUERY () FOR GRAPH {TG_GRAPH} {{ "
                    "s = {Customer.*}; x = SELECT c FROM s:c LIMIT 1; PRINT x.size(); }"
                ),
            },
            timeout=120,
        )
        return True
    except Exception:
        return False


def restart_local():
    if not LOCAL_CONTAINER:
        return False
    print(f"  restarting TigerGraph services in {LOCAL_CONTAINER}", flush=True)
    result = subprocess.run(
        ["docker", "exec", "-u", "tigergraph", LOCAL_CONTAINER, GADMIN, "start", "all"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


async def wait_for_graph(attempts=15, delay=20):
    for i in range(attempts):
        if await healthy():
            return True
        if i == 1:
            restart_local()
        print("  waiting for TigerGraph to come back...", flush=True)
        await asyncio.sleep(delay)
    return False


async def main(use_llm, require_graph, attempts):
    store.init()
    with store.connect() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM cases ORDER BY id")]
    target = ROOT / "output" / "draft-cases"
    target.mkdir(parents=True, exist_ok=True)
    incomplete = []
    for case_id in ids:
        for attempt in range(1, attempts + 1):
            if TG_URL and not await healthy():
                await wait_for_graph()
            try:
                r = await engine.investigate(case_id, use_llm)
            except Exception as e:
                print(case_id, "FAILED", str(e)[:160], flush=True)
                reset(case_id)
                if not await wait_for_graph():
                    break
                continue
            answer = r["result"]
            # Written to the graph is not the same as grounded in it: a case can
            # persist while its evidence came only from the local projection. Use the
            # exporter's own criterion so a retry fixes what the export would refuse.
            grounded = bool(
                (r.get("detail") or {}).get("validation", {}).get("verified")
            )
            if require_graph and TG_URL and not grounded and attempt < attempts:
                print(
                    f"{case_id} attempt {attempt}: not verified "
                    "(graph evidence, vector context or persistence missing), retrying",
                    flush=True,
                )
                reset(case_id)
                await wait_for_graph()
                continue
            (target / f"{case_id}.json").write_text(json.dumps(answer, indent=2))
            case = answer["case"]
            print(
                f"{case_id} {case['verdict']:11s} {case['pattern']:28s} "
                f"${case['exposure_usd']:>10,.2f}  graph={grounded}",
                flush=True,
            )
            if not grounded:
                incomplete.append(case_id)
            break
    if incomplete:
        print(
            f"\n{len(incomplete)} case(s) are not verified: "
            + ", ".join(incomplete)
            + "\nThe exporter will refuse these.",
            flush=True,
        )
    else:
        print(
            "\nAll cases grounded in TigerGraph, carrying graph and document "
            "evidence, and written back with a verified read-back.",
            flush=True,
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--llm", action="store_true", help="run the local evidence reviewer")
    p.add_argument(
        "--require-graph",
        action="store_true",
        help="re-run any case that did not end up graph-backed",
    )
    p.add_argument("--attempts", type=int, default=3)
    args = p.parse_args()
    asyncio.run(main(args.llm, args.require_graph, args.attempts))
