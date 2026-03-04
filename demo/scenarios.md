# AgentGate Demo Scenarios

This document provides detailed walkthroughs of five comprehensive demo scenarios that showcase AgentGate's core functionality.

## Overview

AgentGate is an AI Agent Authentication & Authorization Gateway that provides:
- **OAuth 2.0 Client Credentials** authentication for agents
- **OPA/Rego-based** policy engine for fine-grained access control
- **Just-in-time secret** provisioning and leasing
- **Comprehensive audit** logging for compliance
- **Rate limiting** and token budget enforcement
- **Prompt injection** detection for LLM-based agents

---

## Scenario 1: Agent Registration & Details

### Overview
This scenario demonstrates how different types of agents are registered with AgentGate and their respective permission levels and configurations.

### Sample Agents

#### 1. GitHub Copilot (Full Access Agent)
- **Type**: Copilot/LLM Code Assistant
- **Scopes**: repo:read, repo:write, pull_request:read, pull_request:write, secrets:read
- **Permission Level**: Full read/write to code repositories
- **MFA Required**: No
- **Rotation Interval**: 90 days
- **Use Case**: Provides AI-powered code completion and generation
- **Risk Level**: Medium

**Workflow**:
1. Developer installs GitHub Copilot extension in IDE
2. Copilot requests token from AgentGate using client credentials
3. AgentGate validates credentials and grants token with scopes
4. Copilot uses token to access code repositories, pull requests, and development secrets
5. All access is logged for audit purposes

#### 2. Cursor Editor (MFA-Protected Agent)
- **Type**: Editor/IDE Extension
- **Scopes**: repo:read, repo:write, deploy:read, audit:read
- **Permission Level**: Code access with deployment preview
- **MFA Required**: Yes (requires verified MFA)
- **Rotation Interval**: 60 days
- **Use Case**: Provides AI-enhanced code editing capabilities
- **Risk Level**: Medium

**Workflow**:
1. User authenticates in Cursor Editor with username/password
2. Cursor attempts deployment action
3. AgentGate checks MFA status - requires verification
4. User completes MFA challenge (TOTP/hardware key)
5. AgentGate grants deploy:read scope temporarily
6. Cursor can preview deployments but cannot execute

#### 3. Claude Code (High Capability Agent)
- **Type**: IDE/Terminal Tool
- **Scopes**: repo:read, repo:write, secrets:read, audit:read, deploy:read
- **Permission Level**: Broad code and secrets access
- **MFA Required**: No
- **Rotation Interval**: 30 days (frequent rotation)
- **Rate Limit**: 2000 requests/minute
- **Use Case**: Terminal integration with AI assistance
- **Risk Level**: Low (Anthropic managed)

**Workflow**:
1. User installs Claude Code CLI tool
2. Tool generates device code and requests authorization
3. User visits browser link to approve in AgentGate dashboard
4. Tool receives tokens and credentials
5. Maintains high rate limit due to trusted source

#### 4. CI/CD Pipeline Agent (Restricted Agent)
- **Type**: Pipeline/Automation
- **Scopes**: repo:read, repo:write, secrets:read, deploy:read, deploy:write, audit:read
- **Permission Level**: Read/write with environment restrictions
- **MFA Required**: No
- **Environment Restricted**: Production only on approval
- **Rotation Interval**: 14 days (very frequent)
- **Token TTL**: 2 hours (short-lived)
- **Use Case**: Automated testing, building, and deployment
- **Risk Level**: High (automated agent)

**Workflow**:
1. GitHub Actions workflow triggers
2. Requests token from AgentGate using CI secret
3. Token includes environment constraints (dev/staging/prod)
4. For production deployment, requires approval from AWS API
5. Token automatically revoked after workflow completes
6. All deployments audited with workflow ID

#### 5. Custom Internal Analytics Agent (Minimal Access)
- **Type**: Custom Service Agent
- **Scopes**: repo:read, secrets:read, audit:read, analytics:write
- **Permission Level**: Read-only with analytics output
- **MFA Required**: No
- **Rotation Interval**: 45 days
- **Token TTL**: 8 hours
- **Use Case**: Data pipeline orchestration and analytics
- **Risk Level**: Low

**Workflow**:
1. Internal analytics service starts daily job
2. Requests token for data access
3. Token limited to whitelisted analytics secrets
4. Can read code for metadata but cannot write
5. Output logged to analytics system
6. Tokens scoped to specific service endpoints

### Key Learning Points
- Different agent types have different permission models
- MFA can be required for sensitive operations
- Rotation intervals reflect risk level (CI agents rotate frequently)
- Token TTL varies by use case (CI agents get short-lived tokens)
- All agents logged and auditable

---

## Scenario 2: Policy Evaluation Engine

### Overview
AgentGate uses Open Policy Agent (OPA) with Rego language to define sophisticated authorization policies. This scenario shows how policies control agent access.

### Sample Policy Evaluation Cases

#### Test Case 1: GitHub Copilot Repository Read
**Input**:
```json
{
  "agent_type": "copilot",
  "action": "repo:read",
  "resource": "my-company/main-app"
}
```

**Policy Rule Applied**: `Full Access Agent Policy`
```rego
allow if {
    input.agent_type == "copilot"
    input.action in ["repo:read", "repo:write", "pull_request:read", "pull_request:write"]
}
```

**Decision**: ALLOW ✓

**Reason**: GitHub Copilot has blanket read/write access to repositories

**Audit Log Entry**:
```json
{
  "event_id": "event-0001",
  "timestamp": "2026-03-04T10:15:00Z",
  "agent_id": "copilot-github-001",
  "action": "POLICY_EVALUATION",
  "resource": "my-company/main-app",
  "decision": "ALLOW",
  "policy_matched": "full_access_agent_policy"
}
```

#### Test Case 2: Pipeline Agent Writing to Production
**Input**:
```json
{
  "agent_type": "pipeline",
  "action": "repo:write",
  "environment": "production",
  "resource": "prod-database-config"
}
```

**Policy Rule Applied**: `Environment-Scoped Access Policy`
```rego
allow if {
    input.agent_type == "pipeline"
    input.environment == "production"
    startswith(input.resource, "prod-")
    input.action in ["repo:read", "deploy:read"]  # Note: write not allowed!
}
```

**Decision**: DENY ✗

**Reason**: Pipeline agents can only READ in production, not WRITE

**Audit Log Entry**:
```json
{
  "event_id": "event-0002",
  "timestamp": "2026-03-04T10:16:00Z",
  "agent_id": "ci-pipeline-deploy-001",
  "action": "POLICY_EVALUATION",
  "resource": "prod-database-config",
  "decision": "DENY",
  "denial_reason": "pipeline_production_write_not_allowed"
}
```

#### Test Case 3: Cursor Editor Deploying with MFA
**Input**:
```json
{
  "agent_type": "editor",
  "action": "deploy:write",
  "environment": "production",
  "mfa_verified": true,
  "approval_required": false
}
```

**Policy Rule Applied**: `MFA-Protected Access Policy`
```rego
allow if {
    input.agent_type == "editor"
    input.action == "deploy:write"
    input.mfa_verified == true
    input.approval_required == false
}
```

**Decision**: ALLOW ✓

**Reason**: MFA verified + approval not required

**Audit Log Entry**:
```json
{
  "event_id": "event-0003",
  "timestamp": "2026-03-04T10:17:00Z",
  "agent_id": "cursor-editor-001",
  "action": "POLICY_EVALUATION",
  "resource": "production_deployment",
  "decision": "ALLOW",
  "details": {
    "mfa_verified": true,
    "approval_required": false
  }
}
```

#### Test Case 4: Pipeline Accessing Development Resources
**Input**:
```json
{
  "agent_type": "pipeline",
  "action": "repo:write",
  "environment": "development",
  "resource": "dev-database"
}
```

**Policy Rule Applied**: `Environment-Scoped Access Policy`
```rego
allow if {
    input.agent_type == "pipeline"
    input.environment == "development"
    startswith(input.resource, "dev-")
    input.action in ["repo:read", "repo:write", "deploy:write"]
}
```

**Decision**: ALLOW ✓

**Reason**: Full write access allowed in development environment

#### Test Case 5: Custom Agent Reading Whitelisted Secrets
**Input**:
```json
{
  "agent_type": "custom",
  "action": "secrets:read",
  "secret_id": "analytics_api_key",
  "service": "analytics"
}
```

**Policy Rule Applied**: `Secrets Access Control Policy`
```rego
allow if {
    input.agent_type == "custom"
    input.action == "secrets:read"
    input.service == "analytics"
    is_read_only_secret(input.secret_id)
}

is_read_only_secret(secret_id) if {
    secret_id in [
        "analytics_api_key",
        "monitoring_token",
        "log_aggregation_key"
    ]
}
```

**Decision**: ALLOW ✓

**Reason**: Secret is whitelisted for analytics service access

### Policy Caching
All policy evaluations are cached. Identical inputs within TTL return cached results in ~0.5ms instead of 5-10ms full evaluation.

### Key Learning Points
- Policies define fine-grained access rules in code
- Environment restrictions prevent accidental production changes
- MFA can gate sensitive operations
- Secrets access is whitelisted for specific agents
- All decisions are logged for audit/compliance

---

## Scenario 3: Secret Leasing & Management

### Overview
Instead of long-lived secrets, AgentGate uses a leasing model where secrets are provisioned just-in-time with automatic expiration.

### Secrets Catalog

1. **db_password** (Production Database)
   - Default TTL: 1 hour
   - Rotation interval: 30 days
   - Access: Requires secrets:read scope
   - Whitelisted agents: copilot, pipeline, custom

2. **api_key_github** (GitHub API)
   - Default TTL: 2 hours
   - Rotation interval: 90 days
   - Access: Requires secrets:read scope
   - Whitelisted agents: copilot, pipeline

3. **aws_credentials** (AWS IAM)
   - Default TTL: 1 hour
   - Rotation interval: 7 days (frequent due to AWS best practices)
   - Access: Requires secrets:read + deploy:write scopes
   - Whitelisted agents: pipeline only

### Lease Workflow Example

#### Agent: GitHub Copilot
**Step 1: Request Lease**
```http
POST /secrets/api_key_github/lease
Authorization: Bearer YOUR_JWT_TOKEN
Content-Type: application/json

{
  "ttl_seconds": 3600,
  "reason": "code_completion"
}
```

**Step 2: AgentGate Validation**
- ✓ Token is valid and not expired
- ✓ Copilot has secrets:read scope
- ✓ api_key_github is whitelisted for copilot
- ✓ No existing lease for this agent/secret combo

**Step 3: Lease Granted**
```json
{
  "lease_id": "lease-0001",
  "secret_id": "api_key_github",
  "secret_value": "ghp_xxxxxxxxxxxxxxxxxxx",
  "ttl_seconds": 3600,
  "expires_at": "2026-03-04T11:15:00Z",
  "renewable": true
}
```

**Step 4: Audit Logged**
```json
{
  "event_id": "event-lease-0001",
  "timestamp": "2026-03-04T10:15:00Z",
  "agent_id": "copilot-github-001",
  "action": "SECRET_LEASE_GRANTED",
  "resource": "api_key_github",
  "decision": "ALLOW",
  "details": {
    "lease_id": "lease-0001",
    "ttl_seconds": 3600
  }
}
```

#### Agent: CI/CD Pipeline
**Step 1: Request Lease**
```http
POST /secrets/aws_credentials/lease
Authorization: Bearer YOUR_JWT_TOKEN_CI
```

**Step 2: AgentGate Validation**
- ✓ CI token is valid and not expired
- ✓ Token has deploy:write scope
- ✓ aws_credentials is whitelisted for CI
- ✓ Lease issued successfully

**Step 3: Lease Granted**
```json
{
  "lease_id": "lease-0002",
  "secret_id": "aws_credentials",
  "secret_value": {
    "access_key_id": "ASIA...",
    "secret_access_key": "xxxx...",
    "session_token": "...",
    "expiration": "2026-03-04T11:15:00Z"
  },
  "ttl_seconds": 3600
}
```

### Lease Lifecycle

**Timeline**:
```
T+0:00  Lease issued - Agent begins using secret
T+0:10  Lease active - Agent happily using secret
T+0:55  Warning - 5 minutes remaining on lease
T+0:59  Last chance - Only 1 minute left
T+1:00  EXPIRED - Secret access denied
        Agent should have renewed lease before expiry
```

**Renewal Workflow** (before expiry):
```http
POST /leases/lease-0001/renew
Authorization: Bearer YOUR_JWT_TOKEN
```

**Response**:
```json
{
  "lease_id": "lease-0001",
  "renewed_at": "2026-03-04T10:55:00Z",
  "new_expiry": "2026-03-04T11:55:00Z",
  "ttl_seconds": 3600
}
```

### Automatic Cleanup
- Expired leases are automatically revoked
- Secret value is zeroed in memory
- Lease record kept for audit history
- If agent tries to use expired lease: 401 Unauthorized

### Key Learning Points
- Leasing model is more secure than static credentials
- Short TTLs force rotation and reduce blast radius
- Whitelisting limits which agents can access which secrets
- Audit trail shows who accessed what and when
- Automatic expiration prevents credential proliferation

---

## Scenario 4: Audit Log Review & Analysis

### Overview
Every action in AgentGate is audited. This scenario shows how to query and analyze the audit log.

### Audit Event Structure

```json
{
  "event_id": "event-0001",
  "timestamp": "2026-03-04T10:15:30Z",
  "agent_id": "copilot-github-001",
  "agent_type": "copilot",
  "action": "SECRET_ACCESS",
  "resource": "api_key_github",
  "decision": "ALLOW",
  "denial_reason": null,
  "ip_address": "203.0.113.45",
  "user_agent": "AgentGate-SDK/1.0",
  "request_id": "req-abc123def456",
  "evaluation_time_ms": 2.5,
  "cache_hit": true,
  "details": {
    "lease_id": "lease-0001",
    "ttl_seconds": 3600,
    "scope": "secrets:read"
  }
}
```

### Sample Queries

#### Query 1: All Denied Requests
**SQL-like Query**:
```
SELECT * FROM audit_log
WHERE decision = 'DENY'
ORDER BY timestamp DESC
```

**Result**:
```
event-0002: Pipeline agent DENIED repo:write to production
event-0005: Custom agent DENIED admin:modify scope
event-0008: Unknown agent DENIED all access (failed auth)
```

**Analysis**: 3 denied requests in past hour
- 1 legitimate policy restriction (pipeline prod write)
- 1 insufficient permissions (custom agent)
- 1 security concern (failed auth suggests attack attempt)

#### Query 2: Secret Access Audit Trail
**Query**: All secret access in past 24 hours
```
SELECT * FROM audit_log
WHERE action = 'SECRET_ACCESS'
AND timestamp > NOW() - INTERVAL '24 hours'
```

**Results**:
```
event-0001: copilot-github-001 accessed api_key_github - ALLOW
event-0003: ci-pipeline-deploy-001 accessed aws_credentials - ALLOW
event-0006: custom-internal-agent-001 accessed db_password - ALLOW
event-0009: copilot-github-001 accessed aws_credentials - DENY (no scope)
event-0012: unknown-agent accessed db_password - DENY (failed auth)
```

**Findings**:
- ✓ 3 legitimate secret accesses
- ⚠ 1 policy violation (copilot tried to access AWS creds without scope)
- ✗ 1 failed authentication (attempted unauthorized access)

#### Query 3: Agent Activity Summary
**Aggregate Query**: Activity by agent
```
SELECT agent_id, COUNT(*) as total_requests,
  SUM(CASE WHEN decision='ALLOW' THEN 1 ELSE 0 END) as allowed,
  SUM(CASE WHEN decision='DENY' THEN 1 ELSE 0 END) as denied
FROM audit_log
GROUP BY agent_id
ORDER BY total_requests DESC
```

**Results**:
```
copilot-github-001:      245 requests (242 allow, 3 deny)   99%
ci-pipeline-deploy-001:  156 requests (155 allow, 1 deny)   99%
cursor-editor-001:        48 requests (47 allow, 1 deny)    98%
custom-internal-agent:    12 requests (12 allow, 0 deny)   100%
```

**Insights**:
- Copilot is the most active agent (high usage)
- All agents have >98% allow rate (policies working as expected)
- Custom agent has perfect record

#### Query 4: Risk Analysis - Failed Authentication Attempts
**Query**: Failed authentication in past hour
```
SELECT * FROM audit_log
WHERE action LIKE 'AUTH%'
AND decision = 'DENY'
AND timestamp > NOW() - INTERVAL '1 hour'
```

**Results**:
```
event-0015: 2026-03-04 10:23:15 IP 192.0.2.1 - INVALID_CREDENTIALS (3rd attempt)
event-0016: 2026-03-04 10:24:30 IP 192.0.2.1 - INVALID_CREDENTIALS (4th attempt)
event-0017: 2026-03-04 10:25:45 IP 192.0.2.1 - INVALID_CREDENTIALS (5th attempt)
```

**Action**: Alert triggers after 5 failed attempts from same IP
- IP 192.0.2.1 added to temporary block list
- Email alert sent to security team
- Audit event created for security incident

### Compliance Report Generation

**Report Fields**:
```
Period: 2026-02-04 to 2026-03-04
Total Events: 4,521
Allowed: 4,413 (97.6%)
Denied: 108 (2.4%)

By Agent Type:
  Copilot: 1,245 events (27.5%)
  Pipeline: 1,156 events (25.5%)
  Editor: 856 events (18.9%)
  Custom: 654 events (14.5%)
  Other: 610 events (13.5%)

Security Incidents:
  Failed auth attempts: 23
  Policy violations: 8
  Revoked credentials: 2
  Suspicious patterns: 1

Compliance:
  GDPR: ✓ All secrets redacted
  SOC2: ✓ Immutable audit trail
  HIPAA: ✓ Encryption in transit/at rest
  PCI: ✓ Access logging complete
```

### Key Learning Points
- All actions are immutably logged
- Queries reveal patterns and anomalies
- Failed attempts suggest attack attempts
- Audit trail proves compliance
- Aggregates show usage trends

---

## Scenario 5: Credential Rotation Workflow

### Overview
AgentGate enforces regular credential rotation based on risk level. This scenario shows the complete rotation lifecycle.

### Rotation Schedule by Agent Type

| Agent Type | Interval | Reason | Impact |
|---|---|---|---|
| Copilot | 90 days | Medium risk, widely used | 20+ developers affected |
| Editor | 60 days | Medium risk, MFA protected | ~5 developers |
| Claude Code | 30 days | Low risk, Anthropic managed | Automation handles |
| CI/CD | 14 days | High risk, automated | Daily workflows (auto-renewal) |
| Custom | 45 days | Low risk, limited scope | Internal service restart |

### Rotation Workflow Detail

#### Phase 1: Detection (Day 35 for CI/CD Agent)
**AgentGate checks at hourly intervals**:
```
CI/CD Agent last rotated: 2026-02-20 16:30:00Z
Current time: 2026-03-06 09:00:00Z
Days elapsed: 14.69 days
Rotation interval: 14 days
STATUS: OVERDUE FOR ROTATION ⚠️
```

**Alert Notifications**:
1. Internal dashboard shows "Credential Rotation Overdue"
2. Email sent to DevOps team: "CI/CD credentials rotation required"
3. Metrics system increments "credentials_overdue" counter

#### Phase 2: Old Credentials Still Valid (Grace Period)
**Timeline**:
```
T-0:00:00  Rotation triggered
T+0:30:00  Old credentials still valid (accepting requests)
T+1:00:00  Old credentials still valid
T+2:00:00  Old credentials still valid
           ...all the while new credentials can be generated
```

**Request Handling During Rotation**:
```
Agent uses old credential:
  Request comes in with old client_secret
  AgentGate checks: "Is this old but valid secret?"
  Status: YES - old secret still in grace period
  Result: Request ALLOWED (with audit note: "using_old_credential")

Agent uses new credential:
  Request comes in with new client_secret
  AgentGate checks: "Is this the new secret?"
  Status: YES - new secret already issued
  Result: Request ALLOWED (with audit note: "using_new_credential")
```

#### Phase 3: New Credentials Generated
**Credentials Flow**:
```
Step 1: Admin initiates rotation (or automated trigger)
  POST /agents/ci-pipeline-deploy-001/rotate

Step 2: AgentGate generates new client_secret
  New secret: YOUR_NEW_CLIENT_SECRET_CI_PIPELINE_A1B2C3D4E5F6
  Old secret: YOUR_OLD_CLIENT_SECRET_CI_PIPELINE_ZXCVBNMASDFGH (still valid)

Step 3: New secret delivered securely
  Old secret revoked in AWS Secrets Manager: ✓
  New secret created in AWS Secrets Manager: ✓
  Notification sent to CI/CD team: "New credentials available"

Step 4: Credentials displayed in AgentGate dashboard
  CI team logs into AgentGate
  Sees "New credentials ready - old credentials expire in 24 hours"
  Downloads new credentials.json file

Step 5: CI/CD system updated
  New secret injected into GitHub Actions secrets: ✓
  New secret injected into GitLab CI variables: ✓
  Pipeline logs rotated: "Updated authentication credentials"
```

#### Phase 4: Grace Period Expiry
**Timeline**:
```
T+24:00:00  Grace period expires
            Old credentials REVOKED
            AgentGate rejects old secret

Request with old credential:
  Request comes in with old (now invalid) client_secret
  AgentGate checks validity
  Status: REVOKED - outside grace period
  Result: Request DENIED (401 Unauthorized)
  Audit: "credential_revoked_after_grace_period"
  Alert: "CI/CD system still using old credentials - incident!"

Request with new credential:
  Request comes in with new client_secret
  AgentGate checks validity
  Status: VALID - newly issued secret
  Result: Request ALLOWED
  Audit: "using_new_rotated_credential"
```

#### Phase 5: Automation Handles Renewal
**In practice, for CI agents**:
```
GitHub Actions checks run continuously:

Pre-rotation:
  [Run] npm test
  [Run] docker build
  [Run] npm publish
  Status: SUCCESS (using valid credentials)

During rotation window:
  [Run] npm test
  [Run] docker build - tries old credentials
  ERROR: 401 Unauthorized (old creds expired early)
  [Retry] docker build - tries new credentials
  [Retry] SUCCESS (new creds valid)

CI/CD system automatically:
  1. Detects credential failure
  2. Reloads fresh credentials from secrets manager
  3. Retries failed step with new credentials
  4. Completes successfully
  5. Sends "credentials rotated" notification
```

### Audit Trail for Rotation

```json
{
  "event_id": "event-rotation-001",
  "timestamp": "2026-03-06T09:00:00Z",
  "agent_id": "ci-pipeline-deploy-001",
  "action": "CREDENTIAL_ROTATION_TRIGGERED",
  "decision": "INITIATED",
  "details": {
    "old_secret_id": "secret-ci-001",
    "new_secret_id": "secret-ci-002",
    "trigger": "scheduled_rotation",
    "grace_period_hours": 24
  }
}

{
  "event_id": "event-rotation-002",
  "timestamp": "2026-03-06T10:30:00Z",
  "agent_id": "ci-pipeline-deploy-001",
  "action": "CREDENTIAL_ROTATED",
  "decision": "COMPLETED",
  "details": {
    "old_secret_id": "secret-ci-001",
    "new_secret_id": "secret-ci-002",
    "rotated_by": "automatic_scheduler",
    "rotation_time_ms": 245
  }
}

{
  "event_id": "event-rotation-003",
  "timestamp": "2026-03-07T09:00:00Z",
  "agent_id": "ci-pipeline-deploy-001",
  "action": "CREDENTIAL_REVOKED",
  "decision": "REVOKED",
  "details": {
    "secret_id": "secret-ci-001",
    "reason": "grace_period_expired",
    "used_for_days": 14
  }
}

{
  "event_id": "event-rotation-004",
  "timestamp": "2026-03-07T09:05:30Z",
  "agent_id": "ci-pipeline-deploy-001",
  "action": "AUTH_FAILED",
  "decision": "DENIED",
  "details": {
    "reason": "revoked_credential",
    "attempted_secret_id": "secret-ci-001"
  }
}
```

### Key Learning Points
- Rotation is automated but can be manual
- Grace period prevents service disruption
- Old credentials work during transition
- Audit trail shows complete lifecycle
- Failed auth triggers alerts if not handled

---

## Running the Demo

### Prerequisites
```bash
python3.8+
pip install -r requirements.txt
```

### Execute Demo
```bash
cd demo/
python3 run_demo.py
```

### Output
The demo will:
1. Load sample agents from JSON
2. Display agent registrations
3. Evaluate sample policies
4. Lease secrets with TTLs
5. Generate audit events
6. Export audit log to `audit_log_demo.json`
7. Print summary statistics

---

## Key Takeaways

1. **Agent Management**: Different agent types have different security requirements
2. **Policy Engine**: OPA/Rego enables powerful, auditable authorization
3. **Secret Leasing**: JIT provisioning with TTLs beats long-lived secrets
4. **Audit Logging**: Immutable logs enable compliance and forensics
5. **Credential Rotation**: Automated rotation reduces risk and blast radius
6. **Rate Limiting**: Cost-based rate limiting prevents abuse
7. **Prompt Injection**: ML-based detection protects against LLM attacks

---

## Next Steps

- Deploy AgentGate to production
- Integrate with your identity provider
- Configure custom policies for your use cases
- Set up Prometheus/Grafana monitoring
- Enable S3 audit log archival
- Configure email/Slack alerts
