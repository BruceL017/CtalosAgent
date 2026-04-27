"""
Task Executor: Enterprise Agent Run State Machine
States: pending -> planning -> awaiting_approval -> approved -> running
        -> paused -> resumed -> retrying -> completed / failed / cancelled
        -> rolling_back -> rolled_back

Each transition is logged to task_events.
Supports: plan, tool_use, tool_result, memory_update, skill_update, eval, final
         failure, retry, pause, resume, cancel

WorkflowEngine handles: plan generation, step execution, state persistence.
TaskExecutor handles: overall coordination, memory/skill/rollback/eval post-processing.
"""
import asyncio
import json
import time
from typing import Any

import asyncpg

from models.schemas import (
    AgentPlan,
    EventType,
    RiskLevel,
    TaskStatus,
)
from services.event_logger import EventLogger
from services.memory_service import MemoryService
from services.policy_engine import PolicyEngine
from services.provider_router import ProviderRouter
from services.rollback_service import RollbackService
from services.skill_service import SkillService
from services.subagent_manager import SubagentManager
from services.eval_service import EvalService
from services.workflow_engine import WorkflowEngine
from utils.json_utils import json_dumps


class TaskExecutor:
    _running_tasks: dict[str, asyncio.Task] = {}
    _paused_tasks: dict[str, dict[str, Any]] = {}
    _pending_plans: dict[str, dict[str, Any]] = {}  # task_id -> {plan, current_step, tool_calls_log, result_data}

    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.logger = EventLogger(db_pool)
        self.memory = MemoryService(db_pool)
        self.skill = SkillService(db_pool, ProviderRouter())
        self.policy = PolicyEngine()
        self.rollback = RollbackService(db_pool)
        self.subagent = SubagentManager(db_pool, ProviderRouter())
        self.provider = ProviderRouter()
        self.workflow = WorkflowEngine(db_pool, self.logger, self.provider, self.policy)
        self.eval_service = EvalService(db_pool)

    async def run(self, task_id: str, task: dict[str, Any]) -> dict[str, Any]:
        """Main entry: start or resume a task. Checks memory, DB, then falls back to fresh execution."""
        # 1. Resume from in-memory pending plan (after approval in same process)
        if task_id in self._pending_plans:
            pending = self._pending_plans.pop(task_id)
            task_future = asyncio.create_task(self._resume_with_state(task_id, task, pending))
            self._running_tasks[task_id] = task_future
            try:
                return await task_future
            finally:
                self._running_tasks.pop(task_id, None)

        # 2. Resume from DB persisted state (after service restart)
        db_state = await self.workflow.state_store.load_state(task_id)
        if db_state and db_state["state_type"] in ("paused", "tool_approval", "plan_approval"):
            pending = {
                "plan": db_state["plan"],
                "current_step": db_state["current_step"],
                "tool_calls_log": db_state["tool_calls_log"],
                "result_data": db_state["result_data"],
            }
            task_future = asyncio.create_task(self._resume_with_state(task_id, task, pending))
            self._running_tasks[task_id] = task_future
            try:
                return await task_future
            finally:
                self._running_tasks.pop(task_id, None)

        # 3. Fresh execution
        task_future = asyncio.create_task(self._execute_task(task_id, task))
        self._running_tasks[task_id] = task_future
        try:
            return await task_future
        finally:
            self._running_tasks.pop(task_id, None)

    async def _execute_task(self, task_id: str, task: dict[str, Any]) -> dict[str, Any]:
        start_time = time.time()
        tool_calls_log: list[dict[str, Any]] = []

        try:
            await self._transition(task_id, TaskStatus.PENDING, TaskStatus.PLANNING, "executor")

            # === Step 1: task.created ===
            await self.logger.log(task_id, EventType.TASK_CREATED, {
                "task_title": task.get("title"),
                "risk_level": task.get("risk_level", "low"),
                "environment": task.get("environment", "test"),
            })

            # === Step 2: Load Skill ===
            skill = await self.skill.get_skill(task.get("skill_id"))
            if skill:
                await self.logger.log(task_id, EventType.SKILL_USED, {
                    "skill_id": skill["id"],
                    "skill_name": skill["name"],
                    "version": skill["current_version"],
                })

            # === Step 3: Retrieve Memories ===
            session_id = task.get("session_id")
            memory_results = await self.memory.retrieve_for_task(
                task_id=task_id,
                session_id=session_id,
                query=task.get("title", ""),
            )
            memories = []
            for scope, scoped_memories in memory_results.items():
                memories.extend(scoped_memories)

            await self.logger.log(task_id, EventType.MEMORY_USED, {
                "memory_count": len(memories),
                "memory_ids": [m["id"] for m in memories],
                "memory_snippets": [m["content"][:200] for m in memories],
                "scopes": {k: len(v) for k, v in memory_results.items()},
            })

            # === Step 4: Generate Plan via WorkflowEngine ===
            plan = await self.workflow.generate_plan(task, skill, memories)
            await self.logger.log(task_id, EventType.PLAN_CREATED, {
                "steps": [s.model_dump() for s in plan.steps],
                "estimated_risk": plan.estimated_risk.value,
                "requires_approval": plan.requires_approval,
            })

            # Plan-level approval check
            env = task.get("environment", "test")
            if plan.requires_approval and env != "test":
                await self._transition(task_id, TaskStatus.PLANNING, TaskStatus.AWAITING_APPROVAL, "policy_engine")
                await self.logger.log(task_id, EventType.APPROVAL_REQUESTED, {
                    "reason": f"Plan risk level: {plan.estimated_risk.value}",
                    "steps": [s.tool for s in plan.steps],
                })
                # Persist state for resume after approval
                await self.workflow.state_store.save_state(
                    task_id=task_id,
                    state_type="plan_approval",
                    plan=plan,
                    current_step=0,
                    tool_calls_log=tool_calls_log,
                    result_data={},
                )
                pending_state = {
                    "plan": plan,
                    "current_step": 0,
                    "tool_calls_log": tool_calls_log,
                    "result_data": {},
                }
                self._pending_plans[task_id] = pending_state
                approval_id = await self._create_approval_record(
                    task_id=task_id,
                    action_type="plan_execution",
                    reason=f"Plan requires approval: risk={plan.estimated_risk.value}, steps={[s.tool for s in plan.steps]}",
                    plan_state={
                        "current_step": 0,
                        "total_steps": len(plan.steps),
                        "step_tools": [s.tool for s in plan.steps],
                    },
                )
                await self.logger.log(task_id, EventType.APPROVAL_REQUESTED, {
                    "approval_id": approval_id,
                    "reason": f"Plan risk level: {plan.estimated_risk.value}",
                    "steps": [s.tool for s in plan.steps],
                })
                return {"success": True, "task_id": task_id, "status": "awaiting_approval", "message": "Waiting for approval", "approval_id": approval_id}

            await self._transition(task_id, TaskStatus.PLANNING, TaskStatus.RUNNING, "executor")

            # === Step 5: Execute Plan via WorkflowEngine ===
            exec_result = await self.workflow.execute_plan(
                task_id=task_id,
                task=task,
                plan=plan,
                tool_calls_log=tool_calls_log,
                result_data={},
                start_from_step=0,
                check_cancelled=lambda: self._is_cancelled(task_id),
                check_paused=lambda: task_id in self._paused_tasks,
            )

            return await self._finalize_execution(task_id, task, plan, exec_result, start_time)

        except Exception as e:
            error_msg = str(e)
            await self._transition(task_id, TaskStatus.PLANNING, TaskStatus.FAILED, "executor")
            await self._update_task(task_id, TaskStatus.FAILED, {}, error_msg)
            await self.logger.log(task_id, EventType.TASK_FAILED, {"error": error_msg, "phase": "execution"})
            return {"success": False, "task_id": task_id, "error": error_msg}

    async def _resume_with_state(self, task_id: str, task: dict[str, Any], pending: dict[str, Any]) -> dict[str, Any]:
        """Resume execution from a saved plan state (memory or DB)."""
        start_time = time.time()
        plan: AgentPlan = pending["plan"]
        tool_calls_log: list[dict[str, Any]] = pending.get("tool_calls_log", [])
        result_data: dict[str, Any] = pending.get("result_data", {})
        current_step = pending.get("current_step", 0)

        await self._transition(task_id, TaskStatus.APPROVED, TaskStatus.RUNNING, "executor")
        await self.logger.log(task_id, EventType.TASK_STATE_CHANGED, {
            "from_state": "approved",
            "to_state": "running",
            "triggered_by": "approval_resolved",
            "reason": "Resuming from saved plan state",
        })

        try:
            exec_result = await self.workflow.execute_plan(
                task_id=task_id,
                task=task,
                plan=plan,
                tool_calls_log=tool_calls_log,
                result_data=result_data,
                start_from_step=current_step,
                check_cancelled=lambda: self._is_cancelled(task_id),
                check_paused=lambda: task_id in self._paused_tasks,
            )

            return await self._finalize_execution(task_id, task, plan, exec_result, start_time)

        except Exception as e:
            error_msg = str(e)
            await self._transition(task_id, TaskStatus.RUNNING, TaskStatus.FAILED, "executor")
            await self._update_task(task_id, TaskStatus.FAILED, {}, error_msg)
            await self.logger.log(task_id, EventType.TASK_FAILED, {"error": error_msg, "phase": "execution"})
            return {"success": False, "task_id": task_id, "error": error_msg}

    async def _finalize_execution(
        self,
        task_id: str,
        task: dict[str, Any],
        plan: AgentPlan,
        exec_result: dict[str, Any],
        start_time: float,
    ) -> dict[str, Any]:
        """Handle post-execution: cancel, pause, approval, fail, or complete with artifact/memory/skill/eval."""
        tool_calls_log: list[dict[str, Any]] = exec_result.get("tool_calls_log", [])
        result_data: dict[str, Any] = exec_result.get("result_data", {})

        status = exec_result.get("status")

        if status == "cancelled":
            await self._transition(task_id, TaskStatus.RUNNING, TaskStatus.CANCELLED, "user")
            await self.logger.log(task_id, EventType.TASK_CANCELLED, {"reason": "User cancelled"})
            await self.workflow.state_store.clear_state(task_id)
            return {"success": False, "task_id": task_id, "status": "cancelled"}

        if status == "paused":
            await self._update_task_status(task_id, "paused")
            await self.logger.log(task_id, EventType.TASK_STATE_CHANGED, {
                "from_state": "running",
                "to_state": "paused",
                "triggered_by": "user",
            })
            return {"success": True, "task_id": task_id, "status": "paused"}

        if status == "awaiting_approval":
            await self._transition(task_id, TaskStatus.RUNNING, TaskStatus.AWAITING_APPROVAL, "policy_engine")
            pending_tool = exec_result.get("pending_tool", "unknown")
            approval_id = await self._create_approval_record(
                task_id=task_id,
                action_type="tool_execution",
                reason=f"Tool {pending_tool} requires approval in {task.get('environment', 'test')} environment",
                plan_state={
                    "current_step": exec_result.get("current_step", 0),
                    "total_steps": len(plan.steps),
                    "pending_tool": pending_tool,
                },
            )
            # Also keep in memory for same-process resume
            self._pending_plans[task_id] = {
                "plan": plan,
                "current_step": exec_result.get("current_step", 0),
                "tool_calls_log": tool_calls_log,
                "result_data": result_data,
            }
            await self.logger.log(task_id, EventType.APPROVAL_REQUESTED, {
                "approval_id": approval_id,
                "tool": pending_tool,
                "reason": f"Tool requires approval in {task.get('environment', 'test')}",
            })
            return {
                "success": True,
                "task_id": task_id,
                "status": "awaiting_approval",
                "message": f"Waiting for approval for tool {pending_tool}",
                "approval_id": approval_id,
            }

        if status == "failed":
            error_msg = exec_result.get("error", "Unknown error")
            await self._transition(task_id, TaskStatus.RUNNING, TaskStatus.FAILED, "executor")
            await self._update_task(task_id, TaskStatus.FAILED, {}, error_msg)
            await self.logger.log(task_id, EventType.TASK_FAILED, {"error": error_msg, "phase": "execution"})
            await self.workflow.state_store.clear_state(task_id)
            return {"success": False, "task_id": task_id, "error": error_msg}

        # status == "completed"
        current_step = exec_result.get("steps_completed", len(plan.steps))

        # === Generate Artifact ===
        artifact_result = await self._generate_artifact(task_id, task, result_data)
        await self.logger.log(task_id, EventType.ARTIFACT_CREATED, {
            "artifact_path": artifact_result.get("file_path"),
            "artifact_type": "text/plain",
        })

        # === Rollback Plan ===
        rollback_plan = await self._create_rollback_plan(task_id, tool_calls_log)
        await self.logger.log(task_id, EventType.ROLLBACK_PLAN_CREATED, {
            "rollback_plan_id": rollback_plan.get("id"),
            "strategy": rollback_plan.get("strategy"),
        })

        # === Finalize Task ===
        final_result = {
            "status": "completed",
            "artifact_path": artifact_result.get("file_path"),
            "tools_used": [t["tool_name"] for t in tool_calls_log],
            "total_duration_ms": int((time.time() - start_time) * 1000),
            "steps_completed": current_step,
        }

        await self._transition(task_id, TaskStatus.RUNNING, TaskStatus.COMPLETED, "executor")
        await self._update_task(task_id, TaskStatus.COMPLETED, final_result)

        # === Memory Update ===
        memory_ids = await self.memory.update_after_task(
            task_id=task_id,
            task_title=task.get("title", ""),
            task_result=final_result,
            tool_calls=tool_calls_log,
        )
        await self.logger.log(task_id, EventType.MEMORY_UPDATED, {
            "memory_ids": memory_ids,
            "count": len(memory_ids),
            "types": ["episodic", "semantic", "performance", "procedural"],
        })

        # === Skill Update ===
        if task.get("skill_id"):
            events = await self.logger.get_events_for_task(task_id)
            proposal = await self.skill.propose_update(
                skill_id=task["skill_id"], task_id=task_id,
                task_result=final_result, tool_calls=tool_calls_log, events=events,
            )
            if proposal:
                await self.logger.log(task_id, EventType.SKILL_UPDATED, {
                    "skill_id": proposal["skill_id"],
                    "proposed_version": proposal["proposed_version"],
                    "changelog": proposal["changelog"],
                    "eval_score": proposal.get("eval_score"),
                })
            sop_extracts = await self.skill.extract_sop(task_id, events)
            await self.logger.log(task_id, EventType.SOP_EXTRACTED, {
                "extract_count": len(sop_extracts),
                "extracts": [{"type": e["extract_type"], "category": e["category"]} for e in sop_extracts],
            })

        # === Eval ===
        eval_result = await self.eval_service.record_eval(
            task_id=task_id,
            task=task,
            plan=plan,
            tool_calls_log=tool_calls_log,
            result_data=result_data,
            memory_ids=memory_ids,
            skill_id=task.get("skill_id"),
        )
        await self.logger.log(task_id, EventType.EVAL_COMPLETED, {
            "score": eval_result["score"],
            "metrics": eval_result["metrics"],
            "eval_id": eval_result["eval_id"],
            "feedback": eval_result["feedback"],
        })
        await self.logger.log(task_id, EventType.TASK_COMPLETED, {"result": final_result})

        # Clear workflow state after successful completion
        await self.workflow.state_store.clear_state(task_id)

        return {"success": True, "task_id": task_id, "result": final_result}

    async def _create_approval_record(
        self,
        task_id: str,
        action_type: str,
        reason: str,
        plan_state: dict[str, Any] | None = None,
        tool_call_id: str | None = None,
    ) -> str:
        """Create an approval record in the approvals table."""
        requester = "00000000-0000-0000-0000-000000000001"
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO approvals (task_id, tool_call_id, requester, action_type, reason, status, plan_state)
                VALUES ($1, $2, $3, $4, $5, 'pending', $6)
                RETURNING id
                """,
                task_id,
                tool_call_id,
                requester,
                action_type,
                reason,
                json.dumps(plan_state) if plan_state else "{}",
            )
            return str(row["id"])

    async def _generate_artifact(self, task_id: str, task: dict[str, Any], result_data: dict[str, Any]) -> dict[str, Any]:
        file_result = result_data.get("step_2", {}).get("output", result_data.get("step_1", {}).get("output", {}))
        file_path = file_result.get("file_path", "")

        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO artifacts (task_id, artifact_type, name, mime_type, file_path, content)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                task_id,
                "text",
                task.get("title", "artifact"),
                "text/plain",
                file_path,
                str(file_result.get("bytes_written", 0)),
            )
        return file_result

    async def _create_rollback_plan(self, task_id: str, tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
        strategies = []
        for tc in tool_calls:
            from tools.registry import ToolRegistry
            manifest = ToolRegistry.get(tc["tool_name"])
            if manifest and manifest.risk_level in ("high", "critical"):
                strategies.append({
                    "tool": tc["tool_name"],
                    "strategy": manifest.rollback_strategy,
                    "details": f"Rollback using {manifest.rollback_strategy}",
                })

        plan = {
            "task_id": task_id,
            "strategy": "composite" if len(strategies) > 1 else (strategies[0]["strategy"] if strategies else "none"),
            "steps": strategies,
        }

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO rollback_plans (task_id, strategy, plan)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                task_id,
                plan["strategy"],
                json_dumps(plan),
            )
            plan["id"] = str(row["id"])
        return plan

    async def _transition(self, task_id: str, from_state: TaskStatus, to_state: TaskStatus, triggered_by: str) -> None:
        await self.logger.log_state_transition(
            task_id=task_id,
            from_state=from_state.value,
            to_state=to_state.value,
            triggered_by=triggered_by,
        )
        await self._update_task_status(task_id, to_state.value)

    async def _update_task(self, task_id: str, status: TaskStatus, result: dict[str, Any], error_message: str = "") -> None:
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE tasks SET status = $1, result = $2, error_message = $3, updated_at = NOW() WHERE id = $4",
                status.value,
                json_dumps(result),
                error_message,
                task_id,
            )
            if status.value in ("completed", "failed", "cancelled", "rolled_back"):
                await conn.execute(
                    "UPDATE tasks SET completed_at = NOW() WHERE id = $1 AND completed_at IS NULL",
                    task_id,
                )

    async def _update_task_status(self, task_id: str, status: str) -> None:
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE tasks SET status = $1, updated_at = NOW() WHERE id = $2",
                status,
                task_id,
            )

    async def _is_cancelled(self, task_id: str) -> bool:
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT status FROM tasks WHERE id = $1", task_id)
            return row is not None and row["status"] == "cancelled"

    async def cancel(self, task_id: str) -> dict[str, Any]:
        """Cancel a running task"""
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            del self._running_tasks[task_id]

        await self._update_task_status(task_id, "cancelled")
        await self.logger.log(task_id, EventType.TASK_CANCELLED, {"reason": "User requested cancellation"})
        return {"success": True, "task_id": task_id, "status": "cancelled"}

    async def pause(self, task_id: str) -> dict[str, Any]:
        """Pause a running task"""
        if task_id in self._running_tasks:
            self._paused_tasks[task_id] = {"paused_at": time.time()}
            await self._update_task_status(task_id, "paused")
            return {"success": True, "task_id": task_id, "status": "paused"}
        return {"success": False, "error": "Task not running"}

    async def _resume(self, task_id: str, task: dict[str, Any] | None = None) -> dict[str, Any]:
        """Resume a paused or approval-pending task from saved plan state."""
        if task_id in self._paused_tasks:
            del self._paused_tasks[task_id]

        if task is None:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
            if not row:
                return {"success": False, "error": "Task not found"}
            task = dict(row)

        # If we have saved plan state, resume from where we left off
        if task_id in self._pending_plans:
            pending = self._pending_plans.pop(task_id)
            await self._update_task_status(task_id, "resumed")
            await self.logger.log(task_id, EventType.TASK_STATE_CHANGED, {
                "from_state": "paused",
                "to_state": "resumed",
                "triggered_by": "user",
                "reason": "Resuming from saved plan state",
            })
            task_future = asyncio.create_task(self._resume_with_state(task_id, task, pending))
            self._running_tasks[task_id] = task_future
            try:
                return await task_future
            finally:
                self._running_tasks.pop(task_id, None)

        # Fallback: re-fetch task and re-execute from scratch (legacy behavior for tasks without plan state)
        await self._update_task_status(task_id, "resumed")
        return await self._execute_task(task_id, task)

    async def run_subagent_analysis(
        self,
        task_id: str,
        task_context: dict[str, Any],
        roles: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run multi-perspective subagent analysis"""
        from models.schemas import SubagentRole

        if roles is None:
            roles = ["product", "dev", "ops"]

        role_enums = []
        for r in roles:
            try:
                role_enums.append(SubagentRole(r))
            except ValueError:
                role_enums.append(SubagentRole.GENERAL)

        return await self.subagent.run_multi_perspective_analysis(task_id, task_context, role_enums)

    async def execute_rollback(self, task_id: str, executed_by: str = "system") -> dict[str, Any]:
        """Execute rollback for a task"""
        async with self.db_pool.acquire() as conn:
            plans = await conn.fetch(
                "SELECT * FROM rollback_plans WHERE task_id = $1 AND executed = FALSE",
                task_id,
            )

        results = []
        for plan in plans:
            result = await self.rollback.execute_rollback(str(plan["id"]), executed_by)
            results.append(result)

        if results:
            await self._transition(task_id, TaskStatus.RUNNING, TaskStatus.ROLLED_BACK, "rollback_service")

        return {"success": True, "task_id": task_id, "rollback_results": results}
