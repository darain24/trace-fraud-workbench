"""The synthetic demo dataset honours the contract the pipeline reads, and is
reproducible byte for byte from its seed."""

import csv
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tracework import store

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = script("generate_demo_data")


def rows(raw, name):
    with open(raw / name, newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def raw(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo") / "raw"
    gen.generate(out)
    return out


def test_column_contract(raw):
    with open(raw / "transactions.csv", newline="") as f:
        header = next(csv.reader(f))
    assert len(header) == 397
    assert header[:4] == ["TransactionID", "TransactionDT", "TransactionAmt", "ProductCD"]
    assert header[-4:] == ["customer_id", "ts", "channel", "risk_score"]
    assert header[-5] == "V339"
    with open(raw / "identity.csv", newline="") as f:
        assert next(csv.reader(f)) == gen.IDENTITY_COLUMNS
    assert list(rows(raw, "case_pack.csv")[0]) == gen.CASE_COLUMNS
    assert list(rows(raw, "closed_cases_history.csv")[0]) == gen.HISTORY_COLUMNS


def test_case_pack_is_anchored(raw):
    txns = {r["TransactionID"]: r for r in rows(raw, "transactions.csv")}
    cases = rows(raw, "case_pack.csv")
    assert [c["case_id"] for c in cases] == [f"DEMO-{i:03d}" for i in range(1, 21)]
    assert {c["trigger_type"] for c in cases} == {
        "risk_score",
        "customer_report",
        "analyst_request",
    }
    for c in cases:
        flagged = txns[c["flagged_txn_id"]]
        assert flagged["customer_id"] == c["customer_id"]
        assert c["card_id"].startswith(c["customer_id"] + "-")
        assert flagged["risk_score"] == c["risk_score"]
        assert c["opened_at"] > flagged["ts"]


def test_history_vocabulary(raw):
    txns = {r["TransactionID"]: r for r in rows(raw, "transactions.csv")}
    patterns = {
        "account_takeover",
        "card_not_present_fraud",
        "card_not_present_new_device",
        "card_testing",
        "out_of_region_use",
        "undocumented",
        "none",
    }
    seen = {}
    for h in rows(raw, "closed_cases_history.csv"):
        assert h["outcome"] in {"confirmed_fraud", "cleared"}
        assert h["pattern"] in patterns
        assert (h["pattern"] == "none") == (h["outcome"] == "cleared")
        assert h["opened_at"] < h["closed_at"]
        ids = h["txn_ids"].split("|")
        assert len(ids) == int(h["n_txns"])
        for tid in ids:
            assert txns[tid]["customer_id"] == h["customer_id"]
            # One transaction, one card: a conflicting anchor would be dropped.
            assert seen.setdefault(tid, h["card_id"]) == h["card_id"]


def test_history_spans_the_fitting_split(raw):
    fit = script("fit_evidence_model")
    txns = {r["TransactionID"]: r for r in rows(raw, "transactions.csv")}
    alerts = [
        h
        for h in rows(raw, "closed_cases_history.csv")
        if float(txns[h["txn_ids"].split("|")[0]]["risk_score"]) >= fit.ALERT_SCORE
    ]
    for side in (
        [h for h in alerts if h["opened_at"] < fit.SPLIT],
        [h for h in alerts if h["opened_at"] >= fit.SPLIT],
    ):
        assert {h["outcome"] for h in side} == {"confirmed_fraud", "cleared"}


def test_policy_readme_slices(raw):
    """`provision_tigergraph.corpus()` and `/api/policy` slice between these."""
    text = (raw / "README.md").read_text()
    headings = [
        "# Fraud Policy",
        "# Answer Format",
        "## The five known fraud patterns",
        "## Regulatory references",
        "## Things to know",
        "## Rules",
    ]
    positions = [text.index(h) for h in headings]
    assert positions == sorted(positions)
    for start, end in zip(headings, headings[1:]):
        assert text.split(start, 1)[1].split(end, 1)[0].strip()
    for rule in [f"R{i}." for i in range(1, 10)]:
        assert rule in text


def test_deterministic(raw, tmp_path):
    # A separate interpreter with a different hash seed must write the same bytes.
    env = {**os.environ, "PYTHONHASHSEED": "1"}
    subprocess.run(
        [sys.executable, str(SCRIPTS / "generate_demo_data.py"), "--out", str(tmp_path)],
        check=True,
        env=env,
        capture_output=True,
    )
    for name in gen.FILES:
        assert (tmp_path / name).read_bytes() == (raw / name).read_bytes(), name
    other = tmp_path / "other"
    gen.generate(other, seed=gen.SEED + 1)
    assert (other / "transactions.csv").read_bytes() != (
        raw / "transactions.csv"
    ).read_bytes()


def test_ingest_and_fit_accept_it(raw, tmp_path, monkeypatch):
    ingest = script("ingest")
    monkeypatch.setattr(store, "DB", tmp_path / "trace.db")
    monkeypatch.setattr(ingest, "DATA", raw.parent)
    monkeypatch.setattr(ingest, "DATASET", "demo")
    ingest.main()  # raises on any case anchor mismatch
    with store.connect() as c:
        assert c.execute("SELECT count(*) FROM cases").fetchone()[0] == 20
        unverified = c.execute(
            "SELECT count(*) FROM transactions t JOIN cases k "
            "ON t.id = json_extract(k.trigger_json, '$.flagged_txn_id') "
            "WHERE t.card_verified = 0"
        ).fetchone()[0]
    assert unverified == 0
    fit = script("fit_evidence_model")
    built = fit.build(0)
    assert any(r["opened"] < fit.SPLIT for r in built)
    assert any(r["opened"] >= fit.SPLIT for r in built)


def test_ingest_refuses_the_other_dataset(raw, tmp_path, monkeypatch):
    ingest = script("ingest")
    monkeypatch.setattr(store, "DB", tmp_path / "trace.db")
    monkeypatch.setattr(ingest, "DATA", raw.parent)
    monkeypatch.setattr(ingest, "DATASET", "full")
    with pytest.raises(SystemExit, match="synthetic demo"):
        ingest.main()


def test_generator_never_overwrites_real_data(tmp_path, monkeypatch):
    (tmp_path / "transactions.csv").write_text("TransactionID\n1\n")
    monkeypatch.setattr(sys, "argv", ["generate_demo_data.py", "--out", str(tmp_path)])
    with pytest.raises(SystemExit, match="did not"):
        gen.main()
    assert (tmp_path / "transactions.csv").read_text() == "TransactionID\n1\n"
