"""Test approval-resume execution flow, pause/resume, cancel, and rollback.
These tests use mock provider to ensure deterministic state machine behavior.
"""
import asyncio
import os
import uuid
import pytest
import pytest_asyncio
import asyncpg

from services.task_executor import TaskExecutor

# Force mock provider for deterministic state machine tests
os.environ["DEFAULT_PROVIDER"] = "mock"
for key in ["SILICONFLOW_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "ZHIPU_API_KEY", "MOONSHOT_API_KEY", "GOOGLE_API_KEY"]:
    os.environ.pop(key, None)


DB_URL = "postgresql://agent:agent_secret@localhost:5432/agent_db"


async def _cleanup_task(conn, task_id: str):
    """Delete all related records for a task in FK-safe order."""
    await conn.execute("DELETE FROM tool_calls WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM task_state_transitions WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM task_events WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM approvals WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM rollback_plans WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM artifacts WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM memories WHERE source_task_id = $1", task_id)
    await conn.execute("DELETE FROM subagents WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)


@pytest_asyncio.fixture
async def db_pool():
    pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=2)
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def executor(db_pool):
    return TaskExecutor(db_pool)


@pytest.mark.asyncio
async def test_production_task_awaits_approval_and_creates_record(db_pool, executor):
    """Production task should enter awaiting_approval state and create approvals record."""
    task_id = str(uuid.uuid4())

    async with db_pool.acquire() as conn:
        await _cleanup_task(conn, task_id)
        await conn.execute(
            "INSERT INTO tasks (id, title, description, status, risk_level, environment, created_by) VALUES ($1, $2, $3, $4, $5, $6, $7)",
            task_id, "Production approval test", "Test", "pending", "high", "production",
            "00000000-0000-0000-0000-000000000001",
        )

    task = {
        "id": task_id,
        "title": "Production approval test",
        "description": "Test",
        "environment": "production",
        "risk_level": "high",
        "created_by": "00000000-0000-0000-0000-000000000001",
    }

    result = await executor.run(task_id, task)
    assert result["status"] == "awaiting_approval"
    assert "approval_id" in result
    assert task_id in executor._pending_plans
    assert "plan" in executor._pending_plans[task_id]

    # Verify approval record exists in DB
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM approvals WHERE task_id = $1", task_id)
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    assert rows[0]["action_type"] == "plan_execution"
    assert rows[0]["plan_state"] is not None

    # Simulate approval by resuming
    result2 = await executor.run(task_id, task)
    assert result2["success"] is True
    assert result2["result"]["status"] == "completed"

    async with db_pool.acquire() as conn:
        await _cleanup_task(conn, task_id)


@pytest.mark.asyncio
async def test_test_env_auto_approves(db_pool, executor):
    """Test environment should auto-approve and complete."""
    task_id = str(uuid.uuid4())

    async with db_pool.acquire() as conn:
        await _cleanup_task(conn, task_id)
        await conn.execute(
            "INSERT INTO tasks (id, title, description, status, risk_level, environment, created_by) VALUES ($1, $2, $3, $4, $5, $6, $7)",
            task_id, "Auto approve test", "Test", "pending", "low", "test",
            "00000000-0000-0000-0000-000000000001",
        )

    task = {
        "id": task_id,
        "title": "Auto approve test",
        "description": "Test",
        "environment": "test",
        "risk_level": "low",
        "created_by": "00000000-0000-0000-0000-000000000001",
    }

    result = await executor.run(task_id, task)
    assert result["success"] is True
    assert result["result"]["status"] == "completed"

    async with db_pool.acquire() as conn:
        await _cleanup_task(conn, task_id)


@pytest.mark.asyncio
async def test_multi_approval_resume(db_pool, executor):
    """Multiple approval points in a single task should each resume correctly."""
    task_id = str(uuid.uuid4())

    async with db_pool.acquire() as conn:
        await _cleanup_task(conn, task_id)
        await conn.execute(
            "INSERT INTO tasks (id, title, description, status, risk_level, environment, created_by) VALUES ($1, $2, $3, $4, $5, $6, $7)",
            task_id, "Multi approval test", "Test", "pending", "high", "production",
            "00000000-0000-0000-0000-000000000001",
        )

    task = {
        "id": task_id,
        "title": "Multi approval test",
        "description": "Test",
        "environment": "production",
        "risk_level": "high",
        "created_by": "00000000-0000-0000-0000-000000000001",
    }

    result = await executor.run(task_id, task)
    assert result["status"] == "awaiting_approval"
    assert task_id in executor._pending_plans
    pending1 = executor._pending_plans[task_id]
    assert pending1["current_step"] == 0

    # Resume after first approval
    result2 = await executor.run(task_id, task)
    assert result2["success"] is True
    assert result2["result"]["status"] == "completed"

    # Verify events show full flow including approval
    async with db_pool.acquire() as conn:
        events = await conn.fetch(
            "SELECT event_type FROM task_events WHERE task_id = $1 ORDER BY sequence",
            task_id,
        )
    event_types = [e["event_type"] for e in events]
    assert "approval.requested" in event_types
    assert "task.completed" in event_types

    async with db_pool.acquire() as conn:
        await _cleanup_task(conn, task_id)


@pytest.mark.asyncio
async def test_cancel_task(db_pool, executor):
    """Task should be cancellable."""
    task_id = str(uuid.uuid4())

    async with db_pool.acquire() as conn:
        await _cleanup_task(conn, task_id)
        await conn.execute(
            "INSERT INTO tasks (id, title, description, status, risk_level, environment, created_by) VALUES ($1, $2, $3, $4, $5, $6, $7)",
            task_id, "Cancel test", "Test", "pending", "low", "test",
            "00000000-0000-0000-0000-000000000001",
        )

    task = {
        "id": task_id,
        "title": "Cancel test",
        "description": "Test",
        "environment": "test",
        "risk_level": "low",
        "created_by": "00000000-0000-0000-0000-000000000001",
    }

    # Start task in background, then cancel
    run_task = asyncio.create_task(executor.run(task_id, task))
    await asyncio.sleep(0.05)
    cancel_result = await executor.cancel(task_id)
    assert cancel_result["status"] == "cancelled"

    try:
        await asyncio.wait_for(run_task, timeout=2.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT status FROM tasks WHERE id = $1", task_id)
    assert row["status"] == "cancelled"

    async with db_pool.acquire() as conn:
        await _cleanup_task(conn, task_id)


@pytest.mark.asyncio
async def test_approval_record_written_with_plan_state(db_pool, executor):
    """Approval records must include plan_state for audit and resume integrity."""
    task_id = str(uuid.uuid4())

    async with db_pool.acquire() as conn:
        await _cleanup_task(conn, task_id)
        await conn.execute(
            "INSERT INTO tasks (id, title, description, status, risk_level, environment, created_by) VALUES ($1, $2, $3, $4, $5, $6, $7)",
            task_id, "Plan state test", "Test", "pending", "high", "production",
            "00000000-0000-0000-0000-000000000001",
        )

    task = {
        "id": task_id,
        "title": "Plan state test",
        "description": "Test",
        "environment": "production",
        "risk_level": "high",
        "created_by": "00000000-0000-0000-0000-000000000001",
    }

    result = await executor.run(task_id, task)
    assert result["status"] == "awaiting_approval"

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM approvals WHERE task_id = $1", task_id)
    assert row is not None
    assert row["plan_state"] is not None
    plan_state = row["plan_state"]
    assert "current_step" in plan_state
    assert "total_steps" in plan_state
    assert "step_tools" in plan_state

    # Resume and complete
    result2 = await executor.run(task_id, task)
    assert result2["success"] is True

    async with db_pool.acquire() as conn:
        await _cleanup_task(conn, task_id)
