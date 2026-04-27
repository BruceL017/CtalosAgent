"""Tests for EvalService: multi-dimensional task scoring."""
import uuid

import asyncpg
import pytest
import pytest_asyncio

from models.schemas import AgentPlan, AgentPlanStep, RiskLevel
from services.eval_service import EvalService

DB_URL = "postgresql://agent:agent_secret@127.0.0.1:5432/agent_db"


@pytest_asyncio.fixture
async def db_pool():
    pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=2)
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def eval_service(db_pool):
    return EvalService(db_pool)


async def _create_task(conn, task_id: str) -> None:
    await conn.execute(
        """
        INSERT INTO tasks (id, title, description, status, environment, risk_level, created_by)
        VALUES ($1, 'Eval Test', 'Test', 'completed', 'test', 'low', '00000000-0000-0000-0000-000000000001')
        ON CONFLICT (id) DO NOTHING
        """,
        task_id,
    )


class TestEvalService:
    @pytest.mark.asyncio
    async def test_record_eval_success(self, eval_service, db_pool):
        task_id = str(uuid.uuid4())
        async with db_pool.acquire() as conn:
            await _create_task(conn, task_id)

        task = {"title": "Test", "environment": "test", "risk_level": "low"}
        plan = AgentPlan(
            task_id=task_id,
            goal="Test",
            steps=[AgentPlanStep(step_number=1, tool="mock.analyze", input={}, description="Step 1", retry_on_failure=True)],
            estimated_risk=RiskLevel.LOW,
            requires_approval=False,
        )
        tool_calls_log = [
            {"tool_name": "mock.analyze", "status": "success", "duration_ms": 200},
        ]

        result = await eval_service.record_eval(
            task_id=task_id,
            task=task,
            plan=plan,
            tool_calls_log=tool_calls_log,
            result_data={"step_1": {"status": "success"}},
            memory_ids=["m1", "m2"],
        )

        assert result["score"] is not None
        assert 0 <= result["score"] <= 1
        assert result["eval_id"] is not None
        assert "metrics" in result
        assert result["metrics"]["tool_success_rate"] == 1.0
        assert "feedback" in result

        # Verify DB persistence
        db_result = await eval_service.get_task_eval(task_id)
        assert db_result is not None
        assert float(db_result["score"]) == result["score"]

        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM eval_runs WHERE task_id = $1", task_id)
            await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)

    @pytest.mark.asyncio
    async def test_record_eval_with_failures(self, eval_service, db_pool):
        task_id = str(uuid.uuid4())
        async with db_pool.acquire() as conn:
            await _create_task(conn, task_id)

        task = {"title": "Test", "environment": "production", "risk_level": "high"}
        plan = AgentPlan(
            task_id=task_id,
            goal="Test",
            steps=[
                AgentPlanStep(step_number=1, tool="mock.analyze", input={}, description="", retry_on_failure=False),
            ],
            estimated_risk=RiskLevel.HIGH,
            requires_approval=True,
        )
        tool_calls_log = [
            {"tool_name": "mock.analyze", "status": "failed", "duration_ms": 50},
        ]

        result = await eval_service.record_eval(
            task_id=task_id,
            task=task,
            plan=plan,
            tool_calls_log=tool_calls_log,
            result_data={},
            memory_ids=[],
        )

        assert result["score"] < 0.8
        assert result["metrics"]["tool_success_rate"] == 0.0
        assert result["metrics"]["risk_compliance"] <= 0.8
        assert "成功率偏低" in result["feedback"] or "low" in result["feedback"].lower()

        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM eval_runs WHERE task_id = $1", task_id)
            await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)

    @pytest.mark.asyncio
    async def test_list_evals(self, eval_service, db_pool):
        task_id = str(uuid.uuid4())
        async with db_pool.acquire() as conn:
            await _create_task(conn, task_id)

        task = {"title": "Test", "environment": "test", "risk_level": "low"}
        plan = AgentPlan(task_id=task_id, goal="Test", steps=[], estimated_risk=RiskLevel.LOW, requires_approval=False)

        await eval_service.record_eval(
            task_id=task_id, task=task, plan=plan,
            tool_calls_log=[], result_data={}, memory_ids=[],
        )

        results = await eval_service.list_evals(task_id=task_id, limit=10)
        assert len(results) >= 1
        assert results[0]["task_id"] == task_id

        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM eval_runs WHERE task_id = $1", task_id)
            await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)
