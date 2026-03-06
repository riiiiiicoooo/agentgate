# AgentGate Improvements & Technology Roadmap

A comprehensive analysis of the AgentGate codebase with actionable improvements, emerging technologies, and a prioritized roadmap for evolving the platform.

---

## Product Overview

AgentGate is an authentication, authorization, and secrets management gateway purpose-built for AI agents (GitHub Copilot, Cursor, Claude Code, and custom LLM-powered automation). It solves a critical enterprise gap: as organizations adopt AI coding agents across engineering teams, those agents inherit overly broad credentials, access secrets without governance, and operate with no audit trail.

The platform provides:

- **OAuth 2.0 client credentials flow** for agent-to-service authentication with JWT access tokens
- **OPA/Rego-inspired policy engine** for attribute-based access control with caching
- **Just-in-time secret leasing** with automatic TTL expiration and multi-provider backends (Vault, AWS Secrets Manager, 1Password)
- **Audit logging** with SIEM integration (Splunk, Datadog, S3) for SOC 2 compliance
- **Token budget enforcement** with per-agent monthly/hourly limits to prevent runaway LLM spend
- **Prompt injection detection** using pattern-based heuristics
- **MCP server** for Model Context Protocol integration

Built for a Series B developer tools company (75 engineers, 12 squads) that experienced a near-miss where a CI/CD agent auto-committed production database credentials to a public PR.

---

## Current Architecture

### Tech Stack

| Layer | Technology | Files |
|-------|-----------|-------|
| API Server | Python 3.11+ / FastAPI | `src/api/endpoints/*.py` |
| Policy Engine | Custom OPA/Rego-inspired | `src/policy/engine.py`, `src/policy/defaults.py` |
| Secrets Broker | JIT leasing, multi-provider | `src/secrets/broker.py`, `src/secrets/providers.py`, `src/secrets/rotation.py` |
| Identity | Agent registration, JWT | `src/identity/manager.py`, `src/identity/tokens.py` |
| Audit | Structured logging, SIEM export | `src/audit/logger.py` |
| Gateway | LLM proxy, token budgets | `src/gateway/token_budget.py`, `src/api/endpoints/gateway.py` |
| Database | PostgreSQL 15 (asyncpg) | `src/db/connection.py`, `src/db/migrations/001_initial_schema.sql` |
| Cache | Redis 7 | Referenced in `docker-compose.yml` |
| SDK | TypeScript | `sdk/src/index.ts`, `sdk/src/auth.ts` |
| CLI | TypeScript (Commander.js) | `cli/src/commands/*.ts` |
| MCP | Python | `mcp/server.py` |
| Observability | OpenTelemetry + Prometheus + Grafana | `observability/instrumentation.py` |
| Infrastructure | Terraform (AWS ECS Fargate + Aurora PostgreSQL + ElastiCache) | `terraform/main.tf` |

### Key Components

1. **IdentityManager** (`src/identity/manager.py`) -- In-memory agent registry with SHA-256 hashed client secrets. Manages registration, credential verification, rotation, API key lifecycle, and deactivation.

2. **TokenProvider** (`src/identity/tokens.py`) -- HS256 JWT creation/validation. Access tokens (1 hour), refresh tokens (30 days). Symmetric secret from environment variable.

3. **PolicyEngine** (`src/policy/engine.py`) -- Evaluates compiled policies with rules containing effect/actions/resources/conditions. Supports wildcard resource matching (fnmatch), condition operators (eq, neq, in, contains, matches), and an in-memory decision cache (dict-based LRU).

4. **SecretsBroker** (`src/secrets/broker.py`) -- Lease-based secret access with TTL (60s-86400s), renewal limits (max 3), access tracking, and periodic cleanup. Stores secret values in memory alongside leases.

5. **SecretProviders** (`src/secrets/providers.py`) -- Abstract provider with implementations for EnvVar, Vault, AWS Secrets Manager, 1Password, and a MultiProvider router. Vault/AWS/1Password implementations are currently stubs.

6. **AuditLogger** (`src/audit/logger.py`) -- In-memory deque buffer (10k events) with exporters for Splunk, Datadog, and S3. Supports filtering by event_type, actor, resource, severity.

7. **TokenBudgetManager** (`src/gateway/token_budget.py`) -- Per-agent monthly/hourly token limits with automatic reset. Used by the gateway to enforce LLM API spend limits.

8. **Prompt Injection Detection** (`src/api/endpoints/gateway.py`) -- Regex-based pattern matching for instruction override, role override, data extraction, jailbreak, SQL injection, and code injection patterns.

---

## Recommended Improvements

### 1. Replace In-Memory State with Database Persistence

**Problem:** The core business logic stores all state in Python dictionaries and lists. `IdentityManager.agents` (dict), `SecretsBroker.leases` (dict), `AuditLogger.buffer` (deque), `TokenBudgetManager.budgets` (dict), and `agents_db` in `src/api/endpoints/agents.py` are all in-memory. A server restart loses all agents, active leases, and audit history.

**Files affected:**
- `src/identity/manager.py` lines 62-63 (`self.agents`, `self.client_id_to_agent`)
- `src/secrets/broker.py` line 108 (`self.leases`)
- `src/audit/logger.py` line 105 (`self.buffer`)
- `src/gateway/token_budget.py` line 123 (`self.budgets`)
- `src/api/endpoints/agents.py` line 106 (`agents_db`)
- `src/api/endpoints/secrets.py` lines 106-108 (`leases_db`, `secrets_db`, `audit_log`)
- `src/api/endpoints/gateway.py` line 83 (`agent_usage`)

**Fix:** The database schema already exists in `src/db/migrations/001_initial_schema.sql` with proper tables for agents, api_keys, policies, policy_bindings, secrets, secret_leases, audit_logs, token_budgets, and secret_rotations. Wire each manager class to use `src/db/connection.py` query functions (`execute`, `fetch`, `fetchrow`, `fetchval`) instead of in-memory dicts. Use Redis (`docker-compose.yml` already provisions it) for hot caches and rate limiting counters.

### 2. Upgrade JWT from HS256 to RS256/ES256

**Problem:** `src/identity/tokens.py` line 17 uses `HS256` (symmetric HMAC) with a shared secret. Every service that needs to validate tokens must know the signing secret. This is a security risk in a distributed system -- if any validating service is compromised, the secret is exposed and tokens can be forged.

**Fix:** Switch to RS256 (RSA) or ES256 (ECDSA) asymmetric signing. The API server holds the private key and signs tokens; all other services validate with the public key. This also enables standard JWKS (JSON Web Key Set) endpoint publication at `/.well-known/jwks.json`, which is the industry-standard pattern for token verification in distributed systems.

```python
# tokens.py changes
JWT_ALGORITHM = "ES256"  # or "RS256"
# Load from files or environment
PRIVATE_KEY = load_private_key(os.getenv("JWT_PRIVATE_KEY_PATH"))
PUBLIC_KEY = load_public_key(os.getenv("JWT_PUBLIC_KEY_PATH"))
```

### 3. Implement Proper Secret Hashing with bcrypt

**Problem:** `src/identity/manager.py` lines 92, 138, 171 use `hashlib.sha256` for client secret hashing. SHA-256 is fast, which makes it vulnerable to brute-force attacks. The `requirements.txt` already includes `bcrypt==4.1.1` and `passlib==1.7.4`, but they are unused.

**Fix:** Replace SHA-256 with bcrypt for all credential storage:

```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash
client_secret_hash = pwd_context.hash(client_secret)

# Verify
is_valid = pwd_context.verify(client_secret, stored_hash)
```

### 4. Fix Policy Engine Cache Key Bug

**Problem:** `src/policy/engine.py` line 385-388 applies `@lru_cache` to `_generate_cache_key`, but the method signature accepts a `str` parameter called `input_data`. However, line 220 calls it with a dict (`cache_input`), not a string. Additionally, `lru_cache` requires hashable arguments, and dicts are not hashable. The method needs to serialize the dict first.

**Fix:**
```python
def _generate_cache_key(self, input_data: Dict[str, Any]) -> str:
    """Generate cache key for input."""
    data_str = json.dumps(input_data, sort_keys=True, default=str)
    return hashlib.sha256(data_str.encode()).hexdigest()
```

Also, the cache eviction at line 392-395 uses a naive "remove first item" approach. Replace with `cachetools.TTLCache` or `cachetools.LRUCache` for proper LRU semantics with TTL-based expiration.

### 5. Implement Actual Secret Provider Integrations

**Problem:** `src/secrets/providers.py` -- the `VaultProvider`, `AWSSecretsManagerProvider`, and `OnePasswordProvider` classes are all stubs that return hardcoded strings (lines 109, 152, 192). This means the multi-provider architecture does not actually connect to any real secret backend.

**Fix:** Implement real integrations using:
- **Vault:** `hvac` library (https://github.com/hvac/hvac) -- the standard Python client for HashiCorp Vault
- **AWS Secrets Manager:** `boto3` with `aiobotocore` for async support
- **1Password:** `onepassword-sdk` (https://github.com/1Password/onepassword-sdk-python) -- 1Password's official SDK

### 6. Add Token Revocation List / Blocklist

**Problem:** `src/identity/tokens.py` has no mechanism to revoke issued JWTs before expiry. If an agent is deactivated via `IdentityManager.deactivate_agent()`, any tokens it already holds remain valid until natural expiration (up to 1 hour for access tokens, 30 days for refresh tokens).

**Fix:** Implement a token revocation strategy:
- **Redis-backed blocklist:** On revocation, add the token's `jti` (JWT ID -- currently missing from the payload) to a Redis set with TTL matching the token's remaining lifetime. Check the blocklist on every `verify_token()` call.
- **Add `jti` claim** to all tokens for unique identification.
- **Short-lived tokens:** Reduce access token TTL from 3600s to 300-900s and rely more on the refresh flow.

### 7. Harden Prompt Injection Detection

**Problem:** `src/api/endpoints/gateway.py` lines 103-117 use basic regex patterns that are easily bypassed. The test fixtures in `tests/conftest.py` lines 362-400 explicitly include unicode obfuscation and base64 encoding bypass test cases, but the current detection does not handle these.

**Fix:**
- Add unicode normalization before pattern matching (`unicodedata.normalize('NFKC', prompt)`)
- Add base64 decoding detection (detect and decode base64 strings, then check)
- Add LLM-based classification as a second pass for high-value requests (e.g., using Claude Haiku for fast classification)
- Integrate with Promptfoo evals (`evals/promptfoo/`) to continuously test and improve detection
- Consider the `rebuff` library (https://github.com/protectai/rebuff) for ML-based injection detection

### 8. Add Rate Limiting Middleware

**Problem:** The `docker-compose.yml` provisions Redis and `requirements.txt` includes `redis==5.2.0`, but there is no actual rate limiting middleware in the API layer. The gateway endpoint has ad-hoc per-agent token tracking in `agent_usage` (line 83), but this is in-memory and does not protect other endpoints.

**Fix:** Add Redis-backed rate limiting using `slowapi` or a custom middleware:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, storage_uri="redis://redis:6379")
app.state.limiter = limiter

@app.get("/api/v1/agents")
@limiter.limit("100/minute")
async def list_agents(request: Request):
    ...
```

### 9. Add Request Validation and Input Sanitization

**Problem:** Several endpoints accept user input without sufficient validation:
- `src/api/endpoints/secrets.py` line 148 -- auto-creates secrets on request if they do not exist, which could be exploited
- `src/api/endpoints/gateway.py` line 258 -- token estimation is `len(prompt) // 4`, which is inaccurate
- Policy engine conditions in `src/policy/engine.py` line 379 use `re.search(value, field_str)` where `value` comes from policy definitions -- if policies are user-defined, this could enable ReDoS attacks

**Fix:**
- Remove auto-creation of secrets; require explicit secret registration
- Use `tiktoken` for accurate token counting
- Validate regex patterns in policy conditions during compilation, and use `re.compile()` with a timeout or limited pattern complexity

### 10. Add Health Check and Readiness Probes

**Problem:** The `docker-compose.yml` references `/health` endpoint (line 77), and the SDK has `health()` and `readiness()` methods, but the actual health/readiness endpoints are not implemented in the API layer (not found in any of the endpoint files).

**Fix:** Add a proper health check router that verifies:
- Database connectivity (`src/db/connection.py` already has `health_check()`)
- Redis connectivity
- Policy engine loaded
- Identity manager initialized

### 11. Add Structured Error Responses

**Problem:** Error handling across endpoints is inconsistent. Some raise `HTTPException` with custom messages, others return generic "Failed to..." strings. There is no standard error response schema for API consumers.

**Fix:** Define a standard error model and exception handler:

```python
class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: Optional[dict] = None
    request_id: str
    timestamp: datetime

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error_code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            request_id=request.state.request_id,
            timestamp=datetime.now(timezone.utc),
        ).dict()
    )
```

### 12. Add Pydantic Settings for Configuration Management

**Problem:** Configuration is scattered across files using `os.getenv()` with hardcoded defaults:
- `src/identity/tokens.py` line 16: `JWT_SECRET` with default `"YOUR_JWT_SECRET_KEY_CHANGE_IN_PRODUCTION"`
- `src/db/connection.py` line 23: `DATABASE_URL` with default containing `password`
- `requirements.txt` already includes `pydantic-settings==2.6.0` but it is unused

**Fix:** Create a centralized settings module:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "ES256"
    redis_url: str = "redis://localhost:6379"
    cors_origins: list[str] = ["http://localhost:3000"]
    environment: str = "development"

    class Config:
        env_file = ".env"
        env_prefix = "AGENTGATE_"

settings = Settings()
```

### 13. Fix SQL Migration Syntax

**Problem:** `src/db/migrations/001_initial_schema.sql` uses MySQL-style `INDEX` declarations inside `CREATE TABLE` statements (e.g., line 18: `INDEX idx_agent_id (agent_id)`). PostgreSQL does not support this syntax. These would cause the migration to fail.

**Fix:** Move all indexes to separate `CREATE INDEX IF NOT EXISTS` statements after the table creation (some already exist at lines 171-174, but the inline ones would cause errors).

### 14. Add Multi-Tenancy Support

**Problem:** The current architecture has no concept of organizations or tenants. All agents, policies, and secrets share a single namespace. The RLS policies in the migration file are commented out (lines 154-168).

**Fix:** Add an `organization_id` foreign key to agents, policies, and secrets tables. Enable PostgreSQL Row Level Security (RLS) for tenant isolation. Add `organization_id` to JWT claims and extract it in middleware for automatic query scoping.

### 15. Improve TypeScript SDK Error Handling

**Problem:** `sdk/src/index.ts` line 63 catches errors from non-JSON responses with `.catch(() => ({}))`, which silently swallows error details. The `AuthClient` in `sdk/src/auth.ts` does not handle token refresh race conditions.

**Fix:**
- Add typed error classes (e.g., `AgentGateAuthError`, `AgentGateRateLimitError`)
- Add retry logic with exponential backoff for transient failures
- Add mutex/lock around token refresh to prevent concurrent refresh requests
- Add request interceptor pattern for automatic token refresh on 401

---

## New Technologies & Trends

### 1. SPIFFE/SPIRE for Workload Identity

**What:** SPIFFE (Secure Production Identity Framework for Everyone) is a CNCF graduated project that provides a standard for issuing and verifying identities for workloads (non-human entities) in heterogeneous environments. SPIRE is the production implementation.

**Why it matters for AgentGate:** AgentGate currently uses a custom identity model with OAuth 2.0 client credentials. SPIFFE provides a standardized, platform-agnostic identity system that issues short-lived X.509-SVIDs (SPIFFE Verifiable Identity Documents) or JWT-SVIDs. This eliminates the need for static secrets entirely -- agents get cryptographic identities automatically attested by SPIRE.

**How to integrate:**
- Use SPIRE as the identity provider for agent workloads
- Replace static client_id/client_secret with SPIFFE IDs (`spiffe://agentgate.io/agent/data-processor`)
- The SPIRE agent running alongside each agent workload handles automatic credential rotation
- Reference: https://spiffe.io/, https://github.com/spiffe/spire

### 2. Amazon Cedar Policy Language

**What:** Cedar is an open-source policy language developed by Amazon and used in AWS Verified Access, Amazon Verified Permissions, and Cedar Agent. Version 4.x is the current major release.

**Why it matters for AgentGate:** AgentGate's custom OPA-inspired policy engine (`src/policy/engine.py`) handles basic allow/deny with conditions, but lacks the formal verification, type-safe schema validation, and deterministic evaluation guarantees that Cedar provides. Cedar is purpose-built for authorization and has a Rust core with Python bindings (`cedarpy`).

**How to integrate:**
- Replace the custom policy engine with `cedarpy` (the Python binding for the Cedar engine)
- Cedar policies are formally verifiable -- you can prove that no policy combination allows unintended access
- Cedar supports entity-based policies that naturally model agent-resource relationships
- Reference: https://github.com/cedar-policy/cedar, https://www.cedarpolicy.com/

### 3. OpenFGA (Fine-Grained Authorization)

**What:** OpenFGA is a CNCF project (originally from Auth0/Okta) implementing Zanzibar-style relationship-based access control (ReBAC). It is a high-performance authorization system that models permissions as relationships between objects.

**Why it matters for AgentGate:** The current policy engine evaluates rules sequentially per request. OpenFGA provides sub-millisecond authorization checks against a pre-computed relationship graph. For an agent gateway handling thousands of requests per second, this is significantly faster than evaluating rule lists.

**How to integrate:**
- Deploy OpenFGA as a sidecar or service alongside AgentGate
- Model agent-to-resource relationships as tuples (e.g., `agent:data-processor` is `reader` of `secret:database/prod`)
- Use the OpenFGA Python SDK for authorization checks
- Reference: https://openfga.dev/, https://github.com/openfga/openfga

### 4. Infisical for Secrets Management

**What:** Infisical is an open-source secrets management platform that has gained significant traction as a modern alternative to HashiCorp Vault for cloud-native teams. It provides secret syncing, rotation, dynamic secrets, and a developer-friendly experience.

**Why it matters for AgentGate:** The current Vault/AWS/1Password providers in `src/secrets/providers.py` are stubs. Infisical offers a simpler operational model than Vault (no unsealing ceremony), native Kubernetes integration, and a well-documented Python SDK. Its machine identity feature (Universal Auth) is specifically designed for non-human identity scenarios.

**How to integrate:**
- Add `InfisicalProvider` to the `SecretProvider` hierarchy in `src/secrets/providers.py`
- Use `infisical-python` SDK for secret retrieval and dynamic secret generation
- Infisical's built-in secret rotation can replace the custom `RotationScheduler`
- Reference: https://infisical.com/, https://github.com/Infisical/infisical

### 5. Permit.io for Authorization-as-a-Service

**What:** Permit.io provides a managed authorization layer with OPA, Cedar, and OPAL (Open Policy Administration Layer) support. It offers a UI for policy management, audit logging, and a multi-tenant authorization API.

**Why it matters for AgentGate:** Instead of maintaining a custom policy engine, Permit.io provides a production-hardened authorization service with a visual policy editor (useful for the dashboard at `dashboard/`), real-time policy updates via OPAL, and built-in audit logging.

**How to integrate:**
- Use Permit.io's PDP (Policy Decision Point) container as a sidecar
- Replace `PolicyEngine.evaluate()` calls with Permit.io SDK calls
- Use OPAL for GitOps-based policy management (policies stored in git, auto-synced)
- Reference: https://www.permit.io/, https://github.com/permitio/opal

### 6. Cosign and Sigstore for Supply Chain Security

**What:** Sigstore (CNCF project) provides keyless signing and verification for software artifacts. Cosign is the container signing tool within the Sigstore ecosystem.

**Why it matters for AgentGate:** AI agents are software artifacts that should be verified before being granted credentials. Cosign can sign agent container images, and AgentGate can verify signatures during agent registration to ensure only trusted, verified agents receive credentials.

**How to integrate:**
- Add a `signature_verification` step to `IdentityManager.register_agent()`
- Require agents to present a Cosign signature or SLSA provenance attestation during registration
- Integrate with Sigstore's Rekor transparency log for tamper-evident audit
- Reference: https://www.sigstore.dev/, https://github.com/sigstore/cosign

### 7. Model Context Protocol (MCP) with OAuth 2.1

**What:** The Model Context Protocol (MCP) by Anthropic is becoming the standard for AI agent-to-tool communication. The latest MCP specification includes OAuth 2.1 support for authentication, which standardizes how MCP servers authenticate agents.

**Why it matters for AgentGate:** The current MCP server (`mcp/server.py`) is a basic stub with mock responses and no authentication. As MCP adoption grows, AgentGate should serve as an MCP-native authentication provider, issuing MCP-compatible credentials and enforcing policies on MCP tool calls.

**How to integrate:**
- Implement MCP's official OAuth 2.1 authentication flow in the MCP server
- Use the `mcp` Python SDK (https://github.com/modelcontextprotocol/python-sdk) for proper MCP server implementation
- Add MCP tool call auditing to the audit system
- Register AgentGate as an MCP authorization server

### 8. Pydantic v2 with Strict Mode

**What:** Pydantic v2 (already in `requirements.txt` as `pydantic==2.10.0`) offers 5-50x performance improvements over v1 through Rust-based validation. Strict mode prevents silent type coercion.

**Why it matters for AgentGate:** The API layer already uses Pydantic models, but some patterns are v1-style. The `Config` inner class pattern (e.g., `src/api/endpoints/agents.py` line 35) should use `model_config` dict. Strict mode would catch type errors in policy conditions that currently silently coerce (e.g., `src/policy/engine.py` line 364: `str(field_value)` coerces everything to string).

**How to integrate:**
- Replace `class Config:` with `model_config = ConfigDict(...)` across all Pydantic models
- Enable strict mode for security-critical models (auth requests, policy definitions)
- Use `model_validate()` instead of `**dict` constructors

### 9. tiktoken for Accurate Token Counting

**What:** `tiktoken` is OpenAI's official BPE tokenizer library. It provides exact token counts for GPT-3.5, GPT-4, and compatible models.

**Why it matters for AgentGate:** The gateway's token estimation at `src/api/endpoints/gateway.py` line 258 uses `len(prompt) // 4`, which is highly inaccurate. For a system that enforces token budgets, inaccurate counting means either over-charging (rejecting valid requests) or under-charging (exceeding budgets).

**How to integrate:**
- `pip install tiktoken`
- Replace the estimation with: `encoding = tiktoken.encoding_for_model(request.model); token_count = len(encoding.encode(prompt))`
- Add Anthropic model support using `anthropic-tokenizer` or character-based estimation with model-specific multipliers

### 10. Temporal for Workflow Orchestration

**What:** Temporal is a durable execution platform for orchestrating complex, long-running workflows with automatic retries, timeouts, and state persistence.

**Why it matters for AgentGate:** Secret rotation (`src/secrets/rotation.py`) currently uses a simple `asyncio.sleep(60)` loop (line 243) to poll for scheduled rotations. This is fragile -- if the process restarts, scheduled rotations are lost. Similarly, lease cleanup is triggered opportunistically during secret requests (line 164 of `broker.py`).

**How to integrate:**
- Use Temporal workflows for secret rotation scheduling (guaranteed execution even across restarts)
- Use Temporal for lease lifecycle management (automatic revocation on expiry)
- Use Temporal for audit log batch export to S3
- Reference: https://temporal.io/, `temporalio` Python SDK

### 11. ValKey (Redis Fork) or DragonflyDB

**What:** ValKey is the Linux Foundation's fork of Redis (post-license change), maintaining Redis 7 compatibility with an open-source license. DragonflyDB is a multi-threaded, Redis-compatible in-memory store that claims 25x throughput.

**Why it matters for AgentGate:** The `docker-compose.yml` uses `redis:7-alpine`. ValKey provides the same functionality with a more permissive license (BSD-3). DragonflyDB could handle significantly higher throughput for rate limiting and caching without horizontal scaling.

**How to integrate:**
- Drop-in replacement: change `redis:7-alpine` to `valkey/valkey:7-alpine` or `docker.dragonflydb.io/dragonflydb/dragonfly:latest`
- No code changes needed as both are protocol-compatible with the `redis` Python library

### 12. Structured Concurrency with TaskGroup (Python 3.11+)

**What:** Python 3.11 introduced `asyncio.TaskGroup` for structured concurrency, ensuring all child tasks complete or cancel together.

**Why it matters for AgentGate:** The rotation scheduler (`src/secrets/rotation.py` line 211) and audit flushing (`src/audit/logger.py` line 210) use bare `asyncio` patterns that can leak tasks on errors. TaskGroup provides structured lifecycle management.

**How to integrate:**
```python
async with asyncio.TaskGroup() as tg:
    tg.create_task(rotation_scheduler.start_scheduler())
    tg.create_task(audit_logger.start_export_loop())
    tg.create_task(lease_cleanup_loop())
```

---

## Priority Roadmap

### P0 -- Critical (Do Immediately)

| # | Improvement | Effort | Impact |
|---|------------|--------|--------|
| 1 | **Persist state to PostgreSQL** -- Replace all in-memory dicts with database queries. The schema already exists. Without this, a server restart loses all registered agents, active leases, and audit history. | 2-3 days | Server restart resilience, data durability |
| 2 | **Upgrade JWT from HS256 to RS256/ES256** -- The shared symmetric secret is a single point of compromise. Add JWKS endpoint. | 1 day | Prevents token forgery if any validating service is compromised |
| 3 | **Replace SHA-256 with bcrypt for secret hashing** -- `hashlib.sha256` is vulnerable to brute-force. bcrypt is already in requirements.txt but unused. | 0.5 days | Credential security hardening |
| 4 | **Fix SQL migration syntax** -- Inline INDEX declarations in CREATE TABLE are invalid PostgreSQL. Migrations would fail on first deployment. | 0.5 days | Deployment blocker |
| 5 | **Fix policy engine cache key bug** -- `@lru_cache` with dict argument will raise TypeError at runtime. | 0.5 days | Runtime crash prevention |

### P1 -- High Priority (Next Sprint)

| # | Improvement | Effort | Impact |
|---|------------|--------|--------|
| 6 | **Add token revocation (JTI + Redis blocklist)** -- Without this, deactivated agents retain valid tokens for up to 30 days. | 1-2 days | Immediate access revocation capability |
| 7 | **Implement Redis-backed rate limiting** -- Redis is already provisioned but unused for rate limiting. Protect all API endpoints. | 1 day | DDoS protection, abuse prevention |
| 8 | **Implement real secret provider integrations** -- VaultProvider, AWSSecretsManagerProvider, OnePasswordProvider are stubs. Use hvac, boto3, onepassword-sdk. | 3-5 days | Core feature completion |
| 9 | **Centralize configuration with pydantic-settings** -- Remove scattered os.getenv with dangerous defaults (e.g., `YOUR_JWT_SECRET_KEY_CHANGE_IN_PRODUCTION`). | 1 day | Eliminate configuration-related security risks |
| 10 | **Add health/readiness endpoints** -- Referenced by docker-compose and SDK but not implemented. | 0.5 days | Container orchestration compatibility |
| 11 | **Harden prompt injection detection** -- Add unicode normalization, base64 detection, and ML-based classification. | 2-3 days | Security posture improvement |

### P2 -- Medium Priority (Next Quarter)

| # | Improvement | Effort | Impact |
|---|------------|--------|--------|
| 12 | **Adopt SPIFFE/SPIRE for workload identity** -- Eliminate static secrets for agent authentication entirely. Cryptographic identity attestation. | 2-3 weeks | Industry-standard identity model |
| 13 | **Replace custom policy engine with Cedar or OpenFGA** -- Formally verifiable policies, sub-millisecond evaluation, battle-tested. | 2-3 weeks | Authorization reliability and performance |
| 14 | **Add multi-tenancy** -- Organization-scoped agents, policies, and secrets with RLS. | 1-2 weeks | Enterprise readiness |
| 15 | **Implement proper MCP server with OAuth 2.1** -- Use the official MCP Python SDK instead of custom stub. | 1 week | MCP ecosystem compatibility |
| 16 | **Add tiktoken for accurate token counting** -- Replace `len(prompt) // 4` estimation. | 0.5 days | Token budget accuracy |
| 17 | **Adopt Temporal for rotation/cleanup workflows** -- Durable execution for scheduled operations. | 1-2 weeks | Operational reliability |
| 18 | **Add structured error responses** -- Standardize error format across all endpoints. | 1-2 days | API consumer experience |
| 19 | **Improve TypeScript SDK** -- Add retry logic, typed errors, automatic token refresh with mutex. | 3-5 days | Developer experience |

### P3 -- Nice to Have (Future)

| # | Improvement | Effort | Impact |
|---|------------|--------|--------|
| 20 | **Add Infisical as a secrets provider** -- Modern alternative to Vault with simpler operations. | 3-5 days | Operational simplicity |
| 21 | **Integrate Sigstore/Cosign** -- Verify agent container signatures during registration. | 1-2 weeks | Supply chain security |
| 22 | **Switch to ValKey or DragonflyDB** -- Better license (ValKey) or 25x throughput (Dragonfly). | 0.5 days | License compliance or performance |
| 23 | **Adopt Permit.io for managed authorization** -- Visual policy management, OPAL for GitOps. | 2-3 weeks | Policy management UX |
| 24 | **Add Python SDK** -- The project serves Python AI agents but only has a TypeScript SDK. | 1-2 weeks | Broader agent ecosystem support |
| 25 | **Add gRPC API** -- For lower-latency, strongly-typed inter-service communication. | 2-3 weeks | Performance for high-throughput scenarios |
| 26 | **Use structured concurrency (TaskGroup)** -- Clean up async lifecycle management in rotation scheduler and audit flusher. | 1-2 days | Code quality, error handling |
| 27 | **Add Pydantic v2 strict mode** -- Prevent silent type coercion in security-critical models. | 1 day | Type safety |
| 28 | **Add OpenAPI client generation** -- Auto-generate SDK clients from FastAPI's OpenAPI spec using `openapi-generator`. | 1-2 days | Multi-language SDK support |

---

## Summary

AgentGate addresses a genuine and growing market need -- non-human identity management for AI agents. The architecture is well-designed with clear separation of concerns and the right abstractions (provider pattern for secrets, compiled policy model, lease-based access). The most critical improvements are operational: persisting state to the already-defined database schema, hardening cryptographic primitives (JWT algorithm, secret hashing), and fixing the migration syntax that would block deployment. The technology landscape for this domain is evolving rapidly, with SPIFFE/SPIRE, Cedar, and the MCP OAuth 2.1 spec representing the most impactful integration opportunities.
