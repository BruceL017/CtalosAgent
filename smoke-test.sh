#!/usr/bin/env bash
set -e

echo "=== Enterprise Agent v0.3.1 Smoke Test ==="
echo

API_URL="${API_URL:-http://127.0.0.1:3001}"
RUNTIME_URL="${RUNTIME_URL:-http://localhost:8000}"

# Get auth token first
AUTH_RESPONSE=$(curl -sf -X POST "$API_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@enterprise.local","password":"admin123"}')
TOKEN=$(echo "$AUTH_RESPONSE" | jq -r '.data.token')
if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "ERROR: Failed to get auth token"
  exit 1
fi
echo "Auth token acquired"

AUTH_HEADER="Authorization: Bearer $TOKEN"

# Health checks
echo
echo "1. API Server health"
curl -sf "$API_URL/health" | jq .

echo
echo "2. Agent Runtime health"
curl -sf "$RUNTIME_URL/health" | jq .

echo
echo "3. Agent Runtime detailed health"
curl -sf "$RUNTIME_URL/health/detailed" | jq '.service, .status, .database.healthy'

# Provider status
echo
echo "4. Provider status"
curl -sf "$RUNTIME_URL/providers" | jq '.data.default_provider'

echo
echo "5. Provider health"
curl -sf -H "$AUTH_HEADER" "$API_URL/api/providers/health" | jq '.data[0].provider, .data[0].healthy'

# Tool registry
echo
echo "6. Tool registry"
curl -sf "$RUNTIME_URL/tools" | jq '.data | length'

# Auth me
echo
echo "7. Auth /me"
curl -sf -H "$AUTH_HEADER" "$API_URL/api/auth/me" | jq '.data.email, .data.role'

# Create a task
echo
echo "8. Create task"
TASK_RESPONSE=$(curl -sf -X POST "$API_URL/api/tasks" \
  -H "Content-Type: application/json" \
  -H "$AUTH_HEADER" \
  -d '{"title":"Smoke Test Report","description":"Generate a smoke test report","environment":"test","risk_level":"low"}')
echo "$TASK_RESPONSE" | jq .
TASK_ID=$(echo "$TASK_RESPONSE" | jq -r '.data.id')

# Execute task
echo
echo "9. Execute task: $TASK_ID"
curl -sf -X POST -H "$AUTH_HEADER" "$API_URL/api/tasks/$TASK_ID/execute" | jq '.success, .status'

# Wait a bit
echo
echo "10. Waiting for execution..."
sleep 5

# Check task status
echo
echo "11. Task status"
curl -sf -H "$AUTH_HEADER" "$API_URL/api/tasks/$TASK_ID" | jq '.data.status, .data.result != null'

# Check events
echo
echo "12. Task events count"
curl -sf -H "$AUTH_HEADER" "$API_URL/api/tasks/$TASK_ID/events" | jq '.data | length'

# Check memories
echo
echo "13. Memories created"
curl -sf -H "$AUTH_HEADER" "$API_URL/api/memories" | jq '.data | length'

# Check skills
echo
echo "14. Skills"
curl -sf -H "$AUTH_HEADER" "$API_URL/api/skills" | jq '.data | length'

# Session API
echo
SESSION_RESPONSE=$(curl -sf -X POST "$API_URL/api/sessions" \
  -H "Content-Type: application/json" \
  -H "$AUTH_HEADER" \
  -d '{"title":"Smoke Test Session","description":"Session smoke test"}')
SESSION_ID=$(echo "$SESSION_RESPONSE" | jq -r '.data.id')

echo
echo "15. Session created: $SESSION_ID"

# Create task in session
TASK_IN_SESSION=$(curl -sf -X POST "$API_URL/api/sessions/$SESSION_ID/tasks" \
  -H "Content-Type: application/json" \
  -H "$AUTH_HEADER" \
  -d '{"title":"Session Task","description":"Task inside session"}')
echo "16. Task in session: $(echo "$TASK_IN_SESSION" | jq -r '.data.id')"

# Verify session has task
SESSION_DETAIL=$(curl -sf -H "$AUTH_HEADER" "$API_URL/api/sessions/$SESSION_ID")
echo "17. Session tasks count: $(echo "$SESSION_DETAIL" | jq '.data.tasks | length')"

# Provider stats
echo
echo "18. Provider stats"
curl -sf -H "$AUTH_HEADER" "$API_URL/api/providers/stats" | jq '.data | length'

# Audit logs
echo
echo "19. Audit logs"
curl -sf -H "$AUTH_HEADER" "$API_URL/api/audit" | jq '.data | length'

# Approvals
echo
echo "20. Approvals queue"
curl -sf -H "$AUTH_HEADER" "$API_URL/api/approvals" | jq '.data | length'

echo
echo "=== Smoke Test Complete ==="
