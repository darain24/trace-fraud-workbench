import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from tracework import engine, store
from tracework.config import ROOT
from tracework.models import Answer

with store.connect() as c:
    ids = [r[0] for r in c.execute("SELECT id FROM cases ORDER BY id")]
if len(ids) != 20:
    raise SystemExit("Expected exactly twenty benchmark cases")
answers = []
for id in ids:
    a = Answer.model_validate(store.get_case(id)["result"])
    v = engine.validate(a)
    if not v["verified"]:
        raise SystemExit(
            f"{id}: export blocked; verify TigerGraph graph/vector evidence, persistence, and output integrity first."
        )
    answers.append(a)
for a in answers:
    (ROOT / "examples" / "benchmark-results" / f"{a.case_id}.json").write_text(a.model_dump_json(indent=2))
print("Exported 20 verified results to examples/benchmark-results/")
