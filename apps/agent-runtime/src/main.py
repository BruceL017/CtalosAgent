"""
Enterprise Agent Runtime - FastAPI Application
v0.3 - 企业级落地硬化版
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from config.settings import get_settings
from models.schemas import ChatMessage
from services.provider_router import ProviderRouter
from services.eval_service import EvalService
from services.replay_service import ReplayService
from services.rollback_service import RollbackService
from services.task_executor import TaskExecutor
from tools.registry import ToolRegistry
from tools.integrations.mcp_gateway import MCPGateway
from utils.structured_logger import ContextLogger

settings = get_settings()

# Prometheus metrics
REQUEST_COUNT = Counter("agent_runtime_requests_total", "Total requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("agent_runtime_request_duration_seconds", "Request latency", ["method", "endpoint"])
TASK_COUNT = Counter("agent_runtime_tasks_total", "Total tasks", ["status"])
TOOL_COUNT = Counter("agent_runtime_tools_total", "Total tool calls", ["tool", "status"])

structured_logger = ContextLogger(task_id=None, session_id=None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=10,
    )
    app.state.executor = TaskExecutor(app.state.db_pool)
    app.state.provider = ProviderRouter()
    app.state.rollback = RollbackService(app.state.db_pool)
    app.state.eval_service = EvalService(app.state.db_pool)
    app.state.replay = ReplayService(app.state.db_pool)
    app.state.mcp = ToolRegistry.get_mcp_gateway()
    print(f"Agent Runtime v0.2 started on {settings.host}:{settings.port}")
    yield
    await app.state.db_pool.close()


app = FastAPI(title="Enterprise Agent Runtime v0.3", version="0.3.0", lifespan=lifespan)

# Structured logging middleware
@app.middleware("http")
async def structured_logging_middleware(request: Request, call_next):
    import time as time_mod
    start = time_mod.time()
    trace_id = request.headers.get("X-Trace-ID", str(__import__("uuid").uuid4()))
    request.state.trace_id = trace_id

    response = await call_next(request)

    duration = time_mod.time() - start
    status = str(response.status_code)
    path = request.url.path
    method = request.method

    REQUEST_COUNT.labels(method=method, endpoint=path, status=status).inc()
    REQUEST_LATENCY.labels(method=method, endpoint=path).observe(duration)

    structured_logger.info(
        f"{method} {path} {status} {duration*1000:.1f}ms",
        trace_id=trace_id,
        method=method,
        path=path,
        status_code=status,
        duration_ms=round(duration * 1000, 2),
    )
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Basic health check."""
    return {"status": "ok", "service": "agent-runtime", "version": "0.3.0"}


@app.get("/health/detailed")
async def health_detailed():
    """Detailed health check including DB and provider availability."""
    checks = {
        "service": "agent-runtime",
        "version": "0.3.0",
        "status": "ok",
    }

    # DB check
    try:
        async with app.state.db_pool.acquire() as conn:
            db_result = await conn.fetchrow("SELECT 1 as ping")
            checks["database"] = {"healthy": db_result is not None, "latency_ms": 0}
    except Exception as e:
        checks["database"] = {"healthy": False, "error": str(e)}
        checks["status"] = "degraded"

    # Provider health checks
    provider_health = await app.state.provider.health_checks()
    checks["providers"] = [h.model_dump() for h in provider_health]
    if any(not h.healthy for h in provider_health):
        checks["status"] = "degraded"

    # Embedding service health
    from services.embedding_service import EmbeddingService
    emb = EmbeddingService()
    checks["embedding"] = {"available": emb.is_real(), "provider": "siliconflow" if emb.is_real() else "mock"}

    return checks


# =====================================================
# Task Execution
# =====================================================

@app.post("/execute")
async def execute_task(request: dict):
    task_id = request.get("task_id")
    task = request.get("task", {})

    if not task_id:
        return {"success": False, "error": "task_id is required"}

    asyncio.create_task(app.state.executor.run(task_id, task))
    return {"success": True, "data": {"task_id": task_id, "status": "running"}}


@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    result = await app.state.executor.cancel(task_id)
    return result


@app.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    result = await app.state.executor.pause(task_id)
    return result


@app.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    async with app.state.db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    task = dict(row)
    result = await app.state.executor.run(task_id, task)
    return result


@app.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    async with app.state.db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, result, error_message, started_at, completed_at FROM tasks WHERE id = $1",
            task_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "data": dict(row)}


# =====================================================
# Subagent
# =====================================================

@app.post("/tasks/{task_id}/subagents/analyze")
async def run_subagent_analysis(task_id: str, request: dict):
    task_context = request.get("task_context", {})
    roles = request.get("roles", ["product", "dev", "ops"])
    result = await app.state.executor.run_subagent_analysis(task_id, task_context, roles)
    return {"success": True, "data": result}


# =====================================================
# Rollback
# =====================================================

@app.post("/tasks/{task_id}/rollback")
async def execute_rollback(task_id: str, request: dict | None = None):
    executed_by = (request or {}).get("executed_by", "system")
    result = await app.state.executor.execute_rollback(task_id, executed_by)
    return result


@app.post("/rollback-plans/{plan_id}/execute")
async def execute_rollback_plan(plan_id: str, request: dict | None = None):
    executed_by = (request or {}).get("executed_by", "system")
    result = await app.state.rollback.execute_rollback(plan_id, executed_by)
    return result


@app.post("/rollback-plans/{plan_id}/dry-run")
async def dry_run_rollback_plan(plan_id: str):
    result = await app.state.rollback.dry_run_rollback(plan_id)
    return result


# =====================================================
# Replay
# =====================================================

@app.post("/tasks/{task_id}/replay")
async def create_replay(task_id: str, request: dict):
    replay_type = request.get("replay_type", "full")
    from_seq = request.get("from_sequence")
    to_seq = request.get("to_sequence")
    speed = request.get("speed", "1x")

    session = await app.state.replay.create_replay_session(
        task_id=task_id,
        replay_type=replay_type,
        from_sequence=from_seq,
        to_sequence=to_seq,
        speed=speed,
    )

    # Run replay in background
    asyncio.create_task(app.state.replay.replay_task(session["id"]))

    return {"success": True, "data": session}


@app.get("/replay-sessions/{session_id}")
async def get_replay_session(session_id: str):
    async with app.state.db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM replay_sessions WHERE id = $1", session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Replay session not found")
    return {"success": True, "data": dict(row)}


@app.post("/tool-calls/{tool_call_id}/debug")
async def debug_tool_call(tool_call_id: str):
    result = await app.state.replay.debug_tool_call(tool_call_id)
    return result


@app.get("/tasks/{task_id}/audit-trail")
async def export_audit_trail(task_id: str):
    result = await app.state.replay.export_audit_trail(task_id)
    return result


# =====================================================
# Provider Router
# =====================================================

@app.get("/providers")
async def list_providers():
    return {"success": True, "data": app.state.provider.get_status()}


@app.get("/providers/health")
async def providers_health():
    health = await app.state.provider.health_checks()
    return {"success": True, "data": [h.model_dump() for h in health]}


@app.get("/providers/stats")
async def providers_stats():
    return {"success": True, "data": app.state.provider.get_stats()}


@app.post("/providers/chat")
async def provider_chat(request: dict):
    messages = [ChatMessage(**m) for m in request.get("messages", [])]
    provider = request.get("provider")
    model = request.get("model")
    temperature = request.get("temperature", 0.7)
    tools = request.get("tools")

    try:
        response = await app.state.provider.chat(
            messages=messages,
            provider=provider,
            model=model,
            temperature=temperature,
            tools=tools,
        )
        return {
            "success": True,
            "data": {
                "content": response.content,
                "tool_calls": [t.model_dump() for t in response.tool_calls],
                "usage": response.usage,
                "model": response.model,
                "provider": response.provider,
                "finish_reason": response.finish_reason,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# =====================================================
# MCP Gateway
# =====================================================

@app.get("/mcp/servers")
async def list_mcp_servers():
    return {"success": True, "data": app.state.mcp.list_servers()}


@app.post("/mcp/servers/register")
async def register_mcp_server(request: dict):
    result = app.state.mcp.register_server(
        name=request["name"],
        transport=request.get("transport", "stdio"),
        command=request.get("command"),
        args=request.get("args"),
        env=request.get("env"),
        capabilities=request.get("capabilities"),
        permissions=request.get("permissions"),
    )
    return {"success": True, "data": result}


@app.get("/mcp/servers/{server_name}/tools")
async def list_mcp_tools(server_name: str):
    tools = await app.state.mcp.list_tools(server_name)
    return {"success": True, "data": tools}


@app.post("/mcp/servers/{server_name}/call")
async def call_mcp_tool(server_name: str, request: dict):
    result = await app.state.mcp.call_tool(
        server_name=server_name,
        tool_name=request["tool_name"],
        arguments=request.get("arguments", {}),
        requester_permissions=request.get("requester_permissions"),
    )
    return result


@app.get("/mcp/servers/{server_name}/health")
async def mcp_health_check(server_name: str):
    return {"success": True, "data": app.state.mcp.health_check(server_name)}


# =====================================================
# Tools Registry
# =====================================================

@app.get("/tools")
async def list_tools():
    tools = ToolRegistry.list_tools()
    return {
        "success": True,
        "data": [
            {
                "name": t.name,
                "owner": t.owner,
                "risk_level": t.risk_level,
                "environment": t.environment,
                "requires_approval_on": t.requires_approval_on,
                "rollback_strategy": t.rollback_strategy,
                "timeout_seconds": t.timeout_seconds,
                "description": t.description,
            }
            for t in tools
        ],
    }


# =====================================================
# Eval
# =====================================================

@app.get("/tasks/{task_id}/eval")
async def get_task_eval(task_id: str):
    result = await app.state.eval_service.get_task_eval(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Eval not found for this task")
    return {"success": True, "data": result}


@app.get("/evals")
async def list_evals(task_id: str | None = None, limit: int = 20, offset: int = 0):
    results = await app.state.eval_service.list_evals(task_id=task_id, limit=limit, offset=offset)
    return {"success": True, "data": results}


# =====================================================
# Metrics (Prometheus)
# =====================================================

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return PlainTextResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)
