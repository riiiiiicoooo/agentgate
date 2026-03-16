# Architecture Decision Records

This document captures the key architectural decisions made during the design and implementation of AgentGate, an AI agent identity and access management platform.

---

## ADR-001: FastAPI as the API Framework

**Status:** Accepted
**Date:** 2024-01

**Context:** AgentGate requires a high-performance, async-capable API layer to handle concurrent agent authentication, policy evaluation, and secret leasing requests. The framework must support dependency injection for auth middleware, automatic OpenAPI documentation for the TypeScript SDK and CLI consumers, and native Pydantic integration for request/response validation across complex nested models (e.g., `PolicyRule` with embedded `PolicyCondition` lists).

**Decision:** Use FastAPI with Uvicorn as the ASGI server. All endpoint modules (`agents.py`, `policies.py`, `secrets.py`, `audit.py`, `gateway.py`) use FastAPI's `APIRouter` with typed Pydantic models and `Depends()` for injecting authenticated `AgentCredentials` into every protected route.

**Alternatives Considered:**
- **Django REST Framework** -- Full-featured but heavier, synchronous by default, and the ORM would conflict with the asyncpg connection pool approach.
- **Flask + Connexion** -- Lightweight but lacks native async support and automatic OpenAPI generation from type hints.
- **gRPC** -- High performance but would complicate browser-based dashboard integration and require a separate REST gateway.

**Consequences:**
- All endpoints benefit from auto-generated OpenAPI docs, which the TypeScript SDK (`sdk/src/`) and CLI (`cli/src/`) consume directly.
- The `Depends(get_current_agent)` pattern enforces authentication uniformly across all routers without decorator repetition.
- Pydantic models with `Field(pattern=...)` constraints (e.g., status enum validation, severity levels) provide schema-level input validation before business logic executes.
- Tight coupling to the Python async ecosystem; adding non-Python microservices would require a separate API gateway.

---

## ADR-002: OAuth 2.0 Client Credentials Flow for Agent Authentication

**Status:** Accepted
**Date:** 2024-01

**Context:** AI agents are non-interactive service principals that cannot perform browser-based login flows. They need machine-to-machine authentication with scoped access tokens, credential rotation capability, and both short-lived access and long-lived refresh tokens. The system must also support API key authentication as a simpler alternative for development and lower-security contexts.

**Decision:** Implement OAuth 2.0 Client Credentials grant as the primary authentication mechanism, issuing HS256-signed JWTs with embedded scopes. Each agent receives a `client_id` and hashed `client_secret` at registration. The `TokenManager` issues access tokens (60-minute TTL) and refresh tokens (30-day TTL). `APIKeyManager` provides HMAC-SHA256-derived API keys as an alternative auth method. The `get_current_agent` FastAPI dependency extracts and validates Bearer tokens on every protected endpoint.

**Alternatives Considered:**
- **mTLS (mutual TLS)** -- Stronger identity assurance but operationally complex for agents running in diverse environments; certificate provisioning and rotation overhead is significant.
- **API keys only** -- Simpler but lacks token expiration, scope enforcement, and refresh semantics; no standard for revocation.
- **OIDC with external IdP (Auth0, Keycloak)** -- Adds a runtime dependency on an external service; the client credentials flow maps naturally to built-in JWT issuance.

**Consequences:**
- Scopes (`admin:write`, `policy:read`, `secret:read`, `audit:read`, `llm:write`, etc.) are embedded in JWT claims and checked via `AgentCredentials.has_scope()` at every endpoint, enabling fine-grained RBAC.
- Client secrets are stored as SHA-256 hashes; plaintext secrets are returned only once at registration or rotation time.
- The `ClientCredentialsFlow` class encapsulates token exchange and refresh logic, keeping endpoint handlers focused on business logic.
- JWT secret is configured via `JWT_SECRET` environment variable, which must be rotated through infrastructure (Terraform deploys it via AWS Secrets Manager).

---

## ADR-003: Custom Policy Engine with OPA-Inspired Design

**Status:** Accepted
**Date:** 2024-02

**Context:** AgentGate needs to enforce access control policies that determine whether a given agent can perform a specific action on a specific resource. Policies must support allow/deny effects, wildcard resource matching, attribute-based conditions (e.g., `agent.team == "backend"`), and be evaluatable with sub-millisecond latency. An optional external OPA sidecar is available in docker-compose for organizations that prefer Rego-based policies.

**Decision:** Build a custom `PolicyEngine` class (`src/policy/engine.py`) that compiles policies into `CompiledPolicy` objects with SHA-256 checksums, evaluates rules with fnmatch-based wildcard resource matching and configurable condition operators (`eq`, `neq`, `in`, `contains`, `matches`), and caches decisions in an LRU-evicting in-memory dictionary. Default policies are shipped via `src/policy/defaults.py` and include least-privilege baseline, read-only, break-glass emergency, and tiered secret access policies. The policies API exposes a `/simulate` endpoint for dry-run testing.

**Alternatives Considered:**
- **Open Policy Agent (OPA) exclusively** -- Powerful Rego-based engine, but adds operational complexity (sidecar deployment, gRPC communication latency, Rego learning curve). Kept as an optional docker-compose service rather than a hard dependency.
- **Casbin** -- Model-based access control library, but its policy format is less expressive for the nested condition evaluation AgentGate requires.
- **AWS IAM-style inline policies** -- Familiar model but tightly coupled to AWS semantics; AgentGate needs cloud-agnostic policy evaluation.

**Consequences:**
- Policy evaluation runs in-process with no network hops, achieving microsecond-level latency for cached decisions.
- The `PolicySimulationRequest` / `PolicySimulationResult` models enable policy authors to test rules before binding them to agents, reducing misconfigurations.
- Policy binding is a many-to-many relationship (`bindings_db: agent_id -> [policy_ids]`), allowing flexible policy composition.
- Default deny semantics: when no policy matches, the engine returns `effect: "deny"`, enforcing least-privilege by default.
- OPA remains available as an optional sidecar for organizations with existing Rego policy libraries.

---

## ADR-004: Just-in-Time Secret Leasing with TTL Enforcement

**Status:** Accepted
**Date:** 2024-02

**Context:** AI agents often need short-lived access to secrets (database credentials, API keys, service tokens) for specific tasks. Long-lived secrets shared across agents create a large blast radius if compromised. The system needs to issue secrets with automatic expiration, track access patterns, support lease renewal with limits, and enable immediate revocation during incident response.

**Decision:** Implement a `SecretsBroker` (`src/secrets/broker.py`) that provisions secrets as time-bounded leases (`SecretLease`) with configurable TTLs (60 seconds to 24 hours). Each lease tracks `accessed_count`, `renewal_count` (max 3 renewals), and supports immediate revocation via `revoke_lease()` or bulk `revoke_agent_leases()`. Backend secret storage uses a provider abstraction (`SecretProvider` ABC in `src/secrets/providers.py`) with pluggable implementations: `EnvVarProvider`, `VaultProvider`, `AWSSecretsManagerProvider`, `OnePasswordProvider`, and `MultiProvider` for prefix-based routing. A `RotationScheduler` (`src/secrets/rotation.py`) manages periodic rotation with random, incremental, and custom strategies.

**Alternatives Considered:**
- **Direct Vault integration only** -- HashiCorp Vault has native leasing, but mandating Vault as a dependency limits adoption. The provider abstraction enables Vault as one of several backends.
- **Static secret distribution** -- Simpler operationally but creates persistent credentials that accumulate risk over time and cannot be revoked granularly.
- **AWS Secrets Manager native rotation** -- Cloud-specific; AgentGate needs to support multi-cloud and on-premise deployments.

**Consequences:**
- Agents access secrets through time-bounded leases rather than static credentials, reducing the window of exposure if a lease is compromised.
- The `MultiProvider` enables routing different secret paths to different backends (e.g., `database/*` to Vault, `api-key/*` to AWS Secrets Manager).
- Lease renewal limits (max 3) prevent indefinite access accumulation; agents must re-request secrets after exhausting renewals.
- The periodic `cleanup_expired_leases()` method prevents memory growth from accumulated expired lease objects.
- Secret access auditing is built in: every lease request, renewal, and revocation is logged to the audit system.

---

## ADR-005: OpenTelemetry-Based Observability Stack

**Status:** Accepted
**Date:** 2024-02

**Context:** AgentGate operates as a security-critical middleware layer. Operators need distributed tracing across auth flows, policy evaluations, and secret operations; metrics for SLO tracking (auth latency, policy cache hit rates, active lease counts); and structured logging that correlates with traces. The observability infrastructure must support multiple export targets since different organizations use different SIEM and APM platforms.

**Decision:** Instrument the application with OpenTelemetry using domain-specific instrumentation classes: `AuthenticationInstrumentation`, `PolicyEngineInstrumentation`, `SecretsBrokerInstrumentation`, `AuditInstrumentation`, and `GatewayInstrumentation` (all in `observability/instrumentation.py`). Each class defines counters, histograms, and up-down counters relevant to its domain. The OTel Collector config (`observability/otel_config.yaml`) supports multi-target export: Jaeger for traces, Prometheus for metrics, Loki for logs, with optional Datadog and New Relic exporters. Auto-instrumentation covers FastAPI, requests, SQLAlchemy, Redis, and psycopg2. Tail sampling prioritizes error traces (100%), slow traces (>1s at 50%), and security events (100%) while sampling normal traces at 1%.

**Alternatives Considered:**
- **Datadog-only APM** -- Full-featured but vendor lock-in; not all target users have Datadog.
- **Custom logging + Prometheus** -- Simpler but lacks distributed tracing across async operations and cross-service correlation.
- **AWS CloudWatch + X-Ray** -- Cloud-specific; would not work for on-premise or multi-cloud deployments.

**Consequences:**
- Domain-specific metrics like `policy.cache.hits.total`, `secrets.active_leases`, and `gateway.injections.detected.total` provide actionable operational insights beyond generic HTTP metrics.
- Tail sampling reduces trace storage costs while ensuring all error and security-relevant traces are captured.
- The pre-built Grafana dashboard (`observability/dashboards/grafana_agent_overview.json`) provides immediate visibility on deployment.
- Multiple propagation formats (W3C TraceContext, Jaeger, B3, X-Ray) ensure compatibility with upstream/downstream services regardless of their tracing implementation.

---

## ADR-006: PostgreSQL with asyncpg and In-Memory Fallback

**Status:** Accepted
**Date:** 2024-01

**Context:** AgentGate needs persistent storage for agents, policies, secret metadata, leases, audit logs, and token budgets. The storage layer must support high write throughput for audit logging, complex queries for compliance reporting, JSONB for flexible metadata and policy rules, and array types for scopes and tags. During development and testing, an in-memory fallback is needed so the system can run without a database dependency.

**Decision:** Use PostgreSQL (v15) as the primary datastore with asyncpg for async connection pooling (`src/db/connection.py`): min 5, max 20 connections, 60-second command timeout. The schema (`src/db/migrations/001_initial_schema.sql`) defines tables for agents, API keys, policies, policy bindings, secrets, secret leases, audit logs, token budgets, and secret rotations, with appropriate indexes and two convenience views (`active_secret_leases`, `audit_summary`). For production AWS deployment, Terraform provisions Aurora PostgreSQL with 30-day backup retention. API endpoint modules maintain parallel in-memory dicts (`agents_db`, `policies_db`, `leases_db`, etc.) that serve as the working storage during development and testing, with database persistence as the production path.

**Alternatives Considered:**
- **MongoDB** -- Flexible schema but weaker consistency guarantees and no native support for the complex JOIN queries needed for compliance reports.
- **Supabase (managed Postgres)** -- Considered and partially supported (commented-out RLS policies in the migration), but adds a vendor dependency. Raw PostgreSQL with asyncpg keeps deployment flexibility.
- **DynamoDB** -- Serverless scaling but limited query flexibility; the audit log query patterns (time-range, multi-field filtering, aggregation) are poorly suited to DynamoDB's access patterns.

**Consequences:**
- JSONB columns for `rules` (policies) and `details` (audit logs) provide schema flexibility without sacrificing query capability.
- The asyncpg pool with connection limits prevents database connection exhaustion under high concurrency.
- In-memory fallback enables rapid iteration and testing without database infrastructure, at the cost of maintaining two code paths.
- Aurora PostgreSQL deployment via Terraform provides automated backups, read replicas, and encryption at rest for production readiness.
- The `health_check()` function enables readiness probes in the Kubernetes/ECS deployment.
