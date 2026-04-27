"""
Tool Registry: all tools must be registered with manifest.
Supports both mock and real adapters.
"""
import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .integrations.github_adapter import RealGitHubAdapter
from .integrations.supabase_adapter import RealSupabaseAdapter
from .integrations.lark_adapter import RealLarkAdapter
from .integrations.telegram_adapter import RealTelegramAdapter
from .integrations.mcp_gateway import MCPGateway
from .mock_adapters import (
    MockGitHubAdapter,
    MockSupabaseAdapter,
    MockLarkAdapter,
    MockTelegramAdapter,
    MockMCPGatewayAdapter,
)


@dataclass
class ToolManifest:
    name: str
    owner: str
    risk_level: str
    environment: list[str] = field(default_factory=lambda: ["test"])
    requires_approval_on: list[str] = field(default_factory=list)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    rollback_strategy: str = "manual_compensation"
    timeout_seconds: int = 60
    description: str = ""
    estimated_blast_radius: str = "none"


ToolHandler = Callable[..., Awaitable[dict[str, Any]]]


class ToolRegistry:
    _tools: dict[str, ToolManifest] = {}
    _handlers: dict[str, ToolHandler] = {}
    _adapters: dict[str, Any] | None = None
    _mcp_gateway: MCPGateway | None = None
    _use_real: bool = os.getenv("USE_REAL_ADAPTERS", "false").lower() == "true"

    @classmethod
    def get_adapters(cls) -> dict[str, Any]:
        if cls._adapters is None:
            if cls._use_real:
                cls._adapters = {
                    "github": RealGitHubAdapter(),
                    "supabase": RealSupabaseAdapter(),
                    "lark": RealLarkAdapter(),
                    "telegram": RealTelegramAdapter(),
                    "mcp": cls.get_mcp_gateway(),
                }
            else:
                cls._adapters = {
                    "github": MockGitHubAdapter(),
                    "supabase": MockSupabaseAdapter(),
                    "lark": MockLarkAdapter(),
                    "telegram": MockTelegramAdapter(),
                    "mcp": MockMCPGatewayAdapter(),
                }
        return cls._adapters

    @classmethod
    def get_mcp_gateway(cls) -> MCPGateway:
        if cls._mcp_gateway is None:
            cls._mcp_gateway = MCPGateway()
            # Register default MCP servers
            cls._mcp_gateway.register_server(
                name="filesystem",
                transport="stdio",
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                capabilities=["read_file", "write_file", "list_directory"],
                permissions=["file_access"],
            )
        return cls._mcp_gateway

    @classmethod
    def register(cls, manifest: ToolManifest, handler: ToolHandler) -> None:
        cls._tools[manifest.name] = manifest
        cls._handlers[manifest.name] = handler

    @classmethod
    def get(cls, name: str) -> ToolManifest | None:
        return cls._tools.get(name)

    @classmethod
    def get_handler(cls, name: str) -> ToolHandler | None:
        return cls._handlers.get(name)

    @classmethod
    def list_tools(cls) -> list[ToolManifest]:
        return list(cls._tools.values())

    @classmethod
    def requires_approval(cls, name: str, environment: str) -> bool:
        manifest = cls._tools.get(name)
        if not manifest:
            return False
        if environment in manifest.requires_approval_on:
            return True
        if "production" in manifest.requires_approval_on and environment == "production":
            return True
        return False


# =====================================================
# Internal tools
# =====================================================

async def _mock_analyze(args: dict[str, Any]) -> dict[str, Any]:
    data = args.get("data", [])
    return {
        "success": True,
        "summary": f"Analyzed {len(data)} records",
        "insights": ["Trend shows positive growth", "Anomaly detected in Q3", "User engagement up 15%"],
        "mock": not ToolRegistry._use_real,
    }


async def _file_write(args: dict[str, Any]) -> dict[str, Any]:
    import os as os_mod
    artifacts_dir = os.environ.get("ARTIFACTS_DIR", "/app/artifacts")
    filename = args.get("filename", f"artifact_{int(__import__('time').time())}.txt")
    content = args.get("content", "")
    filepath = os_mod.path.join(artifacts_dir, filename)
    os_mod.makedirs(artifacts_dir, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return {
        "success": True,
        "file_path": filepath,
        "bytes_written": len(content.encode("utf-8")),
    }


async def _file_read(args: dict[str, Any]) -> dict[str, Any]:
    filepath = args.get("path", "")
    if not filepath or not __import__("os").path.exists(filepath):
        return {"success": False, "error": "File not found"}
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return {"success": True, "content": content}


async def _github_create_issue(args: dict[str, Any]) -> dict[str, Any]:
    adapters = ToolRegistry.get_adapters()
    return await adapters["github"].create_issue(
        args.get("repo", os.getenv("GITHUB_DEFAULT_REPO", "")),
        args.get("title", ""),
        args.get("body", ""),
        args.get("labels"),
    )


async def _github_create_branch(args: dict[str, Any]) -> dict[str, Any]:
    adapters = ToolRegistry.get_adapters()
    return await adapters["github"].create_branch(
        args.get("repo", os.getenv("GITHUB_DEFAULT_REPO", "")),
        args.get("branch", ""),
        args.get("from_branch", "main"),
    )


async def _github_create_commit(args: dict[str, Any]) -> dict[str, Any]:
    adapters = ToolRegistry.get_adapters()
    return await adapters["github"].create_commit(
        args.get("repo", os.getenv("GITHUB_DEFAULT_REPO", "")),
        args.get("branch", "main"),
        args.get("message", ""),
        args.get("files", {}),
    )


async def _github_create_pr(args: dict[str, Any]) -> dict[str, Any]:
    adapters = ToolRegistry.get_adapters()
    return await adapters["github"].create_pr(
        args.get("repo", os.getenv("GITHUB_DEFAULT_REPO", "")),
        args.get("title", ""),
        args.get("head", ""),
        args.get("base", "main"),
        args.get("body", ""),
    )


async def _github_merge_pr(args: dict[str, Any]) -> dict[str, Any]:
    adapters = ToolRegistry.get_adapters()
    return await adapters["github"].merge_pr(
        args.get("repo", os.getenv("GITHUB_DEFAULT_REPO", "")),
        args.get("pr_number", 0),
        args.get("commit_message", ""),
    )


async def _github_revert_commit(args: dict[str, Any]) -> dict[str, Any]:
    adapters = ToolRegistry.get_adapters()
    return await adapters["github"].revert_commit(
        args.get("repo", os.getenv("GITHUB_DEFAULT_REPO", "")),
        args.get("commit_sha", ""),
        args.get("branch", "main"),
    )


async def _github_get_repo_files(args: dict[str, Any]) -> dict[str, Any]:
    adapters = ToolRegistry.get_adapters()
    files = await adapters["github"].get_repo_files(
        args.get("repo", os.getenv("GITHUB_DEFAULT_REPO", "")),
        args.get("path", ""),
        args.get("ref", "main"),
    )
    return {"success": True, "files": files}


async def _supabase_execute_sql(args: dict[str, Any]) -> dict[str, Any]:
    adapters = ToolRegistry.get_adapters()
    return await adapters["supabase"].execute_sql(
        args.get("sql", ""),
        args.get("environment", "test"),
    )


async def _supabase_query(args: dict[str, Any]) -> dict[str, Any]:
    adapters = ToolRegistry.get_adapters()
    result = await adapters["supabase"].query(
        args.get("table", ""),
        args.get("filters"),
        args.get("limit", 100),
    )
    if isinstance(result, list):
        return {"success": True, "data": result}
    return result


async def _lark_write_doc(args: dict[str, Any]) -> dict[str, Any]:
    adapters = ToolRegistry.get_adapters()
    return await adapters["lark"].write_doc(
        args.get("doc_token", ""),
        args.get("content", ""),
        args.get("block_type", 1),
    )


async def _lark_send_message(args: dict[str, Any]) -> dict[str, Any]:
    adapters = ToolRegistry.get_adapters()
    return await adapters["lark"].send_message(
        args.get("receive_id", ""),
        args.get("content", ""),
        args.get("msg_type", "text"),
        args.get("receive_id_type", "chat_id"),
    )


async def _lark_create_task(args: dict[str, Any]) -> dict[str, Any]:
    adapters = ToolRegistry.get_adapters()
    return await adapters["lark"].create_task(
        args.get("title", ""),
        args.get("description", ""),
        args.get("followers"),
    )


async def _telegram_send(args: dict[str, Any]) -> dict[str, Any]:
    adapters = ToolRegistry.get_adapters()
    return await adapters["telegram"].send_message(
        args.get("chat_id", os.getenv("TELEGRAM_DEFAULT_CHAT_ID", "")),
        args.get("text", ""),
    )


async def _mcp_call_tool(args: dict[str, Any]) -> dict[str, Any]:
    gateway = ToolRegistry.get_mcp_gateway()
    return await gateway.call_tool(
        args.get("server_name", ""),
        args.get("tool_name", ""),
        args.get("arguments", {}),
        args.get("requester_permissions"),
    )


async def _mcp_list_tools(args: dict[str, Any]) -> dict[str, Any]:
    gateway = ToolRegistry.get_mcp_gateway()
    tools = await gateway.list_tools(args.get("server_name", ""))
    return {"success": True, "tools": tools}


# =====================================================
# Register all tools
# =====================================================

ToolRegistry.register(
    ToolManifest(name="mock.analyze", owner="data", risk_level="low", environment=["test", "production"], description="Data analysis", rollback_strategy="snapshot"),
    _mock_analyze,
)

ToolRegistry.register(
    ToolManifest(name="file.write", owner="system", risk_level="low", environment=["test", "production"], description="Write artifact file", rollback_strategy="snapshot"),
    _file_write,
)

ToolRegistry.register(
    ToolManifest(name="file.read", owner="system", risk_level="low", environment=["test", "production"], description="Read file", rollback_strategy="snapshot"),
    _file_read,
)

ToolRegistry.register(
    ToolManifest(name="github.create_issue", owner="integration", risk_level="medium", environment=["test", "production"], requires_approval_on=["production"], description="Create GitHub issue", rollback_strategy="manual_compensation"),
    _github_create_issue,
)

ToolRegistry.register(
    ToolManifest(name="github.create_branch", owner="integration", risk_level="low", environment=["test", "production"], description="Create GitHub branch", rollback_strategy="snapshot"),
    _github_create_branch,
)

ToolRegistry.register(
    ToolManifest(name="github.create_commit", owner="integration", risk_level="medium", environment=["test", "production"], requires_approval_on=["production"], description="Create GitHub commit", rollback_strategy="revert_commit"),
    _github_create_commit,
)

ToolRegistry.register(
    ToolManifest(name="github.create_pr", owner="integration", risk_level="medium", environment=["test", "production"], requires_approval_on=["production"], description="Create GitHub PR", rollback_strategy="manual_compensation"),
    _github_create_pr,
)

ToolRegistry.register(
    ToolManifest(name="github.merge_pr", owner="integration", risk_level="high", environment=["test"], requires_approval_on=["production"], description="Merge GitHub PR", rollback_strategy="revert_commit", estimated_blast_radius="org_wide"),
    _github_merge_pr,
)

ToolRegistry.register(
    ToolManifest(name="github.revert_commit", owner="integration", risk_level="medium", environment=["test", "production"], description="Revert GitHub commit", rollback_strategy="manual_compensation"),
    _github_revert_commit,
)

ToolRegistry.register(
    ToolManifest(name="github.get_repo_files", owner="integration", risk_level="low", environment=["test", "production"], description="List repo files", rollback_strategy="snapshot"),
    _github_get_repo_files,
)

ToolRegistry.register(
    ToolManifest(name="supabase.execute_sql", owner="data", risk_level="high", environment=["test"], requires_approval_on=["production"], description="Execute SQL", rollback_strategy="reverse_sql"),
    _supabase_execute_sql,
)

ToolRegistry.register(
    ToolManifest(name="supabase.query", owner="data", risk_level="low", environment=["test", "production"], description="Query data", rollback_strategy="snapshot"),
    _supabase_query,
)

ToolRegistry.register(
    ToolManifest(name="lark.write_doc", owner="integration", risk_level="medium", environment=["test", "production"], requires_approval_on=["production"], description="Write Lark doc", rollback_strategy="revert_document"),
    _lark_write_doc,
)

ToolRegistry.register(
    ToolManifest(name="lark.send_message", owner="integration", risk_level="low", environment=["test", "production"], description="Send Lark message", rollback_strategy="recall_message"),
    _lark_send_message,
)

ToolRegistry.register(
    ToolManifest(name="lark.create_task", owner="integration", risk_level="low", environment=["test", "production"], description="Create Lark task", rollback_strategy="manual_compensation"),
    _lark_create_task,
)

ToolRegistry.register(
    ToolManifest(name="telegram.send", owner="integration", risk_level="low", environment=["test", "production"], description="Send Telegram message", rollback_strategy="recall_message"),
    _telegram_send,
)

ToolRegistry.register(
    ToolManifest(name="mcp.call_tool", owner="integration", risk_level="medium", environment=["test", "production"], description="Call MCP tool", rollback_strategy="manual_compensation"),
    _mcp_call_tool,
)

ToolRegistry.register(
    ToolManifest(name="mcp.list_tools", owner="integration", risk_level="low", environment=["test", "production"], description="List MCP tools", rollback_strategy="snapshot"),
    _mcp_list_tools,
)
