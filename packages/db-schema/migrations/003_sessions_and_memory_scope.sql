-- Migration 003: Sessions, Session Messages, Session-Task Links, Memory Scope Enhancement

-- =====================================================
-- SESSIONS
-- =====================================================
CREATE TABLE IF NOT EXISTS sessions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  title VARCHAR(255) NOT NULL,
  description TEXT,
  status VARCHAR(50) DEFAULT 'active',
  created_by UUID REFERENCES users(id),
  context JSONB DEFAULT '{}',
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  ended_at TIMESTAMPTZ
);

CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_created_by ON sessions(created_by);
CREATE INDEX idx_sessions_created_at ON sessions(created_at);

-- =====================================================
-- SESSION MESSAGES
-- =====================================================
CREATE TABLE IF NOT EXISTS session_messages (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  role VARCHAR(50) NOT NULL, -- user, assistant, system, tool
  content TEXT NOT NULL,
  tool_calls JSONB DEFAULT '[]',
  tool_call_id VARCHAR(100),
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_session_messages_session ON session_messages(session_id);
CREATE INDEX idx_session_messages_created ON session_messages(created_at);

-- =====================================================
-- SESSION TASK LINKS
-- =====================================================
CREATE TABLE IF NOT EXISTS session_task_links (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  link_type VARCHAR(50) DEFAULT 'direct', -- direct, subtask, referenced
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(session_id, task_id)
);

CREATE INDEX idx_session_task_links_session ON session_task_links(session_id);
CREATE INDEX idx_session_task_links_task ON session_task_links(task_id);

-- =====================================================
-- MEMORY SCOPE ENHANCEMENT
-- =====================================================
ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_session_id UUID REFERENCES sessions(id);
ALTER TABLE memories ADD COLUMN IF NOT EXISTS enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ;

-- Rename last_accessed_at to last_used_at if exists, otherwise just ensure it exists
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'memories' AND column_name = 'last_accessed_at'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'memories' AND column_name = 'last_used_at'
  ) THEN
    ALTER TABLE memories RENAME COLUMN last_accessed_at TO last_used_at;
  END IF;
END $$;

-- Ensure scope has proper constraint values
-- Note: existing scopes should already be valid: global, project, product, team, session, user

-- =====================================================
-- TASKS: ADD SESSION REFERENCE
-- =====================================================
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS session_id UUID REFERENCES sessions(id);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);

-- =====================================================
-- APPROVALS: ADD PLAN STATE FOR RESUME
-- =====================================================
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS plan_state JSONB DEFAULT '{}';

-- =====================================================
-- INSERT SAMPLE SESSION
-- =====================================================
INSERT INTO sessions (id, title, description, status, created_by, context)
VALUES (
  '00000000-0000-0000-0000-000000000100',
  'Default Session',
  'System default session for tasks without explicit session',
  'active',
  '00000000-0000-0000-0000-000000000001',
  '{"system": true}'
)
ON CONFLICT (id) DO NOTHING;
