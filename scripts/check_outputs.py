import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from tracework import engine, store
from tracework.models import Answer

store.init()
with store.connect() as c:
    ids = [r[0] for r in c.execute("SELECT id FROM cases ORDER BY id")]
errors = []
ready = 0
for id in ids:
    r = store.get_case(id)
    try:
        a = Answer.model_validate(r["result"])
        v = engine.validate(a)
        if v["errors"]:
            errors.append({"case": id, "errors": v["errors"]})
        ready += v["verified"]
    except Exception as e:
        errors.append({"case": id, "error": str(e)})
print(
    json.dumps(
        {
            "cases": len(ids),
            "valid": len(ids) - len(errors),
            "verified": ready,
            "errors": errors,
        },
        indent=2,
    )
)
if errors:
    raise SystemExit(1)
