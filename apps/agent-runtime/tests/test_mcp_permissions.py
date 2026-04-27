"""Test MCP Gateway permissions, whitelist, and risk levels."""
import pytest

from tools.integrations.mcp_gateway import MCPGateway


@pytest.fixture
def gateway():
    g = MCPGateway()
    g.register_server(
        name="filesystem",
        transport="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        capabilities=["read_file", "list_directory"],
        permissions=["file_access"],
        risk_level="medium",
        trusted=False,
    )
    g.register_server(
        name="trusted_search",
        transport="stdio",
        command="echo",
        args=["test"],
        capabilities=["web_search"],
        risk_level="low",
        trusted=True,
    )
    return g


class TestMCPPermissions:
    @pytest.mark.asyncio
    async def test_tool_not_in_whitelist(self, gateway):
        result = await gateway.call_tool(
            "filesystem", "write_file", {"path": "/tmp/test.txt", "content": "x"},
        )
        assert result["success"] is False
        assert result["policy_blocked"] is True
        assert "not in server capabilities" in result["error"]

    @pytest.mark.asyncio
    async def test_untrusted_server_requires_permission(self, gateway):
        result = await gateway.call_tool(
            "filesystem", "read_file", {"path": "/tmp/test.txt"},
            requester_permissions=[],  # no file_access
        )
        assert result["success"] is False
        assert result["policy_blocked"] is True
        assert "Untrusted server" in result["error"]

    @pytest.mark.asyncio
    async def test_untrusted_server_with_permission(self, gateway):
        result = await gateway.call_tool(
            "filesystem", "read_file", {"path": "/tmp/test.txt"},
            requester_permissions=["file_access"],
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_trusted_server_no_permission_needed(self, gateway):
        result = await gateway.call_tool(
            "trusted_search", "web_search", {"query": "test"},
            requester_permissions=[],
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_production_high_risk_requires_approval(self, gateway):
        gateway.register_server(
            name="dangerous",
            transport="stdio",
            capabilities=["execute_command"],
            risk_level="high",
            trusted=False,
        )
        result = await gateway.call_tool(
            "dangerous", "execute_command", {"cmd": "rm -rf /"},
            requester_permissions=["admin"],
            environment="production",
        )
        assert result["success"] is False
        assert result["requires_approval"] is True
        assert "production" in result["error"]

    @pytest.mark.asyncio
    async def test_server_not_found(self, gateway):
        result = await gateway.call_tool("nonexistent", "tool", {})
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_server_list_no_secrets(self, gateway):
        servers = gateway.list_servers()
        for s in servers:
            assert "env" not in s
            assert "command" not in s or s.get("command") != "npx"

    def test_health_check(self, gateway):
        health = gateway.health_check("filesystem")
        assert health["healthy"] is True
        assert health["trusted"] is False
