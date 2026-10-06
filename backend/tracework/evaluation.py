"""Actual chronological historical evaluation; never claims hidden benchmark accuracy."""

import json

from . import analysis, store
from .engine import validate
from .models import Answer


def overview():
    with store.connect() as c:
        cases = c.execute("SELECT id,result_json,detail_json FROM cases").fetchall()
    completed = [r for r in cases if r["result_json"]]
    answers = [Answer.model_validate_json(r["result_json"]) for r in completed]
    checks = [validate(a) for a in answers]
    return {
        "total": len(cases),
        "completed": len(completed),
        "valid_exports": sum(not x["errors"] for x in checks),
        "graph_verified": sum(a.case.written_to_graph for a in answers),
        "policy_errors": sum(len(x["errors"]) for x in checks),
        "tokens": sum(a.tokens for a in answers),
        "avg_latency_s": round(sum(a.latency_s for a in answers) / len(answers), 2)
        if answers
        else 0,
        "verdicts": {
            v: sum(a.case.verdict == v for a in answers)
            for v in ["fraud", "legitimate", "uncertain"]
        },
        "verified": bool(answers)
        and len(answers) == 20
        and all(c["verified"] for c in checks),
        "historical": store.meta("evaluation"),
        "statistical_model": store.meta("scoring_model"),
        "benchmark_accuracy": None,
        "note": "The benchmark answer key is hidden. Completeness and policy checks are not accuracy.",
    }


def run_historical(limit=40):
    with store.connect() as c:
        # Deterministic class-stratified holdout, explicit selection bias disclosure.
        fraud = c.execute(
            "SELECT * FROM history WHERE opened_at>='2016-10-01' AND outcome='confirmed_fraud' ORDER BY opened_at LIMIT ?",
            (limit // 2,),
        ).fetchall()
        clear = c.execute(
            "SELECT * FROM history WHERE opened_at>='2016-10-01' AND outcome='cleared' ORDER BY opened_at LIMIT ?",
            (limit // 2,),
        ).fetchall()
    metrics = {
        m: {"correct": 0, "brier": 0, "n": 0, "abstained": 0}
        for m in ["risk_score_only", "no_memory", "trace"]
    }
    details = []
    skipped = []
    for row in sorted(fraud + clear, key=lambda r: r["opened_at"]):
        tid = row["txn_ids"].split("|")[0]
        trigger = {
            "case_id": row["id"],
            "flagged_txn_id": tid,
            "customer_id": row["customer_id"],
            "card_id": row["card_id"],
            "opened_at": row["opened_at"],
            "trigger_type": "risk_score",
        }
        try:
            packet = analysis.collect(trigger)
            a = analysis.assess(packet, trigger)
            no_memory = analysis.assess({**packet, "history": []}, trigger)
            y = int(row["outcome"] == "confirmed_fraud")
            for name, p, verdict in [
                (
                    "risk_score_only",
                    packet["flagged"]["risk"],
                    "fraud" if packet["flagged"]["risk"] >= 0.7 else "legitimate",
                ),
                ("no_memory", no_memory["probability"], no_memory["verdict"]),
                ("trace", a["probability"], a["verdict"]),
            ]:
                m = metrics[name]
                m["n"] += 1
                m["brier"] += (p - y) ** 2
                m["abstained"] += verdict == "uncertain"
                m["correct"] += (
                    ((verdict == "fraud") == bool(y)) if verdict != "uncertain" else 0
                )
            details.append(
                {
                    "case_id": row["id"],
                    "actual": row["outcome"],
                    "verdict": a["verdict"],
                    "probability": a["probability"],
                }
            )
        except Exception as e:
            skipped.append({"case_id": row["id"], "error": str(e)})
    for m in metrics.values():
        m["brier"] = round(m["brier"] / m["n"], 4) if m["n"] else None
        m["accuracy_including_abstentions"] = (
            round(m["correct"] / m["n"], 4) if m["n"] else None
        )
        m["coverage"] = round((m["n"] - m["abstained"]) / m["n"], 4) if m["n"] else None
    report = {
        "split": "October historical cases; retrieval restricted to outcomes closed before each alert. Up to 20 fraud and 20 cleared cases.",
        "metrics": metrics,
        "cases": details,
        "skipped": skipped,
        "calibrated": False,
        "limitations": [
            "Selected historical investigations are not population prevalence.",
            "This diagnostic sample is not the hidden benchmark and is not an unbiased accuracy estimate.",
            "Current deterministic memory retrieval is explanatory; no improvement from memory is claimed without measured evidence.",
        ],
    }
    with store.connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO metadata VALUES(?,?)",
            ("evaluation", json.dumps(report)),
        )
    return report


def discover():
    with store.connect() as c:
        candidates = c.execute(
            "SELECT device,strftime('%Y-%W',ts) AS week,count(DISTINCT customer_id) customers,count(*) transactions,min(ts) first_seen,max(ts) last_seen FROM transactions WHERE ts>='2016-11-01' AND device!='' AND device NOT LIKE '%unknown%' AND new_device='New' AND proxy!='' GROUP BY device,week HAVING count(DISTINCT customer_id)>=3 AND count(*)>=4 ORDER BY count(*)*1.0/count(DISTINCT customer_id) DESC,count(*) DESC LIMIT 12"
        ).fetchall()
        result = []
        c.execute(
            "DELETE FROM discovery"
        )  # Refresh only derived, non-benchmark candidate results.
        for i, row in enumerate(candidates):
            r = dict(row)
            r.update(
                id=f"DISC-{i + 1:03}",
                status="candidate",
                verdict="unassessed",
                reason="Repeated new-device/proxy activity across at least three customers within one calendar week on a fully specified profile. Investigate authorization and historical context before concluding fraud.",
                benchmark=False,
            )
            result.append(r)
            c.execute(
                "INSERT OR REPLACE INTO discovery VALUES(?,?)", (r["id"], json.dumps(r))
            )
    return result
