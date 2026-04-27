-- Migration 002: State Machine, Subagents, Rollback Execution

-- =====================================================
-- SUBAGENTS
-- =====================================================
CREATE TABLE IF NOT EXISTS subagents (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  parent_subagent_id UUID REFERENCES subagents(id),
  role VARCHAR(100) NOT NULL, -- product, dev, ops, data, security
  name VARCHAR(200) NOT NULL,
  status VARCHAR(50) DEFAULT 'pending',
  context JSONB DEFAULT '{}',
  plan JSONB DEFAULT '{}',
  result JSONB DEFAULT '{}',
  error_message TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_subagents_task ON subagents(task_id);
CREATE INDEX idx_subagents_role ON subagents(role);
CREATE INDEX idx_subagents_status ON subagents(status);

-- =====================================================
-- TASK STATE MACHINE TRANSITIONS
-- =====================================================
CREATE TABLE IF NOT EXISTS task_state_transitions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  from_state VARCHAR(50) NOT NULL,
  to_state VARCHAR(50) NOT NULL,
  triggered_by VARCHAR(100) NOT NULL,
  reason TEXT,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_task_state_transitions_task ON task_state_transitions(task_id);

-- =====================================================
-- ROLLBACK EXECUTIONS
-- =====================================================
CREATE TABLE IF NOT EXISTS rollback_executions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  rollback_plan_id UUID NOT NULL REFERENCES rollback_plans(id) ON DELETE CASCADE,
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  tool_call_id UUID REFERENCES tool_calls(id),
  status VARCHAR(50) DEFAULT 'pending',
  strategy VARCHAR(100) NOT NULL,
  steps JSONB DEFAULT '[]',
  result JSONB DEFAULT '{}',
  error_message TEXT,
  executed_by UUID REFERENCES users(id),
  executed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_rollback_executions_plan ON rollback_executions(rollback_plan_id);
CREATE INDEX idx_rollback_executions_status ON rollback_executions(status);

-- =====================================================
-- REPLAY SESSIONS
-- =====================================================
CREATE TABLE IF NOT EXISTS replay_sessions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  replay_type VARCHAR(50) NOT NULL, -- full, step, tool_debug
  from_event_sequence INTEGER,
  to_event_sequence INTEGER,
  speed VARCHAR(20) DEFAULT '1x',
  status VARCHAR(50) DEFAULT 'running',
  result JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

CREATE INDEX idx_replay_sessions_task ON replay_sessions(task_id);

-- =====================================================
-- AUDIT LOGS
-- =====================================================
CREATE TABLE IF NOT EXISTS audit_logs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  actor_id UUID REFERENCES users(id),
  actor_type VARCHAR(50) DEFAULT 'user',
  action VARCHAR(100) NOT NULL,
  resource_type VARCHAR(100) NOT NULL,
  resource_id UUID,
  before_state JSONB,
  after_state JSONB,
  metadata JSONB DEFAULT '{}',
  ip_address INET,
  user_agent TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_actor ON audit_logs(actor_id);
CREATE INDEX idx_audit_logs_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_logs_created ON audit_logs(created_at);

-- =====================================================
-- SOP EXTRACTS (避坑库素材)
-- =====================================================
CREATE TABLE IF NOT EXISTS sop_extracts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  event_id UUID REFERENCES task_events(id),
  extract_type VARCHAR(100) NOT NULL, -- lesson_learned, pitfall, best_practice
  content TEXT NOT NULL,
  category VARCHAR(100),
  severity VARCHAR(20) DEFAULT 'medium',
  applied_to_skill_id UUID REFERENCES skills(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sop_extracts_task ON sop_extracts(task_id);
CREATE INDEX idx_sop_extracts_type ON sop_extracts(extract_type);

-- =====================================================
-- UPDATE PROVIDER CONFIGS
-- =====================================================
ALTER TABLE provider_configs ADD COLUMN IF NOT EXISTS provider_type VARCHAR(50) DEFAULT 'openai';
ALTER TABLE provider_configs ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE;
ALTER TABLE provider_configs ADD COLUMN IF NOT EXISTS fallback_order INTEGER DEFAULT 0;
ALTER TABLE provider_configs ADD COLUMN IF NOT EXISTS timeout_seconds INTEGER DEFAULT 60;
ALTER TABLE provider_configs ADD COLUMN IF NOT EXISTS max_retries INTEGER DEFAULT 3;
ALTER TABLE provider_configs ADD COLUMN IF NOT EXISTS rate_limit_rpm INTEGER DEFAULT 60;

-- =====================================================
-- UPDATE MCP SERVERS
-- =====================================================
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS command_path TEXT;
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS runtime_env JSONB DEFAULT '{}';
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS health_status VARCHAR(50) DEFAULT 'unknown';
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS last_health_check TIMESTAMPTZ;

-- =====================================================
-- PROVIDER STATUS VIEW
-- =====================================================
CREATE OR REPLACE VIEW provider_status AS
SELECT
  id,
  provider,
  provider_type,
  model,
  is_active,
  is_default,
  fallback_order,
  timeout_seconds,
  max_retries,
  rate_limit_rpm,
  CASE
    WHEN is_active THEN 'healthy'
    ELSE 'disabled'
  END AS status,
  created_at,
  updated_at
FROM provider_configs;
