# AgentGate Metrics & Monitoring

## Key Metrics Framework

AgentGate exposes comprehensive metrics for monitoring system health, performance, and business outcomes. All metrics follow the OpenTelemetry specification and are exported to Prometheus-compatible endpoints.

## Performance Metrics

### API Latency

```prometheus
# Histogram of HTTP request duration (seconds)
agentgate_http_request_duration_seconds_bucket{le="0.01", method="GET", endpoint="/oauth2/token", status="200"}
agentgate_http_request_duration_seconds_bucket{le="0.05", method="GET", endpoint="/oauth2/token", status="200"}
agentgate_http_request_duration_seconds_bucket{le="0.1", method="GET", endpoint="/oauth2/token", status="200"}
agentgate_http_request_duration_seconds_bucket{le="0.5", method="GET", endpoint="/oauth2/token", status="200"}
agentgate_http_request_duration_seconds_bucket{le="1", method="GET", endpoint="/oauth2/token", status="200"}
agentgate_http_request_duration_seconds_bucket{le="+Inf"}
agentgate_http_request_duration_seconds_count{method="GET", endpoint="/oauth2/token", status="200"} 150000
agentgate_http_request_duration_seconds_sum{method="GET", endpoint="/oauth2/token", status="200"} 2.5

# Request count by endpoint and status
agentgate_http_requests_total{method="GET", endpoint="/oauth2/token", status="200"} 150000
agentgate_http_requests_total{method="GET", endpoint="/secrets/request", status="200"} 95000
agentgate_http_requests_total{method="GET", endpoint="/secrets/request", status="403"} 2500
agentgate_http_requests_total{method="GET", endpoint="/policies/evaluate", status="200"} 45000

# Percentile targets
histogram_quantile(0.50, agentgate_http_request_duration_seconds) -> <20ms  (median)
histogram_quantile(0.95, agentgate_http_request_duration_seconds) -> <100ms
histogram_quantile(0.99, agentgate_http_request_duration_seconds) -> <200ms
```

### Database Performance

```prometheus
# Database query latency
agentgate_db_query_duration_seconds{query="SELECT * FROM agents", status="success"}
agentgate_db_query_duration_seconds{query="INSERT INTO audit_events", status="success"}

# Connection pool stats
agentgate_db_connection_pool_size{status="active"} 45
agentgate_db_connection_pool_size{status="idle"} 25
agentgate_db_connection_pool_size{status="waiting"} 0

# Query counts
agentgate_db_queries_total{query_type="SELECT", status="success"} 500000
agentgate_db_queries_total{query_type="INSERT", status="success"} 50000
agentgate_db_queries_total{query_type="UPDATE", status="success"} 10000
agentgate_db_queries_total{query_type="SELECT", status="error"} 150

# Slow query tracking (>100ms)
agentgate_slow_queries_total{query="SELECT * FROM audit_events"} 25
```

### Cache Performance

```prometheus
# Cache hit/miss rates
agentgate_cache_hits_total{cache_type="secret", region="us-east-1"} 850000
agentgate_cache_misses_total{cache_type="secret", region="us-east-1"} 150000
# Hit rate: 850000 / (850000 + 150000) = 85%

agentgate_cache_hits_total{cache_type="policy_eval"} 400000
agentgate_cache_misses_total{cache_type="policy_eval"} 100000
# Hit rate: 80%

# Cache evictions
agentgate_cache_evictions_total{cache_type="secret"} 10000
agentgate_cache_evictions_total{reason="expired"} 8000
agentgate_cache_evictions_total{reason="memory_limit"} 2000

# Redis memory usage
agentgate_redis_memory_usage_bytes{host="redis.internal"} 534217728  # 512 MB
agentgate_redis_memory_peak_bytes{host="redis.internal"} 650123456

# Cache size
agentgate_cache_size_items{cache_type="secret"} 50000
agentgate_cache_size_items{cache_type="policy_eval"} 25000
```

## Security Metrics

### Authentication & Authorization

```prometheus
# OAuth token issuance
agentgate_oauth_token_issuance_total{status="success"} 600000
agentgate_oauth_token_issuance_total{status="invalid_credentials"} 1200
agentgate_oauth_token_issuance_total{status="agent_not_active"} 50

# Token validation failures
agentgate_token_validation_failures_total{reason="expired"} 500
agentgate_token_validation_failures_total{reason="revoked"} 150
agentgate_token_validation_failures_total{reason="invalid_signature"} 20
agentgate_token_validation_failures_total{reason="malformed"} 100

# Policy evaluation results
agentgate_policy_evaluations_total{decision="ALLOW", policy="staging-policy"} 95000
agentgate_policy_evaluations_total{decision="DENY", policy="staging-policy"} 2500
agentgate_policy_evaluations_total{decision="AUDIT_ONLY"} 1000

# Policy evaluation latency
agentgate_policy_evaluation_duration_seconds{policy="staging-policy"} histogram
histogram_quantile(0.95, ...) -> <30ms
histogram_quantile(0.99, ...) -> <50ms
```

### Secret Access

```prometheus
# Secret request outcomes
agentgate_secret_requests_total{decision="ALLOW", secret="db_password"} 50000
agentgate_secret_requests_total{decision="DENY", secret="prod_api_key"} 500
agentgate_secret_requests_total{decision="ALLOW_WITH_RESTRICTIONS"} 1000

# Secret rotation metrics
agentgate_secret_rotations_total{secret="db_password", status="success"} 120
agentgate_secret_rotations_total{secret="api_key", status="failed"} 5
agentgate_secret_rotations_duration_seconds{secret="db_password"} histogram

# Attempted unauthorized secret access
agentgate_secret_access_denied_total{secret="prod_db", reason="policy_denied"} 150
agentgate_secret_access_denied_total{secret="prod_api_key", reason="environment_mismatch"} 50
agentgate_secret_access_denied_total{secret="aws_credentials", reason="agent_not_active"} 10
```

### Audit & Compliance

```prometheus
# Audit events logged
agentgate_audit_events_total{event_type="secret_requested", decision="ALLOW"} 500000
agentgate_audit_events_total{event_type="secret_requested", decision="DENY"} 5000
agentgate_audit_events_total{event_type="agent_created"} 500
agentgate_audit_events_total{event_type="policy_updated"} 250
agentgate_audit_events_total{event_type="agent_revoked"} 30

# Audit event processing
agentgate_audit_event_processing_duration_seconds{} histogram
histogram_quantile(0.95, ...) -> <10ms

# Compliance violations
agentgate_compliance_violations_total{violation_type="policy_denied"} 5000
agentgate_compliance_violations_total{violation_type="unauthorized_access_attempt"} 150
```

## Business Metrics

### Agent Usage

```prometheus
# Total registered agents
agentgate_agents_total{status="ACTIVE"} 250
agentgate_agents_total{status="PAUSED"} 10
agentgate_agents_total{status="REVOKED"} 5
agentgate_agents_total{status="ARCHIVED"} 15

# Agents by type
agentgate_agents_total{agent_type="github-copilot"} 150
agentgate_agents_total{agent_type="cursor"} 50
agentgate_agents_total{agent_type="claude"} 30
agentgate_agents_total{agent_type="custom"} 20

# Agents by environment
agentgate_agents_total{environment="dev"} 100
agentgate_agents_total{environment="staging"} 75
agentgate_agents_total{environment="prod"} 75

# Agent activity
agentgate_agent_last_activity_timestamp{agent_id="agent-123"} 1705334400
agentgate_agent_requests_per_day{agent_id="agent-123", date="2024-01-15"} 450

# Inactive agents (no requests in 7 days)
agentgate_inactive_agents_total{inactive_days="7"} 5
agentgate_inactive_agents_total{inactive_days="30"} 12
```

### Secret Metrics

```prometheus
# Total secrets
agentgate_secrets_total{secret_type="database"} 50
agentgate_secrets_total{secret_type="api_key"} 100
agentgate_secrets_total{secret_type="ssh_key"} 25

# Secrets by backend
agentgate_secrets_total{backend_type="vault"} 100
agentgate_secrets_total{backend_type="aws_secrets_manager"} 50
agentgate_secrets_total{backend_type="1password"} 25

# Secret request volume
agentgate_secret_requests_daily_total{date="2024-01-15", secret="db_password"} 1500
agentgate_secret_requests_daily_total{date="2024-01-15", secret="api_key"} 2000

# Secrets due for rotation
agentgate_secrets_due_rotation_total{} 5
agentgate_secrets_overdue_rotation_total{days_overdue="7"} 1
```

### Policy Metrics

```prometheus
# Total policies
agentgate_policies_total{status="ACTIVE"} 15
agentgate_policies_total{status="ARCHIVED"} 3

# Policy application
agentgate_policies_applied_total{policy="staging-policy"} 50000
agentgate_policies_applied_total{policy="prod-policy"} 30000

# Policy violations per policy
agentgate_policy_violations_total{policy="staging-policy"} 100
agentgate_policy_violations_total{policy="prod-policy"} 250

# Most applied policies
Top 5 policies by evaluation count
```

## Rate Limiting Metrics

```prometheus
# Rate limit violations
agentgate_rate_limit_violations_total{agent_id="agent-123", limit_type="requests_per_second"} 50
agentgate_rate_limit_violations_total{agent_id="agent-456", limit_type="token_budget_per_day"} 10

# Current rate limit status (per agent)
agentgate_rate_limit_current{agent_id="agent-123", limit_type="requests_per_second"} 8  # of 10 allowed
agentgate_rate_limit_current{agent_id="agent-456", limit_type="token_budget_per_day"} 9500  # of 10000 allowed

# Rate limit resets today
agentgate_rate_limit_resets_today{agent_id="agent-123", hours_until_reset="6"} 1
```

## System Health Metrics

### API Server Health

```prometheus
# HTTP errors by type
agentgate_http_errors_total{status="400"} 100  # Bad request
agentgate_http_errors_total{status="401"} 200  # Unauthorized
agentgate_http_errors_total{status="403"} 500  # Forbidden
agentgate_http_errors_total{status="404"} 50   # Not found
agentgate_http_errors_total{status="500"} 10   # Server error
agentgate_http_errors_total{status="503"} 5    # Service unavailable

# Goroutine count (FastAPI worker health)
agentgate_goroutines_total{} 256
agentgate_goroutines_max{} 1000

# Memory usage
agentgate_process_memory_bytes{type="rss"} 536870912  # 512 MB
agentgate_process_memory_bytes{type="vms"} 1073741824 # 1 GB

# GC stats (garbage collection)
agentgate_gc_collections_total{generation="0"} 10000
agentgate_gc_collection_duration_seconds{generation="0"} histogram

# Uptime
agentgate_uptime_seconds{} 3456789  # 40 days
```

### Database Health

```prometheus
# Replication lag (PostgreSQL primary-replica)
agentgate_postgres_replication_lag_bytes{} 1024

# Slow queries
agentgate_slow_queries_total{duration_ms="100-500"} 150
agentgate_slow_queries_total{duration_ms="500+"} 10

# Table sizes
agentgate_postgres_table_size_bytes{table="audit_events"} 536870912  # 512 MB
agentgate_postgres_table_size_bytes{table="agent_credentials"} 1048576 # 1 MB

# Index bloat
agentgate_postgres_index_bloat_percent{index="idx_audit_events_created_at"} 5
```

### Redis Health

```prometheus
# Connected clients
agentgate_redis_connected_clients{} 45

# Commands executed
agentgate_redis_commands_total{command="GET"} 500000
agentgate_redis_commands_total{command="SET"} 100000
agentgate_redis_commands_total{command="INCR"} 150000

# Evictions
agentgate_redis_evictions_total{} 10000

# Memory stats
agentgate_redis_memory_used_bytes{} 534217728
agentgate_redis_memory_max_bytes{} 1073741824  # 1 GB
```

## Grafana Dashboard Configuration

### Dashboard 1: Overview

```json
{
  "dashboard": {
    "title": "AgentGate Overview",
    "panels": [
      {
        "title": "API Requests (per minute)",
        "targets": [
          {
            "expr": "rate(agentgate_http_requests_total[1m])",
            "legendFormat": "{{method}} {{endpoint}}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "API Latency (p95)",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, agentgate_http_request_duration_seconds)",
            "legendFormat": "{{endpoint}}"
          }
        ],
        "type": "graph",
        "thresholds": [0.1, 0.2]  # warn at 100ms, critical at 200ms
      },
      {
        "title": "Error Rate",
        "targets": [
          {
            "expr": "rate(agentgate_http_errors_total[5m]) / rate(agentgate_http_requests_total[5m])",
            "legendFormat": "Error rate"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Active Agents",
        "targets": [
          {
            "expr": "agentgate_agents_total{status='ACTIVE'}",
            "legendFormat": "Total active agents"
          }
        ],
        "type": "stat"
      },
      {
        "title": "Policy Violations (24h)",
        "targets": [
          {
            "expr": "increase(agentgate_policy_violations_total[24h])",
            "legendFormat": "{{policy}}"
          }
        ],
        "type": "stat"
      }
    ]
  }
}
```

### Dashboard 2: Security & Compliance

```json
{
  "dashboard": {
    "title": "Security & Compliance",
    "panels": [
      {
        "title": "Secret Requests by Decision",
        "targets": [
          {
            "expr": "agentgate_secret_requests_total",
            "legendFormat": "{{decision}}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Denied Access Attempts",
        "targets": [
          {
            "expr": "rate(agentgate_policy_evaluations_total{decision='DENY'}[5m])",
            "legendFormat": "{{policy}}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Token Validation Failures",
        "targets": [
          {
            "expr": "rate(agentgate_token_validation_failures_total[5m])",
            "legendFormat": "{{reason}}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Audit Events Logged (24h)",
        "targets": [
          {
            "expr": "increase(agentgate_audit_events_total[24h])"
          }
        ],
        "type": "stat"
      },
      {
        "title": "Secret Rotations Status",
        "targets": [
          {
            "expr": "agentgate_secret_rotations_total"
          }
        ],
        "type": "stat"
      }
    ]
  }
}
```

### Dashboard 3: Operational Health

```json
{
  "dashboard": {
    "title": "Operational Health",
    "panels": [
      {
        "title": "Database Connection Pool",
        "targets": [
          {
            "expr": "agentgate_db_connection_pool_size"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Cache Hit Rate",
        "targets": [
          {
            "expr": "agentgate_cache_hits_total / (agentgate_cache_hits_total + agentgate_cache_misses_total)"
          }
        ],
        "type": "gauge"
      },
      {
        "title": "Redis Memory Usage",
        "targets": [
          {
            "expr": "agentgate_redis_memory_used_bytes / 1024 / 1024"
          }
        ],
        "type": "gauge",
        "unit": "MB"
      },
      {
        "title": "PostgreSQL Table Sizes",
        "targets": [
          {
            "expr": "agentgate_postgres_table_size_bytes / 1024 / 1024"
          }
        ],
        "type": "graph",
        "unit": "MB"
      },
      {
        "title": "Process Memory Usage",
        "targets": [
          {
            "expr": "agentgate_process_memory_bytes / 1024 / 1024"
          }
        ],
        "type": "gauge",
        "unit": "MB"
      },
      {
        "title": "API Server Uptime",
        "targets": [
          {
            "expr": "agentgate_uptime_seconds / 3600"
          }
        ],
        "type": "stat",
        "unit": "hours"
      }
    ]
  }
}
```

## Alert Rules (Prometheus)

```yaml
# prometheus/rules.yml

groups:
  - name: agentgate_alerts
    interval: 30s
    rules:
      # Performance Alerts
      - alert: HighAPILatency
        expr: histogram_quantile(0.95, agentgate_http_request_duration_seconds) > 0.2
        for: 5m
        annotations:
          summary: "High API latency ({{ $value | humanize }}s p95)"
          dashboard: "http://grafana:3000/d/agentgate-overview"

      - alert: HighErrorRate
        expr: rate(agentgate_http_errors_total[5m]) > 0.01
        for: 5m
        annotations:
          summary: "High error rate ({{ $value | humanizePercentage }})"

      # Security Alerts
      - alert: PolicyViolationSpike
        expr: rate(agentgate_policy_violations_total[5m]) > 10
        for: 2m
        annotations:
          summary: "Spike in policy violations"
          action: "Check dashboard and audit logs"

      - alert: UnauthorizedAccessAttempt
        expr: rate(agentgate_token_validation_failures_total{reason='invalid_signature'}[5m]) > 5
        for: 5m
        annotations:
          summary: "Multiple token validation failures"

      - alert: SecretRotationFailed
        expr: agentgate_secret_rotations_total{status='failed'} > 0
        for: 15m
        annotations:
          summary: "Secret rotation failed"
          action: "Check secret backend connectivity"

      # Infrastructure Alerts
      - alert: DatabaseDown
        expr: agentgate_postgres_up == 0
        for: 1m
        annotations:
          summary: "PostgreSQL database is down"
          severity: "critical"

      - alert: DatabaseHighConnections
        expr: agentgate_db_connection_pool_size{status='active'} / 25 > 0.9
        for: 5m
        annotations:
          summary: "Database connection pool nearly exhausted"

      - alert: RedisMemoryHigh
        expr: agentgate_redis_memory_used_bytes / agentgate_redis_memory_max_bytes > 0.85
        for: 10m
        annotations:
          summary: "Redis memory usage high ({{ $value | humanizePercentage }})"

      - alert: CacheMissRateHigh
        expr: (agentgate_cache_misses_total / (agentgate_cache_hits_total + agentgate_cache_misses_total)) > 0.3
        for: 10m
        annotations:
          summary: "Cache miss rate is high ({{ $value | humanizePercentage }})"

      # Compliance Alerts
      - alert: AuditLogIngestionDelayed
        expr: time() - agentgate_last_audit_event_timestamp > 300
        for: 5m
        annotations:
          summary: "Audit log ingestion delayed ({{ $value }}s)"

      - alert: SecretsOverdueRotation
        expr: agentgate_secrets_overdue_rotation_total > 0
        for: 1h
        annotations:
          summary: "{{ $value }} secrets are overdue for rotation"
          action: "Rotate secrets immediately"
```

## Alerting Channels

### Slack Integration

```python
# agentgate/monitoring/slack_alerter.py

class SlackAlerter:
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def send_alert(self, alert_name, severity, message, dashboard_link):
        color = {
            "critical": "#FF0000",
            "warning": "#FFA500",
            "info": "#0080FF"
        }[severity]

        payload = {
            "attachments": [{
                "color": color,
                "title": f"{alert_name} ({severity})",
                "text": message,
                "actions": [{
                    "type": "button",
                    "text": "View Dashboard",
                    "url": dashboard_link
                }]
            }]
        }

        requests.post(self.webhook_url, json=payload)
```

### PagerDuty Integration

```python
# For critical alerts (database down, security breach)
import pdpyras

client = pdpyras.APISession(token=YOUR_PAGERDUTY_TOKEN)

event = {
    "routing_key": YOUR_INTEGRATION_KEY,
    "event_action": "trigger",
    "dedup_key": f"agentgate-{alert_name}",
    "payload": {
        "summary": "AgentGate critical alert",
        "severity": "critical",
        "source": "prometheus",
        "custom_details": {
            "alert": alert_name,
            "value": metric_value,
            "dashboard": dashboard_url
        }
    }
}

client.post("/events/v2/enqueue", json=event)
```

## Metrics Retention

- **Prometheus**: 15 days (high resolution, 15s scrape interval)
- **Long-term storage**: S3/GCS (via remote write)
  - 1 year retention for dashboards
  - 7 years for compliance/audit metrics
- **Audit logs**: PostgreSQL with archive to S3 after 90 days

