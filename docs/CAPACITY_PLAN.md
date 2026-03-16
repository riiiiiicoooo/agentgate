# AgentGate — Capacity Plan

**Last Updated:** March 2026
**Baseline Workload:** 10M API requests/month (250K daily active agents)

---

## Current State (10M requests/month)

### Infrastructure

| Component | Current | Headroom | Notes |
|-----------|---------|----------|-------|
| **API servers (FastAPI)** | 3 x t3.2xlarge (8 CPU, 32GB) | ~35% CPU utilization avg | Peak hours hit 65% CPU |
| **PostgreSQL (policy + agent DB)** | 1 x r6g.xlarge (4 CPU, 32GB) + 2 read replicas | 1 primary is bottleneck; read replicas at 45% | Policy evaluation queries average 15ms |
| **Redis cache** | 1 x r6g.xlarge (4 CPU, 32GB) | 50% memory utilization | Policy cache (80% hit rate) + session cache |
| **S3 audit logs** | S3 Standard + Object Lock | Unlimited capacity | ~50GB/month growth |
| **Webhook processing (secret rotation)** | SQS queue | 95% headroom | <5K msgs/day for secret rotation notifications |

### Cost

| Category | Monthly | Annual |
|----------|---------|--------|
| Compute (EC2 + ECS) | $3.8K | $45K |
| Database (RDS + read replicas) | $2.2K | $26K |
| Storage (S3 + Object Lock) | $0.5K | $6K |
| Data transfer | $0.3K | $4K |
| **Total** | **$6.8K** | **$81K** |

### Performance Baseline

| Metric | Value | SLO |
|--------|-------|-----|
| Policy eval latency (p95) | 78ms | 100ms ✓ |
| Policy eval latency (p99) | 145ms | — |
| Cache hit rate | 82% | — |
| API error rate | 0.06% | <0.5% ✓ |
| Audit log ingestion latency (p95) | 300ms | <1s ✓ |
| Credential exposure incidents | 0 | 0 (zero tolerance) ✓ |

### What Breaks First at Current Load

1. **PostgreSQL primary** — Policy evaluation queries under load (many agents with different policies) cause connection pool exhaustion; read replicas handle queries but policy writes (new agent registration) create bottleneck
2. **Redis eviction** — Policy cache grows with every new agent; at 250K agents, cache can hold ~20K hot policies; eviction starts at 80% memory
3. **S3 audit logs** — S3 PUT rate limits (3.5K PUTs/sec) are never hit at current volume, but concurrent writes during incident (all agents retrying) could breach limits
4. **API server CPU** — Peak morning hours (7am-12pm) hit 65% CPU; adding 50% more load brings to 97% (dangerous territory)

---

## 2x Scenario (20M requests/month)

### What Changes

- **Agent base:** 500K daily active agents (enterprise GitHub, VSCode Copilot pilots expanding)
- **Request mix:** More complex policies (nested rules, time-based conditions) = longer evaluation time
- **Credential types:** More secret backends (Vault, 1Password, AWS Secrets Manager) = more varied secret fetch patterns

### Infrastructure Changes

| Component | 1x → 2x | Action | Timeline |
|-----------|---------|--------|----------|
| **API servers** | 3 → 6 instances (t3.2xlarge) | Double capacity; enable autoscaling | Week 1 |
| **PostgreSQL** | 1 primary + 2 replicas → 1 primary + 4 replicas | Upgrade primary to r6g.2xlarge; add read-heavy query routing | Month 1 |
| **Redis** | 1 x r6g.xlarge → 1 x r6g.2xlarge (double memory) | Upgrade cache; consider Redis cluster if memory > 80% | Month 1 |
| **Audit logging** | Single S3 bucket → S3 partitioned by date | Prepare for larger S3 PUT volume; shard if needed | Month 2 |
| **Policy evaluation** | Cached in-memory → distributed cache | If p95 latency trends >120ms, add memcached layer | Q3 2026 |

### Cost Impact

| Category | 1x | 2x | Delta | % increase |
|----------|----|----|-------|-----------|
| Compute | $3.8K | $7.2K | +$3.4K | +89% |
| Database | $2.2K | $4.8K | +$2.6K | +118% |
| Storage | $0.5K | $0.9K | +$0.4K | +80% |
| Data transfer | $0.3K | $0.6K | +$0.3K | +100% |
| **Total** | **$6.8K** | **$13.5K** | **+$6.7K** | **+99%** |

### Performance at 2x

| Metric | 1x Baseline | 2x Expected | Status |
|--------|------------|-------------|--------|
| Policy eval latency (p95) | 78ms | 110ms | Slightly over SLO; needs optimization |
| Cache hit rate | 82% | 70% | Acceptable; cache thrashing begins |
| API error rate | 0.06% | 0.12% | Still well within bounds |
| Audit log ingestion latency (p95) | 300ms | 450ms | Acceptable; monitor S3 PUT rate |

### What Breaks First at 2x

1. **Policy eval latency (p95 > 100ms)** — Increased agent count means more cache misses; database queries start to back up
2. **Cache eviction rate spikes** — Policy cache at 90%+ memory; eviction frequency increases from 10/min to 100+/min, causing performance cliff
3. **PostgreSQL read replica lag** — Replication lag grows as write volume increases; agents may see stale policy data (<1 sec old, but still stale)
4. **S3 audit log batching** — Single batch writer becomes bottleneck; need to shard audit log writes across multiple S3 prefixes

### Scaling Triggers for 2x

- **Policy eval p95 > 95ms:** Begin query optimization (add indexes on high-cardinality fields)
- **Redis memory > 85%:** Consider upgrading to r6g.2xlarge or enabling eviction policy
- **Cache hit rate < 75%:** Adjust cache TTL or add policy clustering (group similar policies together)
- **API server CPU > 70%:** Autoscale (+2 servers)
- **PostgreSQL replication lag > 100ms:** Add more read replicas or upgrade primary to larger instance

---

## 10x Scenario (100M requests/month)

### Market Reality at 10x

- **Agent base:** 2.5M+ daily active agents (all major IDEs + AI coding platforms)
- **Policy complexity:** Customers define 100+ custom policies per organization
- **Compliance load:** SOC 2, HIPAA, FedRAMP audits happening simultaneously
- **Incident rate:** Attackers begin targeting AgentGate (honeypot attacks to find policy bypasses)

### What's Fundamentally Broken at 10x

1. **Policy evaluation latency math** — At 100M requests/month, peak concurrent requests are 800-1000 per second. Even perfect caching (95% hit rate) means 40-50 cache misses/sec hitting database. Each database query takes 20-50ms, resulting in p95 latency of 150-200ms minimum. **SLO breach is unavoidable without architectural change.**

2. **Audit log scalability** — 100M requests/month = 3.3M events/day. S3 Object Lock + real-time ingest becomes expensive ($5K-10K/month). Current architecture (single batch writer) becomes bottleneck. **Need distributed audit log architecture (Kafka).**

3. **Policy versioning explosion** — At 10x volume, policies change frequently (5-10 updates/day per organization vs. 1-2 today). Keeping all versions immutable (for audit) causes schema bloat. **Need policy snapshot/archival strategy.**

4. **Credential rotation throughput** — 2.5M agents means rotation events spike from <5K/day to 50K+/day. Current webhook-based rotation (one secret at a time) becomes bottleneck. **Need batch rotation API.**

### Architectural Changes Needed for 10x

| Problem | 1x/2x Solution | 10x Solution |
|---------|---|---|
| **Policy eval latency** | In-memory cache + database queries | Distributed cache (Redis cluster) + policy query optimization (Elasticsearch for complex queries) + write-through cache |
| **Audit logging** | Single S3 bucket + batch writer | Kafka topic for audit events; S3 for cold storage (batch archive daily) |
| **Policy storage** | Single PostgreSQL table | Partition policies by organization; archive old versions to S3; keep only active versions hot |
| **Credential rotation** | Webhook per agent | Batch rotation API; agents poll for updates instead of push |
| **Scalability** | Multi-region failover | Distributed database (Spanner or similar) or read-write replicas across regions |

### Cost at 10x (Realistic Projection)

| Category | 1x | 10x | Ratio |
|----------|----|----|-------|
| Compute | $3.8K | $25K | 6.6x |
| Database (distributed) | $2.2K | $20K | 9x |
| Cache (Redis cluster) | Included in DB | $8K | ∞ |
| Kafka (audit streaming) | $0 | $5K | ∞ |
| Storage (S3 + archival) | $0.5K | $8K | 16x |
| **Total** | **$6.8K** | **$66K** | **9.7x** |

**Cost scales sub-linearly (9.7x cost for 10x volume) due to infrastructure economies of scale.**

### Scaling Triggers for 10x

- **Policy eval p95 > 120ms:** Initiate Redis cluster pilot
- **S3 PUT rate > 2K/sec:** Activate Kafka-based audit log streaming
- **PostgreSQL table size > 200GB:** Implement policy partitioning by organization_id
- **Replication lag > 500ms:** Consider distributed database (Spanner)
- **Cost per request > $0.0001:** Review all infrastructure costs; potential for optimization

---

## Capacity Planning Roadmap

| Quarter | Trigger Level | Action | Investment |
|---------|---|---|---|
| Q2 2026 | Monitor 2x | Pre-stage 2x infrastructure (API servers, database read replicas) | $2K infrastructure |
| Q3 2026 | Approach 2x (15M req/month) | Activate autoscaling; optimize policy queries | $8K infrastructure + 150 eng hours |
| Q4 2026 | Hit 2x (20M req/month) | Full 2x operational | Ongoing ops |
| Q1 2027 | Plan 5x (50M req/month) | Kafka POC for audit logs; Redis cluster evaluation | 300 eng hours |
| Q2 2027+ | 5x+ territory | Execute 10x roadmap; distributed database migration | $40K infra + 800 eng hours over 6 months |

