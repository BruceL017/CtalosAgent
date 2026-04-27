"""
Event Logger: append-only structured event log
Supports replay, debug, audit, SOP extraction
集成结构化日志（task_id, session_id, tool_call_id, trace_id）
"""
import json
import uuid
from datetime import datetime
from typing import Any

import asyncpg

from models.schemas import EventType
from utils.secret_redactor import redact_object, redact_string
from utils.structured_logger import ContextLogger


class _EventJSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def _event_json_dumps(obj: Any) -> str:
    return json.dumps(obj, cls=_EventJSONEncoder)


class EventLogger:
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self._sequence_cache: dict[str, int] = {}
        self._structured = ContextLogger(task_id=None, session_id=None)

    async def log(
        self,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> str:
        # Redact secrets before persisting to event log
        safe_payload = redact_object(payload)
        async with self.db_pool.acquire() as conn:
            # If no cache entry, load max sequence from DB (cross-process resume safety)
            if task_id not in self._sequence_cache:
                max_seq = await conn.fetchval(
                    "SELECT COALESCE(MAX(sequence), 0) FROM task_events WHERE task_id = $1",
                    task_id,
                )
                self._sequence_cache[task_id] = max_seq or 0
            seq = self._sequence_cache.get(task_id, 0) + 1
            self._sequence_cache[task_id] = seq

            row = await conn.fetchrow(
                """
                INSERT INTO task_events (task_id, event_type, sequence, payload)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                task_id,
                event_type,
                seq,
                _event_json_dumps(safe_payload),
            )
            event_id = str(row["id"])

        # Structured logging with trace context
        self._structured.info(
            f"Event logged: {event_type}",
            task_id=task_id,
            event_type=event_type,
            event_id=event_id,
            sequence=seq,
        )
        return event_id

    async def log_tool_call(
        self,
        task_id: str,
        tool_name: str,
        tool_version: str,
        input_data: dict[str, Any],
        risk_level: str,
        environment: str,
        event_id: str | None = None,
        subagent_id: str | None = None,
    ) -> str:
        safe_input = redact_object(input_data)
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO tool_calls (task_id, event_id, subagent_id, tool_name, tool_version, input, status, risk_level, environment)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
                """,
                task_id,
                event_id,
                subagent_id,
                tool_name,
                tool_version,
                _event_json_dumps(safe_input),
                "pending",
                risk_level,
                environment,
            )
            return str(row["id"])

    async def update_tool_call(
        self,
        tool_call_id: str,
        status: str,
        output: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        error_message: str | None = None,
    ) -> None:
        safe_output = redact_object(output) if output else None
        safe_error = redact_string(error_message) if error_message else None
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE tool_calls
                SET status = $1, output = $2, duration_ms = $3, error_message = $4
                WHERE id = $5
                """,
                status,
                _event_json_dumps(safe_output) if safe_output else None,
                duration_ms,
                safe_error,
                tool_call_id,
            )

    async def log_state_transition(
        self,
        task_id: str,
        from_state: str,
        to_state: str,
        triggered_by: str,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        event_id = await self.log(task_id, EventType.TASK_STATE_CHANGED, {
            "from_state": from_state,
            "to_state": to_state,
            "triggered_by": triggered_by,
            "reason": reason,
            "metadata": metadata or {},
        })

        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO task_state_transitions (task_id, from_state, to_state, triggered_by, reason, metadata)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                task_id,
                from_state,
                to_state,
                triggered_by,
                reason,
                _event_json_dumps(metadata) if metadata else None,
            )
        return event_id

    async def get_events_for_task(
        self,
        task_id: str,
        from_sequence: int = 1,
    ) -> list[dict[str, Any]]:
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM task_events WHERE task_id = $1 AND sequence >= $2 ORDER BY sequence ASC",
                task_id,
                from_sequence,
            )
            return [dict(r) for r in rows]
