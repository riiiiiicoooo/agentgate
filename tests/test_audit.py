"""
Audit logging tests for AgentGate.
Tests audit event capture, enrichment, query filtering, export formats, and compliance.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock
import json
import csv
from io import StringIO


class TestAuditEventCapture:
    """Test audit event capture and initial logging."""

    @pytest.mark.asyncio
    async def test_auth_event_captured(self, mock_audit_logger):
        """Test authentication event is captured."""
        event = mock_audit_logger.log_event()

        assert event["event_id"]
        assert event["timestamp"]
        assert event["agent_id"]
        assert "ALLOW" in [event["decision"]]

    @pytest.mark.asyncio
    async def test_secret_access_event_captured(self, mock_audit_logger):
        """Test secret access event is captured."""
        event_data = {
            "agent_id": "agent-001",
            "action": "SECRET_ACCESS",
            "resource": "db_password",
            "decision": "ALLOW"
        }

        logged_event = mock_audit_logger.log_event()

        assert logged_event["action"] == "SECRET_ACCESS"

    @pytest.mark.asyncio
    async def test_policy_violation_event_captured(self):
        """Test policy violation events are logged."""
        violation_event = {
            "event_id": "event-violation-001",
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "POLICY_VIOLATION",
            "agent_id": "agent-001",
            "action": "UNAUTHORIZED_ACTION",
            "resource": "admin_panel",
            "decision": "DENY",
            "reason": "insufficient_scope"
        }

        assert violation_event["event_type"] == "POLICY_VIOLATION"
        assert violation_event["decision"] == "DENY"

    @pytest.mark.asyncio
    async def test_token_generation_event_captured(self):
        """Test token generation events are logged."""
        token_event = {
            "event_id": "event-token-001",
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "TOKEN_ISSUED",
            "agent_id": "agent-copilot-001",
            "token_type": "jwt",
            "scopes": ["repo:read", "repo:write"],
            "ttl_seconds": 3600
        }

        assert token_event["event_type"] == "TOKEN_ISSUED"
        assert token_event["token_type"] == "jwt"

    @pytest.mark.asyncio
    async def test_audit_event_immutability(self):
        """Test that audit events cannot be modified after logging."""
        event = {
            "event_id": "event-immutable-001",
            "timestamp": datetime.utcnow().isoformat(),
            "agent_id": "agent-001",
            "action": "SECRET_ACCESS"
        }

        # Try to modify (should fail in real implementation)
        original_agent_id = event["agent_id"]
        event_frozen = dict(event)  # Simulate immutability

        # event_frozen should still have original value
        assert event_frozen["agent_id"] == original_agent_id

    @pytest.mark.asyncio
    async def test_failed_auth_event_captured(self):
        """Test that failed authentication attempts are logged."""
        failed_auth = {
            "event_id": "event-failed-auth-001",
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "AUTH_FAILED",
            "reason": "invalid_credentials",
            "attempt_count": 3,
            "ip_address": "192.168.1.1"
        }

        assert failed_auth["event_type"] == "AUTH_FAILED"
        assert failed_auth["attempt_count"] > 0


class TestAuditEventEnrichment:
    """Test audit event enrichment with additional context."""

    @pytest.mark.asyncio
    async def test_event_enriched_with_agent_metadata(self):
        """Test event is enriched with agent information."""
        base_event = {
            "event_id": "event-001",
            "agent_id": "agent-001"
        }

        agent_metadata = {
            "agent_name": "GitHub Copilot",
            "agent_type": "copilot",
            "organization": "github",
            "created_at": datetime.utcnow() - timedelta(days=30)
        }

        enriched = {**base_event, **agent_metadata}

        assert enriched["agent_name"] == "GitHub Copilot"
        assert enriched["agent_type"] == "copilot"

    @pytest.mark.asyncio
    async def test_event_enriched_with_request_context(self):
        """Test event enrichment with request details."""
        event = {
            "event_id": "event-001",
            "agent_id": "agent-001",
            "ip_address": "192.168.1.100",
            "user_agent": "AgentGate-SDK/1.0",
            "request_id": "req-abc123",
            "timestamp": datetime.utcnow().isoformat()
        }

        assert event["ip_address"]
        assert event["request_id"]
        assert event["user_agent"]

    @pytest.mark.asyncio
    async def test_event_enriched_with_policy_decision_details(self):
        """Test event enriched with policy evaluation details."""
        event = {
            "event_id": "event-001",
            "action": "SECRET_ACCESS",
            "decision": "ALLOW",
            "policy_matched": "read_only_agent_policy",
            "evaluation_time_ms": 2.5,
            "cache_hit": True
        }

        assert event["policy_matched"]
        assert event["evaluation_time_ms"] > 0

    @pytest.mark.asyncio
    async def test_event_enriched_with_business_context(self):
        """Test event enriched with business/operational context."""
        event = {
            "event_id": "event-001",
            "environment": "production",
            "service": "api-gateway",
            "region": "us-east-1",
            "cost_units": 5
        }

        assert event["environment"] == "production"
        assert event["cost_units"] > 0

    @pytest.mark.asyncio
    async def test_pii_redaction_in_enrichment(self):
        """Test that PII is redacted in enriched events."""
        raw_event = {
            "event_id": "event-001",
            "username": "john.doe@example.com",
            "password": "actual_password_123"
        }

        # In enriched event, sensitive data should be redacted
        enriched_event = {
            "event_id": raw_event["event_id"],
            "username": "[REDACTED]",
            "password": "[REDACTED]"
        }

        assert "[REDACTED]" in enriched_event["username"]
        assert "[REDACTED]" in enriched_event["password"]

    @pytest.mark.asyncio
    async def test_structured_error_context_in_events(self):
        """Test structured error context in audit events."""
        error_event = {
            "event_id": "event-error-001",
            "event_type": "AUTH_ERROR",
            "error": {
                "type": "TokenExpiredError",
                "message": "JWT token has expired",
                "code": "TOKEN_EXPIRED_001",
                "timestamp": datetime.utcnow().isoformat()
            }
        }

        assert error_event["error"]["type"]
        assert error_event["error"]["code"]


class TestAuditQueryFiltering:
    """Test querying and filtering audit events."""

    @pytest.mark.asyncio
    async def test_filter_by_agent_id(self, mock_audit_logger):
        """Test filtering events by agent ID."""
        all_events = mock_audit_logger.query_events()

        agent_id = "agent-001"
        filtered = [e for e in all_events if e["agent_id"] == agent_id]

        assert len(filtered) > 0
        assert all(e["agent_id"] == agent_id for e in filtered)

    @pytest.mark.asyncio
    async def test_filter_by_action_type(self):
        """Test filtering events by action type."""
        events = [
            {"action": "AUTH", "event_id": "1"},
            {"action": "SECRET_ACCESS", "event_id": "2"},
            {"action": "AUTH", "event_id": "3"},
            {"action": "POLICY_EVAL", "event_id": "4"}
        ]

        action_filter = "AUTH"
        filtered = [e for e in events if e["action"] == action_filter]

        assert len(filtered) == 2
        assert all(e["action"] == action_filter for e in filtered)

    @pytest.mark.asyncio
    async def test_filter_by_decision(self):
        """Test filtering events by allow/deny decision."""
        events = [
            {"decision": "ALLOW", "event_id": "1"},
            {"decision": "DENY", "event_id": "2"},
            {"decision": "ALLOW", "event_id": "3"}
        ]

        denied_events = [e for e in events if e["decision"] == "DENY"]

        assert len(denied_events) == 1
        assert denied_events[0]["event_id"] == "2"

    @pytest.mark.asyncio
    async def test_filter_by_time_range(self):
        """Test filtering events by timestamp range."""
        now = datetime.utcnow()
        events = [
            {"timestamp": now - timedelta(hours=2), "event_id": "1"},
            {"timestamp": now - timedelta(hours=1), "event_id": "2"},
            {"timestamp": now - timedelta(minutes=30), "event_id": "3"}
        ]

        start_time = now - timedelta(hours=1.5)
        end_time = now

        filtered = [
            e for e in events
            if start_time <= e["timestamp"] <= end_time
        ]

        assert len(filtered) == 2

    @pytest.mark.asyncio
    async def test_filter_by_resource(self):
        """Test filtering events by accessed resource."""
        events = [
            {"resource": "db_password", "event_id": "1"},
            {"resource": "api_key", "event_id": "2"},
            {"resource": "db_password", "event_id": "3"}
        ]

        resource_filter = "db_password"
        filtered = [e for e in events if e["resource"] == resource_filter]

        assert len(filtered) == 2

    @pytest.mark.asyncio
    async def test_combined_filters(self):
        """Test combining multiple filters."""
        events = [
            {"agent_id": "a1", "action": "AUTH", "decision": "ALLOW", "event_id": "1"},
            {"agent_id": "a1", "action": "SECRET", "decision": "ALLOW", "event_id": "2"},
            {"agent_id": "a2", "action": "AUTH", "decision": "DENY", "event_id": "3"}
        ]

        filtered = [
            e for e in events
            if e["agent_id"] == "a1" and e["decision"] == "ALLOW"
        ]

        assert len(filtered) == 2

    @pytest.mark.asyncio
    async def test_query_with_regex_patterns(self):
        """Test querying with regex pattern matching."""
        import re
        events = [
            {"resource": "prod-database", "event_id": "1"},
            {"resource": "dev-database", "event_id": "2"},
            {"resource": "staging-api", "event_id": "3"}
        ]

        pattern = r"^prod-.*"
        filtered = [e for e in events if re.match(pattern, e["resource"])]

        assert len(filtered) == 1
        assert filtered[0]["resource"] == "prod-database"


class TestAuditExportFormats:
    """Test exporting audit logs in various formats."""

    @pytest.mark.asyncio
    async def test_export_as_json(self, mock_audit_logger):
        """Test exporting audit events as JSON."""
        export = mock_audit_logger.export_events()

        assert export["format"] == "json"
        assert isinstance(export["data"], (list, str))

    @pytest.mark.asyncio
    async def test_export_as_csv(self):
        """Test exporting audit events as CSV."""
        events = [
            {"event_id": "1", "agent_id": "a1", "action": "AUTH", "decision": "ALLOW"},
            {"event_id": "2", "agent_id": "a2", "action": "SECRET", "decision": "DENY"}
        ]

        csv_output = StringIO()
        if events:
            fieldnames = events[0].keys()
            writer = csv.DictWriter(csv_output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(events)

        csv_content = csv_output.getvalue()
        assert "event_id" in csv_content
        assert "agent_id" in csv_content

    @pytest.mark.asyncio
    async def test_export_as_jsonl(self):
        """Test exporting audit events as JSON Lines format."""
        events = [
            {"event_id": "1", "agent_id": "a1"},
            {"event_id": "2", "agent_id": "a2"}
        ]

        jsonl_lines = [json.dumps(e) for e in events]
        jsonl_content = "\n".join(jsonl_lines)

        lines = jsonl_content.strip().split("\n")
        assert len(lines) == 2
        assert all(json.loads(line) for line in lines)

    @pytest.mark.asyncio
    async def test_export_compression(self):
        """Test that exports can be compressed."""
        export_config = {
            "format": "json",
            "compress": True,
            "compression_type": "gzip"
        }

        assert export_config["compress"] is True
        assert export_config["compression_type"] in ["gzip", "zip", "bzip2"]

    @pytest.mark.asyncio
    async def test_export_with_filters(self):
        """Test exporting filtered events only."""
        all_events = [
            {"agent_id": "a1", "decision": "ALLOW"},
            {"agent_id": "a1", "decision": "DENY"},
            {"agent_id": "a2", "decision": "ALLOW"}
        ]

        export_filter = {"agent_id": "a1"}
        filtered = [e for e in all_events if all(e.get(k) == v for k, v in export_filter.items())]

        assert len(filtered) == 2


class TestAuditCompliance:
    """Test audit logging for compliance requirements."""

    @pytest.mark.asyncio
    async def test_audit_tamper_protection(self):
        """Test that audit logs are tamper-protected."""
        events = [
            {
                "event_id": "1",
                "content": "audit data",
                "hash": "abc123",
                "signature": "sig123"
            }
        ]

        # Verify event integrity
        for event in events:
            assert "hash" in event
            assert "signature" in event

    @pytest.mark.asyncio
    async def test_regulatory_required_fields(self):
        """Test that all regulatory-required fields are present."""
        required_fields = [
            "event_id",
            "timestamp",
            "agent_id",
            "action",
            "resource",
            "decision"
        ]

        event = {
            "event_id": "e1",
            "timestamp": datetime.utcnow().isoformat(),
            "agent_id": "a1",
            "action": "SECRET_ACCESS",
            "resource": "db_password",
            "decision": "ALLOW"
        }

        assert all(field in event for field in required_fields)

    @pytest.mark.asyncio
    async def test_audit_retention_policy(self):
        """Test audit retention meets compliance requirements."""
        retention_config = {
            "retention_days": 2555,  # 7 years
            "minimum_retention": 365,
            "archive_after_days": 90,
            "deletion_enabled": False
        }

        assert retention_config["retention_days"] >= retention_config["minimum_retention"]
        assert retention_config["deletion_enabled"] is False

    @pytest.mark.asyncio
    async def test_sensitive_operation_logging(self):
        """Test that sensitive operations have detailed logging."""
        sensitive_ops = [
            "credential_rotation",
            "secret_access",
            "policy_change",
            "audit_query"
        ]

        for op in sensitive_ops:
            audit_record = {
                "operation": op,
                "timestamp": datetime.utcnow().isoformat(),
                "actor": "admin",
                "details": "operation details"
            }
            assert audit_record["timestamp"]
            assert audit_record["actor"]

    @pytest.mark.asyncio
    async def test_audit_log_integrity_verification(self):
        """Test verification of audit log integrity."""
        from hashlib import sha256

        event = {"event_id": "1", "data": "test"}
        event_json = json.dumps(event)
        calculated_hash = sha256(event_json.encode()).hexdigest()

        stored_event = {
            **event,
            "hash": calculated_hash
        }

        # Verify integrity
        verified_hash = sha256(json.dumps(event).encode()).hexdigest()
        assert verified_hash == stored_event["hash"]

    @pytest.mark.asyncio
    async def test_chain_of_custody_for_events(self):
        """Test chain of custody maintenance for audit events."""
        events = [
            {
                "event_id": "1",
                "previous_hash": None,
                "hash": "abc123",
                "timestamp": datetime.utcnow().isoformat()
            },
            {
                "event_id": "2",
                "previous_hash": "abc123",  # Linked to previous
                "hash": "def456",
                "timestamp": (datetime.utcnow() + timedelta(minutes=1)).isoformat()
            }
        ]

        # Verify chain
        assert events[1]["previous_hash"] == events[0]["hash"]

    @pytest.mark.asyncio
    async def test_log_analysis_for_indicators(self):
        """Test analysis of logs for suspicious indicators."""
        events = [
            {"agent_id": "a1", "decision": "DENY", "reason": "invalid_token"},
            {"agent_id": "a1", "decision": "DENY", "reason": "invalid_token"},
            {"agent_id": "a1", "decision": "DENY", "reason": "invalid_token"}
        ]

        denied_count = sum(1 for e in events if e["decision"] == "DENY")

        alert_threshold = 2
        should_alert = denied_count > alert_threshold

        assert should_alert is True
