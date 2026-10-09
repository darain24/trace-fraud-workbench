"""Refit and re-verify the evidence weights in `tracework.analysis.WEIGHTS`.

Reproduces the numbers quoted in the README and the module docstring. Training uses
closed investigations opened before October 2016 whose flagged transaction scored at
or above 0.82 -- the alerts where the evidence, not the alert, had to decide. The
holdout is the October alerts of the same kind.

The bank's risk score is a selection filter here, not a feature: it decides which
alerts enter the population, and it is never given a weight.
"""

import argparse
import json
import statistics
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from tracework import analysis, store
from tracework.config import ROOT

ALERT_SCORE = 0.82
SPLIT = "2016-10-01"


def features(c, t, cutoff):
    """The same measurements `analysis.assess` makes, computed the same way."""
    when = analysis.dt(t["ts"])
    ago = lambda **kw: (when - timedelta(**kw)).isoformat(sep=" ")  # noqa: E731
    q = lambda sql, a: [dict(r) for r in c.execute(sql, a)]  # noqa: E731
    base = q(
        "SELECT * FROM transactions WHERE customer_id=? AND ts<? ORDER BY ts DESC LIMIT 400",
        (t["customer_id"], ago(days=7)),
    )
    card48 = q(
        "SELECT * FROM transactions WHERE card_id=? AND ts<=? AND ts>=?",
        (t["card_id"], cutoff, ago(hours=48)),
    )
    cust48 = q(
        "SELECT * FROM transactions WHERE customer_id=? AND ts<=? AND ts>=?",
        (t["customer_id"], cutoff, ago(hours=48)),
    )
    prior30 = q(
        "SELECT ts FROM transactions WHERE card_id=? AND ts<? AND ts>=?",
        (t["card_id"], ago(hours=48), ago(days=30)),
    )
    region_run = q(
        "SELECT * FROM transactions WHERE card_id=? AND region=? AND ts<=? AND ts>=?",
        (t["card_id"], t["region"], cutoff, ago(days=14)),
    )
    regions = {x["region"] for x in base if x["region"]}
    med = statistics.median([abs(x["amount"]) for x in base]) if base else 0.0
    flags = json.loads(t["match_flags"])
    rate48 = len(prior30) / 14.0
    v48 = len(card48)
    v24 = len([x for x in card48 if when - analysis.dt(x["ts"]) <= timedelta(hours=24)])
    tiny = [
        x
        for x in card48
        if x["channel"] == "online"
        and 0 < abs(x["amount"]) < 5
        and x["ts"] < t["ts"]
        and abs((when - analysis.dt(x["ts"])).total_seconds()) <= 3600
    ]
    return {
        "device_seen": int(t["new_device"] == "Found"),
        "no_device": int(not t["device"] and t["channel"] == "in_person"),
        "takeover": int(
            len({x["channel"] for x in card48}) > 1
            and sum(v == "F" for v in flags.values()) >= 2
        ),
        "burst": int(v24 >= 4 or (v48 - rate48) >= 3),
        "heavy": int(v48 >= 8),
        "concurrent": int(
            len(
                [
                    x
                    for x in cust48
                    if x["region"] in regions and x["region"] != t["region"]
                ]
            )
            >= 5
        ),
        "region_run": int(
            bool(regions)
            and t["region"] not in regions
            and len({x["ts"][:10] for x in region_run}) >= 2
        ),
        "testing": int(len(tiny) >= 3),
        "new_device": int(t["new_device"] == "New"),
        "isolated": int(v48 <= 1),
        "one_off": int(med and abs(t["amount"]) / med >= 3 and v48 <= 2),
        "thin_base": int(len(base) < 5),
    }


def build(limit):
    rows = []
    with store.connect() as c:
        history = [
            dict(r) for r in c.execute("SELECT * FROM history ORDER BY opened_at")
        ]
        if limit:
            history = history[:limit]
        for i, h in enumerate(history):
            t = c.execute(
                "SELECT * FROM transactions WHERE id=?", (h["txn_ids"].split("|")[0],)
            ).fetchone()
            if not t:
                continue
            t = dict(t)
            if t["risk"] < ALERT_SCORE:
                continue  # population filter, never a feature
            row = features(c, t, h["opened_at"])
            row["label"] = int(h["outcome"] == "confirmed_fraud")
            row["opened"] = h["opened_at"]
            rows.append(row)
            if i % 500 == 0:
                print(f"  {i}/{len(history)}", flush=True)
    return rows


def main(limit):
    store.init()
    print(f"Building features for alerts scoring >= {ALERT_SCORE}", flush=True)
    rows = build(limit)
    keys = [k for k in analysis.WEIGHTS] + ["testing"]
    train = [r for r in rows if r["opened"] < SPLIT]
    test = [r for r in rows if r["opened"] >= SPLIT]
    X = lambda s: np.array([[r[k] for k in keys] for r in s], dtype=float)  # noqa: E731
    y = lambda s: np.array([r["label"] for r in s])  # noqa: E731
    model = LogisticRegression(max_iter=4000).fit(X(train), y(train))
    p = model.predict_proba(X(test))[:, 1]
    fitted = dict(zip(keys, (round(float(w), 3) for w in model.coef_[0])))
    report = {
        "population": (
            f"Closed investigations whose flagged transaction scored >= {ALERT_SCORE}. "
            "These are the alerts where the evidence, not the alert, had to decide."
        ),
        "train": {
            "split": f"opened before {SPLIT}",
            "n": len(train),
            "fraud_rate": round(float(np.mean(y(train))), 4),
        },
        "holdout": {
            "split": f"opened on or after {SPLIT}",
            "n": len(test),
            "fraud_rate": round(float(np.mean(y(test))), 4),
            "roc_auc": round(float(roc_auc_score(y(test), p)), 4),
            "accuracy": round(float(accuracy_score(y(test), p >= 0.5)), 4),
            "brier": round(float(brier_score_loss(y(test), p)), 4),
        },
        "fitted_weights": fitted,
        "shipped_weights": dict(analysis.WEIGHTS),
        "shipped_intercept": analysis.INTERCEPT,
        "fitted_intercept": round(float(model.intercept_[0]), 3),
        "excluded_feature": (
            "The bank's risk score. Across all closed cases it scores ROC-AUC 0.053, "
            "near-perfectly inverted, because it selects which alerts are opened "
            "rather than which activity is fraud. The benchmark samples risk-score "
            "triggers from 0.52 to 0.90, so the inversion does not transfer."
        ),
        "limitations": [
            "Investigated alerts are not the general transaction population.",
            "Holdout accuracy on October alerts is not benchmark accuracy.",
            "card_testing is fitted at ~0 because it appears in 16 of 5,565 closed "
            "cases; it ships as policy rule R5 with a fixed weight instead.",
        ],
    }
    (ROOT / "output" / "evidence-model.json").write_text(json.dumps(report, indent=2))
    with store.connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO metadata VALUES(?,?)",
            ("evidence_model", json.dumps(report)),
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "--limit", type=int, default=0, help="cap history rows (for a quick run)"
    )
    main(p.parse_args().limit)
