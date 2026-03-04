# AgentGate

**AI Agent Authentication & Authorization Gateway — securing how AI coding agents access secrets, APIs, and infrastructure across 340+ developer environments with zero-trust policy enforcement**

Built for a small developer tools company that had adopted AI coding agents across all teams — Copilot, Cursor, and internal LLM-powered automation — but had no governance over what those agents could access. After a near-miss where a CI/CD agent auto-committed a production database credential to a public PR, the VP of Engineering engaged our team to build a centralized auth and authorization layer specifically designed for non-human identities. AgentGate gives platform engineering a single pane of glass to register AI agents, define scoped access policies, broker just-in-time secrets with automatic revocation, and maintain a full audit trail of every action every agent takes.

---

## The Problem

A fast-growing developer tools company had rolled out AI coding agents to all 12 engineering squads. Developers were using GitHub Copilot, Cursor, and Claude Code daily, and the platform team had built 8 internal LLM-powered agents for code review, deployment, and data pipeline automation. But the security posture hadn't kept pace:

- **No agent identity model** — AI agents authenticated using shared developer credentials or long-lived API keys with broad access. There was no way to distinguish agent activity from human activity in logs, and no mechanism to scope an agent's access to only what it needed.

- **Secrets sprawl** — Agents needed database credentials, API keys, and cloud tokens to do their work. Teams were copy-pasting secrets into agent configs, storing them in environment variables that never rotated, or embedding them directly in prompt templates. 23 unique secrets were exposed in agent logs over a 6-month period.

- **No policy enforcement** — A CI/CD agent had the same access as a senior engineer. There was no way to say "this agent can only read from staging" or "this agent can access the payments API but not the user database." Every agent operated with implicit full-trust.

- **Audit blindspot** — When something went wrong, the team couldn't reconstruct what an agent did, what secrets it accessed, or why. Compliance (SOC 2 Type II) required demonstrating control over all system access — including non-human identities — and the current state was a gap in every audit.

- **Token cost overruns** — Internal agents had no budget guardrails. One runaway summarization agent consumed $4,200 in OpenAI tokens over a weekend because there was no per-agent spending limit or kill switch.

## The Solution

AgentGate is a production-ready authentication, authorization, and secrets management system designed specifically for AI agents. It provides:

- **OAuth 2.0 Client Credentials Flow** - Secure agent-to-service authentication
- **Policy-Based Access Control** - OPA/Rego-inspired policy evaluation engine
- **Just-In-Time Secret Provisioning** - Temporary secret leasing with automatic revocation
- **Audit & Compliance** - Comprehensive audit logging, SIEM integration, and compliance reports
- **Token Budgeting** - Per-agent LLM token quotas with hard limits
- **Prompt Injection Detection** - Pattern-based injection detection for LLM requests
- **Multi-Provider Secrets** - Support for Vault, AWS Secrets Manager, 1Password, and custom backends

## Quick Start

### Python API Server

```bash
# Install dependencies
pip install fastapi uvicorn asyncpg pyjwt cryptography opentelemetry-api

# Start server
python -m src.api.main
# Server runs on http://localhost:8000
```

### TypeScript SDK

```bash
npm install agentgate

const client = new AgentGateClient('http://localhost:8000', 'YOUR_API_KEY');
const secret = await client.secrets.request({ secret_name: 'db/password' });
```

### CLI

```bash
export AGENTGATE_URL=http://localhost:8000
export AGENTGATE_API_KEY=YOUR_API_KEY

agentgate agent register --name "data-processor"
agentgate secret request --name "database/password"
agentgate audit query --event-type auth_success
```

## Architecture

### Core Components

1. **API Layer** (`src/api/`) - FastAPI with OAuth 2.0, rate limiting, middleware
2. **Policy Engine** (`src/policy/`) - OPA/Rego-inspired rule evaluation, caching
3. **Secrets Broker** (`src/secrets/`) - JIT provisioning, TTL enforcement, multi-provider
4. **Identity Management** (`src/identity/`) - Agent registration, credential lifecycle
5. **Audit System** (`src/audit/`) - Structured logging, SIEM integration, compliance
6. **AI Gateway** (`src/gateway/`) - LLM proxy, token budgets, injection detection
7. **Database** (`src/db/`) - Async PostgreSQL, migrations, RLS-enabled

## Features

### Authentication
- OAuth 2.0 client credentials
- JWT access tokens
- API key authentication
- Token refresh flow

### Authorization
- Policy-based access control
- Attribute-based conditions
- Resource pattern matching
- Scope-based permissions

### Secrets
- Just-in-time leasing
- Automatic TTL + revocation
- Multi-backend support (Vault, AWS, 1Password)
- Rotation scheduling

### Audit & Compliance
- Structured event logging
- SIEM integration (Splunk, Datadog, S3)
- SOC 2, HIPAA compliance reports
- Security incident tracking

### AI Safety
- Prompt injection detection
- Token budget enforcement
- Rate limiting
- Cost tracking

## Results

| Metric | Before | After | Impact |
|--------|--------|-------|--------|
| Agent credential incidents | 23 in 6 months | 0 in 4 months | 100% reduction in exposed secrets |
| Secret rotation compliance | Manual, quarterly | Automated, configurable TTL | From 90-day avg age to 4-hour avg lease |
| Agent audit coverage | 0% (no agent-specific logging) | 100% of agent actions logged | Full SOC 2 compliance for non-human identities |
| Time to revoke agent access | 2-4 hours (manual) | < 1 second (policy update) | Instant incident response |
| LLM token cost overruns | $4,200 single incident | $0 (budget-enforced) | Per-agent cost controls with kill switch |
| Agent onboarding time | 1-2 days (manual key provisioning) | < 5 minutes (self-service registration) | 95% reduction |
| Policy changes | Ticket-based, 1-2 week turnaround | Real-time policy evaluation | Immediate enforcement |

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| API Server | Python 3.11+ / FastAPI | Async-native, OpenAPI spec generation, middleware ecosystem |
| Policy Engine | OPA/Rego-inspired | Industry standard for policy-as-code, declarative rules, testable |
| Database | PostgreSQL 15 (Supabase) | JSONB for flexible policy storage, RLS for tenant isolation |
| Cache | Redis 7 | Token caching, policy decision caching, rate limiting |
| Auth | OAuth 2.0 / JWT | Standard client credentials flow, short-lived tokens |
| Secrets Backend | Vault, AWS SM, 1Password | Multi-provider abstraction, JIT leasing |
| SDK | TypeScript | Matches developer tool ecosystem, type-safe |
| CLI | TypeScript (Commander.js) | Terminal-native developer experience |
| Observability | OpenTelemetry + Grafana | Vendor-neutral tracing, metrics, dashboards |
| Infrastructure | Terraform + Docker | Reproducible deployments, ECS/RDS/ElastiCache |
| CI/CD | GitHub Actions | Native to developer workflow |
| AI Evals | Promptfoo | Adversarial testing for injection detection |
| Data Quality | Great Expectations | Audit log completeness, credential health validation |

## Design Decisions

| Decision | Choice | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Agent identity model | OAuth 2.0 client credentials | API keys only, mTLS | Standard protocol, short-lived tokens, ecosystem compatibility |
| Policy language | OPA/Rego-inspired DSL | Custom RBAC, Casbin, Cedar | Declarative, testable, industry familiarity for platform teams |
| Secret leasing | JIT with TTL + auto-revoke | Static secrets with rotation | Eliminates standing access, secrets exist only when needed |
| Multi-provider secrets | Abstraction layer over Vault/AWS/1Password | Single provider lock-in | Matches reality that teams use different secret stores |
| Token budgets | Per-agent hard limits | Org-level soft limits only | Prevents runaway agents, enables chargeback per team |
| Injection detection | Pattern + heuristic | LLM-based classification | Lower latency, no additional API cost, deterministic |
| Audit storage | PostgreSQL + SIEM export | Dedicated log store | Queryable, joins with agent/policy data, export to any SIEM |
| SDK language | TypeScript | Python, Go, multi-language | Developers building AI agents primarily work in TS/JS |

## Environment Variables

```bash
PORT=8000
DATABASE_URL=postgresql://user:password@localhost/agentgate
JWT_SECRET=YOUR_JWT_SECRET_KEY_CHANGE_IN_PRODUCTION
CORS_ORIGINS=http://localhost:3000
OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317
```

## Development

```bash
# Install Python dependencies
pip install -r requirements.txt

# Run database migrations
python -c "from src.db import connection; import asyncio; asyncio.run(connection.init_db())"

# Start development server
python -m src.api.main

# Install SDK/CLI dependencies
npm install --prefix sdk
npm install --prefix cli
```

## Production Deployment

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8000
CMD ["python", "-m", "src.api.main"]
```

### Kubernetes with Supabase

```bash
# Create PostgreSQL database on Supabase
# Set DATABASE_URL secret
kubectl create secret generic agentgate-db --from-literal=url=$DATABASE_URL

# Deploy
kubectl apply -f k8s/deployment.yaml
```

## API Examples

### Authentication

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "client_credentials",
    "client_id": "YOUR_AGENTGATE_CLIENT_ID_...",
    "client_secret": "YOUR_AGENTGATE_SECRET_...",
    "scope": ["read:data", "write:results"]
  }'
```

### Request Secret

```bash
curl -X POST http://localhost:8000/api/v1/secrets/request \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "secret_name": "database/prod/password",
    "ttl_seconds": 3600,
    "justification": "Daily batch job"
  }'
```

### Query Audit Logs

```bash
curl -X POST http://localhost:8000/api/v1/audit/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "secret_accessed",
    "severity": "critical",
    "limit": 50
  }'
```

## Testing

```bash
pytest tests/
npm test --prefix sdk
npm test --prefix cli
```

## Repository Structure

```
agentgate/
├── src/                          # Core API server (Python/FastAPI)
│   ├── api/                      # REST endpoints, auth middleware
│   │   └── endpoints/            # Agents, policies, secrets, audit, gateway
│   ├── identity/                 # Agent registration, JWT tokens
│   ├── policy/                   # OPA/Rego-inspired policy engine
│   ├── secrets/                  # JIT broker, multi-provider, rotation
│   ├── audit/                    # Structured logging, SIEM export
│   ├── gateway/                  # LLM proxy, token budgets, injection detection
│   └── db/                       # PostgreSQL connection, migrations
├── sdk/                          # TypeScript SDK for developers
├── cli/                          # CLI tool (agentgate agent/policy/secret/audit)
├── mcp/                          # Model Context Protocol server
├── dashboard/                    # React management UI
├── docs/                         # PRD, Architecture, Data Model, Metrics
├── tests/                        # 7 test files (auth, policy, secrets, audit, gateway, API)
├── demo/                         # Sample agents, policies, interactive demo
├── terraform/                    # AWS infrastructure (ECS, RDS, ElastiCache)
├── observability/                # OpenTelemetry config, Grafana dashboards
├── data_quality/                 # Great Expectations validation suites
├── evals/                        # Promptfoo adversarial injection tests
├── emails/                       # React Email notification templates
└── .github/workflows/            # CI/CD pipeline
```

## Related Projects

| Project | What It Does | Relationship |
|---------|-------------|-------------|
| [GenAI Governance](https://github.com/riiiiiicoooo/genai-governance) | AI governance & compliance framework | AgentGate enforces access policies; GenAI Governance defines organizational AI usage policies |
| [Infrastructure Automation Platform](https://github.com/riiiiiicoooo/infrastructure-automation-platform) | IaC provisioning & deployment | AgentGate secures the AI agents that automate infrastructure changes |
| [Integration Health Monitor](https://github.com/riiiiiicoooo/integration-health-monitor) | API reliability & webhook monitoring | AgentGate audit logs feed into integration health dashboards |
| [Contract Intelligence Platform](https://github.com/riiiiiicoooo/contract-intelligence-platform) | AI-powered contract analysis | Contract analysis agents authenticate through AgentGate for secret access |
| [Portfolio Intelligence Hub](https://github.com/riiiiiicoooo/portfolio-intelligence-hub) | RAG-powered analytics for real estate | Text-to-SQL and RAG agents use AgentGate for scoped database access |

## Engagement & Budget

### Team & Timeline

| Role | Allocation | Duration |
|------|-----------|----------|
| Lead PM (Jacob) | 20 hrs/week | 14 weeks |
| Lead Developer (US) | 40 hrs/week | 14 weeks |
| Offshore Developer(s) | 2 × 35 hrs/week | 14 weeks |
| QA Engineer | 20 hrs/week | 14 weeks |

**Timeline:** 14 weeks total across 3 phases
- **Phase 1: Discovery & Design** (3 weeks) — Agent inventory across 12 squads, secret sprawl audit, policy requirements gathering, OAuth 2.0 flow design, compliance gap analysis (SOC 2)
- **Phase 2: Core Build** (8 weeks) — Identity management + OAuth server, policy engine (OPA/Rego), JIT secrets broker, audit logging pipeline, TypeScript SDK + CLI, token budgeting system
- **Phase 3: Integration & Launch** (3 weeks) — Vault/AWS Secrets Manager/1Password connectors, Grafana dashboards, Promptfoo adversarial evals, squad-by-squad rollout (platform team → all 12 squads)

### Budget Summary

| Category | Cost | Notes |
|----------|------|-------|
| PM & Strategy | $51,800 | Discovery, specs, stakeholder management |
| Development (Lead + Offshore) | $139,440 | Core platform build |
| QA Engineer | $9,800 | Testing and quality assurance |
| AI/LLM Token Budget | $3,500/total | Claude Haiku for prompt injection detection (~3M tokens/month) × 14 weeks |
| Infrastructure | $6,720/total | Supabase Pro ($25/mo), Redis ($65/mo), AWS (ECS, RDS, ElastiCache) ($250/mo), Grafana ($25/mo), misc ($115/mo) × 14 weeks |
| **Total Engagement** | **$200,000** | Fixed-price, phases billed at milestones |
| **Ongoing Run Rate** | **$900/month** | Infrastructure + AI tokens + support |

---

## Business Context

### Market Size
~15,000 software companies with 50+ engineers actively using AI coding agents (GitHub Copilot, Cursor, Claude Code). Non-human identity management is a $3.2B market growing 35% annually (Gartner Identity Security, 2025), with AI agent identity as the fastest-growing subsegment.

### Unit Economics

| Metric | Value |
|--------|-------|
| **Before** | |
| Secret exposure incidents/year | 23 |
| Remediation cost per incident | $4K |
| Token overrun cost/year | $50K |
| Manual credential management time/year | $180K |
| **Total annual cost** | **$92K + $50K + $180K** |
| **After** | |
| Secret exposure incidents/year | 0 |
| Token overrun cost/year | $0 |
| Platform management time/year | $18K |
| **Total annual cost** | **$18K** |
| **Annual savings** | **$304K** |
| **Platform build cost** | **$200,000** |
| **Monthly run rate** | **$900** |
| **Payback period** | **8 months** |
| **3-year ROI** | **4.2x** |

### Pricing Model
If productized: $2,000-8,000/month based on agent count and developer seats, targeting $8-15M ARR at 500 companies.

---

## PM Perspective

The hardest decision was whether to build a custom policy language or use OPA/Rego directly. OPA is the industry standard, but it has a steep learning curve — most developers on the team hadn't written Rego before. A custom RBAC system would be simpler to adopt but less powerful. I chose an OPA/Rego-inspired DSL that uses the same concepts (rules, conditions, resource matching) but with a simplified syntax that maps to the team's mental model. Platform engineers who knew Rego could write native policies; everyone else used the simplified syntax. Adoption was 100% within 3 weeks, which wouldn't have happened with raw Rego.

The surprise was learning that the $4,200 runaway token incident wasn't an anomaly — it was the norm waiting to happen. During discovery, I audited all 8 internal agents' token consumption over 30 days. Three of them had no error handling for retry loops — if an LLM call failed, they'd retry indefinitely. One agent was burning $800/month just on retries against rate limits. The token budgeting feature I scoped as a "nice to have" became the #2 priority after the VP of Engineering saw the audit data. What I thought was a security product turned out to be equally a cost management product.

What I'd do differently: I would have shipped the Grafana dashboards in Phase 2 alongside the core platform instead of Phase 3. For the first 3 weeks after launch, the only way to see agent activity was querying the audit log API directly. Platform engineers had to write custom scripts to answer basic questions like "which agents are most active?" and "what's our daily token spend?" The dashboard was trivial to build but made the product feel complete. Missing it at launch meant we had a security product that nobody could easily observe.

---

## About This Project

Built as a product management engagement for a Series B developer tools company (75-person engineering org) that had adopted AI coding agents across all 12 squads with zero governance over what those agents could access. I led discovery across platform engineering, security, and all 12 squad leads to map agent access patterns and secret sprawl. Designed the zero-trust architecture with OAuth 2.0 client credentials, OPA/Rego policy engine, and JIT secret leasing. Made build-vs-buy decisions on secrets management (multi-provider abstraction vs. Vault-only) and policy language (OPA-inspired vs. custom RBAC). Defined the TypeScript SDK and CLI developer experience based on platform team interviews.

**Note:** Client-identifying details have been anonymized. Code represents the architecture and design decisions I drove; production deployments were managed by client engineering teams.

## License

Apache License 2.0
