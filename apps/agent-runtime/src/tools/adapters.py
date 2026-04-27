"""
Adapter Interfaces for external integrations.
All real integrations are stubbed with mock adapters in Phase 1.
"""
from abc import ABC, abstractmethod
from typing import Any, Protocol


class LarkAdapter(ABC):
    """飞书 Lark Adapter 接口"""

    @abstractmethod
    async def write_doc(self, doc_token: str, content: str) -> dict[str, Any]:
        ...

    @abstractmethod
    async def send_message(self, chat_id: str, message: str) -> dict[str, Any]:
        ...

    @abstractmethod
    async def create_task(self, title: str, description: str) -> dict[str, Any]:
        ...


class GitHubAdapter(ABC):
    """GitHub Adapter 接口"""

    @abstractmethod
    async def create_issue(self, repo: str, title: str, body: str) -> dict[str, Any]:
        ...

    @abstractmethod
    async def create_pr(self, repo: str, title: str, head: str, base: str) -> dict[str, Any]:
        ...

    @abstractmethod
    async def get_repo_files(self, repo: str, path: str = "") -> list[dict[str, Any]]:
        ...


class SupabaseAdapter(ABC):
    """Supabase Adapter 接口"""

    @abstractmethod
    async def execute_sql(self, sql: str, environment: str = "test") -> dict[str, Any]:
        ...

    @abstractmethod
    async def query(self, table: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        ...


class TelegramAdapter(ABC):
    """Telegram Adapter 接口"""

    @abstractmethod
    async def send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        ...


class MCPGatewayAdapter(ABC):
    """MCP Gateway Adapter 接口"""

    @abstractmethod
    async def list_tools(self, server_name: str) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        ...
