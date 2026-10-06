"""Temporal model trained exclusively on historical closed cases, never benchmark labels."""

import json
import pickle
from functools import lru_cache

from . import store
from .config import DATA


@lru_cache(maxsize=1)
def model():
    path = DATA / "historical_model.pkl"
    if not path.exists():
        return None
    # Only a locally generated training artifact; never accept uploaded pickle files.
    with path.open("rb") as f:
        return pickle.load(f)


def predict(tx_id):
    bundle = model()
    if not bundle:
        return None
    with store.connect() as c:
        try:
            r = c.execute(
                "SELECT features FROM scoring_features WHERE id=?", (tx_id,)
            ).fetchone()
        except Exception:
            return None
    if not r:
        return None
    import numpy as np

    features = np.array([json.loads(r[0])], dtype=float)[:, bundle["mask"]]
    raw = float(
        bundle["estimator"].predict_proba(np.nan_to_num(features, nan=-999))[0, 1]
    )
    p = float(bundle["calibrator"].predict([raw])[0])
    return {
        "probability": round(max(0.01, min(0.99, p)), 4),
        "raw_probability": raw,
        "method": "Historical gradient-boosted assessment; calibrated on September selected investigations, not general population.",
        "training_period": "July–August 2016",
        "calibration_period": "September 2016",
        "version": bundle["version"],
    }
