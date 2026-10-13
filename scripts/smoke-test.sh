#!/usr/bin/env bash
# Smoke-test a built image: refuses to start without a login, starts with one,
# answers /health, reports a bad database as 503, and refuses unauthenticated MCP
# calls. Uses a throwaway sample database and dummy credentials.
#   scripts/smoke-test.sh <image> [expected-version]
set -euo pipefail

IMAGE="${1:?usage: smoke-test.sh <image> [expected-version]}"
EXPECTED_VERSION="${2:-}"
NAME="cashew-smoke-$$"
PORT=18199
DATA=$(mktemp -d)

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf "$DATA"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; docker logs "$NAME" 2>&1 | tail -20; exit 1; }

# Without this, a missing image would make the "refuses to start" check pass
docker image inspect "$IMAGE" >/dev/null 2>&1 || fail "image $IMAGE not found"

python3 - "$DATA/cashew.sqlite" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
for t in ("wallets", "categories", "transactions", "budgets"):
    c.execute(f"CREATE TABLE {t} (id INTEGER PRIMARY KEY, name TEXT, amount REAL)")
c.commit()
PY
chmod 755 "$DATA" && chmod 644 "$DATA/cashew.sqlite"

if docker run --rm -v "$DATA:/data:ro" "$IMAGE" >/dev/null 2>&1; then
  fail "server started over HTTP with no login configured"
fi
echo "ok   refuses to start without login config"

docker run -d --name "$NAME" -p "127.0.0.1:${PORT}:8000" --read-only --tmpfs /tmp \
  -v "$DATA:/data:ro" \
  -e MCP_BASE_URL=https://cashew.example.com \
  -e MCP_GITHUB_CLIENT_ID=smoke \
  -e MCP_GITHUB_CLIENT_SECRET=smoke-secret \
  -e MCP_ALLOWED_GITHUB_USERS=smoke \
  "$IMAGE" >/dev/null

for _ in $(seq 1 30); do
  curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1 && break
  sleep 1
done

HEALTH=$(curl -fsS "http://127.0.0.1:${PORT}/health") || fail "/health not answering 200"
echo "ok   /health -> $HEALTH"
if [[ -n "$EXPECTED_VERSION" && "$HEALTH" != *"$EXPECTED_VERSION"* ]]; then
  fail "expected version ${EXPECTED_VERSION}"
fi

CODE=$(curl -sS -o /dev/null -w '%{http_code}' -X POST \
  -H 'Host: cashew.example.com' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  "http://127.0.0.1:${PORT}/mcp")
[[ "$CODE" == "401" ]] || fail "/mcp without a token returned $CODE, want 401"
echo "ok   /mcp without a token -> 401"

# A bad backup must show as unhealthy, not ok. The data mount is read-only to the
# container, so the file is swapped from the host side.
printf 'not a database' > "$DATA/cashew.sqlite"
CODE=$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/health")
[[ "$CODE" == "503" ]] || fail "/health with a corrupt database returned $CODE, want 503"
echo "ok   /health with a corrupt database -> 503"

echo "PASS $IMAGE"
