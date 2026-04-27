"""
Policy Engine: 权限策略引擎
参考 claw-code 权限模式：read_only、workspace_write、approval_required、admin_full_access
"""
from typing import Any

from models.schemas import PermissionMode, PolicyDecision, PolicyInput, RiskLevel


class PolicyEngine:
    """策略引擎：判断工具调用是否允许、是否需要审批"""

    # 风险级别 -> 默认权限模式
    RISK_MODE_MAP: dict[RiskLevel, PermissionMode] = {
        RiskLevel.LOW: PermissionMode.WORKSPACE_WRITE,
        RiskLevel.MEDIUM: PermissionMode.APPROVAL_REQUIRED,
        RiskLevel.HIGH: PermissionMode.APPROVAL_REQUIRED,
        RiskLevel.CRITICAL: PermissionMode.ADMIN_FULL_ACCESS,
    }

    # 环境 -> 默认提升策略
    ENV_ESCALATION: dict[str, int] = {
        "test": 0,
        "staging": 1,
        "production": 2,
    }

    # 操作类型 -> 基础风险加成
    OP_RISK_BONUS: dict[str, int] = {
        "read": 0,
        "write": 1,
        "delete": 2,
        "execute": 1,
        "merge": 2,
        "deploy": 2,
    }

    @classmethod
    def evaluate(cls, input_data: PolicyInput) -> PolicyDecision:
        """评估策略决策"""
        base_mode = cls.RISK_MODE_MAP.get(input_data.risk_level, PermissionMode.APPROVAL_REQUIRED)

        # 环境提升
        env_level = cls.ENV_ESCALATION.get(input_data.environment, 0)
        op_bonus = cls.OP_RISK_BONUS.get(input_data.operation_type, 0)

        # 计算最终风险指数
        risk_score = env_level + op_bonus

        # 生产环境删除/合并操作强制审批
        if input_data.environment == "production" and input_data.operation_type in ("delete", "merge", "deploy"):
            requires_approval = True
            mode = PermissionMode.APPROVAL_REQUIRED
        # 无回滚能力的高风险操作
        elif not input_data.rollback_available and input_data.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            requires_approval = True
            mode = PermissionMode.APPROVAL_REQUIRED
        # 大面积影响
        elif input_data.estimated_blast_radius in ("org_wide", "customer_facing"):
            requires_approval = True
            mode = PermissionMode.APPROVAL_REQUIRED
        # 正常流程
        elif risk_score >= 2:
            requires_approval = True
            mode = PermissionMode.APPROVAL_REQUIRED
        else:
            requires_approval = base_mode == PermissionMode.APPROVAL_REQUIRED
            mode = base_mode

        # admin 永远允许
        if input_data.actor_id == "admin" or input_data.actor_id == "00000000-0000-0000-0000-000000000001":
            return PolicyDecision(
                allowed=True,
                mode=PermissionMode.ADMIN_FULL_ACCESS,
                reason="Admin override",
                requires_approval=False,
                risk_level=input_data.risk_level,
            )

        allowed = mode != PermissionMode.READ_ONLY or input_data.operation_type == "read"

        return PolicyDecision(
            allowed=allowed,
            mode=mode,
            reason=f"Risk score: {risk_score}, base mode: {base_mode.value}, env: {input_data.environment}",
            requires_approval=requires_approval,
            risk_level=input_data.risk_level,
        )

    @classmethod
    def check_tool_permission(
        cls,
        actor_id: str,
        tool_name: str,
        tool_manifest: dict[str, Any],
        environment: str,
        operation_type: str = "execute",
    ) -> PolicyDecision:
        """检查工具权限"""
        requires_approval_on = tool_manifest.get("requires_approval_on", [])
        risk_level_str = tool_manifest.get("risk_level", "low")

        try:
            risk_level = RiskLevel(risk_level_str)
        except ValueError:
            risk_level = RiskLevel.LOW

        # 特定环境强制审批
        env_requires_approval = environment in requires_approval_on

        input_data = PolicyInput(
            actor_id=actor_id,
            tool_name=tool_name,
            environment=environment,
            risk_level=risk_level,
            operation_type=operation_type,
            rollback_available=tool_manifest.get("rollback_strategy") != "manual_compensation",
            estimated_blast_radius=tool_manifest.get("estimated_blast_radius", "none"),
        )

        decision = cls.evaluate(input_data)

        if env_requires_approval:
            decision.requires_approval = True
            decision.reason += f"; {environment} environment requires approval for {tool_name}"

        return decision
