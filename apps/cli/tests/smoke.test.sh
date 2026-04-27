#!/usr/bin/env bash
set -e

API_URL="${API_URL:-http://127.0.0.1:3001}"
CLI="node /Users/hkd-xiaobei/harmess-test/apps/cli/src/index.ts"

echo "=== CLI Smoke Test ==="

echo "1. Health"
$CLI health

echo "2. Create session"
SESSION_OUTPUT=$($CLI session:create "Smoke Test Session" 2>&1)
SESSION_ID=$(echo "$SESSION_OUTPUT" | grep "Session created:" | awk '{print $3}')
echo "Session: $SESSION_ID"

echo "3. List sessions"
$CLI session:list | grep -q "Smoke Test Session"

echo "4. Send message"
$CLI chat:message "$SESSION_ID" "Test message"

echo "5. Create task in session"
TASK_OUTPUT=$($CLI task:create "Smoke Task" --session "$SESSION_ID" 2>&1)
TASK_ID=$(echo "$TASK_OUTPUT" | grep "Task created:" | awk '{print $3}')
echo "Task: $TASK_ID"

echo "6. Run task"
$CLI task:run "$TASK_ID"

echo "7. Wait and check status"
sleep 3
STATUS=$($CLI task:status "$TASK_ID" 2>&1 | grep "Status:" | awk '{print $2}')
echo "Status: $STATUS"

echo "8. Check events"
$CLI task:events "$TASK_ID" | grep -q "task.created"

echo "9. List memories"
$CLI memory:list | grep -q "episodic\|semantic\|performance"

echo "10. List skills"
$CLI skill:list | grep -q "generate_report"

echo "=== CLI Smoke Test Complete ==="
