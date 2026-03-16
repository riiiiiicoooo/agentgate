# Production Readiness Checklist

Comprehensive checklist for deploying AgentGate to production. Items marked `[x]` are implemented in the current codebase. Items marked `[ ]` require additional work before production deployment.

---

## Security

### Authentication & Authorization
- [x] OAuth 2.0 Client Credentials flow for agent authentication (`src/api/auth.py` - `ClientCredentialsFlow`)
- [x] JWT access tokens with configurable expiration (`TokenManager` with HS256 signing)
- [x] Refresh token flow with 30-day lifetime (`create_refresh_token`)
- [x] API key authentication as alternative auth method (`APIKeyManager` with HMAC-SHA256)
- [x] Scope-based authorization on all endpoints (`AgentCredentials.has_scope()` checked per route)
- [x] Bearer token extraction via FastAPI dependency injection (`get_current_agent`)
- [ ] Upgrade JWT signing from HS256 to RS256/ES256 asymmetric algorithm for key rotation without secret sharing
- [ ] Implement token revocation list (JTI blacklist) for immediate access token invalidation
- [ ] Add rate limiting on authentication endpoints to prevent credential brute-force attacks
- [ ] Implement PKCE extension for enhanced OAuth security

### Secrets Management
- [x] Client secrets stored as SHA-256 hashes, never in plaintext (`IdentityManager.register_agent`)
- [x] API keys hashed before storage (`APIKeyManager.hash_api_key`)
- [x] Secret leasing with automatic TTL expiration (60s to 24h range, `SecretsBroker`)
- [x] Lease revocation for immediate access removal (`revoke_lease`, `revoke_agent_leases`)
- [x] Credential rotation endpoint for client secrets and API keys (`/agents/{id}/rotate-credentials`)
- [x] Automated secret rotation scheduler with configurable intervals (`RotationScheduler`)
- [x] Multiple secret backend support: Vault, AWS Secrets Manager, 1Password, environment variables (`src/secrets/providers.py`)
- [x] Production secrets injected via AWS Secrets Manager in Terraform config (DB password, JWT secret)
- [ ] Enable HashiCorp Vault transit encryption for secret values at rest in the broker
- [ ] Implement secret value encryption in the in-memory lease cache (currently stored plaintext in `SecretLease.secret_value`)
- [ ] Add mutual TLS between AgentGate and secret backend providers
- [ ] Implement Hardware Security Module (HSM) integration for JWT signing key storage

### Network Security
- [x] HTTPS/TLS termination at ALB with TLS 1.2 minimum policy (`ELBSecurityPolicy-TLS-1-2-2017-01` in Terraform)
- [x] VPC with public/private subnet separation (API in private subnets, ALB in public)
- [x] Security group isolation for ECS tasks, RDS, Redis, and ALB (Terraform `aws_security_group` resources)
- [x] Redis transit encryption and at-rest encryption enabled in Terraform (`transit_encryption_enabled = true`)
- [x] CORS configuration via environment variable (`CORS_ORIGINS` in `.env.example`)
- [ ] Implement WAF rules on the ALB for common attack patterns (SQLi, XSS, path traversal)
- [ ] Add network policies for pod-to-pod traffic if migrating to Kubernetes
- [ ] Enable VPC Flow Logs for network traffic auditing
- [ ] Configure TLS for internal service-to-database connections

### Input Validation & Injection Prevention
- [x] Prompt injection detection with regex pattern matching (`check_prompt_injection` in `gateway.py`)
- [x] Pydantic model validation on all request bodies with field constraints (min/max length, regex patterns)
- [x] Injection patterns cover: instruction override, role override, data extraction, jailbreak, SQL injection, code injection
- [ ] Add ML-based prompt injection detection beyond regex patterns (integrate with promptfoo evals at `evals/promptfoo/`)
- [ ] Implement request body size limits at the reverse proxy layer
- [ ] Add Content Security Policy headers to dashboard responses

---

## Reliability

### High Availability
- [x] ECS Fargate deployment with configurable desired count (`var.service_desired_count` in Terraform)
- [x] Multi-AZ deployment across 2 availability zones (2 public + 2 private subnets)
- [x] Aurora PostgreSQL cluster with configurable instance count for read replicas
- [x] Application Load Balancer with health check probes (`/health` endpoint, 30s interval)
- [x] Auto-scaling policy based on CPU utilization (target 70%, `aws_autoscaling_policy`)
- [ ] Implement database connection retry logic with exponential backoff in `init_db()`
- [ ] Add Redis cluster mode with automatic failover (current config is single-node ElastiCache)
- [ ] Configure cross-region disaster recovery for the database
- [ ] Implement graceful shutdown handling for in-flight requests during deployments

### Failover & Recovery
- [x] Database health check function (`health_check()` in `src/db/connection.py`)
- [x] Docker Compose health checks on all services (PostgreSQL, Redis, API, Dashboard)
- [x] RDS automated backups with 30-day retention (`backup_retention_period = 30` in Terraform)
- [x] Final snapshot on production database deletion (`skip_final_snapshot = false` for production)
- [ ] Implement circuit breaker pattern for external secret provider calls (Vault, AWS, 1Password)
- [ ] Add fallback secret provider when primary is unavailable (MultiProvider only routes, does not failover)
- [ ] Configure automated database point-in-time recovery runbook
- [ ] Implement dead letter queue for failed audit event exports

### Data Integrity
- [x] PostgreSQL foreign key constraints between agents, policies, leases, and bindings
- [x] Unique constraints on agent_id, client_id, policy_id, lease_id, and event_id
- [x] Policy checksum validation via SHA-256 hash on compilation (`CompiledPolicy.checksum`)
- [x] Lease state validation (expired, revoked, valid) before secret access (`SecretLease.is_valid()`)
- [ ] Add optimistic concurrency control (version column) for concurrent policy updates
- [ ] Implement database migration versioning with rollback support (Alembic referenced but not fully configured)

---

## Observability

### Logging
- [x] Structured logging with Python `logging` module across all modules
- [x] Severity-graded log messages (DEBUG, INFO, WARNING, ERROR) with contextual details
- [x] Security events logged at WARNING/ERROR level (auth failures, injection detections, lease revocations)
- [x] CloudWatch log group with 30-day retention in Terraform (`/ecs/agentgate`)
- [x] OTel Collector log pipeline with Loki and Datadog exporters
- [ ] Implement structured JSON log formatting (current logs are plain-text format strings)
- [ ] Add correlation IDs to link related log entries across a single request lifecycle
- [ ] Configure log sampling for high-volume DEBUG messages in production

### Metrics
- [x] OpenTelemetry metrics with Prometheus and OTLP exporters (`observability/instrumentation.py`)
- [x] Authentication metrics: `auth.requests.total`, `auth.failures.total`, `auth.latency.milliseconds`, `auth.tokens.issued.total`
- [x] Policy engine metrics: `policy.evaluations.total`, `policy.allows.total`, `policy.denies.total`, `policy.cache.hits.total`
- [x] Secrets broker metrics: `secrets.leases.total`, `secrets.active_leases`, `secrets.rotation.latency.milliseconds`
- [x] Gateway metrics: `gateway.requests.total`, `gateway.request.latency.milliseconds`, `gateway.injections.detected.total`
- [x] Audit metrics: `audit.events.total`, `audit.write.latency.milliseconds`
- [x] Prometheus scrape configuration in OTel Collector (15s interval)
- [x] Pre-built Grafana dashboard (`observability/dashboards/grafana_agent_overview.json`)
- [ ] Define SLIs/SLOs and configure alerting rules (e.g., auth latency p99 < 200ms, policy eval p99 < 50ms)
- [ ] Add business-level metrics: active agents count, secrets per agent, policy violations per hour
- [ ] Implement metric cardinality controls to prevent label explosion

### Tracing
- [x] OpenTelemetry distributed tracing with OTLP and Jaeger exporters
- [x] Domain-specific trace spans: `oauth_client_credentials_flow`, `policy_evaluation`, `secret_lease`, `audit_event_logging`
- [x] Span events for sub-operation tracking (e.g., `token_validation_started`, `cache_lookup`, `secret_retrieval`)
- [x] Auto-instrumentation for FastAPI, requests, SQLAlchemy, Redis, psycopg2
- [x] Tail sampling: 100% error traces, 100% security events, 50% slow traces (>1s), 1% normal traces
- [x] Multiple propagation formats: W3C TraceContext, Jaeger, B3, X-Ray
- [ ] Add trace context propagation to outbound calls to secret backends
- [ ] Implement trace-based alerting for auth failure spikes

### Alerting
- [ ] Configure PagerDuty/OpsGenie integration for critical alerts
- [ ] Define alert rules: auth failure rate > 10%, policy violation spike, secret rotation failure
- [ ] Implement anomaly detection for unusual agent behavior patterns
- [ ] Set up on-call rotation and escalation policies

---

## Performance

### Caching
- [x] Policy decision LRU cache with configurable size (default 1000 entries, `PolicyEngine.decision_cache`)
- [x] Redis service provisioned in docker-compose and Terraform for session/cache storage
- [x] ElastiCache Redis with at-rest and transit encryption in production Terraform
- [ ] Implement Redis-backed policy decision cache (currently in-memory only, lost on restart)
- [ ] Add cache invalidation on policy update/delete (currently requires manual `clear_cache()`)
- [ ] Implement token validation cache to avoid re-parsing JWTs on repeated requests

### Connection Management
- [x] asyncpg connection pool with min 5, max 20 connections and 60s command timeout (`src/db/connection.py`)
- [x] PostgreSQL max_connections configured to 200 in docker-compose
- [x] Connection pool cleanup on application shutdown (`close_db()`)
- [ ] Implement connection pool health monitoring and auto-recovery
- [ ] Add Redis connection pooling with health checks
- [ ] Configure connection pool metrics (active, idle, waiting connections)

### Load Testing & Capacity
- [ ] Run load tests with realistic agent authentication patterns (target: 1000 concurrent agents)
- [ ] Benchmark policy evaluation latency under load (target: p99 < 10ms)
- [ ] Profile secret leasing throughput and lease cleanup performance
- [ ] Establish capacity planning baselines for CPU, memory, and database connections per agent
- [ ] Document horizontal scaling characteristics (stateless API, shared database)

### Token Budget & Rate Limiting
- [x] Per-agent token budget with monthly and hourly limits (`TokenBudgetManager`)
- [x] Hourly budget auto-reset logic (`TokenBudget.reset_hourly_if_needed`)
- [x] Token budget enforcement on LLM proxy endpoint (`gateway.py`)
- [x] Cost estimation per request (tokens * rate)
- [ ] Implement distributed rate limiting via Redis (currently in-memory, per-instance only)
- [ ] Add configurable rate limit tiers per agent classification
- [ ] Implement request queuing when approaching budget limits rather than hard rejection

---

## Compliance

### Audit Logging
- [x] Comprehensive audit event capture for all security-relevant operations (`src/audit/logger.py`)
- [x] Audit event types cover: agent CRUD, policy CRUD, secret access/rotation, auth events, policy violations
- [x] Structured audit events with: event_id, timestamp, actor, resource, action, status, severity, details
- [x] In-memory audit buffer with configurable max size (default 10,000 events)
- [x] Multi-sink export architecture: Splunk, Datadog, S3 exporters defined (`SplunkExporter`, `DatadogExporter`, `S3Exporter`)
- [x] Audit log query API with filtering by event type, actor, resource, severity, time range
- [x] CSV export endpoint for SIEM ingestion (`/audit/export/csv`)
- [x] Secret access audit trail with per-secret and per-agent filtering (`/secrets/audit`)
- [ ] Implement S3 export for long-term audit log retention (exporter defined but upload is stubbed)
- [ ] Add audit log tamper detection (hash chaining or Merkle tree)
- [ ] Implement audit log retention policy with automated archival

### Compliance Reporting
- [x] Compliance report generation endpoint supporting SOC 2, HIPAA, PCI-DSS frameworks (`/audit/compliance/generate`)
- [x] Security incident aggregation from critical/error audit events (`/audit/incidents`)
- [x] Audit statistics endpoint with success/failure rates and event type breakdown (`/audit/stats`)
- [x] Data quality expectations defined for audit logs and agent credentials (`data_quality/expectations/`)
- [ ] Implement automated compliance evidence collection against specific framework controls
- [ ] Add data classification labels to secrets and audit events
- [ ] Generate compliance reports on a scheduled basis and store in S3

### Access Controls
- [x] Scope-based RBAC with fine-grained permissions (admin:read/write, policy:read/write, secret:read/write, audit:read)
- [x] Default deny policy baseline shipped with the engine (`policy_least_privilege`)
- [x] Break-glass emergency access policy with approval requirement (`policy_break_glass` requires `approval_id`)
- [x] Agent deactivation with immediate credential revocation (`IdentityManager.deactivate_agent`)
- [x] Agent archival instead of hard deletion for audit trail preservation (`delete_agent` sets status to "archived")
- [x] Row-level security policies defined for Supabase deployments (commented SQL in migration)
- [ ] Implement approval workflow for break-glass policy activation
- [ ] Add time-bound elevated access (auto-revoke after N hours)
- [ ] Implement segregation of duties (policy creator cannot self-bind policies)

---

## Deployment

### Infrastructure as Code
- [x] Terraform configuration for AWS deployment: VPC, ECS Fargate, Aurora PostgreSQL, ElastiCache Redis, ALB, Secrets Manager (`terraform/main.tf`)
- [x] S3 backend with DynamoDB state locking for Terraform state
- [x] Docker Compose for local development with all services: PostgreSQL, Redis, API, Dashboard, Jaeger, Prometheus, Grafana, OPA
- [x] Parameterized Terraform variables for environment, instance sizes, scaling limits (`terraform/variables.tf`)
- [x] Resource tagging strategy (Project, Environment, ManagedBy) via default_tags
- [ ] Add Terraform modules for staging and production environment separation
- [ ] Implement infrastructure drift detection and automated remediation
- [ ] Add cost estimation tags and budget alerts

### CI/CD Pipeline
- [x] Makefile with build, test, and deployment targets
- [x] Playwright test configuration for end-to-end testing (`playwright.config.ts`)
- [x] Test suite covering auth, policy engine, secrets broker, audit, gateway, and API (`tests/`)
- [ ] Configure GitHub Actions CI pipeline (`.github/` directory exists but workflows not yet defined)
- [ ] Add automated Docker image build and push to ECR
- [ ] Implement staged deployment: build -> unit test -> integration test -> staging -> production
- [ ] Add automated rollback on health check failure post-deployment

### Rollback & Safety
- [x] Database migration file structure supports incremental schema changes (`src/db/migrations/`)
- [x] ECS service with ALB health checks enables rolling updates (unhealthy tasks drained before new tasks registered)
- [ ] Implement blue-green deployment strategy with traffic shifting
- [ ] Add canary deployment support with automated rollback on error rate increase
- [ ] Create database migration rollback scripts for each forward migration
- [ ] Implement feature flags for gradual feature rollout

### Container & Runtime
- [x] Container health checks defined in docker-compose for all services
- [x] ECS Fargate with FARGATE and FARGATE_SPOT capacity providers
- [x] Container Insights enabled on ECS cluster (`containerInsights = "enabled"`)
- [x] Environment-based configuration via environment variables (12-factor app pattern)
- [ ] Add container image vulnerability scanning in CI pipeline
- [ ] Implement non-root container user in Dockerfile
- [ ] Add resource limits (CPU, memory) to docker-compose service definitions
- [ ] Configure liveness and readiness probe separation (currently same `/health` endpoint)
