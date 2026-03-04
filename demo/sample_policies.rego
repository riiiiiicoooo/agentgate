# AgentGate Sample Authorization Policies
# Open Policy Agent (OPA) Rego policies for agent authorization and access control

package agentgate.authz

import data.agentgate.agents
import data.agentgate.secrets
import future.keywords.contains
import future.keywords.if
import future.keywords.in

# Default decision: deny all access unless explicitly allowed
default allow = false
default reason = "no matching policy"
default approval_required = false

# ============================================================================
# POLICY 1: Full Access Agent (GitHub Copilot)
# ============================================================================
# Allows GitHub Copilot to read and write to repositories with broad access
allow if {
    input.agent_type == "copilot"
    input.action in ["repo:read", "repo:write", "pull_request:read", "pull_request:write"]
}

reason = "github_copilot_full_access" if {
    input.agent_type == "copilot"
    input.action in ["repo:read", "repo:write", "pull_request:read", "pull_request:write"]
}

# ============================================================================
# POLICY 2: Read-Only Agent (CI/CD with restrictions)
# ============================================================================
# Restricts agents to read-only operations on repository
allow if {
    input.agent_type == "pipeline"
    input.action == "repo:read"
    input.environment != "production"
}

allow if {
    input.agent_type == "pipeline"
    input.action == "repo:read"
    input.environment == "production"
    input.approval_required == false
}

reason = "pipeline_read_only_access" if {
    input.agent_type == "pipeline"
    input.action == "repo:read"
}

reason = "pipeline_production_requires_approval" if {
    input.agent_type == "pipeline"
    input.action == "repo:read"
    input.environment == "production"
    input.approval_required == true
}

# ============================================================================
# POLICY 3: MFA-Protected Access (Cursor Editor)
# ============================================================================
# Require MFA verification for sensitive operations
allow if {
    input.agent_type == "editor"
    input.mfa_required == true
    input.mfa_verified == true
    input.action in ["repo:read", "repo:write"]
}

allow if {
    input.agent_type == "editor"
    input.action == "deploy:read"
    input.mfa_verified == true
}

reason = "editor_mfa_verified" if {
    input.agent_type == "editor"
    input.mfa_verified == true
}

reason = "editor_mfa_required_not_verified" if {
    input.agent_type == "editor"
    input.mfa_required == true
    input.mfa_verified != true
}

# Deny deployment write without explicit approval
denial_reason = "deploy_write_approval_required" if {
    input.agent_type == "editor"
    input.action == "deploy:write"
    input.approval_id == ""
}

# ============================================================================
# POLICY 4: Environment-Scoped Access (CI/CD Pipeline)
# ============================================================================
# Restrict resource access based on environment naming conventions
allow if {
    input.agent_type == "pipeline"
    input.environment == "development"
    startswith(input.resource, "dev-")
    input.action in ["repo:read", "repo:write", "deploy:write"]
}

allow if {
    input.agent_type == "pipeline"
    input.environment == "staging"
    startswith(input.resource, "staging-")
    input.action in ["repo:read", "repo:write", "deploy:write"]
}

allow if {
    input.agent_type == "pipeline"
    input.environment == "production"
    startswith(input.resource, "prod-")
    input.action in ["repo:read", "deploy:read"]
}

reason = "environment_scoped_access" if {
    input.agent_type == "pipeline"
    (
        (input.environment == "development" and startswith(input.resource, "dev-")) or
        (input.environment == "staging" and startswith(input.resource, "staging-")) or
        (input.environment == "production" and startswith(input.resource, "prod-"))
    )
}

# ============================================================================
# POLICY 5: Secrets Access Control
# ============================================================================
# Restrict secrets access with additional safeguards
allow if {
    input.agent_type == "copilot"
    input.action == "secrets:read"
    input.environment == "development"
    is_whitelisted_secret(input.secret_id)
}

allow if {
    input.agent_type == "pipeline"
    input.action == "secrets:read"
    is_whitelisted_for_ci(input.secret_id)
}

allow if {
    input.agent_type == "custom"
    input.action == "secrets:read"
    input.service == "analytics"
    is_read_only_secret(input.secret_id)
}

reason = "secrets_access_allowed" if {
    input.action == "secrets:read"
    (
        is_whitelisted_secret(input.secret_id) or
        is_whitelisted_for_ci(input.secret_id) or
        is_read_only_secret(input.secret_id)
    )
}

reason = "secrets_access_denied_not_whitelisted" if {
    input.action == "secrets:read"
    not is_whitelisted_secret(input.secret_id)
}

# ============================================================================
# POLICY 6: Time-Based Access Control
# ============================================================================
# Restrict critical operations to business hours
allow if {
    input.action == "deploy:write"
    is_business_hours
    input.environment != "production"
}

allow if {
    input.action == "deploy:write"
    input.environment == "production"
    is_business_hours
    input.approval_required == false
}

reason = "outside_business_hours_restricted" if {
    input.action == "deploy:write"
    not is_business_hours
}

# ============================================================================
# POLICY 7: Rate Limiting and Token Bucket
# ============================================================================
# Enforce operational limits based on cost
allow if {
    input.current_cost + input.operation_cost <= input.daily_budget
    input.requests_this_minute < input.rate_limit_per_minute
}

reason = "rate_limit_exceeded" if {
    input.requests_this_minute >= input.rate_limit_per_minute
}

reason = "daily_budget_exceeded" if {
    input.current_cost + input.operation_cost > input.daily_budget
}

# ============================================================================
# POLICY 8: IP Whitelist Enforcement
# ============================================================================
# Require IP whitelist for sensitive operations
allow if {
    input.action in ["secrets:write", "policy:modify"]
    ip_is_whitelisted(input.ip_address)
}

reason = "ip_not_whitelisted" if {
    input.action in ["secrets:write", "policy:modify"]
    not ip_is_whitelisted(input.ip_address)
}

# ============================================================================
# POLICY 9: Audit and Compliance
# ============================================================================
# Ensure all sensitive operations are audited
allow if {
    input.audit_event_id != ""
    input.action in ["secrets:read", "secrets:write", "deploy:write", "policy:modify"]
}

reason = "audit_required_missing_event_id" if {
    input.audit_event_id == ""
    input.action in ["secrets:read", "secrets:write", "deploy:write", "policy:modify"]
}

# ============================================================================
# Helper Functions
# ============================================================================

# Check if current time is within business hours (9 AM to 5 PM UTC)
is_business_hours if {
    hour := time.now_ns() / 3600000000000
    hour >= 9
    hour < 17
}

# Whitelist of secrets allowed for general agents
is_whitelisted_secret(secret_id) if {
    secret_id in [
        "api_key_public",
        "database_user_read_only",
        "npm_registry_token"
    ]
}

# Whitelist of secrets for CI/CD pipelines
is_whitelisted_for_ci(secret_id) if {
    secret_id in [
        "deploy_ssh_key",
        "github_token_ci",
        "docker_registry_password",
        "npm_token_ci"
    ]
}

# Identify read-only secrets (no modification allowed)
is_read_only_secret(secret_id) if {
    secret_id in [
        "analytics_api_key",
        "monitoring_token",
        "log_aggregation_key"
    ]
}

# Whitelist of allowed IP addresses for sensitive operations
ip_is_whitelisted(ip_address) if {
    ip_address in [
        "192.168.1.0/24",
        "10.0.0.0/8",
        "203.0.113.0/24"
    ]
}

# ============================================================================
# Violation Rules (Explicit Denies)
# ============================================================================

# Explicitly deny policy modification for non-admin agents
violation = "policy_modification_denied" if {
    input.action == "policy:modify"
    input.agent_type != "admin"
}

# Deny access to production secrets for non-approved agents
violation = "production_secret_access_denied" if {
    input.action == "secrets:read"
    contains(input.secret_id, "prod_")
    input.approval_id == ""
}

# Deny deletion operations for all agents except admin
violation = "deletion_not_permitted" if {
    contains(input.action, "delete")
    input.agent_type != "admin"
}

# ============================================================================
# Approval Requirements
# ============================================================================

# Require approval for production deployments
approval_required = true if {
    input.action == "deploy:write"
    input.environment == "production"
}

# Require approval for credential rotation
approval_required = true if {
    input.action == "credential:rotate"
    input.agent_type not in ["admin", "security"]
}

# Require approval for policy changes
approval_required = true if {
    input.action == "policy:modify"
}

# ============================================================================
# Test Cases
# ============================================================================

# Test: GitHub Copilot can read repositories
test_copilot_repo_read if {
    allow with input as {
        "agent_type": "copilot",
        "action": "repo:read"
    }
}

# Test: Pipeline agent can only read in production
test_pipeline_prod_read_only if {
    allow with input as {
        "agent_type": "pipeline",
        "environment": "production",
        "action": "repo:read"
    }
}

# Test: Cursor editor requires MFA for deployment
test_editor_mfa_deploy if {
    allow with input as {
        "agent_type": "editor",
        "action": "deploy:write",
        "mfa_verified": true,
        "approval_required": false
    }
}

# Test: Environment-scoped access works correctly
test_env_scope_dev if {
    allow with input as {
        "agent_type": "pipeline",
        "environment": "development",
        "resource": "dev-database",
        "action": "repo:write"
    }
}
