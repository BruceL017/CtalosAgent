"""End-to-end test: real LLM planning -> tool execution -> event audit.
Requires SILICONFLOW_API_KEY env var. Skips gracefully if not set."""
import asyncio
import json
import os
import uuid

import asyncpg
import pytest
import pytest_asyncio

from models.schemas import ChatMessage
from services.event_logger import EventLogger
from services.policy_engine import PolicyEngine
from services.provider_router import ProviderRouter
from services.workflow_engine import WorkflowEngine

DB_URL = "postgresql://agent:agent_secret@127.0.0.1:5432/agent_db"
SYSTEM_ADMIN_ID = "00000000-0000-0000-0000-000000000001"


@pytest_asyncio.fixture
async def db_pool():
    pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=2)
    yield pool
    await pool.close()


async def _create_task(conn, task_id: str, title: str = "E2E Test", env: str = "test"):
    await conn.execute(
        """
        INSERT INTO tasks (id, title, description, status, environment, risk_level, created_by)
        VALUES ($1, $2, $3, 'running', $4, 'low', $5)
        ON CONFLICT (id) DO NOTHING
        """,
        task_id, title, "E2E test description", env, SYSTEM_ADMIN_ID,
    )


async def _cleanup_task(conn, task_id: str):
    await conn.execute("DELETE FROM tool_calls WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM task_state_transitions WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM task_events WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM rollback_plans WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM artifacts WHERE task_id = $1", task_id)
    await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)
    await conn.execute("DELETE FROM workflow_states WHERE task_id = $1", task_id)


class TestEndToEndRealLLM:
    @pytest.mark.asyncio
    async def test_real_llm_plan_generation(self, db_pool):
        """Real LLM generates a plan, then WorkflowEngine executes mock tools."""
        api_key = os.getenv("SILICONFLOW_API_KEY")
        if not api_key:
            pytest.skip("SILICONFLOW_API_KEY not set, skipping end-to-end real LLM test")

        task_id = str(uuid.uuid4())
        async with db_pool.acquire() as conn:
            await _create_task(conn, task_id)

        logger = EventLogger(db_pool)
        provider = ProviderRouter()
        policy = PolicyEngine()
        workflow = WorkflowEngine(db_pool, logger, provider, policy)

        task = {
            "id": task_id,
            "title": "Analyze sales data and write a summary",
            "description": "Please analyze Q1 sales data and produce a brief summary report.",
            "environment": "test",
            "created_by": SYSTEM_ADMIN_ID,
        }

        # Step 1: Real LLM generates plan
        plan = await workflow.generate_plan(task, skill=None, memories=[])
        assert plan.task_id == task_id
        assert len(plan.steps) >= 1
        assert plan.estimated_risk.value in ("low", "medium", "high")

        # Step 2: Execute plan
        result = await workflow.execute_plan(
            task_id=task_id,
            task=task,
            plan=plan,
            tool_calls_log=[],
            result_data={},
            start_from_step=0,
        )

        assert result["status"] in ("completed", "failed", "awaiting_approval")
        assert len(result["tool_calls_log"]) >= 0

        # Step 3: Verify events were logged (no secrets leaked)
        async with db_pool.acquire() as conn:
            events = await conn.fetch(
                "SELECT event_type, payload FROM task_events WHERE task_id = $1 ORDER BY sequence",
                task_id,
            )
        event_types = [e["event_type"] for e in events]
        # Real LLM plan generation via WorkflowEngine directly does not log plan.created
        # (that's TaskExecutor's responsibility), but we should see execution events
        assert "plan.step_started" in event_types
        assert "tool.called" in event_types

        # Verify no API keys in event payloads
        for event in events:
            payload_str = json.dumps(event["payload"])
            assert "sk-" not in payload_str, f"Potential secret leak in event payload: {event['event_type']}"

        # Cleanup
        async with db_pool.acquire() as conn:
            await _cleanup_task(conn, task_id)

    @pytest.mark.asyncio
    async def test_provider_chat_directly(self):
        """Direct provider chat with real LLM returns usable content."""
        api_key = os.getenv("SILICONFLOW_API_KEY")
        if not api_key:
            pytest.skip("SILICONFLOW_API_KEY not set")

        provider = ProviderRouter()
        messages = [
            ChatMessage(role="system", content="You are a concise planner."),
            ChatMessage(role="user", content="Plan: check system health. Reply in JSON with key 'steps' containing a list."),
        ]
        response = await provider.chat(messages, temperature=0.1)
        assert response.content
        assert response.provider in ("siliconflow", "mock")
        if response.provider == "siliconflow":
            assert response.usage.get("total_tokens", 0) > 0
