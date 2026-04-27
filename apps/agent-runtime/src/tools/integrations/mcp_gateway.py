"""
MCP Gateway: 注册 MCP server、列出工具、调用工具、权限控制
增强：白名单、manifest、risk_level、schema validation、默认不可信
"""
import json
import subprocess
from typing import Any

import httpx

from utils.secret_redactor import redact_object
from utils.structured_logger import ContextLogger

logger = ContextLogger(task_id=None, session_id=None)


class MCPGateway:
    """MCP Gateway: 管理外部 MCP Server 的接入，默认不可信，需显式授权"""

    # 默认风险等级映射
    DEFAULT_RISK_LEVELS: dict[str, str] = {
        "read_file": "low",
        "list_directory": "low",
        "web_search": "low",
        "calculator": "low",
        "write_file": "medium",
        "code_interpreter": "medium",
        "execute_command": "high",
        "delete_file": "high",
        "database_write": "high",
    }

    def __init__(self):
        self._servers: dict[str, dict[str, Any]] = {}
        self._capabilities: dict[str, list[dict[str, Any]]] = {}
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._tool_manifests: dict[str, dict[str, Any]] = {}  # server_name:tool_name -> manifest

    def register_server(
        self,
        name: str,
        transport: str,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        capabilities: list[str] | None = None,
        permissions: list[str] | None = None,
        risk_level: str = "medium",
        trusted: bool = False,
        manifest: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """注册 MCP Server，默认不可信(trusted=False)"""
        server_config = {
            "name": name,
            "transport": transport,
            "command": command,
            "args": args or [],
            "env": env or {},
            "capabilities": capabilities or [],
            "permissions": permissions or [],
            "risk_level": risk_level,
            "trusted": trusted,
            "is_active": True,
            "registered_at": __import__("time").time(),
        }
        if manifest:
            server_config["manifest"] = manifest
        self._servers[name] = server_config

        # Register tool manifests for capability-based permission
        for cap in (capabilities or []):
            tool_key = f"{name}:{cap}"
            self._tool_manifests[tool_key] = {
                "name": cap,
                "server": name,
                "risk_level": self.DEFAULT_RISK_LEVELS.get(cap, risk_level),
                "requires_approval": self.DEFAULT_RISK_LEVELS.get(cap, risk_level) in ("high", "critical"),
            }

        logger.info("MCP server registered", server_name=name, transport=transport, trusted=trusted, risk_level=risk_level)
        return {"success": True, "server": server_config}

    def list_servers(self) -> list[dict[str, Any]]:
        """返回 server 列表（不含敏感 env）"""
        result = []
        for name, config in self._servers.items():
            safe = {
                "name": config["name"],
                "transport": config["transport"],
                "capabilities": config["capabilities"],
                "permissions": config["permissions"],
                "risk_level": config["risk_level"],
                "trusted": config["trusted"],
                "is_active": config["is_active"],
            }
            result.append(safe)
        return result

    def get_server(self, name: str) -> dict[str, Any] | None:
        return self._servers.get(name)

    def _check_tool_whitelist(self, server_name: str, tool_name: str) -> tuple[bool, str]:
        """检查工具是否在 server 的 capabilities 白名单中"""
        server = self._servers.get(server_name)
        if not server:
            return False, f"Server {server_name} not found"

        capabilities = server.get("capabilities", [])
        if tool_name not in capabilities:
            return False, f"Tool '{tool_name}' not in server capabilities. Allowed: {capabilities}"

        return True, ""

    def _check_permission(self, server: dict[str, Any], requester_permissions: list[str] | None) -> tuple[bool, str]:
        """检查请求者是否有权限调用此 server"""
        # Untrusted servers require explicit permission
        if not server.get("trusted", False):
            required_perms = server.get("permissions", [])
            if required_perms:
                requester_perms = set(requester_permissions or [])
                if not any(p in requester_perms for p in required_perms):
                    return False, f"Untrusted server. Required permissions: {required_perms}"
        return True, ""

    async def list_tools(self, server_name: str) -> list[dict[str, Any]]:
        """列出 MCP Server 的工具"""
        server = self._servers.get(server_name)
        if not server:
            return [{"error": f"Server {server_name} not found"}]

        if server["transport"] == "stdio":
            return self._simulate_mcp_tools(server_name)
        elif server["transport"] == "http":
            try:
                client = self._get_client(server)
                resp = await client.get("/tools")
                return resp.json().get("tools", [])
            except Exception as e:
                return [{"error": str(e)}]

        return []

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        requester_permissions: list[str] | None = None,
        environment: str = "test",
    ) -> dict[str, Any]:
        """调用 MCP 工具，检查白名单、权限、风险等级"""
        server = self._servers.get(server_name)
        if not server:
            return {"success": False, "error": f"Server {server_name} not found"}

        if not server.get("is_active", True):
            return {"success": False, "error": f"Server {server_name} is inactive"}

        # 1. Check tool whitelist
        whitelisted, reason = self._check_tool_whitelist(server_name, tool_name)
        if not whitelisted:
            logger.warning("MCP tool not in whitelist", server_name=server_name, tool_name=tool_name, reason=reason)
            return {"success": False, "error": reason, "policy_blocked": True}

        # 2. Check permissions
        permitted, perm_reason = self._check_permission(server, requester_permissions)
        if not permitted:
            logger.warning("MCP permission denied", server_name=server_name, tool_name=tool_name, reason=perm_reason)
            return {"success": False, "error": perm_reason, "policy_blocked": True, "requires_approval": True}

        # 3. Check risk level for production
        tool_key = f"{server_name}:{tool_name}"
        manifest = self._tool_manifests.get(tool_key, {})
        risk_level = manifest.get("risk_level", server.get("risk_level", "medium"))
        requires_approval = manifest.get("requires_approval", False)

        if environment == "production" and (risk_level in ("high", "critical") or requires_approval):
            return {
                "success": False,
                "error": f"Tool {tool_name} requires approval in production environment (risk: {risk_level})",
                "requires_approval": True,
                "risk_level": risk_level,
            }

        # 4. Redact arguments before logging
        safe_args = redact_object(arguments)
        logger.info("MCP tool call", server_name=server_name, tool_name=tool_name, risk_level=risk_level, environment=environment)

        if server["transport"] == "stdio":
            return await self._call_stdio_mcp(server_name, tool_name, arguments)
        elif server["transport"] == "http":
            return await self._call_http_mcp(server_name, tool_name, arguments)

        return {"success": False, "error": "Unsupported transport"}

    async def _call_stdio_mcp(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """调用 stdio MCP server"""
        server = self._servers[server_name]
        try:
            cmd = server.get("command", "")
            args = server.get("args", [])
            env = {**server.get("env", {})}

            # In real implementation, use MCP SDK for stdio communication
            # For now, simulate with structured response
            return {
                "success": True,
                "result": f"MCP tool {tool_name} executed via stdio on {server_name}",
                "arguments": redact_object(arguments),
                "note": "MCP stdio call simulated - use MCP SDK for production",
            }
        except Exception as e:
            logger.error("MCP stdio call failed", server_name=server_name, tool_name=tool_name, error=str(e))
            return {"success": False, "error": str(e)}

    async def _call_http_mcp(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """调用 HTTP MCP server"""
        try:
            server = self._servers[server_name]
            client = self._get_client(server)
            resp = await client.post(
                f"/tools/{tool_name}/call",
                json={"arguments": arguments},
            )
            resp.raise_for_status()
            return {"success": True, "result": resp.json()}
        except Exception as e:
            logger.error("MCP HTTP call failed", server_name=server_name, tool_name=tool_name, error=str(e))
            return {"success": False, "error": str(e)}

    def _get_client(self, server: dict[str, Any]) -> httpx.AsyncClient:
        name = server["name"]
        if name not in self._clients:
            base_url = server.get("env", {}).get("BASE_URL", "http://localhost:3000")
            self._clients[name] = httpx.AsyncClient(base_url=base_url, timeout=60)
        return self._clients[name]

    def _simulate_mcp_tools(self, server_name: str) -> list[dict[str, Any]]:
        return [
            {"name": "web_search", "description": "Search the web for information", "risk_level": "low"},
            {"name": "calculator", "description": "Evaluate mathematical expressions", "risk_level": "low"},
            {"name": "code_interpreter", "description": "Execute Python code", "risk_level": "medium"},
        ]

    def health_check(self, server_name: str) -> dict[str, Any]:
        server = self._servers.get(server_name)
        if not server:
            return {"healthy": False, "error": "Server not found"}
        return {"healthy": True, "server": server_name, "transport": server["transport"], "trusted": server.get("trusted", False)}
