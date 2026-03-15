#!/bin/bash
#
# Functional test script — runs inside the test container.
# TEST_SCENARIO env var selects the test path.
#
set -euo pipefail

SCENARIO="${TEST_SCENARIO:?TEST_SCENARIO not set}"
WHEEL=$(ls /dist/kanban_mcp-*.whl)
echo "=== Functional test: $SCENARIO ==="
echo "Wheel: $WHEEL"
echo

# -----------------------------------------------------------
# 1. Install wheel via pipx (simulates real user install)
# -----------------------------------------------------------

case "$SCENARIO" in
    sqlite)
        echo "--- pipx install (SQLite only) ---"
        pipx install "$WHEEL"
        ;;
    sqlite-semantic)
        echo "--- pipx install (SQLite + semantic) ---"
        pipx install "$WHEEL[semantic]"
        ;;
    mysql)
        echo "--- pipx install (MySQL) ---"
        pipx install "$WHEEL[mysql]"
        ;;
    mysql-semantic)
        echo "--- pipx install (MySQL + semantic) ---"
        pipx install "$WHEEL[full]"
        ;;
    *)
        echo "Unknown scenario: $SCENARIO"
        exit 1
        ;;
esac
echo

# -----------------------------------------------------------
# 2. Verify binaries are on PATH
# -----------------------------------------------------------

echo "--- Checking installed commands ---"
for cmd in kanban-mcp kanban-web kanban-cli kanban-setup; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "FAIL: $cmd not found"
        exit 1
    fi
    echo "  OK: $cmd"
done
echo

# -----------------------------------------------------------
# 3. Run setup (migrations)
# -----------------------------------------------------------

echo "--- Running kanban-setup ---"
case "$SCENARIO" in
    sqlite|sqlite-semantic)
        export KANBAN_BACKEND=sqlite
        kanban-setup --auto --backend sqlite
        ;;
    mysql|mysql-semantic)
        kanban-setup --auto --migrate-only
        ;;
esac
echo

# -----------------------------------------------------------
# 4. Functional: MCP server responds
# -----------------------------------------------------------

echo "--- Testing MCP server ---"
# MCP server uses stdio — send a JSON-RPC initialize request and check the response
INIT_REQUEST='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
RESPONSE=$(echo "$INIT_REQUEST" | timeout 10 kanban-mcp 2>/dev/null | head -1 || true)
if echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('result',{}).get('serverInfo',{}).get('name')" 2>/dev/null; then
    echo "  OK: MCP server responded to initialize"
else
    echo "FAIL: MCP server did not respond correctly"
    echo "  Response: $RESPONSE"
    exit 1
fi
echo

# -----------------------------------------------------------
# 5. Functional: Web UI starts and serves /
# -----------------------------------------------------------

echo "--- Testing web UI ---"
kanban-web &
WEB_PID=$!
sleep 2

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/ || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo "  OK: Web UI responds 200 on /"
else
    echo "FAIL: Web UI returned $HTTP_CODE (expected 200)"
    kill "$WEB_PID" 2>/dev/null || true
    exit 1
fi
kill "$WEB_PID" 2>/dev/null || true
wait "$WEB_PID" 2>/dev/null || true
echo

# -----------------------------------------------------------
# 6. Functional: CLI works
# -----------------------------------------------------------

echo "--- Testing CLI ---"
kanban-cli --project /tmp/func-test summary
echo "  OK: CLI summary works"
echo

# -----------------------------------------------------------
# 7. Semantic-specific: verify embedding tools exist
# -----------------------------------------------------------

case "$SCENARIO" in
    *-semantic)
        echo "--- Testing semantic search availability ---"
        # Use the MCP server to check — send a tools/list request
        TOOLS_REQUEST='{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
        INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
        INITIALIZED='{"jsonrpc":"2.0","method":"notifications/initialized"}'
        TOOLS_RESPONSE=$(printf '%s\n%s\n%s\n' "$INIT" "$INITIALIZED" "$TOOLS_REQUEST" | timeout 10 kanban-mcp 2>/dev/null || true)
        for tool in semantic_search find_similar rebuild_embeddings; do
            if echo "$TOOLS_RESPONSE" | grep -q "\"$tool\""; then
                echo "  OK: $tool tool registered"
            else
                echo "FAIL: $tool tool missing from tools/list"
                exit 1
            fi
        done
        echo
        ;;
esac

echo "=== $SCENARIO: ALL PASSED ==="
