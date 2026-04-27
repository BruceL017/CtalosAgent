"""
Subagent Manager: 支持多角色 subagent 的创建、执行和结果汇总
"""
import uuid
from typing import Any

import asyncpg

from models.schemas import ChatMessage, SubagentRole
from services.event_logger import EventLogger
from services.provider_router import ProviderRouter
from utils.json_utils import json_dumps


class SubagentManager:
    """Subagent 管理器"""

    ROLE_SYSTEM_PROMPTS: dict[SubagentRole, str] = {
        SubagentRole.PRODUCT: "You are a product manager. Analyze from product strategy, user needs, market positioning, and roadmap perspectives. Be critical and thorough.",
        SubagentRole.DEV: "You are a senior software engineer. Analyze from technical feasibility, architecture, code quality, performance, and maintainability perspectives.",
        SubagentRole.OPS: "You are an operations expert. Analyze from operational efficiency, cost, scalability, monitoring, and incident response perspectives.",
        SubagentRole.DATA: "You are a data analyst. Analyze from data quality, metrics, analytics, and data-driven decision making perspectives.",
        SubagentRole.SECURITY: "You are a security engineer. Analyze from security posture, compliance, threat modeling, and risk mitigation perspectives.",
        SubagentRole.GENERAL: "You are a general consultant. Provide balanced, comprehensive analysis.",
    }

    def __init__(self, db_pool: asyncpg.Pool, provider_router: ProviderRouter):
        self.db_pool = db_pool
        self.provider = provider_router
        self.logger = EventLogger(db_pool)

    async def create_subagent(
        self,
        task_id: str,
        role: SubagentRole,
        name: str,
        context: dict[str, Any],
        parent_subagent_id: str | None = None,
    ) -> dict[str, Any]:
        """创建 subagent"""
        subagent_id = str(uuid.uuid4())

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO subagents (id, task_id, parent_subagent_id, role, name, status, context)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING *
                """,
                subagent_id,
                task_id,
                parent_subagent_id,
                role.value,
                name,
                "pending",
                json_dumps(context),
            )

        await self.logger.log(task_id, "subagent.created", {
            "subagent_id": subagent_id,
            "role": role.value,
            "name": name,
        })

        return dict(row)

    async def execute_subagent(
        self,
        subagent_id: str,
        task_context: dict[str, Any],
    ) -> dict[str, Any]:
        """执行 subagent 任务"""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM subagents WHERE id = $1", subagent_id)
        if not row:
            raise ValueError(f"Subagent {subagent_id} not found")

        subagent = dict(row)
        task_id = subagent["task_id"]
        role = SubagentRole(subagent["role"])

        # Update to running
        await conn.execute(
            "UPDATE subagents SET status = 'running', started_at = NOW() WHERE id = $1",
            subagent_id,
        )

        try:
            # Build context for the subagent
            system_prompt = self.ROLE_SYSTEM_PROMPTS.get(role, self.ROLE_SYSTEM_PROMPTS[SubagentRole.GENERAL])
            messages = [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=f"""Task: {task_context.get('title', '')}
Description: {task_context.get('description', '')}
Context: {json_dumps(task_context.get('context', {}), ensure_ascii=False)}

Please analyze this from your role perspective and provide:
1. Key findings
2. Risks or concerns
3. Recommendations
4. Any conflicts with other perspectives (if known)

Respond in JSON format with keys: findings, risks, recommendations, conflicts"""),
            ]

            response = await self.provider.chat(messages, temperature=0.7)

            # Parse result
            result_text = response.content
            try:
                result_json = json.loads(result_text)
            except json.JSONDecodeError:
                # Fallback: wrap raw text
                result_json = {
                    "findings": result_text[:500],
                    "risks": [],
                    "recommendations": [],
                    "conflicts": [],
                    "raw_response": result_text,
                }

            # Update subagent
            await conn.execute(
                """
                UPDATE subagents
                SET status = 'completed', result = $1, completed_at = NOW(), updated_at = NOW()
                WHERE id = $2
                """,
                json_dumps(result_json),
                subagent_id,
            )

            await self.logger.log(task_id, "subagent.completed", {
                "subagent_id": subagent_id,
                "role": role.value,
                "model": response.model,
                "provider": response.provider,
            })

            return {
                "subagent_id": subagent_id,
                "role": role.value,
                "status": "completed",
                "result": result_json,
                "provider": response.provider,
                "model": response.model,
            }

        except Exception as e:
            await conn.execute(
                """
                UPDATE subagents
                SET status = 'failed', error_message = $1, updated_at = NOW()
                WHERE id = $2
                """,
                str(e),
                subagent_id,
            )

            await self.logger.log(task_id, "subagent.failed", {
                "subagent_id": subagent_id,
                "role": role.value,
                "error": str(e),
            })

            return {
                "subagent_id": subagent_id,
                "role": role.value,
                "status": "failed",
                "error": str(e),
            }

    async def run_multi_perspective_analysis(
        self,
        task_id: str,
        task_context: dict[str, Any],
        roles: list[SubagentRole] | None = None,
    ) -> dict[str, Any]:
        """运行多视角分析：创建多个 subagent，汇总结果"""
        if roles is None:
            roles = [SubagentRole.PRODUCT, SubagentRole.DEV, SubagentRole.OPS]

        # Create all subagents
        subagents = []
        for role in roles:
            sa = await self.create_subagent(
                task_id=task_id,
                role=role,
                name=f"{role.value}_analyst",
                context=task_context,
            )
            subagents.append(sa)

        # Execute all subagents (could be parallel in production)
        results = []
        for sa in subagents:
            result = await self.execute_subagent(sa["id"], task_context)
            results.append(result)

        # Conflict resolution and synthesis
        synthesis = await self._synthesize_results(task_id, task_context, results)

        return {
            "task_id": task_id,
            "subagent_results": results,
            "synthesis": synthesis,
            "conflicts_detected": synthesis.get("conflicts", []),
        }

    async def _synthesize_results(
        self,
        task_id: str,
        task_context: dict[str, Any],
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """汇总多个 subagent 结果，进行冲突消解"""
        # Build synthesis prompt
        results_text = "\n\n".join([
            f"=== {r['role']} ===\n{r.get('result', {}).get('findings', '')}"
            for r in results if r.get("status") == "completed"
        ])

        messages = [
            ChatMessage(role="system", content="You are a synthesis expert. Combine multiple expert perspectives into a coherent summary. Identify and resolve any conflicts between perspectives."),
            ChatMessage(role="user", content=f"""Original Task: {task_context.get('title', '')}

Expert Perspectives:
{results_text}

Please provide:
1. Synthesis summary
2. Areas of agreement
3. Areas of conflict (with resolution recommendation)
4. Final recommendation

Respond in JSON with keys: summary, agreements, conflicts, final_recommendation"""),
        ]

        try:
            response = await self.provider.chat(messages, temperature=0.5)
            try:
                return json.loads(response.content)
            except json.JSONDecodeError:
                return {
                    "summary": response.content[:800],
                    "agreements": [],
                    "conflicts": [],
                    "final_recommendation": "See summary above",
                }
        except Exception as e:
            return {
                "summary": f"Synthesis failed: {e}",
                "agreements": [],
                "conflicts": [],
                "final_recommendation": "Manual review required",
            }
