import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DATA = Path(os.getenv("TRACE_DATA_DIR", str(ROOT / "data")))
DB = DATA / "trace.db"
# "demo" is the synthetic dataset from scripts/generate_demo_data.py; "full" is the
# benchmark from scripts/download_data.py. Both are read from DATA / "raw".
DATASET = os.getenv("TRACE_DATASET", "demo")
if DATASET not in ("demo", "full"):
    raise ValueError(f"TRACE_DATASET must be demo or full, not {DATASET!r}")
# Written beside the demo files, so neither dataset is mistaken for the other.
DEMO_MARKER = ".trace-demo"
MODEL = os.getenv("TRACE_MODEL", "qwen3:4b")
OLLAMA = "http://127.0.0.1:11434"  # local-only: no paid provider fallback
TG_URL = os.getenv("TG_MCP_URL", "")
TG_GRAPH = os.getenv("TG_GRAPH", "Trace")
