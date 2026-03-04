# AgentGate Data Model

## Overview

This document describes the complete data model for AgentGate, including PostgreSQL schemas, Supabase configuration, Redis schemas, and database migrations.

## PostgreSQL Schemas

All tables use UUID primary keys with created_at/updated_at timestamps for audit trail. Sensitive data (secrets, API keys) are encrypted before storage.

### 1. Agents Table

Represents AI agents registered with AgentGate.

```sql
CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    agent_type VARCHAR(50) NOT NULL,  -- github-copilot, cursor, claude, langchain, custom
    owner_email VARCHAR(255) NOT NULL,
    team VARCHAR(100),
    environment VARCHAR(50),  -- dev, staging, prod
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE, PAUSED, REVOKED, ARCHIVED
    last_activity_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT agent_name_unique UNIQUE(name),
    CONSTRAINT agent_type_valid CHECK(agent_type IN ('github-copilot', 'cursor', 'claude', 'langchain', 'custom')),
    CONSTRAINT agent_status_valid CHECK(status IN ('ACTIVE', 'PAUSED', 'REVOKED', 'ARCHIVED')),
    CONSTRAINT environment_valid CHECK(environment IS NULL OR environment IN ('dev', 'staging', 'prod'))
);

-- Indexes for common queries
CREATE INDEX idx_agents_status ON agents(status);
CREATE INDEX idx_agents_owner ON agents(owner_email);
CREATE INDEX idx_agents_type ON agents(agent_type);
CREATE INDEX idx_agents_environment ON agents(environment);
CREATE INDEX idx_agents_team ON agents(team);
CREATE INDEX idx_agents_created_at ON agents(created_at DESC);
```

**Columns**:
- `id`: UUID primary key
- `name`: Unique agent name (e.g., "copilot-team-backend")
- `description`: Human-readable description
- `agent_type`: Type of agent (required for different handling)
- `owner_email`: Developer who owns this agent
- `team`: Team or group this agent belongs to
- `environment`: Deployment environment
- `status`: Current lifecycle state
- `metadata`: JSONB for custom fields (e.g., `{tags: ["prod", "critical"]}`)

---

### 2. Agent Credentials Table

Stores OAuth client credentials for agents.

```sql
CREATE TABLE agent_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    client_id VARCHAR(255) NOT NULL,
    client_secret_hash VARCHAR(255) NOT NULL,  -- NEVER plaintext, use bcrypt or Argon2
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    rotated_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,

    -- Constraints
    CONSTRAINT client_id_unique UNIQUE(client_id),
    CONSTRAINT agent_fk FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX idx_agent_credentials_agent_id ON agent_credentials(agent_id);
CREATE INDEX idx_agent_credentials_client_id ON agent_credentials(client_id);
CREATE INDEX idx_agent_credentials_active ON agent_credentials(is_active) WHERE is_active = TRUE;
```

**Columns**:
- `id`: UUID primary key
- `agent_id`: Reference to agent
- `client_id`: OAuth client ID (publicly visible, unique)
- `client_secret_hash`: Bcrypt hash of client secret (never store plaintext)
- `is_active`: Whether this credential is currently usable
- `expires_at`: Automatic expiration time

**Security**:
- Client secret is NEVER stored plaintext
- Only shown once at creation time
- Uses bcrypt or Argon2 for hashing
- All operations use constant-time comparison

---

### 3. Policies Table

Stores OPA/Rego policy documents.

```sql
CREATE TABLE policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    rego_content TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMP WITH TIME ZONE,

    -- Constraints
    CONSTRAINT policy_name_unique UNIQUE(name),
    CONSTRAINT policy_version_positive CHECK(version > 0)
);

-- Indexes
CREATE INDEX idx_policies_name ON policies(name);
CREATE INDEX idx_policies_active ON policies(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_policies_created_at ON policies(created_at DESC);
```

**Columns**:
- `rego_content`: Full Rego source code
- `version`: Incremented on each update for audit trail
- `archived_at`: Soft delete timestamp

**Example Rego Policy**:
```rego
package agentgate

# Default deny policy
default allow = false

# Allow staging agents to read staging secrets
allow {
    input.agent.environment == "staging"
    input.action == "read_secret"
    input.resource.environment == "staging"
}

# Allow specific agents unrestricted access
allow {
    input.agent.id == "agent-admin-123"
}

# Deny production access for unapproved agents
deny[msg] {
    input.resource.environment == "production"
    not is_approved_for_production[input.agent.id]
    msg := sprintf("Agent %v not approved for production access", [input.agent.id])
}

is_approved_for_production["agent-prod-001"] { }
is_approved_for_production["agent-prod-002"] { }
```

---

### 4. Policy Bindings Table

Maps policies to agents or agent groups.

```sql
CREATE TABLE policy_bindings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id UUID NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    agent_group VARCHAR(255),  -- e.g., "github-copilot-*", "team-backend-*"
    priority INTEGER DEFAULT 100,  -- lower = higher priority
    effective_from TIMESTAMP WITH TIME ZONE NOT NULL,
    effective_until TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT at_least_one CHECK((agent_id IS NOT NULL) OR (agent_group IS NOT NULL)),
    CONSTRAINT priority_valid CHECK(priority >= 0 AND priority <= 1000)
);

-- Indexes
CREATE INDEX idx_policy_bindings_policy_id ON policy_bindings(policy_id);
CREATE INDEX idx_policy_bindings_agent_id ON policy_bindings(agent_id);
CREATE INDEX idx_policy_bindings_agent_group ON policy_bindings(agent_group);
CREATE INDEX idx_policy_bindings_priority ON policy_bindings(priority);
```

**Columns**:
- `policy_id`: Reference to policy
- `agent_id`: Specific agent (if NULL, uses agent_group)
- `agent_group`: Wildcard group name (e.g., "github-copilot-staging-*")
- `priority`: Resolution order if multiple policies apply (lower = higher)
- `effective_from`/`until`: Time-based policy activation

---

### 5. Secrets Table

Metadata about secrets managed by AgentGate.

```sql
CREATE TABLE secrets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    secret_type VARCHAR(50) NOT NULL,  -- database, api_key, ssh_key, jwt, oauth_token
    backend_type VARCHAR(50) NOT NULL,  -- vault, aws_secrets_manager, 1password, infisical
    backend_config JSONB NOT NULL,  -- {path: "...", role: "...", auth_method: "..."}
    rotation_interval INTERVAL DEFAULT '90 days'::interval,
    rotation_due_at TIMESTAMP WITH TIME ZONE,
    ttl INTERVAL DEFAULT '1 hour'::interval,  -- lease lifetime
    is_rotatable BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT secret_name_unique UNIQUE(name),
    CONSTRAINT secret_type_valid CHECK(secret_type IN ('database', 'api_key', 'ssh_key', 'jwt', 'oauth_token', 'certificate')),
    CONSTRAINT backend_type_valid CHECK(backend_type IN ('vault', 'aws_secrets_manager', '1password', 'infisical', 'custom')),
    CONSTRAINT ttl_positive CHECK(EXTRACT(EPOCH FROM ttl) > 0)
);

-- Indexes
CREATE INDEX idx_secrets_name ON secrets(name);
CREATE INDEX idx_secrets_backend_type ON secrets(backend_type);
CREATE INDEX idx_secrets_rotation_due ON secrets(rotation_due_at) WHERE rotation_due_at IS NOT NULL;
```

**Columns**:
- `backend_config`: JSON with backend-specific configuration
  - Vault: `{path: "database/config/db", role: "agent-role"}`
  - AWS: `{secret_arn: "arn:aws:secretsmanager:...", region: "us-east-1"}`
  - 1Password: `{vault_id: "...", item_id: "..."}`

---

### 6. Secret Leases Table

Temporary credentials issued to agents.

```sql
CREATE TABLE secret_leases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    secret_id UUID NOT NULL REFERENCES secrets(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    lease_token VARCHAR(255) NOT NULL,
    issued_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE,
    secret_version INTEGER NOT NULL DEFAULT 1,
    backend_lease_id VARCHAR(255),  -- reference in backend system

    -- Constraints
    CONSTRAINT lease_token_unique UNIQUE(lease_token),
    CONSTRAINT expires_after_issued CHECK(expires_at > issued_at)
);

-- Indexes (critical for cleanup)
CREATE INDEX idx_secret_leases_agent_id ON secret_leases(agent_id);
CREATE INDEX idx_secret_leases_secret_id ON secret_leases(secret_id);
CREATE INDEX idx_secret_leases_token ON secret_leases(lease_token);
CREATE INDEX idx_secret_leases_expires_at ON secret_leases(expires_at);
CREATE INDEX idx_secret_leases_revoked_at ON secret_leases(revoked_at) WHERE revoked_at IS NOT NULL;
```

**Columns**:
- `lease_token`: Unique token for this specific lease
- `backend_lease_id`: Reference to lease in external system (Vault lease ID, AWS session ID, etc)
- `revoked_at`: When lease was manually revoked

---

### 7. Audit Events Table

Immutable audit log of all actions.

```sql
CREATE TABLE audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(50) NOT NULL,  -- agent_created, secret_requested, policy_updated, etc
    agent_id UUID REFERENCES agents(id),
    action VARCHAR(50) NOT NULL,  -- read, write, delete, execute
    resource VARCHAR(255),  -- secret name, policy id, agent id
    resource_type VARCHAR(50),  -- secret, policy, agent, credential
    resource_environment VARCHAR(50),  -- dev, staging, prod
    decision VARCHAR(50) NOT NULL,  -- ALLOW, DENY, AUDIT_ONLY
    reason TEXT,
    source_ip VARCHAR(45),  -- supports IPv4 and IPv6
    user_agent VARCHAR(255),
    policy_applied VARCHAR(255),  -- which policy was evaluated
    http_status INTEGER,
    error_message TEXT,
    enriched_data JSONB DEFAULT '{}'::jsonb,  -- GitHub user, AWS tags, etc
    request_id VARCHAR(255),  -- for correlation
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Immutability constraints
    CONSTRAINT audit_immutable_policy BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION raise_immutability_error()
);

-- Make table even more immutable at database level
ALTER TABLE audit_events DISABLE TRIGGER ALL;
ALTER TABLE audit_events DISABLE ROW SECURITY;

-- Indexes for query performance
CREATE INDEX idx_audit_events_agent_id ON audit_events(agent_id);
CREATE INDEX idx_audit_events_event_type ON audit_events(event_type);
CREATE INDEX idx_audit_events_decision ON audit_events(decision);
CREATE INDEX idx_audit_events_created_at ON audit_events(created_at DESC);
CREATE INDEX idx_audit_events_resource ON audit_events(resource);
CREATE INDEX idx_audit_events_source_ip ON audit_events(source_ip);
CREATE INDEX idx_audit_events_composite ON audit_events(agent_id, created_at DESC);
```

**Columns**:
- `event_type`: Categorizes the action (audit searches often filter by this)
- `decision`: ALLOW = successful action, DENY = blocked by policy, AUDIT_ONLY = logged but allowed
- `enriched_data`: Additional context (GitHub username, AWS resource tags, etc)

**Example Events**:
```json
{
  "event_type": "secret_requested",
  "agent_id": "agent-123",
  "action": "read",
  "resource": "db_password",
  "decision": "ALLOW",
  "reason": "Policy allows staging agents to read staging secrets",
  "source_ip": "10.0.1.5",
  "policy_applied": "staging-policy-v2",
  "enriched_data": {
    "owner": "alice@company.com",
    "team": "backend",
    "repository": "core-api"
  }
}

{
  "event_type": "secret_requested",
  "agent_id": "agent-456",
  "action": "read",
  "resource": "prod_db_password",
  "decision": "DENY",
  "reason": "Agent not approved for production access",
  "source_ip": "192.168.1.100",
  "error_message": "Authorization failed",
  "enriched_data": {
    "owner": "bob@company.com",
    "team": "qa"
  }
}
```

---

### 8. OAuth Tokens Table

For fast revocation checking.

```sql
CREATE TABLE oauth_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    jti VARCHAR(255) NOT NULL,  -- JWT ID for revocation
    issued_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE,
    revocation_reason VARCHAR(255),

    -- Constraints
    CONSTRAINT jti_unique UNIQUE(jti),
    CONSTRAINT expires_after_issued CHECK(expires_at > issued_at)
);

-- Indexes
CREATE INDEX idx_oauth_tokens_agent_id ON oauth_tokens(agent_id);
CREATE INDEX idx_oauth_tokens_jti ON oauth_tokens(jti);
CREATE INDEX idx_oauth_tokens_revoked ON oauth_tokens(revoked_at) WHERE revoked_at IS NOT NULL;
CREATE INDEX idx_oauth_tokens_expires ON oauth_tokens(expires_at);

-- Automatic cleanup of expired tokens
CREATE OR REPLACE FUNCTION cleanup_expired_tokens()
RETURNS void AS $$
BEGIN
    DELETE FROM oauth_tokens WHERE expires_at < NOW() - INTERVAL '1 day';
END;
$$ LANGUAGE plpgsql;
```

---

### 9. Rate Limit Rules Table

Configuration for rate limiting.

```sql
CREATE TABLE rate_limit_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    agent_type VARCHAR(50),  -- applies to all agents of this type if agent_id is NULL
    requests_per_second INTEGER DEFAULT 10,
    requests_per_minute INTEGER DEFAULT 600,
    requests_per_hour INTEGER DEFAULT 36000,
    token_budget_per_day INTEGER,  -- for LLM agents (tokens, not requests)
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT at_least_one_target CHECK((agent_id IS NOT NULL) OR (agent_type IS NOT NULL)),
    CONSTRAINT limits_positive CHECK(
        requests_per_second > 0 AND
        requests_per_minute > 0 AND
        requests_per_hour > 0
    ),
    CONSTRAINT unique_agent_rule UNIQUE(agent_id),
    CONSTRAINT unique_type_rule UNIQUE(agent_type)
);

-- Indexes
CREATE INDEX idx_rate_limits_agent_id ON rate_limit_rules(agent_id);
CREATE INDEX idx_rate_limits_agent_type ON rate_limit_rules(agent_type);
```

---

### 10. Audit Compliance Snapshots Table

Snapshots for compliance reports.

```sql
CREATE TABLE compliance_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    compliance_type VARCHAR(50) NOT NULL,  -- SOC2, HIPAA, FedRAMP, PCI-DSS
    snapshot_date TIMESTAMP WITH TIME ZONE NOT NULL,
    total_agents INTEGER NOT NULL,
    total_secrets INTEGER NOT NULL,
    total_audit_events BIGINT NOT NULL,
    agents_with_active_policies INTEGER NOT NULL,
    denied_requests_count BIGINT NOT NULL,
    policy_violations_count BIGINT NOT NULL,
    snapshot_data JSONB,  -- detailed metrics
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT compliance_type_valid CHECK(compliance_type IN ('SOC2', 'HIPAA', 'FedRAMP', 'PCI-DSS'))
);

-- Indexes
CREATE INDEX idx_compliance_snapshots_type ON compliance_snapshots(compliance_type);
CREATE INDEX idx_compliance_snapshots_date ON compliance_snapshots(snapshot_date DESC);
```

---

## Supabase Configuration

### Row-Level Security (RLS) Policies

RLS ensures data is accessed only by authorized parties.

```sql
-- Agents: Users can see agents they own or that are in their team
CREATE POLICY agents_owner_read ON agents FOR SELECT
    USING (owner_email = current_user_email() OR team = current_user_team());

CREATE POLICY agents_admin_all ON agents FOR ALL
    USING (current_user_role() = 'admin');

-- Audit Events: Only security team and auditors can read
CREATE POLICY audit_events_read_security ON audit_events FOR SELECT
    USING (current_user_role() IN ('security', 'auditor', 'admin'));

CREATE POLICY audit_events_insert_system ON audit_events FOR INSERT
    WITH CHECK (current_user_role() = 'system' OR current_user_role() = 'admin');

-- Audit events: Nobody can delete (immutable)
CREATE POLICY audit_events_no_delete ON audit_events FOR DELETE
    USING (false);

-- Policies: Can be read by all authenticated users, modified by admins
CREATE POLICY policies_read ON policies FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY policies_modify ON policies FOR UPDATE
    USING (current_user_role() = 'admin');

-- Rate Limits: Admins only
CREATE POLICY rate_limits_admin ON rate_limit_rules FOR ALL
    USING (current_user_role() = 'admin');
```

### Custom Functions

```sql
-- Function to get current user email from JWT
CREATE OR REPLACE FUNCTION current_user_email() RETURNS text AS $$
  SELECT auth.jwt() -> 'email'
$$ LANGUAGE sql;

-- Function to get current user role
CREATE OR REPLACE FUNCTION current_user_role() RETURNS text AS $$
  SELECT auth.jwt() -> 'user_role'
$$ LANGUAGE sql;

-- Function to prevent audit event modification
CREATE OR REPLACE FUNCTION raise_immutability_error()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit events are immutable and cannot be modified or deleted';
END;
$$ LANGUAGE plpgsql;

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all tables with updated_at
CREATE TRIGGER update_agents_updated_at BEFORE UPDATE ON agents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_policies_updated_at BEFORE UPDATE ON policies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_secrets_updated_at BEFORE UPDATE ON secrets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

---

## Redis Schemas

Redis stores ephemeral data: sessions, rate limit counters, and caches.

### Session Storage

```
Key: session:{jti}
Value: {
  "agent_id": "agent-123",
  "client_id": "client-abc123",
  "scopes": ["secrets:read", "policies:query"],
  "issued_at": 1705334400,
  "expires_at": 1705338000
}
TTL: token_expiry_time
Type: string (JSON)
```

### Revocation List

```
Key: revoked_tokens:{agent_id}
Value: ["jti-1", "jti-2", "jti-3"]
TTL: token_expiry_time + 1 day (grace period)
Type: set
```

### Rate Limit Counters

```
Key: ratelimit:{agent_id}:requests_second
Value: 5 (integer, atomic increment)
TTL: 1 second
Type: string

Key: ratelimit:{agent_id}:requests_minute
Value: 45
TTL: 1 minute
Type: string

Key: ratelimit:{agent_id}:tokens_today
Value: 8500 (for LLM agents)
TTL: 24 hours (reset at midnight UTC)
Type: string
```

### Secret Cache

```
Key: secret_cache:{agent_id}:{secret_name}:{version}
Value: {
  "secret": "actual_secret_value",
  "expires_at": 1705338000,
  "version": 3,
  "cached_at": 1705334400
}
TTL: 5 minutes (configurable)
Type: string (JSON)

Key: secret_cache:index:{secret_name}
Value: ["{agent_id}:{version}", ...]
TTL: 5 minutes
Type: set (for tracking which agents have cached this secret)
```

### Policy Evaluation Cache

```
Key: policy_eval:{policy_id}:{agent_id}:{resource_name}:{action}
Value: {
  "decision": "ALLOW",
  "reason": "Policy rule 5 matched",
  "evaluated_at": 1705334400
}
TTL: 5 minutes (configurable, shorter for security-sensitive policies)
Type: string (JSON)

Key: policy_eval:index:{policy_id}
Value: ["{agent_id}:{resource}:{action}", ...]
TTL: 5 minutes
Type: set (for invalidating cache when policy updates)
```

### Agent Metadata Cache

```
Key: agent:{agent_id}
Value: {
  "id": "agent-123",
  "name": "copilot-team-backend",
  "status": "ACTIVE",
  "environment": "prod",
  "team": "backend",
  "owner_email": "alice@company.com"
}
TTL: 1 hour
Type: string (JSON)

Key: agents:by_email:{owner_email}
Value: ["agent-123", "agent-456"]
TTL: 1 hour
Type: set
```

### Background Job Tracking

```
Key: job:rotation:secret:{secret_id}
Value: {
  "started_at": 1705334400,
  "status": "in_progress",
  "retry_count": 0
}
TTL: 1 hour
Type: string (JSON)

Key: jobs:pending
Value: ["rotation:secret:secret-1", "rotation:secret:secret-2"]
TTL: none (persist until processed)
Type: list
```

---

## Database Migrations

Migrations use Alembic (Python) for version control and reproducibility.

### Migration 001: Initial Schema

```python
# migrations/versions/001_initial_schema.py

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    # Create agents table
    op.create_table('agents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('agent_type', sa.String(50), nullable=False),
        sa.Column('owner_email', sa.String(255), nullable=False),
        sa.Column('team', sa.String(100)),
        sa.Column('environment', sa.String(50)),
        sa.Column('status', sa.String(50), nullable=False, server_default='ACTIVE'),
        sa.Column('last_activity_at', sa.DateTime(timezone=True)),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    # Create agent_credentials table
    op.create_table('agent_credentials',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('client_id', sa.String(255), nullable=False),
        sa.Column('client_secret_hash', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('rotated_at', sa.DateTime(timezone=True)),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('client_id'),
    )

    # Create indices
    op.create_index('idx_agents_status', 'agents', ['status'])
    op.create_index('idx_agents_owner', 'agents', ['owner_email'])
    op.create_index('idx_agent_credentials_agent_id', 'agent_credentials', ['agent_id'])
    op.create_index('idx_agent_credentials_client_id', 'agent_credentials', ['client_id'])

def downgrade():
    op.drop_table('agent_credentials')
    op.drop_table('agents')
```

### Migration 002: Policies and Audit

```python
# migrations/versions/002_policies_and_audit.py

def upgrade():
    # Create policies table
    op.create_table('policies',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('rego_content', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('archived_at', sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    # Create audit_events table (immutable)
    op.create_table('audit_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True)),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('resource', sa.String(255)),
        sa.Column('resource_type', sa.String(50)),
        sa.Column('resource_environment', sa.String(50)),
        sa.Column('decision', sa.String(50), nullable=False),
        sa.Column('reason', sa.Text()),
        sa.Column('source_ip', sa.String(45)),
        sa.Column('user_agent', sa.String(255)),
        sa.Column('policy_applied', sa.String(255)),
        sa.Column('http_status', sa.Integer()),
        sa.Column('error_message', sa.Text()),
        sa.Column('enriched_data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}'),
        sa.Column('request_id', sa.String(255)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create indices
    op.create_index('idx_audit_events_agent_id', 'audit_events', ['agent_id'])
    op.create_index('idx_audit_events_created_at', 'audit_events', ['created_at'], postgresql_using='btree')
    op.create_index('idx_audit_events_decision', 'audit_events', ['decision'])

def downgrade():
    op.drop_table('audit_events')
    op.drop_table('policies')
```

### Migration 003: Secrets and Leases

```python
# migrations/versions/003_secrets_and_leases.py

def upgrade():
    # Create secrets table
    op.create_table('secrets',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('secret_type', sa.String(50), nullable=False),
        sa.Column('backend_type', sa.String(50), nullable=False),
        sa.Column('backend_config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('rotation_interval', sa.Interval(), server_default='90 days'),
        sa.Column('rotation_due_at', sa.DateTime(timezone=True)),
        sa.Column('ttl', sa.Interval(), server_default='1 hour'),
        sa.Column('is_rotatable', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    # Create secret_leases table
    op.create_table('secret_leases',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('secret_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('lease_token', sa.String(255), nullable=False),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.Column('secret_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('backend_lease_id', sa.String(255)),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['secret_id'], ['secrets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lease_token'),
    )

    # Create indices
    op.create_index('idx_secrets_name', 'secrets', ['name'])
    op.create_index('idx_secret_leases_expires_at', 'secret_leases', ['expires_at'])
    op.create_index('idx_secret_leases_agent_id', 'secret_leases', ['agent_id'])

def downgrade():
    op.drop_table('secret_leases')
    op.drop_table('secrets')
```

---

## Database Performance Tuning

### Vacuum and Analyze

```sql
-- Periodic maintenance
VACUUM ANALYZE audit_events;  -- optimize large table
REINDEX TABLE secret_leases;  -- rebuild indices
CLUSTER audit_events USING idx_audit_events_created_at;  -- physical sort by created_at
```

### Connection Pooling

```python
# Using pgbouncer for connection pooling
# /etc/pgbouncer/pgbouncer.ini
[databases]
agentgate = host=postgres.internal port=5432 dbname=agentgate

[pgbouncer]
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
reserve_pool_size = 5
```

---

## Backup and Recovery

### PostgreSQL Backups

```bash
# Daily full backup
pg_dump -Fc agentgate > agentgate-$(date +%Y-%m-%d).dump

# WAL-based continuous archiving
wal_level = replica
archive_mode = on
archive_command = 'cp %p /backup/wal_archive/%f'

# PITR (point-in-time recovery)
restore_command = 'cp /backup/wal_archive/%f %p'
```

### Redis Backups

```bash
# RDB snapshot
CONFIG GET save
# Default: 900 15, 300 10, 60 10000

# AOF persistence
appendonly yes
appendfsync everysec
```

