# Each target wraps one step of the pipeline in scripts/. From a fresh clone:
#
#   make setup && make demo-data && make ingest && make graph && make fit && make up
#
# TRACE_DATASET in .env selects demo (synthetic) or full (the benchmark); use
# `make full-data` instead of `make demo-data` for the latter.

# The container scripts/demo_up.sh manages; the same variable it reads.
TG_LOCAL_CONTAINER ?= tigergraph

.PHONY: setup demo-data full-data ingest graph graph-load graph-tune fit up test lint

setup:
	uv sync --all-extras --dev
	npm ci --prefix frontend
	@test -f .env || { cp .env.example .env && echo "Created .env from .env.example"; }

demo-data:
	uv run python scripts/generate_demo_data.py

full-data:
	uv run python scripts/download_data.py

ingest:
	uv run python scripts/ingest.py

# First run: start TigerGraph and MCP, right-size it, install the schema and
# queries, load.
graph:
	./scripts/demo_up.sh --graph-only
	$(MAKE) graph-tune
	./scripts/demo_up.sh --graph-only
	uv run python scripts/provision_tigergraph.py --schema
	$(MAKE) graph-load

# Reload after a fresh ingest; the schema is already installed.
graph-load:
	./scripts/demo_up.sh --graph-only
	uv run python scripts/provision_tigergraph.py --data --documents --reset-documents
	uv run python scripts/verify_tigergraph.py

# The image is sized for a large host; this fits it to a laptop VM, and
# lifts the 16 s query timeout that an emulated container's first loads exceed.
graph-tune:
	docker exec -u tigergraph $(TG_LOCAL_CONTAINER) bash -lc '\
	G=/home/tigergraph/tigergraph/app/cmd/gadmin; \
	$$G config set KafkaConnect.MaxMemorySizeMB 512 && \
	$$G config set KafkaStreamLL.MaxMemorySizeMB 256 && \
	$$G config set ZK.BasicConfig.Env "ZK_SERVER_HEAP=256;" && \
	$$G config set Kafka.BasicConfig.Env "KAFKA_HEAP_OPTS=-Xms128M -Xmx512M;" && \
	$$G config set RESTPP.Factory.DefaultQueryTimeoutSec 120 && \
	$$G config apply -y && $$G restart all -y'

fit:
	uv run python scripts/fit_evidence_model.py

up:
	./scripts/demo_up.sh

test:
	uv run pytest -q

lint:
	uv run ruff check .
