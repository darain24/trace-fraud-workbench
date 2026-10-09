import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from tracework import analysis, retrieval, store, tigergraph
from tracework.config import DATASET

# A case that exercises device and region neighbours; any case ID may be passed.
CASE = sys.argv[1] if len(sys.argv) > 1 else "HHG-014" if DATASET == "full" else "DEMO-009"


async def main():
    health = await tigergraph.health()
    if not health["available"]:
        raise SystemExit(health["reason"])
    trigger = store.get_case(CASE)["trigger"]
    packet = analysis.collect(trigger)
    grounded = await retrieval.ground(packet, trigger)
    print(
        json.dumps(
            {
                "graph_evidence_verified": grounded["source"] == "tigergraph",
                "vector_documents": len(grounded["graph_documents"]),
                "read_only": True,
            },
            indent=2,
        )
    )
    print(
        "Case persistence is verified separately by the investigation write/read-back."
    )


asyncio.run(main())
