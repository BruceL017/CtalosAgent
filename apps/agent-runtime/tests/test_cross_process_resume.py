"""Test cross-process resume: service restart approval recovery via DB workflow_states.

Simulates:
1. Task starts, hits approval, workflow state persisted to DB
2. Service "restarts" (new TaskExecutor instance)
3. New executor loads state from DB and resumes correctly
4. No re-planning occurs; execution continues from saved step
"""
import os
import uuid

import pytest
import pytest_asyncio
import asyncpg

from services.task_executor import TaskExecutor
from services.workflow_engine import WorkflowEngine

# Force mock provider for deterministic tests
os.environ["DEFAULT_PROVIDER"] = "mock"
for key in ["SILICONFLOW_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
            "DEEPSEEK_API_KEY", "ZHIPU_API_KEY", "MOONSHOT_API_KEY", "GOOGLE_API_KEY"]:
    os.environ.pop(key, None)

DB_URL = "postgresql://agent:agent_secret@localhost:5432/agent_db"

# Use a writable temp dir for artifacts during tests
os.environ.setdefault("ARTIFACTS_DIR", "/tmp/agent_test_artifacts")


async def _cleanup_task(conn, task_id: str):
    for table, col in [
        ("tool_calls", "task_id"),
        ("task_state_transitions", "task_id"),
        ("task_events", "task_id"),
        ("approvals", "task_id"),
        ("rollback_plans", "task_id"),
        ("artifacts", "task_id"),
        ("memories", "source_task_id"),
        ("subagents", "task_id"),
        ("workflow_states", "task_id"),
        ("tasks", "id"),
    ]:
        await conn.execute(f"DELETE FROM {table} WHERE {col} = $1", task_id)


@pytest_asyncio.fixture
async def db_pool():
    pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=2)
    yield pool
    await pool.close()


class TestCrossProcessResume:
    @pytest.mark.asyncio
    async def test_resume_after_executor_recreate(self, db_pool):
        """Simulate service restart: old executor dies, new one resumes from DB."""
        task_id = str(uuid.uuid4())

        async with db_pool.acquire() as conn:
            await _cleanup_task(conn, task_id)
            await conn.execute(
                """INSERT INTO tasks (id, title, description, status, risk_level, environment, created_by)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                task_id, "Cross-process resume test", "Test", "pending", "high", "production",
                "00000000-0000-0000-0000-000000000001",
            )

        task = {
            "id": task_id,
            "title": "Cross-process resume test",
            "description": "Test",
            "environment": "production",
            "risk_level": "high",
            "created_by": "00000000-0000-0000-0000-000000000001",
        }

        # Phase 1: First executor starts task, hits approval, persists state
        executor1 = TaskExecutor(db_pool)
        result1 = await executor1.run(task_id, task)
        assert result1["status"] == "awaiting_approval"

        # Verify workflow state was persisted to DB
        async with db_pool.acquire() as conn:
            state_row = await conn.fetchrow(
                "SELECT * FROM workflow_states WHERE task_id = $1 AND status = 'active'",
                task_id,
            )
        assert state_row is not None
        assert state_row["state_type"] in ("plan_approval", "tool_approval")
        assert state_row["current_step"] == 0

        # Phase 2: Simulate service restart — create NEW executor instance
        # _pending_plans is a class-level cache; clear it to simulate cross-process
        executor2 = TaskExecutor(db_pool)
        executor2._pending_plans.pop(task_id, None)  # simulate process boundary

        # Phase 3: Resume from DB state
        result2 = await executor2.run(task_id, task)
        assert result2["success"] is True
        assert result2["result"]["status"] == "completed"

        # Phase 4: Verify events show full flow (approval + completion)
        async with db_pool.acquire() as conn:
            events = await conn.fetch(
                "SELECT event_type, sequence FROM task_events WHERE task_id = $1 ORDER BY sequence",
                task_id,
            )
        event_types = [e["event_type"] for e in events]
        assert "approval.requested" in event_types
        assert "task.completed" in event_types

        # Phase 5: Verify workflow state is cleared after completion
        async with db_pool.acquire() as conn:
            state_after = await conn.fetchrow(
                "SELECT status FROM workflow_states WHERE task_id = $1",
                task_id,
            )
        assert state_after is None or state_after["status"] == "completed"

        async with db_pool.acquire() as conn:
            await _cleanup_task(conn, task_id)

    @pytest.mark.asyncio
    async def test_resume_from_paused_state(self, db_pool):
        """Task paused state persisted in DB; new executor resumes from saved step."""
        task_id = str(uuid.uuid4())

        async with db_pool.acquire() as conn:
            await _cleanup_task(conn, task_id)
            await conn.execute(
                """INSERT INTO tasks (id, title, description, status, risk_level, environment, created_by)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                task_id, "Pause resume test", "Test", "paused", "low", "test",
                "00000000-0000-0000-0000-000000000001",
            )
            # Manually insert paused workflow state (simulates mid-run pause)
            import json
            await conn.execute(
                """INSERT INTO workflow_states
                   (task_id, state_type, current_step, total_steps, plan, tool_calls_log, result_data, status)
                   VALUES ($1, 'paused', 1, 2,
                           $2::jsonb, '[]'::jsonb, '{}'::jsonb, 'active')""",
                task_id,
                json.dumps({
                    "task_id": task_id,
                    "goal": "Pause resume test",
                    "steps": [
                        {"step_number": 1, "tool": "mock.analyze", "input": {"data": ["x"]}, "description": "Analyze", "retry_on_failure": True},
                        {"step_number": 2, "tool": "file.write", "input": {"filename": "test.txt", "content": "test"}, "description": "Write", "retry_on_failure": True},
                    ],
                    "estimated_risk": "low",
                    "requires_approval": False,
                }),
            )

        task = {
            "id": task_id,
            "title": "Pause resume test",
            "description": "Test",
            "environment": "test",
            "risk_level": "low",
            "created_by": "00000000-0000-0000-0000-000000000001",
        }

        # New executor resumes from DB paused state
        executor = TaskExecutor(db_pool)
        executor._pending_plans.pop(task_id, None)
        result = await executor.run(task_id, task)
        assert result["success"] is True
        assert result["result"]["status"] == "completed"

        # Verify workflow state cleared
        async with db_pool.acquire() as conn:
            state_row = await conn.fetchrow(
                "SELECT status FROM workflow_states WHERE task_id = $1",
                task_id,
            )
        assert state_row is None or state_row["status"] == "completed"

        async with db_pool.acquire() as conn:
            await _cleanup_task(conn, task_id)

    @pytest.mark.asyncio
    async def test_no_replanning_on_resume(self, db_pool):
        """Resumed task must NOT call generate_plan again; use saved plan."""
        task_id = str(uuid.uuid4())

        async with db_pool.acquire() as conn:
            await _cleanup_task(conn, task_id)
            await conn.execute(
                """INSERT INTO tasks (id, title, description, status, risk_level, environment, created_by)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                task_id, "No replan test", "Test", "pending", "high", "production",
                "00000000-0000-0000-0000-000000000001",
            )

        task = {
            "id": task_id,
            "title": "No replan test",
            "description": "Test",
            "environment": "production",
            "risk_level": "high",
            "created_by": "00000000-0000-0000-0000-000000000001",
        }

        executor1 = TaskExecutor(db_pool)
        result1 = await executor1.run(task_id, task)
        assert result1["status"] == "awaiting_approval"

        # Count plan.created events before resume
        async with db_pool.acquire() as conn:
            before = await conn.fetchval(
                "SELECT COUNT(*) FROM task_events WHERE task_id = $1 AND event_type = 'plan.created'",
                task_id,
            )
        assert before == 1

        # Resume with new executor
        executor2 = TaskExecutor(db_pool)
        result2 = await executor2.run(task_id, task)
        assert result2["success"] is True

        # Must NOT create a second plan
        async with db_pool.acquire() as conn:
            after = await conn.fetchval(
                "SELECT COUNT(*) FROM task_events WHERE task_id = $1 AND event_type = 'plan.created'",
                task_id,
            )
        assert after == 1, "Resume should not trigger replanning"

        async with db_pool.acquire() as conn:
            await _cleanup_task(conn, task_id)
