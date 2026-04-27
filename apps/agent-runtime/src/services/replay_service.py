"""
Replay Service: 任务重放、调试、审计
支持完整重放、单步调试、工具调用调试
"""
import asyncio
# import json removed
import time
from typing import Any

import asyncpg

from models.schemas import ReplayType
from services.event_logger import EventLogger
from utils.json_utils import json_dumps


class ReplayService:
    """重放服务"""

    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.logger = EventLogger(db_pool)

    async def create_replay_session(
        self,
        task_id: str,
        replay_type: ReplayType,
        from_sequence: int | None = None,
        to_sequence: int | None = None,
        speed: str = "1x",
    ) -> dict[str, Any]:
        """创建重放会话"""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO replay_sessions (task_id, replay_type, from_event_sequence, to_event_sequence, speed, status)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING *
                """,
                task_id,
                replay_type.value,
                from_sequence,
                to_sequence,
                speed,
                "running",
            )
            return dict(row)

    async def replay_task(self, replay_session_id: str) -> dict[str, Any]:
        """执行任务重放"""
        async with self.db_pool.acquire() as conn:
            session = await conn.fetchrow(
                "SELECT * FROM replay_sessions WHERE id = $1", replay_session_id
            )
            if not session:
                return {"success": False, "error": "Replay session not found"}

            session_dict = dict(session)
            task_id = session_dict["task_id"]
            replay_type = ReplayType(session_dict["replay_type"])
            from_seq = session_dict.get("from_event_sequence")
            to_seq = session_dict.get("to_event_sequence")

            # Get events
            query = "SELECT * FROM task_events WHERE task_id = $1"
            params = [task_id]
            if from_seq is not None:
                query += " AND sequence >= $2"
                params.append(from_seq)
            if to_seq is not None:
                query += f" AND sequence <= ${len(params) + 1}"
                params.append(to_seq)
            query += " ORDER BY sequence ASC"

            events = await conn.fetch(query, *params)

            replay_steps = []
            for event in events:
                event_dict = dict(event)
                step = {
                    "sequence": event_dict["sequence"],
                    "event_type": event_dict["event_type"],
                    "timestamp": event_dict["created_at"].isoformat() if event_dict.get("created_at") else None,
                    "payload": event_dict.get("payload", {}),
                    "notes": [],
                }

                # Add debugging notes based on event type
                if event_dict["event_type"] == "tool.called":
                    step["notes"].append("Tool call can be re-executed for debugging")
                elif event_dict["event_type"] == "tool.result":
                    step["notes"].append("Compare with original output")
                elif event_dict["event_type"] == "approval.requested":
                    step["notes"].append("Approval decision point - can simulate different outcomes")

                replay_steps.append(step)

                # Simulate speed delay
                speed = session_dict.get("speed", "1x")
                if speed != "instant":
                    delay = 0.5
                    if speed == "2x":
                        delay = 0.25
                    elif speed == "0.5x":
                        delay = 1.0
                    await asyncio.sleep(delay)

            # Mark completed
            await conn.execute(
                "UPDATE replay_sessions SET status = 'completed', result = $1, completed_at = NOW() WHERE id = $2",
                json_dumps({"steps_replayed": len(replay_steps)}),
                replay_session_id,
            )

            return {
                "success": True,
                "replay_session_id": replay_session_id,
                "task_id": task_id,
                "type": replay_type.value,
                "steps_replayed": len(replay_steps),
                "steps": replay_steps,
            }

    async def debug_tool_call(self, tool_call_id: str) -> dict[str, Any]:
        """调试单个工具调用"""
        async with self.db_pool.acquire() as conn:
            tool_call = await conn.fetchrow("SELECT * FROM tool_calls WHERE id = $1", tool_call_id)
            if not tool_call:
                return {"success": False, "error": "Tool call not found"}

            tc = dict(tool_call)
            return {
                "success": True,
                "tool_call": {
                    "id": tc["id"],
                    "tool_name": tc["tool_name"],
                    "input": tc.get("input", {}),
                    "output": tc.get("output", {}),
                    "status": tc["status"],
                    "duration_ms": tc.get("duration_ms"),
                    "error_message": tc.get("error_message"),
                },
                "debug_info": {
                    "can_replay": tc["status"] in ("success", "failed"),
                    "can_modify_input": True,
                    "suggested_debug_actions": [
                        "Modify input parameters and re-run",
                        "Check tool manifest for schema validation",
                        "Verify environment and permissions",
                        "Review rollback plan if available",
                    ],
                },
            }

    async def export_audit_trail(self, task_id: str) -> dict[str, Any]:
        """导出审计轨迹"""
        async with self.db_pool.acquire() as conn:
            task = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
            events = await conn.fetch(
                "SELECT * FROM task_events WHERE task_id = $1 ORDER BY sequence ASC",
                task_id,
            )
            tool_calls = await conn.fetch(
                "SELECT * FROM tool_calls WHERE task_id = $1 ORDER BY created_at ASC",
                task_id,
            )
            approvals = await conn.fetch(
                "SELECT * FROM approvals WHERE task_id = $1",
                task_id,
            )
            rollback_plans = await conn.fetch(
                "SELECT * FROM rollback_plans WHERE task_id = $1",
                task_id,
            )

            return {
                "success": True,
                "task_id": task_id,
                "task": dict(task) if task else None,
                "events": [dict(e) for e in events],
                "tool_calls": [dict(t) for t in tool_calls],
                "approvals": [dict(a) for a in approvals],
                "rollback_plans": [dict(r) for r in rollback_plans],
                "export_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "format_version": "1.0",
            }
