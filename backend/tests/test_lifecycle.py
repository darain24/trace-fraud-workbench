import asyncio
import json

from fastapi.testclient import TestClient
from tracework import engine, store
from tracework.api import app
from tracework.models import Answer


def fixture_case():
    trigger = {
        "case_id": "TEST-1",
        "card_id": "c1",
        "customer_id": "u1",
        "flagged_txn_id": "t1",
        "trigger_type": "risk_score",
        "opened_at": "2016-11-01 12:00:00",
    }
    f = {
        "id": "t1",
        "amount": 125,
        "customer_id": "u1",
        "card_id": "c1",
        "ts": "2016-11-01 10:00:00",
        "channel": "online",
        "region": "1",
        "device": "",
    }
    packet = {"flagged": f, "tool_calls": 2, "timeline": [f], "neighbors": []}
    a = {
        "probability": 0.45,
        "exposure": 125,
        "verdict": "uncertain",
        "pattern": "none",
        "disputed": False,
        "recurring": False,
        "testing": False,
        "shared_fraud": False,
        "conflict": False,
        "independent_evidence": 1,
        "affected": [f],
        "connected_cards": [],
        "evidence": [],
        "history": [],
        "findings": [],
        "connected_devices": [],
        "velocity": {"v48": 1, "v24": 1, "baseline_rate_48h": 0.5, "excess": 0.5},
    }
    answer = engine.build_answer(trigger, a, packet)
    with store.connect() as c:
        c.execute(
            "INSERT INTO cases(id,trigger_json) VALUES(?,?)",
            ("TEST-1", json.dumps(trigger)),
        )
    store.save("TEST-1", answer.model_dump(), {"assessment": a, "packet": packet})
    return answer


def test_scenarios_do_not_mutate(db):
    fixture_case()
    before = store.get_case("TEST-1")
    s = engine.scenarios("TEST-1")
    after = store.get_case("TEST-1")
    assert before == after
    assert s["hypothetical"] and not s["persisted"]


def test_initial_decision_immutable_and_duplicate_response_idempotent(db):
    old = fixture_case()
    first = asyncio.run(engine.respond("TEST-1", "denied"))
    second = asyncio.run(engine.respond("TEST-1", "denied"))
    assert (
        first["result"]["next_best_actions"]["initial"]
        == old.model_dump()["next_best_actions"]["initial"]
    )
    assert first["revision"] == second["revision"]
    assert len(first["result"]["evidence_requests"]) == 1
    assert first["result"]["case"]["verdict"] == "fraud"


def test_confirmation_zeroes_exposure(db):
    fixture_case()
    r = asyncio.run(engine.respond("TEST-1", "confirmed"))
    a = Answer.model_validate(r["result"])
    assert a.case.exposure_usd == 0 and not a.case.affected_txn_ids and not a.sar.file


def test_invalid_ids_fail_validation(db):
    a = fixture_case()
    a.case.affected_txn_ids = ["invented"]
    assert engine.validate(a)["errors"]


def test_verified_export_is_blocked_without_graph(db):
    fixture_case()
    with TestClient(app) as c:
        assert c.get("/api/cases/TEST-1/export").status_code == 200
        assert c.get("/api/cases/TEST-1/export?verified=true").status_code == 409


def test_approval_requires_matching_revision_route_and_is_idempotent(db):
    fixture_case()
    r = asyncio.run(engine.respond("TEST-1", "denied"))
    with TestClient(app) as c:
        body = {
            "action": "BLOCK_CARD",
            "route": "L1",
            "decision_revision": r["revision"],
        }
        assert (
            c.post(
                "/api/cases/TEST-1/approve", json={**body, "route": "L2"}
            ).status_code
            == 422
        )
        assert (
            c.post(
                "/api/cases/TEST-1/approve", json={**body, "decision_revision": 1}
            ).status_code
            == 409
        )
        assert (
            c.post("/api/cases/TEST-1/approve", json=body).json()["executed"] is False
        )
        assert (
            c.post("/api/cases/TEST-1/approve", json=body).json()["duplicate"] is True
        )


def test_graph_persistence_alone_is_not_verified(db):
    a = fixture_case()
    a.case.written_to_graph = True
    a.case.graph_case_id = a.case_id
    assert engine.validate(a)["verified"] is False
