-- =====================================================
-- WORKFLOW STATES: persisted plan_state for resume after restart
-- =====================================================

CREATE TABLE IF NOT EXISTS workflow_states (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    state_type VARCHAR(50) NOT NULL, -- 'plan_approval', 'tool_approval', 'paused'
    current_step INT DEFAULT 0,
    total_steps INT DEFAULT 0,
    plan JSONB,
    tool_calls_log JSONB DEFAULT '[]',
    result_data JSONB DEFAULT '{}',
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_workflow_states_task ON workflow_states(task_id);
CREATE INDEX idx_workflow_states_status ON workflow_states(status);

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_workflow_state_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_workflow_state_updated_at ON workflow_states;
CREATE TRIGGER trigger_workflow_state_updated_at
    BEFORE UPDATE ON workflow_states
    FOR EACH ROW
    EXECUTE FUNCTION update_workflow_state_updated_at();
