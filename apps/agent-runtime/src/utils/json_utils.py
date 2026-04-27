"""Shared JSON utilities with UUID and datetime support."""
import json
import uuid
from datetime import datetime
from typing import Any


class AgentJSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def json_dumps(obj: Any, **kwargs: Any) -> str:
    return json.dumps(obj, cls=AgentJSONEncoder, **kwargs)
