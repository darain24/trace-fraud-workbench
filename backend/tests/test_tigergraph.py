import asyncio
import contextlib
import copy
import json
from types import SimpleNamespace

import pytest
from tracework import tigergraph


def test_partial_vector_upload_is_not_success():
    result = SimpleNamespace(
        isError=False,
        content=[
            SimpleNamespace(
                type="text",
                text=json.dumps({"success": True, "data": {"failed_count": 1}}),
            )
        ],
    )
    with pytest.raises(tigergraph.TigerGraphUnavailable):
        tigergraph.unpack(result)


ANSWER = {
    "case_id": "x",
    "case": {
        "written_to_graph": False,
        "graph_case_id": "",
        "affected_txn_ids": [],
        "connected_card_ids": [],
        "connected_device_profiles": [],
        "similar_prior_cases": [],
        "status": "open",
        "verdict": "uncertain",
        "pattern": "none",
        "fraud_probability": 0.4,
        "exposure_usd": 0.0,
        "summary": "s",
    },
    "next_best_actions": {"final": [{"action": "CREATE_CASE"}]},
    "sar": {"file": False},
}


@contextlib.asynccontextmanager
async def no_session(timeout=0):
    """persist() opens one MCP session for the whole write; these tests replace the
    transport, so the session must not try to reach a server."""
    yield None


def test_write_without_readback_cannot_claim_persistence(monkeypatch):
    async def call(name, arguments, timeout=30, client=None):
        return [{"success": True, "data": {}}]

    monkeypatch.setattr(tigergraph, "call", call)
    monkeypatch.setattr(tigergraph, "bulk", no_session)
    with pytest.raises(tigergraph.TigerGraphUnavailable, match="Read-back"):
        asyncio.run(tigergraph.persist(copy.deepcopy(ANSWER)))


def test_verified_readback_matches_exported_graph_fields(monkeypatch):
    saved = {}

    async def call(name, arguments, timeout=30, client=None):
        if name == "tigergraph__add_node":
            saved.update(arguments["attributes"])
            return []
        return [{"attributes": saved}]

    monkeypatch.setattr(tigergraph, "call", call)
    monkeypatch.setattr(tigergraph, "bulk", no_session)
    answer = copy.deepcopy(ANSWER)
    assert asyncio.run(tigergraph.persist(answer, {"card_id": "c1"})) == "x"
    # The archived payload must record the write, not the pre-write state.
    stored = json.loads(saved["payload"])
    assert stored["case"]["written_to_graph"] is True
    assert stored["case"]["graph_case_id"] == "x"
    # ...and the caller's own answer is not mutated behind its back.
    assert answer["case"]["written_to_graph"] is False
    # Attributes a later investigation retrieves on must be real attributes.
    assert saved["verdict"] == "uncertain" and saved["card_id"] == "c1"
    assert saved["actions"] == "CREATE_CASE"


def test_missing_service_never_reports_available(monkeypatch):
    monkeypatch.setattr(tigergraph, "TG_URL", "")
    result = asyncio.run(tigergraph.health())
    assert not result["available"] and not result["verified"]


def test_credential_headers_forward_only_configured_fields(monkeypatch):
    monkeypatch.setenv("TG_HOST", "https://example.invalid")
    monkeypatch.setenv("TG_API_TOKEN", "private-test-token")
    monkeypatch.setenv("TG_PASSWORD", "")
    headers = tigergraph.credential_headers()
    assert headers["X-TG-Host"] == "https://example.invalid"
    assert headers["X-TG-Api-Token"] == "private-test-token"
    assert "X-TG-Password" not in headers


def test_nested_http_error_is_actionable_and_redacted():
    import httpx

    request = httpx.Request("POST", "http://localhost/mcp?secret=private-test-token")
    response = httpx.Response(400, request=request, text="private-test-token")
    error = httpx.HTTPStatusError(
        "private-test-token", request=request, response=response
    )
    nested = ExceptionGroup("outer", [ExceptionGroup("inner", [error])])
    message = tigergraph.transport_error(nested)
    assert "HTTP 400" in message
    assert "TG_HOST" in message
    assert "private-test-token" not in message


def test_session_wraps_transport_failure(monkeypatch):
    from contextlib import asynccontextmanager

    import httpx

    @asynccontextmanager
    async def broken(url, *, headers, timeout):
        assert headers["X-TG-Api-Token"] == "test-token"
        req = httpx.Request("POST", url)
        response = httpx.Response(401, request=req)
        error = httpx.HTTPStatusError("unauthorized", request=req, response=response)
        raise ExceptionGroup("SDK task group", [error])
        yield  # pragma: no cover

    monkeypatch.setenv("TG_API_TOKEN", "test-token")
    monkeypatch.setattr(tigergraph, "TG_URL", "http://localhost/mcp")
    monkeypatch.setattr(tigergraph, "streamablehttp_client", broken)
    result = asyncio.run(tigergraph.health())
    assert result["available"] is False
    assert "HTTP 401" in result["reason"]
    assert "TG_API_TOKEN" in result["reason"]
