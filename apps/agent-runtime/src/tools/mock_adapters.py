"""
Mock Adapters for Phase 1.
All external integrations return simulated responses without making real API calls.
"""
import asyncio
from typing import Any

from .adapters import LarkAdapter, GitHubAdapter, SupabaseAdapter, TelegramAdapter, MCPGatewayAdapter


class MockLarkAdapter(LarkAdapter):
    async def write_doc(self, doc_token: str, content: str) -> dict[str, Any]:
        await asyncio.sleep(0.1)
        return {
            "success": True,
            "doc_token": doc_token,
            "revision": 2,
            "mock": True,
            "note": "Lark doc write simulated",
        }

    async def send_message(self, receive_id: str, content: str, msg_type: str = "text", receive_id_type: str = "chat_id") -> dict[str, Any]:
        await asyncio.sleep(0.05)
        return {
            "success": True,
            "message_id": f"mock_msg_{int(asyncio.get_event_loop().time())}",
            "receive_id": receive_id,
            "mock": True,
        }

    async def create_task(self, title: str, description: str) -> dict[str, Any]:
        await asyncio.sleep(0.1)
        return {
            "success": True,
            "task_id": f"mock_lark_task_{int(asyncio.get_event_loop().time())}",
            "title": title,
            "mock": True,
        }


class MockGitHubAdapter(GitHubAdapter):
    async def create_issue(self, repo: str, title: str, body: str) -> dict[str, Any]:
        await asyncio.sleep(0.15)
        return {
            "success": True,
            "issue_number": 42,
            "repo": repo,
            "title": title,
            "mock": True,
        }

    async def create_branch(self, repo: str, branch: str, from_branch: str = "main") -> dict[str, Any]:
        await asyncio.sleep(0.15)
        return {
            "success": True,
            "branch": branch,
            "repo": repo,
            "mock": True,
        }

    async def create_commit(self, repo: str, branch: str, message: str, files: dict[str, str]) -> dict[str, Any]:
        await asyncio.sleep(0.15)
        return {
            "success": True,
            "commit_sha": f"mock_sha_{int(asyncio.get_event_loop().time())}",
            "repo": repo,
            "mock": True,
        }

    async def create_pr(self, repo: str, title: str, head: str, base: str, body: str = "") -> dict[str, Any]:
        await asyncio.sleep(0.15)
        return {
            "success": True,
            "pr_number": 7,
            "repo": repo,
            "title": title,
            "mock": True,
        }

    async def merge_pr(self, repo: str, pr_number: int, commit_message: str = "") -> dict[str, Any]:
        await asyncio.sleep(0.15)
        return {
            "success": True,
            "pr_number": pr_number,
            "repo": repo,
            "mock": True,
        }

    async def revert_commit(self, repo: str, commit_sha: str, branch: str = "main") -> dict[str, Any]:
        await asyncio.sleep(0.15)
        return {
            "success": True,
            "commit_sha": commit_sha,
            "repo": repo,
            "mock": True,
        }

    async def get_repo_files(self, repo: str, path: str = "") -> list[dict[str, Any]]:
        await asyncio.sleep(0.1)
        return [
            {"name": "README.md", "path": f"{path}README.md", "type": "file"},
            {"name": "src", "path": f"{path}src", "type": "dir"},
            {"name": "package.json", "path": f"{path}package.json", "type": "file"},
        ]


class MockSupabaseAdapter(SupabaseAdapter):
    async def execute_sql(self, sql: str, environment: str = "test") -> dict[str, Any]:
        await asyncio.sleep(0.2)
        if environment == "production" and "DELETE" in sql.upper():
            return {
                "success": False,
                "error": "Destructive SQL in production requires approval",
                "mock": True,
            }
        return {
            "success": True,
            "rows_affected": 1,
            "sql": sql,
            "environment": environment,
            "mock": True,
        }

    async def query(self, table: str, filters: dict[str, Any] | None = None, limit: int = 100) -> dict[str, Any]:
        await asyncio.sleep(0.1)
        return {
            "success": True,
            "data": [
                {"id": 1, "name": "Sample Record", "mock": True},
                {"id": 2, "name": "Another Record", "mock": True},
            ],
            "table": table,
            "mock": True,
        }


class MockTelegramAdapter(TelegramAdapter):
    async def send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        return {
            "success": True,
            "message_id": f"mock_tg_{int(asyncio.get_event_loop().time())}",
            "chat_id": chat_id,
            "mock": True,
        }


class MockMCPGatewayAdapter(MCPGatewayAdapter):
    async def list_tools(self, server_name: str) -> list[dict[str, Any]]:
        await asyncio.sleep(0.1)
        return [
            {"name": "web_search", "description": "Search the web"},
            {"name": "calculator", "description": "Evaluate math expressions"},
        ]

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.2)
        return {
            "success": True,
            "result": f"Mock MCP result for {tool_name} from {server_name}",
            "arguments": arguments,
            "mock": True,
        }


def get_mock_adapters() -> dict[str, Any]:
    return {
        "lark": MockLarkAdapter(),
        "github": MockGitHubAdapter(),
        "supabase": MockSupabaseAdapter(),
        "telegram": MockTelegramAdapter(),
        "mcp": MockMCPGatewayAdapter(),
    }
