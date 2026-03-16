-- AgentGate State Persistence Tables
-- Replaces in-memory state with database persistence

-- Audit Log (replaces audit_events_db list and audit_log list)
CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id VARCHAR(255) UNIQUE NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    event_type VARCHAR(100) NOT NULL,
    actor_agent_id VARCHAR(255),
    actor_ip INET,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    action VARCHAR(100),
    status VARCHAR(50),
    details JSONB DEFAULT '{}',
    severity VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_event_id (event_id),
    INDEX idx_timestamp (timestamp),
    INDEX idx_event_type (event_type),
    INDEX idx_actor_agent_id (actor_agent_id),
    INDEX idx_severity (severity),
    INDEX idx_created_at (created_at)
);

-- Token Budgets (replaces token_budgets dict in gateway.py)
-- Note: token_budgets table already exists in 001_initial_schema.sql
-- This is for reference; the table is already defined there

-- Policy Decision Cache (replaces decision_cache dict in policy/engine.py)
-- This uses Redis instead, but define the schema for reference
CREATE TABLE IF NOT EXISTS policy_decision_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cache_key VARCHAR(255) UNIQUE NOT NULL,
    decision JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    INDEX idx_cache_key (cache_key),
    INDEX idx_expires_at (expires_at)
);

-- Create indexes for performance on audit queries
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp_desc ON audit_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_severity ON audit_events(severity);
CREATE INDEX IF NOT EXISTS idx_audit_events_status ON audit_events(status);

-- Create view for audit summary aggregation
CREATE OR REPLACE VIEW audit_events_summary AS
SELECT
    DATE_TRUNC('day', timestamp) as date,
    event_type,
    status,
    COUNT(*) as count
FROM audit_events
GROUP BY DATE_TRUNC('day', timestamp), event_type, status
ORDER BY date DESC, event_type;

-- Drop old audit_logs table if it exists (keeping for backward compatibility initially)
-- ALTER TABLE audit_logs RENAME TO audit_logs_deprecated;
