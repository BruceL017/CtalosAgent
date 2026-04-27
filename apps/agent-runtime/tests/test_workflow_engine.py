"""Tests for WorkflowEngine: plan generation, execution, and state persistence."""
import json
import uuid

import asyncpg
import pytest
import pytest_asyncio

from models.schemas import AgentPlan, AgentPlanStep, RiskLevel
from services.event_logger import EventLogger
from services.policy_engine import PolicyEngine
from services.provider_router import ProviderRouter
from services.workflow_engine import WorkflowEngine, WorkflowStateStore


@pytest_asyncio.fixture
async def db_pool():
    pool = await asyncpg.create_pool(
        "postgresql://agent:agent_secret@127.0.0.1:5432/agent_db"
    )
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def workflow(db_pool):
    logger = EventLogger(db_pool)
    provider = ProviderRouter()
    policy = PolicyEngine()
    return WorkflowEngine(db_pool, logger, provider, policy)


SYSTEM_ADMIN_ID = '00000000-0000-0000-0000-000000000001'


async def _create_task(conn, task_id: str, title: str = "Test", env: str = "test") -> None:
    """Insert a minimal task record for FK compliance."""
    await conn.execute(
        """
        INSERT INTO tasks (id, title, description, status, environment, risk_level, created_by)
        VALUES ($1, $2, $3, 'running', $4, 'low', $5)
        ON CONFLICT (id) DO NOTHING
        """,
        task_id, title, "Test description", env, SYSTEM_ADMIN_ID,
    )


async def _cleanup_task(conn, task_id: str):
    """Delete task and related records in FK-safe order."""
    await conn.execute("DELETE FROM tool_calls WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM task_state_transitions WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM task_events WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM approvals WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM rollback_plans WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM artifacts WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM memories WHERE source_task_id = $1", task_id)
    await conn.execute("DELETE FROM subagents WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)
    await conn.execute("DELETE FROM workflow_states WHERE task_id = $1", task_id)


class TestWorkflowStateStore:
    @pytest.mark.asyncio
    async def test_save_and_load_state(self, db_pool):
        store = WorkflowStateStore(db_pool)
        task_id = str(uuid.uuid4())
        async with db_pool.acquire() as conn:
            await _create_task(conn, task_id)

        plan = AgentPlan(
            task_id=task_id,
            goal="Test goal",
            steps=[
                AgentPlanStep(step_number=1, tool="mock.analyze", input={"data": [1, 2]}, description="Analyze", retry_on_failure=True),
            ],
            estimated_risk=RiskLevel.LOW,
            requires_approval=False,
        )

        await store.save_state(
            task_id=task_id,
            state_type="paused",
            plan=plan,
            current_step=1,
            tool_calls_log=[{"tool_name": "mock.analyze", "status": "success"}],
            result_data={"step_1": {"status": "success"}},
        )

        loaded = await store.load_state(task_id)
        assert loaded is not None
        assert loaded["state_type"] == "paused"
        assert loaded["current_step"] == 1
        assert loaded["total_steps"] == 1
        assert isinstance(loaded["plan"], AgentPlan)
        assert loaded["plan"].goal == "Test goal"
        assert len(loaded["tool_calls_log"]) == 1
        assert loaded["result_data"]["step_1"]["status"] == "success"

        await store.clear_state(task_id)
        cleared = await store.load_state(task_id)
        assert cleared is None

        async with db_pool.acquire() as conn:
            await _cleanup_task(conn, task_id)

    @pytest.mark.asyncio
    async def test_load_nonexistent_state(self, db_pool):
        store = WorkflowStateStore(db_pool)
        loaded = await store.load_state(str(uuid.uuid4()))
        assert loaded is None


class TestWorkflowEngine:
    @pytest.mark.asyncio
    async def test_generate_plan_heuristic(self, workflow):
        task = {
            "id": str(uuid.uuid4()),
            "title": "Generate monthly report",
            "description": "Create a report for Q1",
            "environment": "test",
        }
        plan = await workflow.generate_plan(task, skill=None, memories=[])
        assert isinstance(plan, AgentPlan)
        assert plan.goal == "Generate monthly report"
        assert len(plan.steps) >= 1
        assert plan.estimated_risk == RiskLevel.LOW

    @pytest.mark.asyncio
    async def test_generate_plan_production_requires_approval(self, workflow):
        task = {
            "id": str(uuid.uuid4()),
            "title": "Generate report",
            "description": "Create report",
            "environment": "production",
        }
        plan = await workflow.generate_plan(task, skill=None, memories=[])
        assert plan.requires_approval is True

    @pytest.mark.asyncio
    async def test_execute_plan_success(self, workflow, db_pool):
        task_id = str(uuid.uuid4())
        async with db_pool.acquire() as conn:
            await _create_task(conn, task_id)
        task = {
            "id": task_id,
            "title": "Test task",
            "description": "Test description",
            "environment": "test",
            "created_by": "system",
        }
        plan = AgentPlan(
            task_id=task_id,
            goal="Test",
            steps=[
                AgentPlanStep(step_number=1, tool="mock.analyze", input={"data": [1, 2, 3]}, description="Analyze", retry_on_failure=True),
            ],
            estimated_risk=RiskLevel.LOW,
            requires_approval=False,
        )

        result = await workflow.execute_plan(task_id=task_id, task=task, plan=plan)
        assert result["status"] == "completed"
        assert result["steps_completed"] == 1
        assert len(result["tool_calls_log"]) == 1
        assert result["tool_calls_log"][0]["status"] == "success"
        assert "step_1" in result["result_data"]

        async with db_pool.acquire() as conn:
            await _cleanup_task(conn, task_id)

    @pytest.mark.asyncio
    async def test_execute_plan_with_retry(self, workflow, db_pool):
        """Test that a failing step with retry_on_failure=True gets retried."""
        task_id = str(uuid.uuid4())
        async with db_pool.acquire() as conn:
            await _create_task(conn, task_id)
        task = {
            "id": task_id,
            "title": "Test retry",
            "description": "Test",
            "environment": "test",
            "created_by": "system",
        }
        plan = AgentPlan(
            task_id=task_id,
            goal="Test retry",
            steps=[
                AgentPlanStep(step_number=1, tool="unknown_tool_that_does_not_exist", input={}, description="Fail", retry_on_failure=True),
            ],
            estimated_risk=RiskLevel.LOW,
            requires_approval=False,
        )

        result = await workflow.execute_plan(task_id=task_id, task=task, plan=plan)
        # Should fail after retry because unknown tool fails both times
        assert result["status"] == "failed"
        assert "Unknown tool" in result.get("error", "")

        async with db_pool.acquire() as conn:
            await _cleanup_task(conn, task_id)

    @pytest.mark.asyncio
    async def test_execute_plan_resumes_from_step(self, workflow, db_pool):
        task_id = str(uuid.uuid4())
        async with db_pool.acquire() as conn:
            await _create_task(conn, task_id)
        task = {
            "id": task_id,
            "title": "Test resume",
            "description": "Test",
            "environment": "test",
            "created_by": "system",
        }
        plan = AgentPlan(
            task_id=task_id,
            goal="Test resume",
            steps=[
                AgentPlanStep(step_number=1, tool="mock.analyze", input={"data": [1]}, description="Step 1", retry_on_failure=True),
                AgentPlanStep(step_number=2, tool="mock.analyze", input={"data": [2]}, description="Step 2", retry_on_failure=True),
            ],
            estimated_risk=RiskLevel.LOW,
            requires_approval=False,
        )

        # Pre-populate tool_calls_log and result_data as if step 1 completed
        tool_calls_log = [{"tool_name": "mock.analyze", "status": "success"}]
        result_data = {"step_1": {"status": "success"}}

        result = await workflow.execute_plan(
            task_id=task_id,
            task=task,
            plan=plan,
            tool_calls_log=tool_calls_log,
            result_data=result_data,
            start_from_step=1,
        )

        assert result["status"] == "completed"
        assert result["steps_completed"] == 2
        assert len(result["tool_calls_log"]) == 2

        async with db_pool.acquire() as conn:
            await _cleanup_task(conn, task_id)

    @pytest.mark.asyncio
    async def test_state_persistence_across_restart(self, workflow, db_pool):
        """Simulate service restart by saving state, clearing memory, then loading from DB."""
        task_id = str(uuid.uuid4())
        async with db_pool.acquire() as conn:
            await _create_task(conn, task_id)
        plan = AgentPlan(
            task_id=task_id,
            goal="Restart test",
            steps=[
                AgentPlanStep(step_number=1, tool="mock.analyze", input={}, description="Step 1", retry_on_failure=True),
                AgentPlanStep(step_number=2, tool="mock.analyze", input={"data": [2]}, description="Step 2", retry_on_failure=True),
            ],
            estimated_risk=RiskLevel.LOW,
            requires_approval=False,
        )

        await workflow.state_store.save_state(
            task_id=task_id,
            state_type="paused",
            plan=plan,
            current_step=1,
            tool_calls_log=[{"tool_name": "mock.analyze", "status": "success"}],
            result_data={"step_1": {"status": "success"}},
        )

        # Simulate new process: create fresh WorkflowEngine
        fresh_workflow = WorkflowEngine(db_pool, workflow.logger, workflow.provider, workflow.policy)
        loaded = await fresh_workflow.state_store.load_state(task_id)

        assert loaded is not None
        assert loaded["current_step"] == 1
        assert loaded["plan"].steps[1].tool == "mock.analyze"

        # Resume execution from loaded state
        task = {
            "id": task_id,
            "title": "Restart test",
            "description": "Test",
            "environment": "test",
            "created_by": SYSTEM_ADMIN_ID,
        }
        result = await fresh_workflow.execute_plan(
            task_id=task_id,
            task=task,
            plan=loaded["plan"],
            tool_calls_log=loaded["tool_calls_log"],
            result_data=loaded["result_data"],
            start_from_step=loaded["current_step"],
        )
        assert result["status"] == "completed", f"Expected completed but got: {result}"

        async with db_pool.acquire() as conn:
            await _cleanup_task(conn, task_id)
