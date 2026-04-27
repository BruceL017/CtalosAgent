"""
Memory Service: PostgreSQL + pgvector
Episodic, Semantic, Procedural, Performance memories
支持真实 embedding（SiliconFlow）和 mock fallback
"""
from typing import Any

import asyncpg

from services.embedding_service import EmbeddingService
from utils.json_utils import json_dumps


class MemoryService:
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self._embedding = EmbeddingService()

    async def create_memory(
        self,
        memory_type: str,
        content: str,
        source_task_id: str | None = None,
        source_event_id: str | None = None,
        source_session_id: str | None = None,
        scope: str = "global",
        confidence: float = 0.8,
        enabled: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO memories (memory_type, content, source_task_id, source_event_id, source_session_id, scope, confidence, version, metadata, is_active, enabled, last_used_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
                RETURNING id
                """,
                memory_type,
                content,
                source_task_id,
                source_event_id,
                source_session_id,
                scope,
                confidence,
                1,
                json_dumps(metadata) if metadata else None,
                True,
                enabled,
            )
            memory_id = str(row["id"])

        # Generate and store embedding asynchronously (don't block on failure)
        try:
            embedding = await self._embedding.embed_single(content)
            if embedding:
                await self.create_embedding(memory_id, embedding, model=self._embedding._provider.default_model if hasattr(self._embedding._provider, "default_model") else "siliconflow")
        except Exception:
            # Embedding failure should not break memory creation
            pass

        return memory_id

    async def create_embedding(self, memory_id: str, embedding: list[float] | None = None, model: str = "siliconflow") -> None:
        """存储向量嵌入到 pgvector"""
        if embedding is None or not embedding:
            return
        async with self.db_pool.acquire() as conn:
            # pgvector expects array literal or direct vector cast
            await conn.execute(
                """
                INSERT INTO memory_embeddings (memory_id, embedding, model)
                VALUES ($1, $2::vector, $3)
                ON CONFLICT (memory_id) DO UPDATE SET
                    embedding = $2::vector,
                    model = $3,
                    created_at = NOW()
                """,
                memory_id,
                embedding,
                model,
            )

    async def search_similar(
        self,
        query_embedding: list[float],
        memory_type: str | None = None,
        limit: int = 5,
        min_similarity: float = 0.7,
    ) -> list[dict[str, Any]]:
        """向量相似度搜索"""
        async with self.db_pool.acquire() as conn:
            conditions = ["me.embedding IS NOT NULL"]
            params: list[Any] = [str(query_embedding), min_similarity, limit]

            if memory_type:
                conditions.append("m.memory_type = $4")
                params.append(memory_type)

            query = f"""
                SELECT m.*,
                       1 - (me.embedding <-> $1::vector) AS similarity
                FROM memories m
                JOIN memory_embeddings me ON m.id = me.memory_id
                WHERE {' AND '.join(conditions)}
                  AND m.is_active = TRUE
                  AND 1 - (me.embedding <-> $1::vector) >= $2
                ORDER BY me.embedding <-> $1::vector
                LIMIT $3
            """

            rows = await conn.fetch(query, *params)
            results = []
            for r in rows:
                d = dict(r)
                d["similarity"] = float(d.get("similarity", 0))
                results.append(d)
            return results

    async def get_relevant_memories(
        self,
        query: str,
        memory_type: str | None = None,
        scope: str | None = None,
        session_id: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """文本搜索 + 向量搜索（MVP 阶段文本搜索为主）"""
        async with self.db_pool.acquire() as conn:
            conditions = ["m.is_active = TRUE", "m.enabled = TRUE"]
            params: list[Any] = [f"%{query}%"]
            param_idx = 2

            if memory_type:
                conditions.append(f"m.memory_type = ${param_idx}")
                params.append(memory_type)
                param_idx += 1
            if scope:
                conditions.append(f"m.scope = ${param_idx}")
                params.append(scope)
                param_idx += 1
            if session_id:
                conditions.append(f"(m.scope = 'session' AND m.source_session_id = ${param_idx} OR m.scope != 'session')")
                params.append(session_id)
                param_idx += 1

            params.append(limit)

            rows = await conn.fetch(
                f"""
                SELECT m.*, 0.0 AS similarity
                FROM memories m
                WHERE {' AND '.join(conditions)}
                  AND m.content ILIKE $1
                ORDER BY m.confidence DESC, m.last_used_at DESC NULLS LAST
                LIMIT ${param_idx}
                """,
                *params,
            )
            return [dict(r) for r in rows]

    async def retrieve_for_task(
        self,
        task_id: str,
        session_id: str | None = None,
        query: str = "",
    ) -> dict[str, list[dict[str, Any]]]:
        """Run前检索记忆：session、global、procedural"""
        results: dict[str, list[dict[str, Any]]] = {}

        # Session scope memories
        if session_id:
            results["session"] = await self.get_relevant_memories(
                query=query, scope="session", session_id=session_id, limit=5
            )

        # Global semantic memories
        results["global"] = await self.get_relevant_memories(
            query=query, scope="global", memory_type="semantic", limit=5
        )

        # Procedural memories (SOP, pitfalls)
        results["procedural"] = await self.get_relevant_memories(
            query=query, memory_type="procedural", limit=5
        )

        return results

    async def update_after_task(
        self,
        task_id: str,
        task_title: str,
        task_result: dict[str, Any],
        tool_calls: list[dict[str, Any]],
    ) -> list[str]:
        """任务结束后自动生成记忆更新"""
        memory_ids: list[str] = []

        # Episodic: 任务执行轨迹
        success_count = sum(1 for t in tool_calls if t.get("status") == "success")
        total_count = len(tool_calls)
        status = task_result.get("status", "unknown")

        episodic = f"""Task '{task_title}' completed with status: {status}.
Tools used: {', '.join(set(t.get('tool_name', '') for t in tool_calls))}
Success rate: {success_count}/{total_count}
Duration: {task_result.get('total_duration_ms', 0)}ms"""

        mid = await self.create_memory(
            memory_type="episodic",
            content=episodic,
            source_task_id=task_id,
            scope="task",
            confidence=0.95,
            metadata={"tool_count": total_count, "success_count": success_count, "status": status},
        )
        memory_ids.append(mid)

        # Semantic: 提取关键事实
        tool_names = list(set(t.get("tool_name", "") for t in tool_calls if t.get("tool_name")))
        if tool_names:
            semantic = f"Task '{task_title}' involved tools: {', '.join(tool_names)}. Status: {status}."
            mid = await self.create_memory(
                memory_type="semantic",
                content=semantic,
                source_task_id=task_id,
                scope="global",
                confidence=0.8,
                metadata={"tools": tool_names},
            )
            memory_ids.append(mid)

        # Performance: 工具成功率
        if total_count > 0:
            perf = f"Tool success rate: {success_count}/{total_count} ({success_count/total_count*100:.1f}%). Task: {task_title}"
            mid = await self.create_memory(
                memory_type="performance",
                content=perf,
                source_task_id=task_id,
                scope="global",
                confidence=0.9,
                metadata={"total": total_count, "success": success_count, "rate": success_count / total_count},
            )
            memory_ids.append(mid)

        # Procedural: 成功/失败经验
        failed_tools = [t for t in tool_calls if t.get("status") == "failed"]
        if failed_tools:
            for ft in failed_tools:
                pitfall = f"Tool {ft['tool_name']} failed with error: {ft.get('error', 'unknown')}. Task: {task_title}"
                mid = await self.create_memory(
                    memory_type="procedural",
                    content=pitfall,
                    source_task_id=task_id,
                    scope="global",
                    confidence=0.85,
                    metadata={"tool_name": ft["tool_name"], "error": ft.get("error"), "type": "pitfall"},
                )
                memory_ids.append(mid)

        return memory_ids

    async def deactivate_memory(self, memory_id: str) -> bool:
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE memories SET is_active = FALSE, updated_at = NOW() WHERE id = $1",
                memory_id,
            )
            return "UPDATE 1" in result

    async def rollback_memory_version(self, memory_id: str) -> bool:
        """回滚记忆（创建新版本标记旧版本为 inactive）"""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM memories WHERE id = $1", memory_id)
            if not row:
                return False
            # Mark as inactive
            await conn.execute(
                "UPDATE memories SET is_active = FALSE, updated_at = NOW() WHERE id = $1",
                memory_id,
            )
            return True
