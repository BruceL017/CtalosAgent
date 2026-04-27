"""
Supabase Adapter: 数据库读写、SQL 执行
区分 test / production 环境，生产写操作需审批
"""
import os
from typing import Any

import httpx


class RealSupabaseAdapter:
    def __init__(self, url: str | None = None, service_key: str | None = None, anon_key: str | None = None):
        self.url = (url or os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.service_key = service_key or os.getenv("SUPABASE_SERVICE_KEY", "")
        self.anon_key = anon_key or os.getenv("SUPABASE_ANON_KEY", "")
        self.headers = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
        }
        self.client = httpx.AsyncClient(base_url=self.url, headers=self.headers, timeout=60)

    async def execute_sql(self, sql: str, environment: str = "test") -> dict[str, Any]:
        """执行 SQL（通过 PostgREST 的 RPC 或直接使用 SQL API）"""
        # 简化实现：使用 Supabase REST API 查询
        # 真实场景应使用 pg API 或 Supabase 的 execute_sql RPC
        if not self.url or not self.service_key:
            return {"success": False, "error": "Supabase not configured"}

        try:
            # 对于 SELECT 使用 PostgREST
            if sql.strip().upper().startswith("SELECT"):
                # Extract table name (simplified)
                parts = sql.upper().split("FROM")
                if len(parts) > 1:
                    table = parts[1].split()[0].strip()
                    response = await self.client.get(f"/rest/v1/{table}", params={"limit": 10})
                    response.raise_for_status()
                    return {"success": True, "data": response.json(), "environment": environment}

            # 写操作需要环境检查
            destructive_keywords = ["DELETE", "DROP", "TRUNCATE", "ALTER", "UPDATE"]
            is_destructive = any(kw in sql.upper() for kw in destructive_keywords)

            if environment == "production" and is_destructive:
                return {
                    "success": False,
                    "error": "Destructive SQL in production requires approval",
                    "requires_approval": True,
                    "environment": environment,
                }

            # 模拟执行（真实场景应通过 SQL API 或 pg connection）
            return {
                "success": True,
                "sql": sql,
                "environment": environment,
                "note": "SQL execution simulated - use pg connection for real execution",
                "rows_affected": 0,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def query(self, table: str, filters: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        try:
            params: dict[str, Any] = {"limit": limit}
            if filters:
                for key, value in filters.items():
                    params[key] = f"eq.{value}"
            response = await self.client.get(f"/rest/v1/{table}", params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return [{"error": str(e)}]

    async def insert(self, table: str, data: dict[str, Any] | list[dict[str, Any]], environment: str = "test") -> dict[str, Any]:
        if environment == "production":
            return {"success": False, "error": "Insert in production requires approval", "requires_approval": True}
        try:
            response = await self.client.post(f"/rest/v1/{table}", json=data, headers={**self.headers, "Prefer": "return=representation"})
            response.raise_for_status()
            return {"success": True, "data": response.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}
