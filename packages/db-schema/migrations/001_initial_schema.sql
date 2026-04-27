-- Enterprise Agent Database Schema v0.1
-- Phase 1: Foundation

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgvector";

-- =====================================================
-- USERS (MVP 单管理员，预留 RBAC 字段)
-- =====================================================
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email VARCHAR(255) NOT NULL UNIQUE,
  name VARCHAR(100) NOT NULL,
  role VARCHAR(50) DEFAULT 'admin',
  permissions JSONB DEFAULT '[]',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- TASKS
-- =====================================================
CREATE TABLE IF NOT EXISTS tasks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  title VARCHAR(255) NOT NULL,
  description TEXT NOT NULL,
  status VARCHAR(50) DEFAULT 'pending',
  risk_level VARCHAR(20) DEFAULT 'low',
  environment VARCHAR(20) DEFAULT 'test',
  created_by UUID REFERENCES users(id),
  assigned_to UUID REFERENCES users(id),
  parent_task_id UUID REFERENCES tasks(id),
  skill_id UUID,
  context JSONB DEFAULT '{}',
  result JSONB DEFAULT '{}',
  error_message TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created_by ON tasks(created_by);
CREATE INDEX idx_tasks_parent ON tasks(parent_task_id);
CREATE INDEX idx_tasks_skill ON tasks(skill_id);

-- =====================================================
-- TASK EVENTS (append-only structured event log)
-- =====================================================
CREATE TABLE IF NOT EXISTS task_events (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  event_type VARCHAR(100) NOT NULL,
  sequence INTEGER NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(task_id, sequence)
);

CREATE INDEX idx_task_events_task ON task_events(task_id);
CREATE INDEX idx_task_events_type ON task_events(event_type);
CREATE INDEX idx_task_events_created ON task_events(created_at);

-- =====================================================
-- TOOL CALLS
-- =====================================================
CREATE TABLE IF NOT EXISTS tool_calls (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  event_id UUID REFERENCES task_events(id),
  tool_name VARCHAR(200) NOT NULL,
  tool_version VARCHAR(50) DEFAULT '1.0.0',
  input JSONB NOT NULL DEFAULT '{}',
  output JSONB DEFAULT '{}',
  status VARCHAR(50) DEFAULT 'pending',
  risk_level VARCHAR(20) DEFAULT 'low',
  environment VARCHAR(20) DEFAULT 'test',
  duration_ms INTEGER,
  error_message TEXT,
  rollback_plan_id UUID,
  subagent_id UUID,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tool_calls_task ON tool_calls(task_id);
CREATE INDEX idx_tool_calls_tool ON tool_calls(tool_name);
CREATE INDEX idx_tool_calls_status ON tool_calls(status);

-- =====================================================
-- APPROVALS
-- =====================================================
CREATE TABLE IF NOT EXISTS approvals (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  tool_call_id UUID REFERENCES tool_calls(id),
  requester UUID NOT NULL REFERENCES users(id),
  approver UUID REFERENCES users(id),
  action_type VARCHAR(200) NOT NULL,
  reason TEXT NOT NULL,
  status VARCHAR(50) DEFAULT 'pending',
  resolved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_approvals_task ON approvals(task_id);
CREATE INDEX idx_approvals_status ON approvals(status);

-- =====================================================
-- ROLLBACK PLANS
-- =====================================================
CREATE TABLE IF NOT EXISTS rollback_plans (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  tool_call_id UUID REFERENCES tool_calls(id),
  strategy VARCHAR(100) NOT NULL,
  plan JSONB NOT NULL DEFAULT '{}',
  executed BOOLEAN DEFAULT FALSE,
  executed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_rollback_plans_task ON rollback_plans(task_id);
CREATE INDEX idx_rollback_plans_executed ON rollback_plans(executed);

-- =====================================================
-- MEMORIES
-- =====================================================
CREATE TABLE IF NOT EXISTS memories (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  memory_type VARCHAR(50) NOT NULL,
  content TEXT NOT NULL,
  source_task_id UUID REFERENCES tasks(id),
  source_event_id UUID REFERENCES task_events(id),
  scope VARCHAR(100) DEFAULT 'global',
  confidence DECIMAL(3,2) DEFAULT 0.8,
  version INTEGER DEFAULT 1,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  last_accessed_at TIMESTAMPTZ,
  is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_memories_type ON memories(memory_type);
CREATE INDEX idx_memories_scope ON memories(scope);
CREATE INDEX idx_memories_task ON memories(source_task_id);
CREATE INDEX idx_memories_created ON memories(created_at);

-- Memory embeddings (pgvector)
CREATE TABLE IF NOT EXISTS memory_embeddings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  embedding vector(1536),
  model VARCHAR(100) DEFAULT 'text-embedding-3-small',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_memory_embeddings_vector ON memory_embeddings
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- =====================================================
-- SKILLS
-- =====================================================
CREATE TABLE IF NOT EXISTS skills (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name VARCHAR(200) NOT NULL UNIQUE,
  description TEXT NOT NULL,
  owner VARCHAR(100) NOT NULL,
  domain VARCHAR(100) NOT NULL,
  risk_level VARCHAR(20) DEFAULT 'low',
  environment JSONB DEFAULT '["test"]',
  input_schema JSONB DEFAULT '{}',
  output_schema JSONB DEFAULT '{}',
  current_version VARCHAR(50) DEFAULT '1.0.0',
  status VARCHAR(50) DEFAULT 'active',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_skills_domain ON skills(domain);
CREATE INDEX idx_skills_status ON skills(status);

-- =====================================================
-- SKILL VERSIONS
-- =====================================================
CREATE TABLE IF NOT EXISTS skill_versions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
  version VARCHAR(50) NOT NULL,
  content JSONB NOT NULL DEFAULT '{}',
  changelog TEXT,
  created_by UUID REFERENCES users(id),
  parent_version VARCHAR(50),
  eval_score DECIMAL(4,3),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(skill_id, version)
);

CREATE INDEX idx_skill_versions_skill ON skill_versions(skill_id);
CREATE INDEX idx_skill_versions_version ON skill_versions(version);

-- =====================================================
-- ARTIFACTS
-- =====================================================
CREATE TABLE IF NOT EXISTS artifacts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  event_id UUID REFERENCES task_events(id),
  artifact_type VARCHAR(100) NOT NULL,
  name VARCHAR(255) NOT NULL,
  mime_type VARCHAR(100),
  file_path TEXT,
  content TEXT,
  metadata JSONB DEFAULT '{}',
  version INTEGER DEFAULT 1,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_artifacts_task ON artifacts(task_id);
CREATE INDEX idx_artifacts_type ON artifacts(artifact_type);

-- =====================================================
-- PROVIDER CONFIGS
-- =====================================================
CREATE TABLE IF NOT EXISTS provider_configs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  provider VARCHAR(100) NOT NULL,
  api_key_encrypted TEXT,
  base_url TEXT,
  model VARCHAR(100),
  config JSONB DEFAULT '{}',
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- MCP SERVERS
-- =====================================================
CREATE TABLE IF NOT EXISTS mcp_servers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name VARCHAR(200) NOT NULL,
  description TEXT,
  transport VARCHAR(50) DEFAULT 'stdio',
  command TEXT,
  args JSONB DEFAULT '[]',
  env JSONB DEFAULT '{}',
  capabilities JSONB DEFAULT '[]',
  permissions JSONB DEFAULT '[]',
  is_active BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- EVAL RUNS
-- =====================================================
CREATE TABLE IF NOT EXISTS eval_runs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  skill_id UUID REFERENCES skills(id),
  eval_type VARCHAR(100) NOT NULL,
  metrics JSONB DEFAULT '{}',
  score DECIMAL(5,4),
  feedback TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_eval_runs_task ON eval_runs(task_id);

-- =====================================================
-- INSERT DEFAULT ADMIN USER
-- =====================================================
INSERT INTO users (id, email, name, role, permissions)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  'admin@enterprise.local',
  'System Admin',
  'admin',
  '["*"]'
)
ON CONFLICT (email) DO NOTHING;

-- =====================================================
-- INSERT SAMPLE SKILL
-- =====================================================
INSERT INTO skills (id, name, description, owner, domain, risk_level, environment, input_schema, output_schema, current_version)
VALUES (
  '00000000-0000-0000-0000-000000000010',
  'generate_report',
  '生成结构化业务报告',
  'system',
  'data',
  'low',
  '["test", "production"]',
  '{"title": "string", "sections": "array"}',
  '{"report_path": "string", "summary": "string"}',
  '1.0.0'
)
ON CONFLICT (name) DO NOTHING;

INSERT INTO skill_versions (skill_id, version, content, changelog, created_by, eval_score)
VALUES (
  '00000000-0000-0000-0000-000000000010',
  '1.0.0',
  '{"steps": ["收集数据", "分析", "生成报告"], "recommended_tools": ["file.write", "mock.analyze"]}',
  'Initial version',
  '00000000-0000-0000-0000-000000000001',
  0.85
)
ON CONFLICT DO NOTHING;
