"""
Lark / 飞书 Adapter: 文档写入、任务创建、消息发送
"""
import json
import os
from typing import Any

import httpx


class RealLarkAdapter:
    def __init__(self, app_id: str | None = None, app_secret: str | None = None):
        self.app_id = app_id or os.getenv("LARK_APP_ID", "")
        self.app_secret = app_secret or os.getenv("LARK_APP_SECRET", "")
        self.base_url = "https://open.feishu.cn/open-apis"
        self._tenant_access_token: str | None = None
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=60)

    async def _get_token(self) -> str:
        if self._tenant_access_token:
            return self._tenant_access_token
        resp = await self.client.post(
            "/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        resp.raise_for_status()
        data = resp.json()
        self._tenant_access_token = data["tenant_access_token"]
        return self._tenant_access_token

    async def write_doc(self, doc_token: str, content: str, block_type: int = 1) -> dict[str, Any]:
        """block_type: 1=text, 2=heading1, 3=heading2, 4=heading3"""
        try:
            token = await self._get_token()
            headers = {"Authorization": f"Bearer {token}"}

            # Lark doc API: append blocks
            resp = await self.client.post(
                f"/docx/v1/documents/{doc_token}/blocks/{doc_token}/children",
                headers=headers,
                json={
                    "children": [
                        {
                            "block_type": block_type,
                            "text": {"elements": [{"text_run": {"content": content}}]},
                        }
                    ],
                    "index": 0,
                },
            )
            resp.raise_for_status()
            return {"success": True, "doc_token": doc_token, "data": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def send_message(self, receive_id: str, content: str, msg_type: str = "text", receive_id_type: str = "chat_id") -> dict[str, Any]:
        try:
            token = await self._get_token()
            headers = {"Authorization": f"Bearer {token}"}

            msg_content = json.dumps({"text": content}) if msg_type == "text" else content

            resp = await self.client.post(
                "/im/v1/messages",
                headers=headers,
                params={"receive_id_type": receive_id_type},
                json={
                    "receive_id": receive_id,
                    "msg_type": msg_type,
                    "content": msg_content,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {"success": True, "message_id": data["data"]["message_id"], "data": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def create_task(self, title: str, description: str = "", followers: list[str] | None = None) -> dict[str, Any]:
        try:
            token = await self._get_token()
            headers = {"Authorization": f"Bearer {token}"}

            resp = await self.client.post(
                "/task/v2/tasks",
                headers=headers,
                json={
                    "summary": title,
                    "description": description,
                    "followers": followers or [],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {"success": True, "task_id": data["data"]["task"]["guid"], "data": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_doc_blocks(self, doc_token: str) -> dict[str, Any]:
        try:
            token = await self._get_token()
            headers = {"Authorization": f"Bearer {token}"}
            resp = await self.client.get(
                f"/docx/v1/documents/{doc_token}/blocks",
                headers=headers,
            )
            resp.raise_for_status()
            return {"success": True, "data": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}
