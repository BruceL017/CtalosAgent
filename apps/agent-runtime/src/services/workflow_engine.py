"""
WorkflowEngine: Plan generation and execution engine.
Responsible for: plan generation, step-by-step execution, state persistence.
TaskExecutor handles: overall coordination, memory/skill/rollback/eval post-processing.
"""
import json
import time
from typing import Any

import asyncpg

from models.schemas import (
    AgentPlan,
    AgentPlanStep,
    ChatMessage,
    EventType,
    RiskLevel,
    TaskStatus,
)
from services.event_logger import EventLogger
from services.policy_engine import PolicyEngine
from services.provider_router import ProviderRouter
from tools.registry import ToolRegistry
from utils.json_utils import json_dumps


class WorkflowStateStore:
    """Persist and load workflow plan_state to/from PostgreSQL."""

    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool

    async def save_state(
        self,
        task_id: str,
        state_type: str,
        plan: AgentPlan,
        current_step: int,
        tool_calls_log: list[dict[str, Any]],
        result_data: dict[str, Any],
        status: str = "active",
    ) -> None:
        """Save or update workflow state for a task."""
        async with self.db_pool.acquire() as conn:
            # Upsert: delete existing then insert
            await conn.execute(
                "DELETE FROM workflow_states WHERE task_id = $1",
                task_id,
            )
            await conn.execute(
                """
                INSERT INTO workflow_states
                (task_id, state_type, current_step, total_steps, plan, tool_calls_log, result_data, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                task_id,
                state_type,
                current_step,
                len(plan.steps) if plan else 0,
                json_dumps(plan.model_dump() if plan else {}),
                json_dumps(tool_calls_log),
                json_dumps(result_data),
                status,
            )

    async def load_state(self, task_id: str) -> dict[str, Any] | None:
        """Load active workflow state for a task."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM workflow_states WHERE task_id = $1 AND status = 'active' ORDER BY updated_at DESC LIMIT 1",
                task_id,
            )
        if not row:
            return None

        plan_data = row["plan"]
        if isinstance(plan_data, str):
            plan_data = json.loads(plan_data)

        steps = []
        for s in plan_data.get("steps", []):
            steps.append(AgentPlanStep(**s))

        plan = AgentPlan(
            task_id=plan_data.get("task_id", task_id),
            goal=plan_data.get("goal", ""),
            steps=steps,
            estimated_risk=RiskLevel(plan_data.get("estimated_risk", "low")),
            requires_approval=plan_data.get("requires_approval", False),
        )

        return {
            "state_type": row["state_type"],
            "current_step": row["current_step"],
            "total_steps": row["total_steps"],
            "plan": plan,
            "tool_calls_log": row["tool_calls_log"] if isinstance(row["tool_calls_log"], list) else json.loads(row["tool_calls_log"] or "[]"),
            "result_data": row["result_data"] if isinstance(row["result_data"], dict) else json.loads(row["result_data"] or "{}"),
        }

    async def clear_state(self, task_id: str) -> None:
        """Mark workflow state as completed (no longer active)."""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE workflow_states SET status = 'completed', updated_at = NOW() WHERE task_id = $1",
                task_id,
            )


class WorkflowEngine:
    """Generates plans and executes them step by step."""

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        logger: EventLogger,
        provider: ProviderRouter,
        policy: PolicyEngine,
    ):
        self.db_pool = db_pool
        self.logger = logger
        self.provider = provider
        self.policy = policy
        self.state_store = WorkflowStateStore(db_pool)

    # =====================================================
    # Plan Generation
    # =====================================================

    async def generate_plan(
        self,
        task: dict[str, Any],
        skill: dict[str, Any] | None,
        memories: list[dict[str, Any]],
    ) -> AgentPlan:
        """Generate execution plan via LLM with heuristic fallback."""
        title = task.get("title", "")
        description = task.get("description", "")
        env = task.get("environment", "test")

        memory_context = "\n".join([f"- {m['content'][:300]}" for m in memories[:3]])
        skill_context = ""
        if skill:
            skill_content = skill.get("input_schema", {})
            if isinstance(skill_content, str):
                try:
                    skill_content = json.loads(skill_content)
                except Exception:
                    skill_content = {}
            skill_context = f"Skill: {skill['name']}\nSteps: {skill_content.get('steps', [])}\nTools: {skill_content.get('recommended_tools', [])}"

        system_prompt = """You are an enterprise agent planner. Given a task, generate a step-by-step execution plan.
Each step should specify a tool and its input.
Available tools: mock.analyze, file.write, file.read, github.create_issue, github.create_branch, github.create_commit, github.create_pr, lark.write_doc, lark.send_message, supabase.execute_sql, supabase.query, telegram.send, mcp.call_tool.

Respond in JSON format:
{
  "steps": [
    {"step_number": 1, "tool": "tool_name", "input": {...}, "description": "...", "expected_output": "...", "retry_on_failure": true, "max_retries": 3}
  ],
  "estimated_risk": "low|medium|high",
  "requires_approval": false
}"""

        user_prompt = f"""Task: {title}
Description: {description}
Environment: {env}

Relevant Memories:
{memory_context}

{skill_context}

Generate an execution plan."""

        try:
            messages = [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt),
            ]
            response = await self.provider.chat(messages, temperature=0.3)

            try:
                plan_data = json.loads(response.content)
            except json.JSONDecodeError:
                plan_data = self._heuristic_plan(title, description, env)

            steps = []
            for s in plan_data.get("steps", []):
                steps.append(AgentPlanStep(**s))

            if not steps:
                steps = self._heuristic_plan_steps(title, description, env)

            return AgentPlan(
                task_id=task.get("id", ""),
                goal=title,
                steps=steps,
                estimated_risk=RiskLevel(plan_data.get("estimated_risk", "low")),
                requires_approval=plan_data.get("requires_approval", False) or env == "production",
            )

        except Exception:
            steps = self._heuristic_plan_steps(title, description, env)
            return AgentPlan(
                task_id=task.get("id", ""),
                goal=title,
                steps=steps,
                estimated_risk=RiskLevel.MEDIUM if env == "production" else RiskLevel.LOW,
                requires_approval=env == "production",
            )

    def _heuristic_plan(self, title: str, description: str, env: str) -> dict[str, Any]:
        return {
            "steps": self._heuristic_plan_steps(title, description, env),
            "estimated_risk": "medium" if env == "production" else "low",
            "requires_approval": env == "production",
        }

    def _heuristic_plan_steps(self, title: str, description: str, env: str) -> list[AgentPlanStep]:
        t = title.lower()
        d = description.lower()

        if "report" in t or "报告" in t:
            return [
                AgentPlanStep(step_number=1, tool="mock.analyze", input={"data": ["item1", "item2", "item3"]}, description="Analyze data", retry_on_failure=True),
                AgentPlanStep(step_number=2, tool="file.write", input={"filename": f"report_{int(time.time())}.md", "content": f"# {title}\n\n{description}\n\n*Generated by Enterprise Agent*"}, description="Write report file", retry_on_failure=True),
            ]
        elif "issue" in t or "bug" in t:
            return [
                AgentPlanStep(step_number=1, tool="github.create_issue", input={"repo": "enterprise-agent/demo", "title": title, "body": description}, description="Create GitHub issue", retry_on_failure=True),
            ]
        elif "sql" in t or "query" in t or "数据" in t:
            return [
                AgentPlanStep(step_number=1, tool="supabase.query", input={"table": "tasks", "limit": 10}, description="Query database", retry_on_failure=True),
                AgentPlanStep(step_number=2, tool="file.write", input={"filename": f"query_result_{int(time.time())}.txt", "content": f"Query results for: {title}"}, description="Save query results", retry_on_failure=True),
            ]
        elif "lark" in t or "飞书" in t or "文档" in t:
            return [
                AgentPlanStep(step_number=1, tool="mock.analyze", input={"data": [title, description]}, description="Analyze content", retry_on_failure=True),
                AgentPlanStep(step_number=2, tool="lark.write_doc", input={"doc_token": "temp_doc", "content": f"{title}\n\n{description}"}, description="Write to Lark doc", retry_on_failure=True),
            ]
        elif "telegram" in t or "消息" in t:
            return [
                AgentPlanStep(step_number=1, tool="telegram.send", input={"chat_id": "default", "text": f"{title}: {description}"}, description="Send Telegram message", retry_on_failure=True),
            ]
        elif "competitor" in t or "竞品" in t or "调研" in t:
            return [
                AgentPlanStep(step_number=1, tool="mock.analyze", input={"data": ["competitor_a", "competitor_b"]}, description="Analyze competitors", retry_on_failure=True),
                AgentPlanStep(step_number=2, tool="file.write", input={"filename": f"competitor_report_{int(time.time())}.md", "content": f"# Competitor Analysis: {title}\n\n{description}"}, description="Write competitor report", retry_on_failure=True),
                AgentPlanStep(step_number=3, tool="lark.write_doc", input={"doc_token": "report_doc", "content": f"Competitor report for {title}"}, description="Write to Lark", retry_on_failure=True),
            ]
        else:
            return [
                AgentPlanStep(step_number=1, tool="mock.analyze", input={"data": [title, description]}, description="Analyze request", retry_on_failure=True),
                AgentPlanStep(step_number=2, tool="file.write", input={"filename": f"output_{int(time.time())}.md", "content": f"# {title}\n\n{description}\n\n*Generated by Enterprise Agent*"}, description="Generate output", retry_on_failure=True),
            ]

    # =====================================================
    # Plan Execution
    # =====================================================

    async def execute_plan(
        self,
        task_id: str,
        task: dict[str, Any],
        plan: AgentPlan,
        tool_calls_log: list[dict[str, Any]] | None = None,
        result_data: dict[str, Any] | None = None,
        start_from_step: int = 0,
        check_cancelled: Any = None,
        check_paused: Any = None,
    ) -> dict[str, Any]:
        """Execute a plan from a given step. Returns execution result or interruption state."""
        tool_calls_log = tool_calls_log or []
        result_data = result_data or {}
        current_step = start_from_step

        for step in plan.steps[start_from_step:]:
            current_step += 1

            if check_cancelled and await check_cancelled():
                return {
                    "status": "cancelled",
                    "task_id": task_id,
                    "current_step": current_step - 1,
                    "tool_calls_log": tool_calls_log,
                    "result_data": result_data,
                }

            if check_paused and check_paused():
                # Persist state for resume
                await self.state_store.save_state(
                    task_id=task_id,
                    state_type="paused",
                    plan=plan,
                    current_step=current_step - 1,
                    tool_calls_log=tool_calls_log,
                    result_data=result_data,
                )
                return {
                    "status": "paused",
                    "task_id": task_id,
                    "current_step": current_step - 1,
                    "tool_calls_log": tool_calls_log,
                    "result_data": result_data,
                }

            await self.logger.log(task_id, EventType.PLAN_STEP_STARTED, {
                "step_number": step.step_number,
                "tool": step.tool,
                "description": step.description,
                "resumed": start_from_step > 0,
            })

            step_result = await self._execute_step(task_id, task, step, tool_calls_log)
            result_data[f"step_{step.step_number}"] = step_result

            if step_result.get("approval_required"):
                await self.state_store.save_state(
                    task_id=task_id,
                    state_type="tool_approval",
                    plan=plan,
                    current_step=current_step,
                    tool_calls_log=tool_calls_log,
                    result_data=result_data,
                )
                return {
                    "status": "awaiting_approval",
                    "task_id": task_id,
                    "current_step": current_step,
                    "tool_calls_log": tool_calls_log,
                    "result_data": result_data,
                    "pending_tool": step.tool,
                }

            if step_result.get("status") == "failed":
                if step.retry_on_failure:
                    await self.logger.log(task_id, EventType.TASK_RETRYING, {
                        "step": step.step_number,
                        "reason": step_result.get("error"),
                        "retry_count": task.get("retry_count", 0) + 1,
                    })
                    retry_result = await self._execute_step(task_id, task, step, tool_calls_log, is_retry=True)
                    result_data[f"step_{step.step_number}_retry"] = retry_result
                    if retry_result.get("status") == "failed":
                        return {
                            "status": "failed",
                            "task_id": task_id,
                            "error": f"Step {step.step_number} failed after retry: {retry_result.get('error')}",
                            "current_step": current_step,
                            "tool_calls_log": tool_calls_log,
                            "result_data": result_data,
                        }
                else:
                    return {
                        "status": "failed",
                        "task_id": task_id,
                        "error": f"Step {step.step_number} failed: {step_result.get('error')}",
                        "current_step": current_step,
                        "tool_calls_log": tool_calls_log,
                        "result_data": result_data,
                    }

            await self.logger.log(task_id, EventType.PLAN_STEP_COMPLETED, {
                "step_number": step.step_number,
                "tool": step.tool,
                "status": step_result.get("status"),
                "duration_ms": step_result.get("duration_ms"),
            })

        return {
            "status": "completed",
            "task_id": task_id,
            "tool_calls_log": tool_calls_log,
            "result_data": result_data,
            "steps_completed": current_step,
        }

    async def _execute_step(
        self,
        task_id: str,
        task: dict[str, Any],
        step: AgentPlanStep,
        tool_calls_log: list[dict[str, Any]],
        is_retry: bool = False,
    ) -> dict[str, Any]:
        """Execute a single plan step."""
        tool_name = step.tool
        tool_input = step.input

        manifest = ToolRegistry.get(tool_name)
        if not manifest:
            return {"status": "failed", "error": f"Unknown tool: {tool_name}"}

        env = task.get("environment", "test")
        actor_id = str(task.get("created_by", "system"))

        # Policy check
        decision = self.policy.check_tool_permission(
            actor_id=actor_id,
            tool_name=tool_name,
            tool_manifest={
                "risk_level": manifest.risk_level,
                "requires_approval_on": manifest.requires_approval_on,
                "rollback_strategy": manifest.rollback_strategy,
                "estimated_blast_radius": manifest.estimated_blast_radius,
            },
            environment=env,
            operation_type="execute",
        )

        if not decision.allowed:
            return {"status": "failed", "error": f"Permission denied: {decision.reason}"}

        # Approval check for production
        if decision.requires_approval and env == "production":
            await self.logger.log(task_id, EventType.APPROVAL_REQUESTED, {
                "tool": tool_name,
                "reason": decision.reason,
                "policy_mode": decision.mode.value if hasattr(decision.mode, "value") else str(decision.mode),
            })
            if manifest.risk_level == "critical":
                return {
                    "status": "approval_required",
                    "tool": tool_name,
                    "reason": decision.reason,
                }
            # Auto-approve non-critical tools
            await self.logger.log(task_id, EventType.APPROVAL_RESOLVED, {
                "tool": tool_name,
                "status": "approved",
                "approver": "system_auto",
            })

        # Execute tool
        event_id = await self.logger.log(task_id, EventType.TOOL_CALLED, {
            "tool": tool_name,
            "input": tool_input,
            "is_retry": is_retry,
        })

        tool_call_id = await self.logger.log_tool_call(
            task_id=task_id,
            tool_name=tool_name,
            tool_version="1.0.0",
            input_data=tool_input,
            risk_level=manifest.risk_level,
            environment=env,
            event_id=event_id,
        )

        t0 = time.time()
        try:
            handler = ToolRegistry.get_handler(tool_name)
            if handler:
                output = await handler(tool_input)
            else:
                output = {"success": False, "error": "No handler registered"}
        except Exception as e:
            output = {"success": False, "error": str(e)}

        duration_ms = int((time.time() - t0) * 1000)
        status = "success" if output.get("success") else "failed"

        await self.logger.update_tool_call(
            tool_call_id=tool_call_id,
            status=status,
            output=output,
            duration_ms=duration_ms,
            error_message=output.get("error"),
        )

        await self.logger.log(task_id, EventType.TOOL_RESULT, {
            "tool": tool_name,
            "status": status,
            "duration_ms": duration_ms,
            "output_summary": str(output)[:500],
        })

        tool_calls_log.append({
            "tool_name": tool_name,
            "status": status,
            "duration_ms": duration_ms,
            "output": output,
            "error": output.get("error"),
        })

        return {
            "status": status,
            "output": output,
            "duration_ms": duration_ms,
            "tool_call_id": tool_call_id,
        }
