#!/usr/bin/env bash
# Bring the whole stack up and refuse to say "ready" until it actually is.
#
# Community Edition on a laptop VM drops a service under load, and a stack that is
# half up looks fine in the UI right up to the moment a live investigation fails.
# Run this before recording, and wait for the green line.
#
#   --graph-only  stop once TigerGraph, Ollama and MCP are up (for provisioning)
set -uo pipefail
cd "$(dirname "$0")/.."
GRAPH_ONLY=0
[ "${1:-}" = "--graph-only" ] && GRAPH_ONLY=1

CONTAINER="${TG_LOCAL_CONTAINER:-tigergraph}"
GADMIN=/home/tigergraph/tigergraph/app/cmd/gadmin
say() { printf '\033[1m%s\033[0m\n' "$*"; }
ok()  { printf '  \033[32mok\033[0m  %s\n' "$*"; }
bad() { printf '  \033[31mFAIL\033[0m %s\n' "$*"; }

say "1/5  TigerGraph container"
if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    docker start "$CONTAINER" >/dev/null 2>&1 || { bad "could not start $CONTAINER"; exit 1; }
  else
    # No container yet: create TigerGraph and the MCP server from docker-compose.yml.
    docker compose up -d >/dev/null || { bad "docker compose up failed"; exit 1; }
  fi
fi
ok "$CONTAINER running"

say "2/5  TigerGraph services (can take several minutes from cold)"
docker exec -u tigergraph "$CONTAINER" $GADMIN start all >/dev/null 2>&1
# GraphStudio and Kafka Connect are ~600 MB we never use: the agent talks to the
# graph over MCP, and nothing here loads from an external data source. On a 3.8 GB
# Docker VM that 600 MB is exactly the headroom GSE needs to finish warming up,
# and without it the kernel kills GSE mid-start every time.
docker exec -u tigergraph "$CONTAINER" $GADMIN stop gui kafkaconn -y >/dev/null 2>&1
sleep 10
docker exec -u tigergraph "$CONTAINER" $GADMIN start gse gpe restpp gsql >/dev/null 2>&1
for i in $(seq 1 60); do
  status=$(docker exec -u tigergraph "$CONTAINER" $GADMIN status 2>&1)
  # GUI and KAFKACONN are deliberately down; everything else must be Online.
  pending=$(grep -E 'Warmup|Down' <<<"$status" | grep -vE 'GUI|KAFKACONN' || true)
  if [ -z "$pending" ]; then ok "graph services online (GUI and KafkaConnect left off)"; break; fi
  # A fresh container has no graph yet, and GSE and GPE stay in Warmup until a
  # schema exists ("rc: kNotFound" in the GSE log). GSQL is all that installing
  # the schema needs, so waiting for the rest here would wait forever.
  if [ -z "$(grep -vE 'GSE|GPE' <<<"$pending")" ] &&
    docker exec -u tigergraph "$CONTAINER" tail -n 20 /home/tigergraph/tigergraph/log/gse/log.INFO 2>/dev/null |
    grep -q 'rc: kNotFound'; then
    ok "GSQL online; no graph schema yet, so GSE and GPE warm up after it is installed"; break
  fi
  [ "$i" = 60 ] && { bad "services still not online"; echo "$pending"; exit 1; }
  sleep 15
done

say "3/5  Ollama"
curl -sf -m 5 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 || { nohup ollama serve >/dev/null 2>&1 & sleep 6; }
curl -sf -m 5 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && ok "ollama responding" || bad "ollama not responding"

say "4/5  TigerGraph MCP server"
# Ask the server itself: with docker compose the TigerGraph container publishes
# :9001, so the port stays bound even while the MCP container is stopped.
mcp_up() { curl -s -m 5 -o /dev/null http://127.0.0.1:9001/mcp; }
if ! mcp_up; then
  if docker compose ps -a -q mcp 2>/dev/null | grep -q .; then
    docker compose start mcp >/dev/null 2>&1
  else
    nohup uv run tigergraph-mcp --env-file .env --transport streamable-http \
      --host 127.0.0.1 --port 9001 >/tmp/trace-mcp.log 2>&1 &
  fi
  sleep 8
fi
mcp_up && ok "mcp on :9001" || { bad "mcp failed; see /tmp/trace-mcp.log or docker compose logs mcp"; exit 1; }
if [ "$GRAPH_ONLY" = 1 ]; then
  printf '\033[42;30m GRAPH READY \033[0m TigerGraph, Ollama and MCP are up\n'
  exit 0
fi

say "5/5  API and workbench"
lsof -ti:8000 >/dev/null 2>&1 || {
  nohup uv run uvicorn tracework.api:app --app-dir backend \
    --host 127.0.0.1 --port 8000 >/tmp/trace-api.log 2>&1 &
  sleep 10
}
lsof -ti:5173 >/dev/null 2>&1 || {
  nohup npm run dev --prefix frontend >/tmp/trace-vite.log 2>&1 &
  sleep 8
}

# The real check: does the graph answer, and does the app see it?
health=$(curl -sf -m 60 http://127.0.0.1:8000/api/health || echo '{}')
verified=$(python3 -c "import json,sys;print(json.loads(sys.argv[1]).get('tigergraph',{}).get('verified',False))" "$health" 2>/dev/null)
reason=$(python3 -c "import json,sys;print(json.loads(sys.argv[1]).get('tigergraph',{}).get('reason',''))" "$health" 2>/dev/null)

echo
if [ "$verified" = "True" ]; then
  printf '\033[42;30m READY \033[0m %s\n' "$reason"
  echo "  workbench  http://127.0.0.1:5173"
  echo "  api docs   http://127.0.0.1:8000/docs"
else
  printf '\033[41;37m NOT READY \033[0m %s\n' "${reason:-api did not answer}"
  echo "  logs: /tmp/trace-api.log  /tmp/trace-mcp.log  /tmp/trace-vite.log"
  exit 1
fi
