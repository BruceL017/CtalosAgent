// =====================================================
// Enterprise Agent v0.1 - Shared Types
// =====================================================

export type TaskStatus =
  | 'pending'
  | 'planning'
  | 'awaiting_approval'
  | 'approved'
  | 'rejected'
  | 'running'
  | 'paused'
  | 'resumed'
  | 'retrying'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'rolling_back'
  | 'rolled_back';

export type EventType =
  | 'task.created'
  | 'task.state_changed'
  | 'context.retrieved'
  | 'memory.used'
  | 'skill.used'
  | 'plan.created'
  | 'plan.step_started'
  | 'plan.step_completed'
  | 'approval.requested'
  | 'approval.resolved'
  | 'tool.called'
  | 'tool.result'
  | 'subagent.created'
  | 'subagent.completed'
  | 'subagent.failed'
  | 'artifact.created'
  | 'rollback.plan_created'
  | 'rollback.executed'
  | 'memory.updated'
  | 'skill.updated'
  | 'sop.extracted'
  | 'eval.completed'
  | 'task.completed'
  | 'task.failed'
  | 'task.cancelled'
  | 'task.retrying';

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';
export type PermissionMode = 'read_only' | 'workspace_write' | 'approval_required' | 'admin_full_access';
export type MemoryType = 'episodic' | 'semantic' | 'procedural' | 'performance';
export type SubagentRole = 'product' | 'dev' | 'ops' | 'data' | 'security' | 'general';
export type ReplayType = 'full' | 'step' | 'tool_debug';
export type SOExtractType = 'lesson_learned' | 'pitfall' | 'best_practice';

export interface Task {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  risk_level: RiskLevel;
  environment: 'test' | 'production';
  created_by: string;
  assigned_to?: string;
  parent_task_id?: string;
  skill_id?: string;
  context?: Record<string, unknown>;
  result?: Record<string, unknown>;
  error_message?: string;
  retry_count: number;
  max_retries: number;
  started_at?: string;
  completed_at?: string;
  created_at: string;
  updated_at: string;
}

export interface TaskEvent {
  id: string;
  task_id: string;
  event_type: EventType;
  sequence: number;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface TaskStateTransition {
  id: string;
  task_id: string;
  from_state: TaskStatus;
  to_state: TaskStatus;
  triggered_by: string;
  reason?: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface ToolCall {
  id: string;
  task_id: string;
  event_id?: string;
  subagent_id?: string;
  tool_name: string;
  tool_version: string;
  input: Record<string, unknown>;
  output?: Record<string, unknown>;
  status: 'pending' | 'success' | 'failed' | 'timeout';
  risk_level: RiskLevel;
  environment: string;
  duration_ms?: number;
  error_message?: string;
  rollback_plan_id?: string;
  created_at: string;
}

export interface ToolManifest {
  name: string;
  owner: string;
  risk_level: RiskLevel;
  environment: string[];
  requires_approval_on: string[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  rollback_strategy: string;
  timeout_seconds: number;
  description: string;
}

export interface Approval {
  id: string;
  task_id: string;
  tool_call_id?: string;
  requester: string;
  approver?: string;
  action_type: string;
  reason: string;
  status: 'pending' | 'approved' | 'rejected';
  resolved_at?: string;
  created_at: string;
}

export interface RollbackPlan {
  id: string;
  task_id: string;
  tool_call_id?: string;
  strategy: string;
  plan: Record<string, unknown>;
  executed: boolean;
  executed_at?: string;
  created_at: string;
}

export interface RollbackExecution {
  id: string;
  rollback_plan_id: string;
  task_id: string;
  tool_call_id?: string;
  status: string;
  strategy: string;
  steps: Record<string, unknown>[];
  result?: Record<string, unknown>;
  error_message?: string;
  executed_by?: string;
  executed_at?: string;
  created_at: string;
}

export interface Memory {
  id: string;
  memory_type: MemoryType;
  content: string;
  source_task_id?: string;
  source_event_id?: string;
  scope: string;
  confidence: number;
  version: number;
  is_active: boolean;
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  last_accessed_at?: string;
}

export interface Skill {
  id: string;
  name: string;
  description: string;
  owner: string;
  domain: string;
  risk_level: RiskLevel;
  environment: string[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  current_version: string;
  status: 'active' | 'deprecated' | 'draft';
  created_at: string;
  updated_at: string;
}

export interface SkillVersion {
  id: string;
  skill_id: string;
  version: string;
  content: Record<string, unknown>;
  changelog: string;
  created_by: string;
  parent_version?: string;
  eval_score?: number;
  is_active: boolean;
  created_at: string;
}

export interface Subagent {
  id: string;
  task_id: string;
  parent_subagent_id?: string;
  role: SubagentRole;
  name: string;
  status: string;
  context?: Record<string, unknown>;
  plan?: Record<string, unknown>;
  result?: Record<string, unknown>;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ReplaySession {
  id: string;
  task_id: string;
  replay_type: ReplayType;
  from_event_sequence?: number;
  to_event_sequence?: number;
  speed: string;
  status: string;
  result?: Record<string, unknown>;
  created_at: string;
  completed_at?: string;
}

export interface AuditLog {
  id: string;
  actor_id?: string;
  actor_type: string;
  action: string;
  resource_type: string;
  resource_id?: string;
  before_state?: Record<string, unknown>;
  after_state?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  ip_address?: string;
  user_agent?: string;
  created_at: string;
}

export interface SOExtract {
  id: string;
  task_id: string;
  event_id?: string;
  extract_type: SOExtractType;
  content: string;
  category?: string;
  severity: string;
  applied_to_skill_id?: string;
  created_at: string;
}

export interface ProviderConfig {
  id: string;
  provider: string;
  provider_type: string;
  model: string;
  base_url?: string;
  config: Record<string, unknown>;
  is_active: boolean;
  is_default: boolean;
  fallback_order: number;
  timeout_seconds: number;
  max_retries: number;
  rate_limit_rpm: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface MCPServer {
  id: string;
  name: string;
  description?: string;
  transport: string;
  command?: string;
  command_path?: string;
  args: string[];
  env: Record<string, string>;
  runtime_env: Record<string, string>;
  capabilities: string[];
  permissions: string[];
  health_status: string;
  last_health_check?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Artifact {
  id: string;
  task_id: string;
  event_id?: string;
  artifact_type: string;
  name: string;
  mime_type?: string;
  file_path?: string;
  content?: string;
  metadata?: Record<string, unknown>;
  version: number;
  created_at: string;
}

export interface PolicyDecision {
  allowed: boolean;
  mode: PermissionMode;
  reason: string;
  requires_approval: boolean;
  risk_level: RiskLevel;
}

export interface ChatMessage {
  role: 'system' | 'developer' | 'user' | 'assistant' | 'tool';
  content: string;
  tool_calls?: ToolCallRequest[];
  tool_call_id?: string;
  name?: string;
}

export interface ToolCallRequest {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string;
  };
}

export interface CreateTaskRequest {
  title: string;
  description: string;
  risk_level?: RiskLevel;
  environment?: 'test' | 'production';
  skill_id?: string;
  context?: Record<string, unknown>;
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface SubagentResult {
  role: SubagentRole;
  result: Record<string, unknown>;
  confidence: number;
  conflicts?: string[];
}
