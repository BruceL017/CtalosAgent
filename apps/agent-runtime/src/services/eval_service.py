"""
Eval Service: 多维度任务执行质量评估
评分维度：工具成功率、计划质量、记忆命中、风险合规、耗时效率
"""
from typing import Any

import asyncpg

from utils.json_utils import json_dumps


class EvalService:
    """任务执行评估服务"""

    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool

    async def record_eval(
        self,
        task_id: str,
        task: dict[str, Any],
        plan: Any,
        tool_calls_log: list[dict[str, Any]],
        result_data: dict[str, Any],
        memory_ids: list[str],
        skill_id: str | None = None,
    ) -> dict[str, Any]:
        """记录完整的多维度评估结果到 eval_runs 表。"""
        metrics = self._compute_metrics(task, plan, tool_calls_log, result_data, memory_ids)
        overall_score = self._compute_overall_score(metrics)

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO eval_runs (task_id, skill_id, eval_type, metrics, score, feedback)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                task_id,
                skill_id,
                "task_execution",
                json_dumps(metrics),
                overall_score,
                self._generate_feedback(metrics),
            )

        return {
            "eval_id": str(row["id"]),
            "score": overall_score,
            "metrics": metrics,
            "feedback": self._generate_feedback(metrics),
        }

    def _compute_metrics(
        self,
        task: dict[str, Any],
        plan: Any,
        tool_calls_log: list[dict[str, Any]],
        result_data: dict[str, Any],
        memory_ids: list[str],
    ) -> dict[str, Any]:
        total_tools = len(tool_calls_log)
        success_tools = sum(1 for t in tool_calls_log if t.get("status") == "success")
        failed_tools = total_tools - success_tools

        # 1. 工具成功率 (0-1)
        tool_success_rate = success_tools / max(total_tools, 1)

        # 2. 计划质量 (0-1): 是否有 plan、steps 是否合理覆盖
        plan_quality = 0.5
        if plan and getattr(plan, "steps", None):
            steps = plan.steps
            has_descriptions = sum(1 for s in steps if getattr(s, "description", "")) / max(len(steps), 1)
            has_retry = sum(1 for s in steps if getattr(s, "retry_on_failure", False)) / max(len(steps), 1)
            plan_quality = 0.3 + 0.4 * has_descriptions + 0.3 * has_retry

        # 3. 记忆命中 (0-1): 是否有使用记忆
        memory_hit = min(len(memory_ids) / 3, 1.0) if memory_ids else 0.0

        # 4. 风险合规 (0-1): 生产环境是否有审批
        env = task.get("environment", "test")
        risk_level = task.get("risk_level", "low")
        risk_compliance = 1.0
        if env == "production" and risk_level in ("high", "critical"):
            # 检查是否有 approval 记录
            risk_compliance = 0.8  # 默认假设合规，实际可通过查询 approval 表精确计算

        # 5. 耗时效率 (0-1): 对比预期耗时
        total_duration_ms = 0
        for tc in tool_calls_log:
            total_duration_ms += tc.get("duration_ms", 0)
        # 假设每个工具预期 500ms，效率 = min(1, expected / actual)
        expected_ms = total_tools * 500
        time_efficiency = min(1.0, expected_ms / max(total_duration_ms, 1))

        return {
            "tool_success_rate": round(tool_success_rate, 4),
            "plan_quality": round(plan_quality, 4),
            "memory_hit": round(memory_hit, 4),
            "risk_compliance": round(risk_compliance, 4),
            "time_efficiency": round(time_efficiency, 4),
            "total_tools": total_tools,
            "success_tools": success_tools,
            "failed_tools": failed_tools,
            "total_duration_ms": total_duration_ms,
        }

    def _compute_overall_score(self, metrics: dict[str, Any]) -> float:
        """加权计算总体评分。"""
        weights = {
            "tool_success_rate": 0.35,
            "plan_quality": 0.20,
            "memory_hit": 0.15,
            "risk_compliance": 0.15,
            "time_efficiency": 0.15,
        }
        score = sum(metrics.get(k, 0) * w for k, w in weights.items())
        return round(score, 4)

    def _generate_feedback(self, metrics: dict[str, Any]) -> str:
        """根据指标生成自然语言反馈。"""
        feedbacks = []
        if metrics["tool_success_rate"] < 0.8:
            feedbacks.append(f"工具成功率偏低 ({metrics['tool_success_rate']:.0%})，建议检查失败工具配置或输入参数。")
        if metrics["plan_quality"] < 0.6:
            feedbacks.append("计划质量有提升空间，建议为步骤添加更详细的描述和重试策略。")
        if metrics["memory_hit"] < 0.3:
            feedbacks.append("记忆利用率低，建议任务前检索更多相关记忆。")
        if metrics["time_efficiency"] < 0.5:
            feedbacks.append("执行耗时较长，建议优化工具调用或检查网络延迟。")
        if not feedbacks:
            return "执行质量良好，各维度指标均达标。"
        return " ".join(feedbacks)

    async def get_task_eval(self, task_id: str) -> dict[str, Any] | None:
        """获取任务最新评估结果。"""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM eval_runs WHERE task_id = $1 ORDER BY created_at DESC LIMIT 1",
                task_id,
            )
        if not row:
            return None
        return {
            "id": str(row["id"]),
            "task_id": str(row["task_id"]),
            "eval_type": row["eval_type"],
            "score": float(row["score"]) if row["score"] else None,
            "metrics": row["metrics"] if isinstance(row["metrics"], dict) else {},
            "feedback": row["feedback"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }

    async def list_evals(
        self,
        task_id: str | None = None,
        skill_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """列出评估记录。"""
        conditions = []
        params: list[Any] = []
        if task_id:
            conditions.append("task_id = $" + str(len(params) + 1))
            params.append(task_id)
        if skill_id:
            conditions.append("skill_id = $" + str(len(params) + 1))
            params.append(skill_id)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.extend([limit, offset])

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM eval_runs {where} ORDER BY created_at DESC LIMIT ${len(params)-1} OFFSET ${len(params)}",
                *params,
            )

        results = []
        for r in rows:
            results.append({
                "id": str(r["id"]),
                "task_id": str(r["task_id"]),
                "eval_type": r["eval_type"],
                "score": float(r["score"]) if r["score"] else None,
                "metrics": r["metrics"] if isinstance(r["metrics"], dict) else {},
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            })
        return results
