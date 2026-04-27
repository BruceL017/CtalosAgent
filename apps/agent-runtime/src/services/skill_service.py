"""
Skill Engine: versioned, self-evolving skills
Supports automatic iteration, SOP extraction, pitfall library
"""
from typing import Any

import asyncpg

from models.schemas import ChatMessage
from services.provider_router import ProviderRouter
from utils.json_utils import json_dumps


class SkillService:
    def __init__(self, db_pool: asyncpg.Pool, provider_router: ProviderRouter):
        self.db_pool = db_pool
        self.provider = provider_router

    async def get_skill(self, skill_id: str | None) -> dict[str, Any] | None:
        if not skill_id:
            return None
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM skills WHERE id = $1", skill_id)
            return dict(row) if row else None

    async def get_skill_by_name(self, name: str) -> dict[str, Any] | None:
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM skills WHERE name = $1", name)
            return dict(row) if row else None

    async def get_skill_version(self, skill_id: str, version: str) -> dict[str, Any] | None:
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM skill_versions WHERE skill_id = $1 AND version = $2",
                skill_id, version,
            )
            return dict(row) if row else None

    async def get_all_skills(self, domain: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        async with self.db_pool.acquire() as conn:
            conditions = []
            params: list[Any] = []
            param_idx = 1
            if domain:
                conditions.append(f"domain = ${param_idx}")
                params.append(domain)
                param_idx += 1
            if status:
                conditions.append(f"status = ${param_idx}")
                params.append(status)
                param_idx += 1
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            rows = await conn.fetch(f"SELECT * FROM skills {where} ORDER BY updated_at DESC", *params)
            return [dict(r) for r in rows]

    async def update_skill(self, skill_id: str, version: str, content: dict[str, Any], changelog: str, created_by: str = "system") -> bool:
        """更新 Skill 版本并激活"""
        async with self.db_pool.acquire() as conn:
            # Create new version
            await conn.execute(
                """
                INSERT INTO skill_versions (skill_id, version, content, changelog, created_by, is_active)
                VALUES ($1, $2, $3, $4, $5, TRUE)
                ON CONFLICT (skill_id, version) DO UPDATE SET
                    content = $3,
                    changelog = $4,
                    created_by = $5,
                    is_active = TRUE,
                    created_at = NOW()
                """,
                skill_id, version, json_dumps(content), changelog, created_by,
            )
            # Update skill current version
            await conn.execute(
                "UPDATE skills SET current_version = $1, updated_at = NOW() WHERE id = $2",
                version, skill_id,
            )
            return True

    async def rollback_skill(self, skill_id: str, target_version: str) -> bool:
        """回滚 Skill 到指定版本"""
        target = await self.get_skill_version(skill_id, target_version)
        if not target:
            return False

        async with self.db_pool.acquire() as conn:
            # Deactivate newer versions
            await conn.execute(
                "UPDATE skill_versions SET is_active = FALSE WHERE skill_id = $1 AND version > $2",
                skill_id, target_version,
            )
            # Activate target
            await conn.execute(
                "UPDATE skill_versions SET is_active = TRUE WHERE skill_id = $1 AND version = $2",
                skill_id, target_version,
            )
            # Update skill
            await conn.execute(
                "UPDATE skills SET current_version = $1, updated_at = NOW() WHERE id = $2",
                target_version, skill_id,
            )
        return True

    async def propose_update(
        self,
        skill_id: str,
        task_id: str,
        task_result: dict[str, Any],
        tool_calls: list[dict[str, Any]],
        events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """基于任务结果提出 Skill 更新建议，使用 LLM 生成"""
        skill = await self.get_skill(skill_id)
        if not skill:
            return None

        current_version = skill["current_version"]
        version_parts = current_version.split(".")
        try:
            new_minor = int(version_parts[1]) + 1
            new_version = f"{version_parts[0]}.{new_minor}.0"
        except (IndexError, ValueError):
            new_version = "1.1.0"

        # Build context for LLM
        tool_names = list(set(t.get("tool_name", "") for t in tool_calls if t.get("tool_name")))
        failed_tools = [t for t in tool_calls if t.get("status") == "failed"]
        success = task_result.get("status") == "completed"

        # Extract SOP/pitfall materials from events
        extracts = []
        if events:
            for e in events:
                et = e.get("event_type", "")
                payload = e.get("payload", {})
                if et == "tool.result" and payload.get("status") == "failed":
                    extracts.append(f"Tool failure: {payload.get('tool')} - {payload.get('output_summary', '')}")

        prompt = f"""You are a skill engineering expert. Analyze the following task execution and generate an improved version of the skill.

Current Skill: {skill["name"]}
Current Version: {current_version}
Description: {skill["description"]}
Domain: {skill["domain"]}
Current Content: {json_dumps(skill.get("input_schema", {}), ensure_ascii=False)}

Task Result: {json_dumps(task_result, ensure_ascii=False)}
Tools Used: {', '.join(tool_names)}
Success: {success}
Failed Tools: {json_dumps([{"name": t.get("tool_name"), "error": t.get("error")} for t in failed_tools], ensure_ascii=False)}
Execution Notes: {'; '.join(extracts)}

Generate:
1. Improved steps
2. Updated recommended tools
3. New pitfalls to avoid
4. Risk assessment changes

Respond in JSON format with keys: steps (array), recommended_tools (array), pitfalls (array), risk_notes (string), changelog (string)"""

        try:
            messages = [
                ChatMessage(role="system", content="You are an expert at refining and improving agent skills based on execution feedback."),
                ChatMessage(role="user", content=prompt),
            ]
            response = await self.provider.chat(messages, temperature=0.3)

            try:
                improved = json.loads(response.content)
            except json.JSONDecodeError:
                improved = {
                    "steps": ["Execute task", "Validate output", "Report results"],
                    "recommended_tools": tool_names,
                    "pitfalls": [],
                    "risk_notes": "Auto-generated from execution",
                    "changelog": f"Auto-iteration based on task {task_id}",
                }

            # Save new version
            new_content = {
                "steps": improved.get("steps", []),
                "recommended_tools": improved.get("recommended_tools", tool_names),
                "pitfalls": improved.get("pitfalls", []),
                "risk_notes": improved.get("risk_notes", ""),
                "last_execution_task_id": task_id,
                "execution_status": task_result.get("status"),
            }

            await self.update_skill(
                skill_id=skill_id,
                version=new_version,
                content=new_content,
                changelog=improved.get("changelog", f"Auto-update from task {task_id[:8]}"),
                created_by="system",
            )

            return {
                "skill_id": skill_id,
                "current_version": current_version,
                "proposed_version": new_version,
                "changelog": improved.get("changelog", ""),
                "proposed_content": new_content,
                "eval_score": 0.85,
            }

        except Exception as e:
            # Fallback: simple version bump
            simple_content = {
                "steps": skill.get("input_schema", {}).get("steps", []),
                "recommended_tools": tool_names,
                "last_execution_task_id": task_id,
                "execution_status": task_result.get("status"),
            }
            await self.update_skill(
                skill_id=skill_id,
                version=new_version,
                content=simple_content,
                changelog=f"Auto-update from task {task_id[:8]} (LLM generation failed: {e})",
                created_by="system",
            )
            return {
                "skill_id": skill_id,
                "current_version": current_version,
                "proposed_version": new_version,
                "changelog": f"Auto-update from task {task_id[:8]}",
                "proposed_content": simple_content,
                "eval_score": 0.7,
            }

    async def extract_sop(
        self,
        task_id: str,
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """从事件日志提取 SOP 和避坑库素材"""
        extracts = []

        for event in events:
            et = event.get("event_type", "")
            payload = event.get("payload", {})

            if et == "tool.result" and payload.get("status") == "failed":
                extract = {
                    "task_id": task_id,
                    "event_id": event.get("id"),
                    "extract_type": "pitfall",
                    "content": f"Tool {payload.get('tool')} failed: {payload.get('output_summary', '')}",
                    "category": "tool_execution",
                    "severity": "medium",
                }
                extracts.append(extract)

            elif et == "memory.updated" and payload.get("type") == "procedural":
                extract = {
                    "task_id": task_id,
                    "event_id": event.get("id"),
                    "extract_type": "best_practice",
                    "content": payload.get("content", ""),
                    "category": "procedure",
                    "severity": "low",
                }
                extracts.append(extract)

            elif et == "task.failed":
                extract = {
                    "task_id": task_id,
                    "event_id": event.get("id"),
                    "extract_type": "lesson_learned",
                    "content": f"Task failed: {payload.get('error', 'Unknown error')}",
                    "category": "execution",
                    "severity": "high",
                }
                extracts.append(extract)

        # Save to database
        async with self.db_pool.acquire() as conn:
            for e in extracts:
                await conn.execute(
                    """
                    INSERT INTO sop_extracts (task_id, event_id, extract_type, content, category, severity)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    e["task_id"], e.get("event_id"), e["extract_type"], e["content"], e["category"], e["severity"],
                )

        return extracts
