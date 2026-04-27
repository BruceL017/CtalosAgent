"""
Telegram Adapter: 消息发送
"""
import os
from typing import Any

import httpx


class RealTelegramAdapter:
    def __init__(self, bot_token: str | None = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30)

    async def send_message(self, chat_id: str, text: str, parse_mode: str = "HTML") -> dict[str, Any]:
        try:
            resp = await self.client.post(
                "/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("ok"):
                return {
                    "success": True,
                    "message_id": data["result"]["message_id"],
                    "chat_id": chat_id,
                }
            return {"success": False, "error": data.get("description", "Unknown error")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def edit_message(self, chat_id: str, message_id: int, text: str) -> dict[str, Any]:
        try:
            resp = await self.client.post(
                "/editMessageText",
                json={"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"},
            )
            resp.raise_for_status()
            return {"success": True, "data": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def delete_message(self, chat_id: str, message_id: int) -> dict[str, Any]:
        try:
            resp = await self.client.post(
                "/deleteMessage",
                json={"chat_id": chat_id, "message_id": message_id},
            )
            resp.raise_for_status()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
