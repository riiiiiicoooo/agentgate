# AgentGate — Service Level Objectives (SLOs)

**Last Updated:** March 2026
**Compliance Scope:** Credential exposure prevention, policy enforcement integrity, audit trail immutability

---

## Error Budget Policy

AgentGate operates on a **zero-tolerance model** for certain SLOs (credential exposure, policy bypass) and a **monthly error budget** for others (API latency, availability). The distinction reflects the criticality: a single undetected credential exposure is worse than 1 hour of API downtime.

**SLO Categories:**
- **Zero-tolerance SLOs:** Credential exposure, policy evaluation correctness, audit trail integrity (no error budget)
- **Traditional SLOs:** API latency, system availability, cache performance (monthly error budgets with burn rate alerts)

---

## SLO 1: Zero Credential Exposures (Token Leakage Prevention)

**Service:** `credential-vault-middleware`
**Definition:** Percentage of credential requests where the plaintext secret: (a) is never logged, (b) is not stored in response bodies or error messages, and (c) is not transmitted insecurely (TLS 1.2+).

**Target:** 100.0% (zero exposures, zero error budget)

**Measurement:**
- Query: `(REQUESTS_WITH_LEAKED_CREDENTIAL) / TOTAL_REQUESTS`
- Sampling: 100% of requests (no sampling acceptable)
- Detection: Log regex for credential patterns (AWS key format, JWT structure, etc.); automated secret scanner on all code commits; memory dumps after each request
- Source: `credential_exposure_audit`, application logs

**Why This Target:**
- **Regulatory reality:** A single exposed API key (e.g., Stripe secret key, AWS credentials) can result in $50K-$500K unauthorized charges; 23 exposures in 6 months (pre-AgentGate baseline) meant 4/month were occurring
- **Blast radius:** One exposed AWS credential allows attacker to spin up 1000 GPUs for cryptomining; cost: $100K/day
- **Customer trust:** If one customer's exposed credential is found in logs/backups, entire customer base loses trust; product becomes non-viable
- **Compliance:** SOC 2 Type II auditors explicitly require zero-tolerance for secrets in logs

**Burn Rate Triggers:**
- **Any exposure detected:** Immediate P0 incident; halt all deployments; RCA within 2 hours
- **3+ exposures in 30 days:** Review credential handling code; potential architectural flaw
- **Pattern of same credential type exposed:** Indicates specific code path is vulnerable (e.g., error messages always log Redis password)

**Mitigations:**
- Never log credentials; use placeholders like `<REDACTED-AWS-KEY-****[LAST-4]>`
- Outbound requests: Strip credentials from error responses (catch exceptions, log "credential fetch failed" without details)
- Memory management: Clear credential variables from memory immediately after use
- Automated scanning: Every code commit scanned for credentials before merge (pre-commit hooks + CI check)
- Quarterly penetration testing: Third-party red team attempts to extract credentials from running system

---

## SLO 2: Policy Evaluation Correctness (No Unintended Policy Bypasses)

**Service:** `policy-evaluation-engine`
**Definition:** Percentage of policy decisions where: (a) correct policy is applied (not wrong version), (b) decision logic is deterministic (same input → same output), and (c) evaluation is complete before allowing secret access.

**Target:** 100.0% (zero policy bypasses, zero error budget)

**Error Budget:** None (this is non-negotiable)

**Measurement:**
- Query: `(POLICY_DECISIONS_CORRECT) / TOTAL_POLICY_DECISIONS`
- Sampling: 100% of decisions; monthly spot-checks against ground truth (manual policy review)
- Source: `policy_evaluations`, policy version history

**Why This Target:**
- **Security model:** The entire product is "stop bad actors from getting secrets"; if policies can be bypassed, product is ineffective
- **Audit evidence:** Financial institutions auditing AgentGate deployment are essentially auditing: "Can I trust that policy decisions are enforced?" If 1% bypass rate exists, answer is "no"
- **Blast radius:** One policy bypass → one attacker gets access to production database password → entire customer's data compromised

**Burn Rate Triggers:**
- **Any policy bypass detected:** P0 incident; customer notification within 1 hour
- **2+ bypasses in 90 days:** Architectural review; consider policy isolation mechanism (separate process)
- **Bypass pattern detected:** (e.g., "admin-only policy can be bypassed by X") — escalate to security team

**Mitigations:**
- Policy versioning: Every policy version is immutable; can't change existing rule mid-evaluation
- Timeout protection: Policy evaluation has hard timeout (2 seconds); if exceeded, deny access rather than timeout
- Dual-check: High-risk decisions (production secret access) evaluated twice by independent code paths
- Testing: Automated tests for every policy rule; monthly adversarial testing by security team

---

## SLO 3: Audit Trail Integrity (Immutable Compliance Log)

**Service:** `audit-log-processor`
**Definition:** Percentage of audit events where: (a) event is written to immutable storage (S3 Object Lock) within 1 second, (b) event includes mandatory fields (timestamp, actor, action, resource, decision), and (c) event cannot be modified or deleted post-write.

**Target:** 99.99% (14 failures per million events, or ~40 min/month at 1M events baseline)

**Error Budget:** 40 minutes/month

**Measurement:**
- Query: `(AUDIT_EVENTS_IMMUTABLY_LOGGED) / TOTAL_EVENTS`
- Sampling: 100% of events (no sampling for compliance)
- Validation: Daily check that all S3 audit objects have Object Lock enabled and cannot be deleted
- Source: `audit_log_ingestion`, S3 Object Lock metadata

**Why This Target:**
- **Regulatory requirement:** Regulators (SOC 2, HIPAA, etc.) require immutable audit trails; loss of audit entries is compliance failure
- **Forensic value:** If incident occurs (credential exposure, policy bypass), regulators ask "Show me the audit trail"; if entries are missing, defensibility erodes
- **Practical impact:** 1M events/month with 99.99% target = ~40 min/month of acceptable log loss. At our volume, that's ~3K events that might not be logged. Defensible because it's <0.01% of total activity

**Burn Rate Triggers:**
- **Log ingestion latency > 5 seconds:** Watch alert; indicates potential lag in immutable storage writes
- **S3 Object Lock validation fails:** Critical alert; audit logs are not actually immutable (might be deletable)
- **24+ hour gap in audit logs:** P0 incident; breach of compliance requirement

**Mitigations:**
- Dual write: Audit events written to both PostgreSQL (for fast query) and S3 (immutable backup)
- S3 Object Lock: GOVERNANCE mode (admin can override) for first 7 days; COMPLIANCE mode (nobody can delete) for >90 days
- Local buffer: If S3 write fails, buffer locally and retry; eventually consistent but no data loss
- Daily validation: Automated job confirms all S3 objects have Object Lock and match database records

---

## SLO 4: Policy Evaluation Latency (For Approval Decisions)

**Service:** `policy-evaluation-engine`
**Definition:** Percentage of policy evaluation requests where decision latency (from request receipt to decision rendered) is ≤ 100ms at p95.

**Target:** 95.0% (max p95 latency 100ms)

**Error Budget:** 36 hours/month (at 100K policy evaluations/day baseline)

**Measurement:**
- Query: `(POLICY_EVAL_LATENCY_P95 <= 100ms) * 100`
- Includes: Policy lookup, rule evaluation, caching checks
- Excludes: Network transit time (pre-request)
- Source: `policy_evaluation_metrics`

**Why This Target:**
- **Developer experience:** Agents (GitHub Copilot, Cursor, Claude) poll for secrets thousands of times per day; latency >100ms becomes noticeable in IDE (editor feels slow)
- **Cache efficiency:** Policies are cached aggressively; 95% of requests should be cache hits (<10ms). The 5% cache misses hit database, which takes 20-50ms
- **Competitive baseline:** Other credential managers (Vault, AWS Secrets Manager) achieve <50ms p95; we target 100ms as acceptable for SDK-based polling

**Burn Rate Triggers:**
- **p95 latency > 200ms (2x target):** High burn; investigate caching hit rate and database query performance
- **p50 latency > 50ms:** Normal burn; monitor for trend
- **Cache hit rate < 80%:** Watch alert; cache should be warmer; investigate policy change frequency

**Mitigations:**
- In-memory policy cache (updated every 30 seconds)
- Connection pooling to policy database (reduce TCP handshake overhead)
- Query optimization: Indexes on (policy_id, agent_id) pairs

---

## SLO 5: System Availability (Overall Platform)

**Service:** `agentgate-platform` (aggregate)
**Definition:** Percentage of 1-minute windows where ≥99% of policy evaluation requests receive a response (allow/deny/audit-only) within 30 seconds.

**Target:** 99.8% (57 minutes downtime/month)

**Error Budget:** 57 minutes/month

**Measurement:**
- Query: `(MINUTES_WITH_99PCT_SUCCESS) / TOTAL_MINUTES`
- Sampling: 1-minute windows; reported as rolling 24h average
- Source: `request_success_metrics`

**Why This Target:**
- **Developer workflow:** Agents use AgentGate synchronously (wait for allow/deny); >99% availability means developers rarely hit "permission service is down"
- **Operational reality:** 99.8% allows ~1 outage per month (1 hour); acceptable for non-mission-critical security gateway
- **SLA to customers:** Enterprise customers expect 99.5-99.8%; we commit to 99.8% to have headroom

**Burn Rate Triggers:**
- **Error rate > 2% (burn rate > 10x):** Page on-call; issue likely is database unavailability or API gateway failure
- **Error rate > 1%:** High burn; investigate
- **Error rate > 0.5%:** Normal burn

**Mitigations:**
- Multi-region active-active (US-East + US-West)
- Database read replicas for load balancing
- Circuit breaker on slow queries; fail fast rather than timeout

---

## Error Budget Consumption Practices

1. **Weekly SLO review:** Every Monday, review SLO burn rate for all objectives
2. **Proactive remediation:** If burn rate > 5x, rollback last deploy before investigating
3. **Cross-functional visibility:** SLO status included in daily standup (show % of target achieved)
4. **Post-incident RCA:** Every incident with burn rate > 2x requires RCA within 48 hours
5. **Executive reporting:** Monthly report to board covers all SLOs and biggest burn drivers

---

## SLO Relationships

```
Zero-Tolerance SLOs (No Error Budget)
├── Zero credential exposures (product integrity)
├── Policy evaluation correctness (security model)
└── Audit trail integrity (compliance requirement)

Traditional SLOs (Monthly Error Budget)
├── Policy evaluation latency (developer experience)
└── System availability (operational reliability)
```

Protecting zero-tolerance SLOs takes precedence over traditional SLOs. If a deploy would improve availability but risks credential exposure, we reject the deploy.

