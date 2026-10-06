import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from . import engine, evaluation, llm, store, tigergraph
from .config import DATA
from .models import Answer, ApprovalInput, InvestigationInput, ResponseInput

TASKS = set()


@asynccontextmanager
async def lifespan(app):
    store.init()
    with store.connect() as c:
        c.execute(
            "UPDATE cases SET state='interrupted',error='Previous process ended; resume investigation.' WHERE state IN ('running','scheduled')"
        )
    yield


app = FastAPI(title="Trace Investigation API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(KeyError)
async def not_found(request, exc):
    return JSONResponse(status_code=404, content={"detail": "Case not found"})


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "cost_mode": "zero paid services",
        "dataset": store.meta("ingest"),
        "model": await llm.status(),
        "tigergraph": await tigergraph.health(),
    }


@app.get("/api/cases")
def cases():
    with store.connect() as c:
        rows = c.execute(
            "SELECT id,trigger_json,state,result_json,revision,error FROM cases ORDER BY id"
        ).fetchall()
    return [
        {
            **json.loads(r["trigger_json"]),
            "state": r["state"],
            "revision": r["revision"],
            "error": r["error"],
            "assessment": json.loads(r["result_json"])["case"]
            if r["result_json"]
            else None,
        }
        for r in rows
    ]


@app.get("/api/cases/{case_id}")
def case(case_id: str):
    return store.get_case(case_id)


async def work(case_id, use_llm):
    try:
        await engine.investigate(case_id, use_llm)
    except Exception:
        pass  # State and actionable error persisted by engine.
    finally:
        TASKS.discard(case_id)


@app.post("/api/cases/{case_id}/investigate")
async def investigate(
    case_id: str, body: InvestigationInput, background: BackgroundTasks
):
    r = store.get_case(case_id)
    if r["result"]:
        return {"state": "complete", "case_id": case_id}
    if case_id in TASKS:
        return {"state": "running", "case_id": case_id}
    TASKS.add(case_id)
    with store.connect() as c:
        c.execute("UPDATE cases SET state='scheduled' WHERE id=?", (case_id,))
    background.add_task(work, case_id, body.use_llm)
    return {"state": "scheduled", "case_id": case_id}


@app.get("/api/cases/{case_id}/events")
def events(case_id: str):
    store.get_case(case_id)
    return store.events(case_id)


@app.get("/api/cases/{case_id}/stream")
async def stream(case_id: str, after: int = 0):
    store.get_case(case_id)

    async def generate():
        cursor = after
        for _ in range(240):
            for e in store.events(case_id, cursor):
                cursor = e["id"]
                yield f"id: {cursor}\ndata: {json.dumps(e)}\n\n"
            r = store.get_case(case_id)
            if r["state"] in ("complete", "failed"):
                yield "event: done\ndata: {}\n\n"
                break
            yield ": keepalive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.post("/api/cases/{case_id}/evidence")
async def evidence(case_id: str, body: ResponseInput):
    return await engine.respond(case_id, body.response, body.note)


@app.get("/api/cases/{case_id}/scenarios")
def scenarios(case_id: str):
    return engine.scenarios(case_id)


@app.post("/api/cases/{case_id}/approve")
def approve(case_id: str, body: ApprovalInput):
    r = store.get_case(case_id)
    if body.decision_revision != r["revision"]:
        raise HTTPException(
            409, "Decision changed; review the current recommendation before approving."
        )
    if not r["result"]:
        raise HTTPException(409, "No recommendation to approve")
    a = next(
        (
            a
            for a in r["result"]["next_best_actions"]["final"]
            if a["action"] == body.action
        ),
        None,
    )
    if not a or a["route"] == "auto" or a["route"] != body.route:
        raise HTTPException(
            422, "Approval route does not match the current recommendation"
        )
    with store.connect() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO approvals VALUES(?,?,?,?,?)",
            (case_id, r["revision"], body.action, body.route, store.now()),
        )
        inserted = cur.rowcount > 0
    if inserted:
        store.event(
            case_id,
            "approval",
            "Simulated approval recorded",
            {
                "action": body.action,
                "route": body.route,
                "revision": r["revision"],
                "executed": False,
                "simulated": True,
            },
        )
    return {
        "approved": True,
        "executed": False,
        "simulated": True,
        "duplicate": not inserted,
    }


@app.get("/api/cases/{case_id}/approvals")
def approvals(case_id: str):
    r = store.get_case(case_id)
    with store.connect() as c:
        return [
            dict(x)
            for x in c.execute(
                "SELECT * FROM approvals WHERE case_id=? AND revision=?",
                (case_id, r["revision"]),
            )
        ]


@app.get("/api/cases/{case_id}/export")
def export(case_id: str, verified: bool = False):
    r = store.get_case(case_id)
    if not r["result"]:
        raise HTTPException(409, "Investigate this case first")
    a = Answer.model_validate(r["result"])
    v = engine.validate(a)
    if v["errors"]:
        raise HTTPException(422, v["errors"])
    if verified and not v["verified"]:
        raise HTTPException(
            409,
            "Draft only: TigerGraph evidence/persistence requirements are not verified.",
        )
    return JSONResponse(
        a.model_dump(),
        headers={
            "Content-Disposition": f'attachment; filename="{case_id}.json"',
            "X-Trace-Verified": str(v["verified"]).lower(),
        },
    )


@app.get("/api/evaluation")
def metrics():
    return evaluation.overview()


@app.post("/api/evaluation/run")
async def evaluate():
    return await asyncio.to_thread(evaluation.run_historical)


@app.get("/api/discovery")
def discoveries():
    with store.connect() as c:
        return [
            json.loads(x[0])
            for x in c.execute("SELECT payload FROM discovery ORDER BY id")
        ]


@app.post("/api/discovery/run")
async def discover():
    return await asyncio.to_thread(evaluation.discover)


@app.get("/api/policy")
def policy():
    path = DATA / "raw" / "README.md"
    if not path.exists():
        raise HTTPException(404, "Dataset README has not been downloaded")
    text = path.read_text()
    return {
        "source": "Dataset README — Fraud Policy v1.0",
        "text": text.split("# Fraud Policy", 1)[1].split("# Answer Format", 1)[0],
    }


@app.post("/api/cases/{case_id}/review")
async def review(case_id: str):
    return await engine.review(case_id)
