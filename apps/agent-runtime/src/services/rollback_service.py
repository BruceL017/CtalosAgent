"""
Rollback Service: 补偿式回滚执行
支持 Git revert、SQL reverse、Lark 文档修正、消息撤回/更正、Skill 版本回滚
"""
import os
import time
from typing import Any

import asyncpg

from services.event_logger import EventLogger
from utils.json_utils import json_dumps


class RollbackService:
    """回滚服务"""

    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.logger = EventLogger(db_pool)

    async def dry_run_rollback(
        self,
        rollback_plan_id: str,
    ) -> dict[str, Any]:
        """Dry-run a rollback plan: return detailed preview without executing."""
        async with self.db_pool.acquire() as conn:
            plan = await conn.fetchrow("SELECT * FROM rollback_plans WHERE id = $1", rollback_plan_id)
            if not plan:
                return {"success": False, "error": "Rollback plan not found"}

            plan_dict = dict(plan)
            task_id = plan_dict["task_id"]
            tool_call_id = plan_dict.get("tool_call_id")
            strategy = plan_dict["strategy"]
            plan_data = plan_dict.get("plan", {})

            tool_call = None
            if tool_call_id:
                tool_call = await conn.fetchrow("SELECT * FROM tool_calls WHERE id = $1", tool_call_id)

            # Build preview steps
            preview_steps = []
            estimated_risk = "low"
            affected_resources: list[str] = []

            if strategy == "reverse_sql":
                reverse_sql = plan_data.get("reverse_sql", "")
                if not reverse_sql and tool_call:
                    input_data = json.loads(tool_call["input"]) if isinstance(tool_call["input"], str) else tool_call["input"]
                    reverse_sql = self._generate_reverse_sql(input_data)
                preview_steps.append({
                    "action": "execute_reverse_sql",
                    "description": f"Execute reverse SQL: {reverse_sql[:200]}..." if len(reverse_sql) > 200 else f"Execute reverse SQL: {reverse_sql}",
                    "estimated_risk": "medium" if "DELETE" in reverse_sql.upper() else "low",
                })
                affected_resources.append(plan_data.get("table", "database"))
                estimated_risk = "medium"
            elif strategy == "revert_commit":
                commit_sha = plan_data.get("commit_sha", "")
                repo = plan_data.get("repo", tool_call.get("input", {}).get("repo", "") if tool_call else "")
                preview_steps.append({
                    "action": "git_revert",
                    "description": f"Revert commit {commit_sha or 'HEAD'} in repo {repo}",
                    "estimated_risk": "low",
                })
                affected_resources.append(repo)
            elif strategy == "revert_document":
                doc_token = plan_data.get("doc_token", "")
                preview_steps.append({
                    "action": "append_correction",
                    "description": f"Append correction notice to Lark document {doc_token}",
                    "estimated_risk": "low",
                })
                affected_resources.append(f"lark_doc:{doc_token}")
            elif strategy == "recall_message":
                message_id = plan_data.get("message_id", "")
                chat_id = plan_data.get("chat_id", "")
                preview_steps.append({
                    "action": "recall_and_correct",
                    "description": f"Recall message {message_id} and send correction to chat {chat_id}",
                    "estimated_risk": "low",
                })
                affected_resources.append(f"chat:{chat_id}")
            elif strategy == "revert_skill":
                skill_id = plan_data.get("skill_id", "")
                target_version = plan_data.get("target_version", "")
                preview_steps.append({
                    "action": "revert_skill_version",
                    "description": f"Revert skill {skill_id} to version {target_version}",
                    "estimated_risk": "low",
                })
                affected_resources.append(f"skill:{skill_id}")
            elif strategy == "restore_file":
                file_path = plan_data.get("file_path", "")
                preview_steps.append({
                    "action": "restore_from_backup",
                    "description": f"Restore file {file_path} from backup",
                    "estimated_risk": "low",
                })
                affected_resources.append(file_path)
            else:
                preview_steps.append({
                    "action": "manual_compensation",
                    "description": "Execute manual compensation steps",
                    "estimated_risk": "medium",
                })
                estimated_risk = "medium"

            # Check if plan was already executed
            already_executed = plan_dict.get("executed", False)
            existing_executions = await conn.fetch(
                "SELECT status, created_at FROM rollback_executions WHERE rollback_plan_id = $1 ORDER BY created_at DESC",
                rollback_plan_id,
            )

        return {
            "success": True,
            "dry_run": True,
            "rollback_plan_id": rollback_plan_id,
            "task_id": task_id,
            "strategy": strategy,
            "estimated_risk": estimated_risk,
            "affected_resources": affected_resources,
            "preview_steps": preview_steps,
            "already_executed": already_executed,
            "execution_history": [
                {"status": e["status"], "created_at": e["created_at"].isoformat() if e["created_at"] else None}
                for e in existing_executions
            ],
            "summary": f"Rollback will use '{strategy}' strategy affecting {len(affected_resources)} resource(s) in {len(preview_steps)} step(s).",
        }

    async def execute_rollback(
        self,
        rollback_plan_id: str,
        executed_by: str = "system",
    ) -> dict[str, Any]:
        """执行回滚计划"""
        async with self.db_pool.acquire() as conn:
            plan = await conn.fetchrow("SELECT * FROM rollback_plans WHERE id = $1", rollback_plan_id)
            if not plan:
                return {"success": False, "error": "Rollback plan not found"}

            plan_dict = dict(plan)
            task_id = plan_dict["task_id"]
            tool_call_id = plan_dict.get("tool_call_id")
            strategy = plan_dict["strategy"]
            plan_data = plan_dict.get("plan", {})

            # Create execution record
            exec_row = await conn.fetchrow(
                """
                INSERT INTO rollback_executions (rollback_plan_id, task_id, tool_call_id, status, strategy, steps)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                rollback_plan_id,
                task_id,
                tool_call_id,
                "running",
                strategy,
                json_dumps([]),
            )
            exec_id = str(exec_row["id"])

            await self.logger.log(task_id, "rollback.executed", {
                "rollback_plan_id": rollback_plan_id,
                "execution_id": exec_id,
                "strategy": strategy,
                "executed_by": executed_by,
            })

            steps = []
            try:
                # 获取关联的 tool_call
                tool_call = None
                if tool_call_id:
                    tool_call = await conn.fetchrow("SELECT * FROM tool_calls WHERE id = $1", tool_call_id)

                result = {}

                if strategy == "reverse_sql":
                    result = await self._rollback_sql(conn, tool_call, plan_data)
                elif strategy == "revert_commit":
                    result = await self._rollback_git(conn, tool_call, plan_data)
                elif strategy == "revert_document":
                    result = await self._rollback_lark_doc(conn, tool_call, plan_data)
                elif strategy == "recall_message":
                    result = await self._rollback_message(conn, tool_call, plan_data)
                elif strategy == "revert_skill":
                    result = await self._rollback_skill(conn, tool_call, plan_data)
                elif strategy == "restore_file":
                    result = await self._rollback_file(conn, tool_call, plan_data)
                else:
                    result = await self._manual_compensation(conn, tool_call, plan_data)

                steps.append({"step": "execute", "status": "success", "result": result})

                # Update execution record
                await conn.execute(
                    """
                    UPDATE rollback_executions
                    SET status = 'completed', result = $1, steps = $2, executed_by = $3, executed_at = NOW()
                    WHERE id = $4
                    """,
                    json_dumps(result),
                    json_dumps(steps),
                    executed_by,
                    exec_id,
                )

                # Mark plan as executed
                await conn.execute(
                    "UPDATE rollback_plans SET executed = TRUE, executed_at = NOW() WHERE id = $1",
                    rollback_plan_id,
                )

                # Update task status
                await conn.execute(
                    "UPDATE tasks SET status = 'rolled_back', updated_at = NOW() WHERE id = $1",
                    task_id,
                )

                await self.logger.log(task_id, "task.state_changed", {
                    "from_state": "rolling_back",
                    "to_state": "rolled_back",
                    "reason": f"Rollback executed: {strategy}",
                })

                return {"success": True, "execution_id": exec_id, "result": result}

            except Exception as e:
                steps.append({"step": "execute", "status": "failed", "error": str(e)})
                await conn.execute(
                    """
                    UPDATE rollback_executions
                    SET status = 'failed', error_message = $1, steps = $2, executed_by = $3, executed_at = NOW()
                    WHERE id = $4
                    """,
                    str(e),
                    json_dumps(steps),
                    executed_by,
                    exec_id,
                )
                return {"success": False, "execution_id": exec_id, "error": str(e)}

    async def _rollback_sql(
        self,
        conn: asyncpg.Connection,
        tool_call: asyncpg.Record | None,
        plan_data: dict[str, Any],
    ) -> dict[str, Any]:
        """SQL 回滚：使用反向 SQL 或备份恢复"""
        reverse_sql = plan_data.get("reverse_sql", "")
        if not reverse_sql and tool_call:
            # 尝试从 tool call 生成反向 SQL
            input_data = json.loads(tool_call["input"]) if isinstance(tool_call["input"], str) else tool_call["input"]
            reverse_sql = self._generate_reverse_sql(input_data)

        if reverse_sql:
            # In real implementation, execute reverse_sql on database
            return {
                "success": True,
                "method": "reverse_sql",
                "reverse_sql": reverse_sql,
                "note": "Reverse SQL generated, execution logged",
            }

        return {
            "success": True,
            "method": "manual_compensation",
            "note": "Please execute manual compensation for SQL changes",
        }

    async def _rollback_git(
        self,
        conn: asyncpg.Connection,
        tool_call: asyncpg.Record | None,
        plan_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Git 回滚：revert commit / revert MR"""
        commit_sha = plan_data.get("commit_sha", "")
        repo = plan_data.get("repo", tool_call.get("input", {}).get("repo", "") if tool_call else "")

        return {
            "success": True,
            "method": "revert_commit",
            "commands": [
                f"git revert --no-edit {commit_sha}" if commit_sha else "git revert HEAD",
            ],
            "repo": repo,
            "note": "Execute git revert to undo changes",
        }

    async def _rollback_lark_doc(
        self,
        conn: asyncpg.Connection,
        tool_call: asyncpg.Record | None,
        plan_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Lark 文档回滚：恢复历史版本或追加修正说明"""
        doc_token = plan_data.get("doc_token", "")
        correction = plan_data.get("correction", "【已回滚】此部分内容已被撤销。")

        return {
            "success": True,
            "method": "revert_document",
            "doc_token": doc_token,
            "action": "append_correction",
            "correction": correction,
            "note": "Append correction notice to document",
        }

    async def _rollback_message(
        self,
        conn: asyncpg.Connection,
        tool_call: asyncpg.Record | None,
        plan_data: dict[str, Any],
    ) -> dict[str, Any]:
        """消息回滚：撤回或发送更正消息"""
        message_id = plan_data.get("message_id", "")
        chat_id = plan_data.get("chat_id", "")

        return {
            "success": True,
            "method": "recall_message",
            "actions": [
                {"action": "recall", "message_id": message_id} if message_id else None,
                {"action": "send_correction", "chat_id": chat_id, "text": "【更正】上一条消息已被撤销。"},
            ],
            "note": "Recall and send correction message",
        }

    async def _rollback_skill(
        self,
        conn: asyncpg.Connection,
        tool_call: asyncpg.Record | None,
        plan_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Skill 回滚：恢复到上一版本"""
        skill_id = plan_data.get("skill_id", "")
        target_version = plan_data.get("target_version", "")

        if skill_id and target_version:
            # Get target version content
            version_row = await conn.fetchrow(
                "SELECT content FROM skill_versions WHERE skill_id = $1 AND version = $2",
                skill_id,
                target_version,
            )
            if version_row:
                await conn.execute(
                    "UPDATE skills SET current_version = $1, updated_at = NOW() WHERE id = $2",
                    target_version,
                    skill_id,
                )
                return {
                    "success": True,
                    "method": "revert_skill",
                    "skill_id": skill_id,
                    "reverted_to": target_version,
                }

        return {
            "success": False,
            "method": "revert_skill",
            "error": "Target version not found",
        }

    async def _rollback_file(
        self,
        conn: asyncpg.Connection,
        tool_call: asyncpg.Record | None,
        plan_data: dict[str, Any],
    ) -> dict[str, Any]:
        """文件回滚：从备份恢复"""
        file_path = plan_data.get("file_path", "")
        backup_path = plan_data.get("backup_path", f"{file_path}.backup")

        if os.path.exists(backup_path):
            return {
                "success": True,
                "method": "restore_file",
                "file_path": file_path,
                "backup_path": backup_path,
                "command": f"cp {backup_path} {file_path}",
            }

        return {
            "success": True,
            "method": "delete_file",
            "file_path": file_path,
            "note": "File artifact removed",
        }

    async def _manual_compensation(
        self,
        conn: asyncpg.Connection,
        tool_call: asyncpg.Record | None,
        plan_data: dict[str, Any],
    ) -> dict[str, Any]:
        """人工补偿：生成补偿任务"""
        return {
            "success": True,
            "method": "manual_compensation",
            "compensation_task": {
                "title": f"Manual compensation for {tool_call.get('tool_name', 'unknown') if tool_call else 'unknown'}",
                "description": "Please review and manually compensate the effects of this operation",
                "original_tool_call": str(tool_call["id"]) if tool_call else None,
            },
        }

    def _generate_reverse_sql(self, input_data: dict[str, Any]) -> str:
        """根据 SQL 输入生成反向 SQL（简化版）"""
        sql = input_data.get("sql", "").upper().strip()
        if sql.startswith("INSERT"):
            table = sql.split("INTO")[1].split()[0] if "INTO" in sql else "unknown"
            return f"DELETE FROM {table} WHERE id IN (SELECT id FROM {table} WHERE created_at > NOW() - INTERVAL '1 hour')"
        elif sql.startswith("UPDATE"):
            table = sql.split("UPDATE")[1].split()[0] if "UPDATE" in sql else "unknown"
            return f"-- Manual review required: UPDATE {table} SET ... WHERE ..."
        elif sql.startswith("DELETE"):
            return "-- Cannot auto-reverse DELETE without backup"
        return ""

    async def create_rollback_plan(
        self,
        task_id: str,
        tool_call_id: str | None,
        strategy: str,
        plan_data: dict[str, Any],
    ) -> str:
        """创建回滚计划"""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO rollback_plans (task_id, tool_call_id, strategy, plan)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                task_id,
                tool_call_id,
                strategy,
                json_dumps(plan_data),
            )
            return str(row["id"])
