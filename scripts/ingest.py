"""Streaming source-data ingestion; anchored card mappings, no invented benchmark IDs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import collections
import csv
import hashlib
import json

from tracework import store
from tracework.config import DATA, DATASET, DEMO_MARKER


def number(v, default=0.0):
    try:
        return float(v) if v else default
    except ValueError:
        return default


def main():
    store.init()
    raw = DATA / "raw"
    for f in [
        "transactions.csv",
        "identity.csv",
        "case_pack.csv",
        "closed_cases_history.csv",
    ]:
        if not (raw / f).exists():
            fetch = (
                "make demo-data" if DATASET == "demo" else "scripts/download_data.py"
            )
            raise SystemExit(f"Missing {raw / f}; run {fetch}")
    if (raw / DEMO_MARKER).exists() != (DATASET == "demo"):
        found = "synthetic demo" if DATASET == "full" else "full benchmark"
        raise SystemExit(
            f"{raw} holds the {found} files but TRACE_DATASET={DATASET}. Set "
            "TRACE_DATASET in .env to match, or move data/raw aside and fetch the "
            "other dataset."
        )
    anchors = {}
    conflicts = set()
    historical = list(csv.DictReader(open(raw / "closed_cases_history.csv")))
    cases = list(csv.DictReader(open(raw / "case_pack.csv")))
    for r in historical:
        for tid in r["txn_ids"].split("|"):
            if tid in anchors and anchors[tid] != r["card_id"]:
                conflicts.add(tid)
            anchors[tid] = r["card_id"]
    for r in cases:
        anchors[r["flagged_txn_id"]] = r["card_id"]
    with store.connect() as c:
        c.executescript("""
  DROP TABLE IF EXISTS transactions;
  DROP TABLE IF EXISTS history;
  DROP TABLE IF EXISTS identity;
  CREATE TABLE transactions(id TEXT PRIMARY KEY,customer_id TEXT,card_id TEXT,card_verified INTEGER,signature TEXT,ts TEXT,amount REAL,channel TEXT,risk REAL,region TEXT,country TEXT,product TEXT,email TEXT,recipient TEXT,device TEXT,new_device TEXT,proxy TEXT,match_flags TEXT);
  CREATE TABLE history(id TEXT PRIMARY KEY,customer_id TEXT,card_id TEXT,opened_at TEXT,closed_at TEXT,outcome TEXT,pattern TEXT,txn_ids TEXT,exposure REAL,notes TEXT,raw_json TEXT);
  CREATE TABLE identity(id TEXT PRIMARY KEY,device TEXT,new_device TEXT,proxy TEXT);
  """)
        identity = []
        for r in csv.DictReader(open(raw / "identity.csv")):
            parts = [r.get(k, "") for k in ["DeviceInfo", "id_30", "id_31", "id_33"]]
            profile = " | ".join(x or "unknown" for x in parts) if any(parts) else ""
            identity.append(
                (r["TransactionID"], profile, r.get("id_15", ""), r.get("id_23", ""))
            )
        c.executemany("INSERT INTO identity VALUES(?,?,?,?)", identity)
        c.executemany(
            "INSERT INTO history VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    r["case_id"],
                    r["customer_id"],
                    r["card_id"],
                    r["opened_at"],
                    r["closed_at"],
                    r["outcome"],
                    r["pattern"],
                    r["txn_ids"],
                    number(r["exposure_usd"]),
                    r["analyst_notes"],
                    json.dumps(r),
                )
                for r in historical
            ],
        )
        identity_map = {r[0]: r[1:] for r in identity}
        del identity
        mapping = collections.defaultdict(set)
        batch = []
        count = 0
        for r in csv.DictReader(open(raw / "transactions.csv")):
            tid = r["TransactionID"]
            customer = r["customer_id"]
            sig = json.dumps(
                [customer] + [r.get(f"card{i}", "") for i in range(1, 7)],
                separators=(",", ":"),
            )
            known = anchors.get(tid, "") if tid not in conflicts else ""
            if known:
                mapping[sig].add(known)
            dev, new, proxy = identity_map.get(tid, ("", "", ""))
            batch.append(
                (
                    tid,
                    customer,
                    known,
                    int(bool(known)),
                    sig,
                    r["ts"],
                    number(r["TransactionAmt"]),
                    r["channel"],
                    number(r["risk_score"]),
                    r.get("addr1", ""),
                    r.get("addr2", ""),
                    r.get("ProductCD", ""),
                    r.get("P_emaildomain", ""),
                    r.get("R_emaildomain", ""),
                    dev,
                    new,
                    proxy,
                    json.dumps({f"M{i}": r.get(f"M{i}", "") for i in range(1, 10)}),
                )
            )
            count += 1
            if len(batch) >= 5000:
                c.executemany(
                    "INSERT INTO transactions VALUES(" + ",".join("?" * 18) + ")", batch
                )
                batch = []
            if count % 100000 == 0:
                print(f"Loaded {count:,} transactions", flush=True)
        if batch:
            c.executemany(
                "INSERT INTO transactions VALUES(" + ",".join("?" * 18) + ")", batch
            )
        c.execute("CREATE INDEX tx_sig ON transactions(signature)")
        ambiguous = {k: sorted(v) for k, v in mapping.items() if len(v) > 1}
        for sig, ids in mapping.items():
            if len(ids) == 1:
                c.execute(
                    "UPDATE transactions SET card_id=?,card_verified=1 WHERE signature=? AND card_id=''",
                    (next(iter(ids)), sig),
                )
        # Unanchored signatures have an internal identifier, never an exported benchmark card ID.
        for row in c.execute(
            "SELECT DISTINCT signature FROM transactions WHERE card_id='' "
        ).fetchall():
            c.execute(
                "UPDATE transactions SET card_id=? WHERE signature=? AND card_id=''",
                (
                    "internal-" + hashlib.sha256(row[0].encode()).hexdigest()[:12],
                    row[0],
                ),
            )
        c.executescript(
            "CREATE INDEX tx_card_time ON transactions(card_id,ts); CREATE INDEX tx_customer_time ON transactions(customer_id,ts); CREATE INDEX tx_device_time ON transactions(device,ts); CREATE INDEX tx_region_time ON transactions(region,ts); CREATE INDEX tx_time ON transactions(ts); CREATE INDEX history_time ON history(closed_at);"
        )
        for r in cases:
            c.execute(
                "INSERT INTO cases(id,trigger_json) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET trigger_json=excluded.trigger_json",
                (r["case_id"], json.dumps(r)),
            )
        report = {
            "dataset": DATASET,
            "transactions": count,
            "identity_records": len(identity_map),
            "historical_cases": len(historical),
            "benchmark_cases": len(cases),
            "anchored_signatures": sum(len(v) == 1 for v in mapping.values()),
            "ambiguous_signatures": len(ambiguous),
            "mapping_method": "Exact six-field card signature propagated only from unambiguous benchmark anchors. Unresolved signatures remain internal; never exported as canonical cards.",
            "verified_transactions": c.execute(
                "SELECT count(*) FROM transactions WHERE card_verified=1"
            ).fetchone()[0],
        }
        for r in cases:
            t = c.execute(
                "SELECT customer_id,card_id FROM transactions WHERE id=?",
                (r["flagged_txn_id"],),
            ).fetchone()
            if not t or t[0] != r["customer_id"] or t[1] != r["card_id"]:
                raise ValueError(f"Case anchor mismatch: {r['case_id']}")
        c.execute(
            "INSERT OR REPLACE INTO metadata VALUES(?,?)",
            ("ingest", json.dumps(report)),
        )
        c.execute(
            "INSERT OR REPLACE INTO metadata VALUES(?,?)",
            ("mapping_ambiguities", json.dumps(ambiguous)),
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
