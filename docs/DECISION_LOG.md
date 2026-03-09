# AgentGate Architectural Decision Log

This document records key architectural decisions made during AgentGate's design, including the context, decision, and rationale.

---

## ADR-001: OAuth 2.0 Client Credentials for Agent Identity

**Date**: 2024-01-01
**Status**: Accepted
**Author**: Jacob

### Context

Agents need cryptographic identity that is:
- Machine-readable (no interactive login)
- Widely supported (works with existing OAuth libraries)
- Industry standard (compliance teams recognize it)
- Revocable (can be instantly invalidated)
- Auditable (can be traced to specific agent)

Alternatives considered:
1. API Keys (simple, but not standardized)
2. Mutual TLS certificates (complex, requires PKI)
3. Service accounts (requires identity provider like Okta)
4. Custom JWT tokens (reinvents OAuth)

### Decision

Use OAuth 2.0 Client Credentials flow (RFC 6749 section 4.4) for agent authentication.

**Implementation**:
- Agents authenticate with client_id and client_secret
- Server responds with JWT access token (1-hour expiry)
- Token includes agent ID, scopes, and other claims
- Token is signed with RS256 (asymmetric, allows verification without shared secret)
- Token can be revoked immediately by adding to revocation list in Redis

### Rationale

**Why OAuth 2.0**: Most widely supported auth standard, recognized by compliance auditors, existing SDK support across languages, well-documented security practices.

**Why client credentials**: Agents cannot handle interactive login (browser redirects), cannot store tokens securely on developer machines, need automated token refresh. Client credentials is the standard grant type for service-to-service auth.

**Why JWT**: Stateless authentication, no server round-trip for validation (can verify signature offline), includes agent metadata in token claims, supported by all major platforms.

**Why RS256 signing**: Allows verification without access to signing key (can distribute public key), stronger security than HS256 (shared secret).

### Consequences

- Agents must securely store client secret (environment variable, secrets manager)
- Token revocation requires Redis lookup (acceptable latency <10ms)
- Team must manage JWT signing keys (rotation, backup)

---

## ADR-002: OPA/Rego for Policy Definition

**Date**: 2024-01-02
**Status**: Accepted
**Author**: Jacob

### Context

Need fine-grained authorization policy language that is:
- Declarative (not imperative code)
- Versionable (can be stored in git)
- Testable locally (no server round-trip)
- Portable (same policy works across different systems)
- Human-readable (security teams can audit it)

Alternatives considered:
1. AWS IAM policy language (AWS-specific, complex)
2. RBAC roles (insufficient granularity for per-agent per-resource control)
3. Custom DSL (requires building and maintaining parser)
4. SQL WHERE clauses (not designed for authorization)
5. OPA/Rego (existing, open-source, Kubernetes standard)

### Decision

Use OPA (Open Policy Agent) with Rego policy language for all authorization decisions.

**Implementation**:
- Policies stored as Rego source code in PostgreSQL
- Versioned in git for change tracking
- Evaluated server-side on every secret request
- Evaluation results cached in Redis (5-min TTL)
- Developers can test policies locally with `agentgate policy test`

### Rationale

**Why OPA/Rego**: Used by Kubernetes admission control (widely trusted), language-agnostic (works with Python, Go, Java, etc), supports complex boolean logic, has built-in testing framework, active open-source community.

**Why not custom DSL**: Would require 4-6 months of development, maintenance burden, security review needed, no existing tooling.

**Why Rego over AWS IAM**: Rego is human-readable (`agent.environment == "staging"` vs `arn:aws:...`), portable (not cloud-specific), supports OPA ecosystem tools.

### Consequences

- Development team must learn Rego syntax (learning curve ~1 day)
- OPA is additional dependency (adds 50MB to Docker image)
- Policy evaluation must be fast (<30ms) for request latency targets

---

## ADR-003: Secrets Broker Pattern vs Direct Environment Variable Access

**Date**: 2024-01-03
**Status**: Accepted
**Author**: Jacob

### Context

Agents need to access secrets (database passwords, API keys). Current industry practice:
1. Store secrets in environment variables (common but insecure)
2. Store in config files (checked into git accidentally)
3. Ask external secret manager directly (no audit trail, over-permissioned)

Need architecture that enables:
- Audit trail of who accessed what
- Just-in-time credential provisioning
- Automatic rotation without code changes
- Instant revocation on compromise
- TTL-based expiration

### Decision

Implement "Secrets Broker" pattern: agents request secrets from AgentGate API instead of accessing backend directly.

**Architecture**:
```
Agent -> AgentGate API -> OPA Policy Evaluation -> Backend (Vault/AWS/etc)
         (request traced)  (decision logged)        (if approved)
```

### Rationale

**Audit trail**: Every secret request is logged with agent ID, decision, time, IP. Compare with env var: no trace of who accessed what.

**Just-in-time provisioning**: For databases, generate temporary credentials on-demand instead of storing pre-made ones. Temporary credentials are isolated to one agent, auto-revoked after TTL.

**Policy enforcement**: Evaluate policy at request time, not deployment time. Can enforce "staging agents can read staging secrets, not production" dynamically.

**Instant revocation**: If compromise detected, revoke all issued leases. With env vars, would need to update all deployments.

**Automatic rotation**: On rotation, new secret is returned on next request. No code changes needed, no downtime.

**Alternatives rejected**:
- Direct Vault access: No audit trail, hard to enforce per-agent policy, agent must manage credentials
- Environment variables: No audit, no rotation, secret sprawl
- Kubernetes secrets: Only works for k8s, not GitHub Copilot, no audit

### Consequences

- Agents must use AgentGate SDK instead of direct secret store access
- Adding 50-100ms latency to secret requests (acceptable trade-off for security)
- Must maintain TTL and lease management code

---

## ADR-004: PostgreSQL + Supabase for Primary Data Store

**Date**: 2024-01-04
**Status**: Accepted
**Author**: Jacob

### Context

Need persistent data store for:
- Agent metadata
- Policy documents
- Immutable audit logs (7+ years retention)
- OAuth tokens
- Secret metadata

Requirements:
- ACID transactions (audit log integrity)
- Row-level security (who can see what data)
- Immutable audit table (no UPDATE/DELETE possible)
- Point-in-time recovery
- Scale to 10k requests/sec

### Decision

Use PostgreSQL (Supabase managed service) as primary data store.

**Configuration**:
- Primary-replica setup (primary for writes, replica for reads)
- RLS policies for authorization (who can see which rows)
- Immutable audit table with constraints
- Connection pooling (pgBouncer)
- Daily automated backups to S3

### Rationale

**Why PostgreSQL**: ACID transactions ensure audit log integrity, RLS provides database-level access control, JSONB for flexible metadata, good performance at 10k RPS scale, mature and battle-tested.

**Why Supabase**: Managed service eliminates operational burden, handles backups/replication/patching, includes auth integration, REST API for real-time subscriptions.

**Why not NoSQL**: Audit logs need strong consistency (can't lose events), transactions are critical (agent creation + credential creation must be atomic), relational queries for audit analysis.

**Why RLS**: Enforces access control at database layer, even if API layer is compromised, audit logs are protected at database level.

### Consequences

- Tight coupling to PostgreSQL (migration to other DB would be expensive)
- Need DBA for schema changes in production
- Connection pooling must be tuned for concurrency

---

## ADR-005: Redis for Ephemeral Data (Sessions, Cache, Rate Limits)

**Date**: 2024-01-05
**Status**: Accepted
**Author**: Jacob

### Context

Need fast in-memory storage for:
- OAuth sessions (token validation <10ms)
- Rate limit counters (atomic increment)
- Secret cache (reduce backend calls)
- Policy evaluation cache (reduce OPA calls)

Cannot use PostgreSQL because latency is too high (5-10ms for DB round trip + 50ms network = 55ms, target is <10ms).

### Decision

Use Redis for all ephemeral data with TTL-based expiration.

**Configuration**:
- Redis cluster (3+ nodes for HA)
- RDB persistence for durability
- Keyspace notification for expiration events
- Connection pooling
- Sentinel for automatic failover

### Rationale

**Why Redis over Memcached**: Supports data structures (sets, lists, sorted sets), TTL on keys, persistence options, better error handling.

**Why not PostgreSQL**: Too slow (5-10ms vs <1ms for Redis), overkill for ephemeral data that expires anyway.

**Why cluster**: Single Redis instance would be bottleneck at 10k RPS, cluster provides sharding and HA.

**Why RDB persistence**: Allows recovery from crashes, doesn't add much latency.

### Consequences

- Must tune memory limits (set eviction policy)
- Need separate Redis infrastructure (another service to operate)
- Session data can be lost in edge cases (acceptable for sessions that auto-refresh)

---

## ADR-006: Next.js for Dashboard UI

**Date**: 2024-01-06
**Status**: Accepted
**Author**: Jacob

### Context

Need web dashboard for:
- Agent management (list, create, edit, revoke)
- Policy editor (syntax highlighting, deploy)
- Audit log viewer (search, filter, export)
- Metrics/analytics

Requirements:
- Modern, responsive UI
- Real-time updates (show new audit events as they arrive)
- Deploy separately from API (can scale independently)
- Type-safe (TypeScript)

### Decision

Use Next.js 14 (React framework) for dashboard.

**Architecture**:
- Separate Next.js application
- Connects to API via REST endpoints
- Deployed independently (Vercel or Docker)
- Real-time updates via WebSocket or Server-Sent Events

### Rationale

**Why Next.js**: Full-stack React framework, serverless-friendly, built-in SSR, TypeScript support, incremental static regeneration for performance.

**Why separate from API**: Dashboard and API have different scaling profiles (dashboard is I/O bound, API is CPU bound), can deploy independently, can cache dashboard with CDN.

**Why React over Vue/Angular**: React is most popular, largest ecosystem, JSX syntax.

**Why TypeScript**: Prevents bugs at compile time, self-documenting code, better IDE support.

### Consequences

- Must maintain separate Next.js deployment
- Need to implement cache invalidation strategy
- Real-time updates add complexity (WebSocket overhead)

---

## ADR-007: FastAPI + Uvicorn for API Server

**Date**: 2024-01-07
**Status**: Accepted
**Author**: Jacob

### Context

Core API server must:
- Handle 10k RPS
- Support async operations (I/O-bound)
- Have auto-generated API docs
- Support Python ecosystem (many ML/data tools)
- Deploy as Docker container

### Decision

Use FastAPI (async Python framework) with Uvicorn ASGI server.

**Configuration**:
- 8 Uvicorn workers (configurable)
- Async/await for all I/O operations
- Pydantic for request/response validation
- OpenAPI/Swagger auto-generated docs

### Rationale

**Why FastAPI over Flask/Django**: Async support is built-in (Flask needs separate tools), Pydantic validation, auto-generated docs, high performance.

**Why async**: I/O operations (database, external APIs) are slow; async allows handling other requests while waiting.

**Why Python over Go/Rust**: Larger ML/data science ecosystem, easier to find developers, fast enough for this workload.

**Why Uvicorn**: ASGI server designed for async Python, high performance, simple configuration.

### Consequences

- Python async can be tricky to debug
- Must be careful about CPU-bound operations (will block other requests)

---

## ADR-008: OpenTelemetry for Observability

**Date**: 2024-01-08
**Status**: Accepted
**Author**: Jacob

### Context

Need comprehensive observability for:
- Distributed tracing (request flow across services)
- Metrics collection (throughput, latency, errors)
- Structured logging

Compliance teams also need:
- Audit trail correlation (trace ID in logs)
- Performance baselines
- Error debugging

### Decision

Use OpenTelemetry (vendor-neutral) for all observability.

**Components**:
- Traces: Jaeger (development), DataDog (production)
- Metrics: Prometheus + Grafana
- Logs: Structured JSON to stdout (picked up by k8s)

### Rationale

**Why OpenTelemetry**: Vendor-neutral, single instrumentation point, supports all three pillars (traces, metrics, logs), widely adopted, no vendor lock-in.

**Why Jaeger for dev, DataDog for prod**: Jaeger is open-source (good for local development), DataDog has better UX and integrations for production.

**Why not ELK Stack**: OpenTelemetry is more modern, better performance, less operational overhead.

### Consequences

- Observability infrastructure adds operational complexity
- Must implement sampling (log all events would be too expensive)

---

## ADR-009: Docker Compose for Local Development, Kubernetes for Production

**Date**: 2024-01-09
**Status**: Accepted
**Author**: Jacob

### Context

Need:
- Simple local development environment (one command to start)
- Production-ready orchestration (scaling, HA, rolling updates)
- Easy onboarding for new developers

### Decision

Use Docker Compose for local development, Kubernetes for production.

**Local**: `docker-compose up` starts API, PostgreSQL, Redis, Jaeger, Dashboard
**Production**: Helm charts for Kubernetes deployment

### Rationale

**Why Docker Compose for local**: Simple YAML, no setup needed, includes health checks.

**Why Kubernetes for production**: Industry standard for container orchestration, handles scaling/HA/rolling updates, large ecosystem.

**Why not Docker Swarm**: Kubernetes is more powerful and widely adopted.

**Why not manual deployment**: Manual scaling, HA, updates is error-prone.

### Consequences

- Development environment mirrors production (but not exactly)
- Kubernetes has steep learning curve
- Helm charts require maintenance

---

## ADR-010: MCP Server Integration for Agent Native Access

**Date**: 2024-01-10
**Status**: Accepted
**Author**: Jacob

### Context

Agents (especially Claude) can use Model Context Protocol (MCP) to discover and call tools natively. If AgentGate exposes itself as MCP server, agents can:
- Discover agent identity endpoint without SDK
- Request secrets without SDK
- Check policies without SDK

This reduces SDK dependency and makes integration easier.

### Decision

Implement MCP server that exposes:
1. `agent_register` — register new agent
2. `get_secret` — request secret
3. `get_permissions` — list what agent can access
4. `check_policy` — test if access allowed

### Rationale

**Why MCP**: Claude has native MCP support, agents can discover tools automatically, no SDK installation required.

**Use case**: Developers using Claude Code can use AgentGate directly without installing Python SDK.

**Reduces friction**: Agent developers don't need to know about agentgate-sdk, just use MCP tools.

### Consequences

- Additional protocol implementation (MCP)
- MCP server must run alongside API server
- Smaller feature set than full SDK (MCP has limitations)

---

## ADR-011: Policy-as-Code in Git (Version Control)

**Date**: 2024-01-11
**Status**: Accepted
**Author**: Jacob

### Context

Policies should be:
- Version controlled (history of changes, rollback capability)
- Code reviewed (require approval before changes)
- Tested before deployment

### Decision

Store all policies in git repository, deploy via `agentgate policy deploy` CLI command.

**Workflow**:
```
1. Developer edits policies/staging.rego in git
2. Creates pull request
3. Security team reviews and tests locally
4. After approval, merge to main
5. CI/CD runs `agentgate policy deploy`
6. Policies are pushed to AgentGate
```

### Rationale

**Why git**: Version control gives history, enables rollback, enables code review.

**Why CLI deploy**: Gives control over when policies are deployed, enables testing before deployment.

**Why not manual UI edits**: Manual edits have no history, no code review, higher risk of mistakes.

### Consequences

- Must maintain git repository
- Deployment is manual (not auto on commit)
- Requires coordination with CI/CD pipeline

---

## ADR-012: TTL-Based Secret Expiration Over Scheduled Revocation

**Date**: 2024-01-12
**Status**: Accepted
**Author**: Jacob

### Context

Secrets (database passwords, API keys) need expiration because:
- Reduces blast radius if compromised
- Enforces rotation
- Prevents long-lived credentials

Two approaches:
1. TTL-based: Secret expires after X time, agent must request new one
2. Scheduled revocation: Background job revokes secrets periodically

### Decision

Use TTL-based expiration (request-time enforcement).

**Implementation**:
- Each secret lease has `expires_at` timestamp
- When agent requests secret, check if expired
- If expired, return 401 Unauthorized
- Agent must request new secret
- No scheduled jobs needed

### Rationale

**Why TTL over scheduled revocation**: Simpler (no background jobs), more responsive (expired immediately, not on schedule), enforces policy at request time.

**Why request-time check**: Agent discovers expiration immediately when it tries to use secret, no surprise failures from "it was revoked yesterday".

### Consequences

- Agents must handle 401 responses gracefully (request new secret)
- Agent deployment could fail if secret leaked and expires

---

## ADR-013: Request-Time Policy Evaluation Over Pre-Computed Access Lists

**Date**: 2024-01-13
**Status**: Accepted
**Author**: Jacob

### Context

Authorization can be evaluated:
1. At request time: evaluate policy on every secret request
2. Pre-computed: generate access matrix at deploy time, cache it

Request-time is more secure but slower. Pre-computed is faster but stale.

### Decision

Evaluate policies at request time (every secret request).

**Implementation**:
- Every secret request triggers policy evaluation
- OPA evaluates Rego rules in <30ms
- Result cached in Redis for 5 minutes
- If policy changes, cache invalidated immediately

### Rationale

**Why request-time**: Catches policy violations immediately, enables dynamic policies (can change without redeploy), compromised agents are instantly blocked if policy is updated.

**Why not pre-computed**: Pre-computed lists would be stale, cannot enforce dynamic policies, cannot block compromised agents without redeploy.

**Why caching**: 80-90% of requests hit cache, performance is acceptable.

### Consequences

- Every secret request has policy evaluation overhead (mitigated by caching)
- Must maintain cache invalidation logic

---

## ADR-014: Session-Scoped Secrets Over Per-Request Provisioning

**Date**: 2024-01-14
**Status**: Accepted (supersedes earlier approach)
**Author**: Jacob

### Context

Initially implemented per-request secret provisioning — every API call from an agent triggered a fresh credential fetch from the secrets broker. Seemed like the most secure approach (minimal credential exposure window).

### What Happened

Load testing revealed 400ms+ overhead per API call. In a typical agent workflow (50-100 API calls per task), this added 20-40 seconds of latency. Developer experience testing showed agents timing out on complex tasks. Two pilot teams reported agents "hanging" during multi-step operations.

### Decision

Switched to session-scoped secrets with configurable TTL (default 15 minutes). Agent authenticates once, receives a session token with scoped credentials, credentials auto-expire at session end or TTL.

### Rationale

95% latency reduction (400ms → 18ms per call). Security tradeoff is acceptable: 15-minute window vs. per-request is minimal risk increase, and session revocation provides immediate kill switch.

### Consequences

Had to build session management layer (2 weeks additional work). Needed to add session revocation to the admin dashboard. Audit logging now captures session-level events, not per-request events (less granular but still sufficient for SOC 2).

### Lesson

Security purity that destroys developer experience is no security at all — developers will work around it.

---

## ADR-015: Pivot from mTLS to OAuth 2.0 Client Credentials

**Date:** 2024-02-15
**Status:** Accepted (supersedes initial mTLS architecture)
**Author:** Jacob

### Context

AgentGate's first architecture used mutual TLS (mTLS) with certificate-based authentication. The design was sound from a security perspective: agents would present X.509 certificates signed by a corporate CA, allowing bidirectional authentication without shared secrets. The model worked well in proof-of-concept testing with 3 pilot teams.

### What Happened

Pilot deployments revealed a critical operational bottleneck: certificate management. In production environments, developers discovered that:
- Certificate renewal required coordinating with security teams to reissue certificates
- Agents crashed silently when certificates expired (not discovered until customer reported outage)
- Rotating certificates across multiple agent deployments required careful orchestration
- Certificate provisioning took 2-3 days per agent due to approval workflows

During the first pilot with 8 agents, 2 certificate expirations happened within a week, each requiring 30+ minutes of debugging. Team feedback was consistent: "The security is great but operationally this is killing us."

### Decision

Pivoted to OAuth 2.0 Client Credentials flow (ADR-001, implemented in revision) as the primary authentication method. This was the single most consequential decision for adoption.

**Implementation changes:**
- Agents authenticate with client_id and client_secret (credentials issued via admin panel)
- Credentials can be rotated in-place without affecting agent deployment
- Secrets can be revoked immediately in case of compromise
- No certificate infrastructure required
- Credential expiration is handled gracefully (agent requests new token)

### Rationale

OAuth 2.0 Client Credentials reduced agent onboarding from 2 days to 15 minutes. This single change drove 100% adoption among pilot teams. The security tradeoff (shared secret vs. mutual authentication) was acceptable because:

1. **Operational simplicity:** Developers could issue new credentials instantly; no approval workflow
2. **Graceful degradation:** Expired credentials trigger automatic refresh, not silent failure
3. **Revocation speed:** A compromised secret can be rotated immediately (not waiting for CA to issue new cert)
4. **Cross-platform consistency:** Same credential model works for CLI agents, container agents, and serverless agents

### Consequences

- **Short-term:** Rewrote authentication layer (1 week). Deprecated mTLS support.
- **Long-term:** Customer feedback improved dramatically. NPS went from 6.2 (mTLS) to 8.1 (OAuth). Pilot teams cited "just works" as a key factor in adoption.
- **Security:** Loss of mutual authentication was mitigated by adding request signing (HMAC-SHA256 on request body), providing a defense against man-in-the-middle attacks in scenario where secrets are compromised.

### Lesson

Security purity without operational feasibility is a failure. mTLS was architecturally superior but practically untenable. OAuth 2.0 Client Credentials won because it was secure enough and operationally trivial. Adoption > perfection.

---

## Decision Rationale Summary

**Security over Performance** (when trade-off exists)
- Request-time policy evaluation vs pre-computed (chose request-time)
- Audit logging every action (can't optimize away)

**Simplicity over Features** (when possible)
- OAuth client credentials vs custom JWT (chose OAuth)
- OPA/Rego vs custom policy DSL (chose OPA)

**Standard Technologies over Custom**
- PostgreSQL + Redis vs custom data store
- OpenTelemetry vs custom logging
- Docker + Kubernetes vs homegrown orchestration

**Separation of Concerns**
- Dashboard separate from API (different scaling profiles)
- API separate from CLI (different deployment targets)
- MCP server can be separate (optional integration)

