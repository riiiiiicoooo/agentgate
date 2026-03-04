-- AgentGate Initial Schema
-- PostgreSQL schema for agents, policies, secrets, and audit logs

-- Agents table
CREATE TABLE IF NOT EXISTS agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    client_id VARCHAR(255) UNIQUE NOT NULL,
    client_secret_hash VARCHAR(64) NOT NULL,
    status VARCHAR(50) DEFAULT 'active',
    scopes TEXT[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_auth_at TIMESTAMP WITH TIME ZONE,
    created_by VARCHAR(255),
    INDEX idx_agent_id (agent_id),
    INDEX idx_client_id (client_id),
    INDEX idx_status (status)
);

-- API Keys table
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(255) NOT NULL REFERENCES agents(agent_id),
    key_hash VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMP WITH TIME ZONE,
    last_used_at TIMESTAMP WITH TIME ZONE,
    INDEX idx_agent_id (agent_id),
    INDEX idx_key_hash (key_hash)
);

-- Policies table
CREATE TABLE IF NOT EXISTS policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    rules JSONB NOT NULL,
    tags TEXT[] DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    INDEX idx_policy_id (policy_id),
    INDEX idx_tags (tags),
    INDEX idx_created_by (created_by)
);

-- Policy Bindings (agents to policies)
CREATE TABLE IF NOT EXISTS policy_bindings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(255) NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    policy_id VARCHAR(255) NOT NULL REFERENCES policies(policy_id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(agent_id, policy_id),
    INDEX idx_agent_id (agent_id),
    INDEX idx_policy_id (policy_id)
);

-- Secrets table (metadata only, actual values in secret backend)
CREATE TABLE IF NOT EXISTS secrets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    secret_name VARCHAR(255) UNIQUE NOT NULL,
    secret_type VARCHAR(50),
    version VARCHAR(50) DEFAULT '1',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_rotated_at TIMESTAMP WITH TIME ZONE,
    rotation_enabled BOOLEAN DEFAULT false,
    rotation_interval_days INTEGER DEFAULT 30,
    INDEX idx_secret_name (secret_name),
    INDEX idx_rotation_enabled (rotation_enabled)
);

-- Secret Leases
CREATE TABLE IF NOT EXISTS secret_leases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lease_id VARCHAR(255) UNIQUE NOT NULL,
    agent_id VARCHAR(255) NOT NULL REFERENCES agents(agent_id),
    secret_name VARCHAR(255) NOT NULL REFERENCES secrets(secret_name),
    ttl_seconds INTEGER NOT NULL,
    issued_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE,
    accessed_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMP WITH TIME ZONE,
    renewal_count INTEGER DEFAULT 0,
    INDEX idx_lease_id (lease_id),
    INDEX idx_agent_id (agent_id),
    INDEX idx_secret_name (secret_name),
    INDEX idx_expires_at (expires_at)
);

-- Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
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

-- Token Budgets
CREATE TABLE IF NOT EXISTS token_budgets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(255) UNIQUE NOT NULL REFERENCES agents(agent_id),
    monthly_limit INTEGER DEFAULT 100000,
    hourly_limit INTEGER DEFAULT 10000,
    monthly_used INTEGER DEFAULT 0,
    hourly_used INTEGER DEFAULT 0,
    monthly_reset_at TIMESTAMP WITH TIME ZONE,
    hourly_reset_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_agent_id (agent_id)
);

-- Secret Rotations
CREATE TABLE IF NOT EXISTS secret_rotations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rotation_id VARCHAR(255) UNIQUE NOT NULL,
    secret_name VARCHAR(255) NOT NULL,
    strategy VARCHAR(50),
    status VARCHAR(50),
    scheduled_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    old_version VARCHAR(50),
    new_version VARCHAR(50),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_rotation_id (rotation_id),
    INDEX idx_secret_name (secret_name),
    INDEX idx_status (status),
    INDEX idx_scheduled_at (scheduled_at)
);

-- Row-level security policies (if using Supabase)
-- Uncomment for Supabase deployments:
/*
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Agents can view themselves" ON agents
    FOR SELECT USING (
        agent_id = current_user_id() OR
        current_user_role() = 'admin'
    );

CREATE POLICY "Admins can manage all" ON agents
    FOR ALL USING (
        current_user_role() = 'admin'
    );
*/

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_agents_created_at ON agents(created_at);
CREATE INDEX IF NOT EXISTS idx_policies_created_at ON policies(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_secret_leases_agent_valid ON secret_leases(agent_id, revoked_at) WHERE revoked_at IS NULL;

-- Create view for active leases
CREATE OR REPLACE VIEW active_secret_leases AS
SELECT
    sl.*,
    (sl.expires_at - CURRENT_TIMESTAMP) as time_remaining
FROM secret_leases sl
WHERE sl.revoked_at IS NULL
    AND sl.expires_at > CURRENT_TIMESTAMP;

-- Create view for audit summary
CREATE OR REPLACE VIEW audit_summary AS
SELECT
    DATE_TRUNC('day', timestamp) as date,
    event_type,
    status,
    COUNT(*) as count
FROM audit_logs
GROUP BY DATE_TRUNC('day', timestamp), event_type, status
ORDER BY date DESC, event_type;
