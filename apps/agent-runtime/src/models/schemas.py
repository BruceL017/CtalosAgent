"""
Pydantic models for Agent Runtime.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    RUNNING = "running"
    PAUSED = "paused"
    RESUMED = "resumed"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"


class EventType(str, Enum):
    TASK_CREATED = "task.created"
    TASK_STATE_CHANGED = "task.state_changed"
    CONTEXT_RETRIEVED = "context.retrieved"
    MEMORY_USED = "memory.used"
    SKILL_USED = "skill.used"
    PLAN_CREATED = "plan.created"
    PLAN_STEP_STARTED = "plan.step_started"
    PLAN_STEP_COMPLETED = "plan.step_completed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"
    TOOL_CALLED = "tool.called"
    TOOL_RESULT = "tool.result"
    SUBAGENT_CREATED = "subagent.created"
    SUBAGENT_COMPLETED = "subagent.completed"
    SUBAGENT_FAILED = "subagent.failed"
    ARTIFACT_CREATED = "artifact.created"
    ROLLBACK_PLAN_CREATED = "rollback.plan_created"
    ROLLBACK_EXECUTED = "rollback.executed"
    MEMORY_UPDATED = "memory.updated"
    SKILL_UPDATED = "skill.updated"
    SOP_EXTRACTED = "sop.extracted"
    EVAL_COMPLETED = "eval.completed"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"
    TASK_RETRYING = "task.retrying"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PermissionMode(str, Enum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    APPROVAL_REQUIRED = "approval_required"
    ADMIN_FULL_ACCESS = "admin_full_access"


class MemoryType(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    PERFORMANCE = "performance"


class SubagentRole(str, Enum):
    PRODUCT = "product"
    DEV = "dev"
    OPS = "ops"
    DATA = "data"
    SECURITY = "security"
    GENERAL = "general"


class ReplayType(str, Enum):
    FULL = "full"
    STEP = "step"
    TOOL_DEBUG = "tool_debug"


class ChatMessage(BaseModel):
    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ToolCallRequest(BaseModel):
    id: str
    type: str = "function"
    function: dict[str, str]


class ToolResult(BaseModel):
    tool_call_id: str
    role: str = "tool"
    name: str
    content: str


class AgentPlanStep(BaseModel):
    step_number: int
    tool: str
    input: dict[str, Any]
    description: str
    expected_output: str | None = None
    retry_on_failure: bool = True
    max_retries: int = 3


class AgentPlan(BaseModel):
    task_id: str
    goal: str
    steps: list[AgentPlanStep]
    estimated_risk: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False


class PolicyInput(BaseModel):
    actor_id: str
    tool_name: str
    environment: str = "test"
    resource: str | None = None
    risk_level: RiskLevel = RiskLevel.LOW
    operation_type: str = "read"
    rollback_available: bool = False
    estimated_blast_radius: str = "none"


class PolicyDecision(BaseModel):
    allowed: bool
    mode: PermissionMode
    reason: str
    requires_approval: bool
    risk_level: RiskLevel


class ProviderConfig(BaseModel):
    id: str
    provider: str
    provider_type: str
    model: str
    base_url: str | None = None
    is_active: bool = True
    is_default: bool = False
    fallback_order: int = 0
    timeout_seconds: int = 60
    max_retries: int = 3
    rate_limit_rpm: int = 60


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    model: str
    provider: str
    finish_reason: str | None = None


class ProviderHealth(BaseModel):
    provider: str
    configured: bool
    healthy: bool
    latency_ms: int | None = None
    last_error: str | None = None
    default_model: str


class ProviderStats(BaseModel):
    provider: str
    total_calls: int = 0
    total_errors: int = 0
    total_tokens: int = 0
    avg_latency_ms: float = 0.0
    last_called_at: str | None = None
