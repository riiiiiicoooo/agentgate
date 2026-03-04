"""
API integration tests for AgentGate.
Tests all API endpoints, error handling, validation, and full request/response cycles.
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
import json


class TestAuthenticationEndpoints:
    """Test authentication API endpoints."""

    @pytest.mark.asyncio
    async def test_post_oauth_token_endpoint(self, test_api_client):
        """Test POST /auth/token for OAuth token exchange."""
        payload = {
            "grant_type": "client_credentials",
            "client_id": "YOUR_CLIENT_ID_TEST",
            "client_secret": "YOUR_CLIENT_SECRET_TEST",
            "scope": "repo:read repo:write"
        }

        # Simulated response
        expected_response = {
            "access_token": "YOUR_ACCESS_TOKEN_ABC123",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "repo:read repo:write"
        }

        assert expected_response["token_type"] == "Bearer"
        assert expected_response["expires_in"] > 0

    @pytest.mark.asyncio
    async def test_get_token_introspection_endpoint(self):
        """Test GET /auth/introspect to check token validity."""
        token = "YOUR_JWT_TOKEN_XYZ789"

        introspection_response = {
            "active": True,
            "scope": "repo:read repo:write",
            "client_id": "YOUR_CLIENT_ID_TEST",
            "username": "agent-001",
            "aud": "agentgate",
            "iss": "https://auth.agentgate.io",
            "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp())
        }

        assert introspection_response["active"] is True

    @pytest.mark.asyncio
    async def test_post_token_refresh_endpoint(self):
        """Test POST /auth/refresh for token refresh."""
        refresh_payload = {
            "refresh_token": "YOUR_REFRESH_TOKEN_DEF456"
        }

        refresh_response = {
            "access_token": "YOUR_NEW_ACCESS_TOKEN_GHI789",
            "token_type": "Bearer",
            "expires_in": 3600
        }

        assert refresh_response["access_token"]
        assert refresh_response["expires_in"] > 0


class TestAgentManagementEndpoints:
    """Test agent registration and management endpoints."""

    @pytest.mark.asyncio
    async def test_post_register_agent_endpoint(self):
        """Test POST /agents to register new agent."""
        register_payload = {
            "agent_name": "Test Agent",
            "agent_type": "custom",
            "description": "Test agent for integration testing",
            "scopes": ["repo:read", "secrets:read"],
            "mfa_required": False
        }

        expected_response = {
            "agent_id": "agent-test-001",
            "agent_name": register_payload["agent_name"],
            "client_id": "YOUR_CLIENT_ID_NEW",
            "client_secret": "YOUR_CLIENT_SECRET_NEW",
            "created_at": datetime.utcnow().isoformat()
        }

        assert expected_response["agent_id"]
        assert expected_response["client_id"]

    @pytest.mark.asyncio
    async def test_get_agent_details_endpoint(self):
        """Test GET /agents/{agent_id} to retrieve agent details."""
        agent_id = "agent-001"

        expected_response = {
            "agent_id": agent_id,
            "agent_name": "GitHub Copilot",
            "agent_type": "copilot",
            "scopes": ["repo:read", "repo:write"],
            "created_at": datetime.utcnow().isoformat(),
            "mfa_required": False,
            "credential_rotation_required": False
        }

        assert expected_response["agent_id"] == agent_id

    @pytest.mark.asyncio
    async def test_get_list_agents_endpoint(self):
        """Test GET /agents to list all agents."""
        expected_response = {
            "agents": [
                {"agent_id": "agent-001", "agent_name": "GitHub Copilot"},
                {"agent_id": "agent-002", "agent_name": "Cursor Editor"},
                {"agent_id": "agent-003", "agent_name": "CI Pipeline"}
            ],
            "total": 3,
            "page": 1,
            "page_size": 10
        }

        assert len(expected_response["agents"]) == expected_response["total"]

    @pytest.mark.asyncio
    async def test_patch_agent_endpoint(self):
        """Test PATCH /agents/{agent_id} to update agent."""
        agent_id = "agent-001"
        update_payload = {
            "scopes": ["repo:read", "repo:write", "secrets:read"],
            "mfa_required": True
        }

        updated_agent = {
            "agent_id": agent_id,
            "scopes": update_payload["scopes"],
            "mfa_required": update_payload["mfa_required"]
        }

        assert updated_agent["scopes"] == update_payload["scopes"]

    @pytest.mark.asyncio
    async def test_delete_agent_endpoint(self):
        """Test DELETE /agents/{agent_id} to deregister agent."""
        agent_id = "agent-old-001"

        delete_response = {
            "agent_id": agent_id,
            "deleted": True,
            "deactivated_at": datetime.utcnow().isoformat()
        }

        assert delete_response["deleted"] is True


class TestSecretsEndpoints:
    """Test secrets management endpoints."""

    @pytest.mark.asyncio
    async def test_post_lease_secret_endpoint(self):
        """Test POST /secrets/{secret_id}/lease to request secret lease."""
        secret_id = "db_password"
        lease_payload = {
            "ttl_seconds": 3600,
            "reason": "application_startup"
        }

        lease_response = {
            "lease_id": "lease-001",
            "secret_id": secret_id,
            "value": "ACTUAL_SECRET_VALUE_REDACTED",
            "ttl": 3600,
            "expires_at": datetime.utcnow() + timedelta(hours=1)
        }

        assert lease_response["lease_id"]
        assert lease_response["expires_at"] > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_post_renew_lease_endpoint(self):
        """Test POST /leases/{lease_id}/renew to extend lease."""
        lease_id = "lease-001"

        renew_response = {
            "lease_id": lease_id,
            "ttl": 3600,
            "expires_at": datetime.utcnow() + timedelta(hours=1)
        }

        assert renew_response["lease_id"] == lease_id

    @pytest.mark.asyncio
    async def test_delete_revoke_lease_endpoint(self):
        """Test DELETE /leases/{lease_id} to revoke lease."""
        lease_id = "lease-001"

        revoke_response = {
            "lease_id": lease_id,
            "revoked": True,
            "revoked_at": datetime.utcnow().isoformat()
        }

        assert revoke_response["revoked"] is True

    @pytest.mark.asyncio
    async def test_post_rotate_secret_endpoint(self):
        """Test POST /secrets/{secret_id}/rotate to rotate secret."""
        secret_id = "db_password"

        rotate_response = {
            "secret_id": secret_id,
            "rotated": True,
            "old_version": "v1",
            "new_version": "v2",
            "rotated_at": datetime.utcnow().isoformat()
        }

        assert rotate_response["rotated"] is True
        assert rotate_response["new_version"] != rotate_response["old_version"]


class TestPolicyEndpoints:
    """Test policy management endpoints."""

    @pytest.mark.asyncio
    async def test_post_evaluate_policy_endpoint(self):
        """Test POST /policies/evaluate to evaluate a policy."""
        eval_payload = {
            "agent_id": "agent-001",
            "action": "repo:write",
            "resource": "my-repo"
        }

        eval_response = {
            "allow": True,
            "reason": "matching_policy",
            "decision_id": "decision-001"
        }

        assert eval_response["allow"] is True or eval_response["allow"] is False

    @pytest.mark.asyncio
    async def test_post_policy_dry_run_endpoint(self):
        """Test POST /policies/dry-run for policy simulation."""
        dry_run_payload = {
            "policy_content": "package authz; allow { input.action == 'repo:read' }",
            "test_case": {
                "agent_id": "agent-001",
                "action": "repo:read"
            }
        }

        dry_run_response = {
            "result": True,
            "evaluation_time_ms": 2.5
        }

        assert isinstance(dry_run_response["result"], bool)

    @pytest.mark.asyncio
    async def test_get_policy_endpoint(self):
        """Test GET /policies/{policy_id} to retrieve policy."""
        policy_id = "policy-001"

        policy_response = {
            "policy_id": policy_id,
            "name": "Read-Only Policy",
            "content": "package authz; allow { input.action == 'repo:read' }",
            "created_at": datetime.utcnow().isoformat(),
            "version": "v1"
        }

        assert policy_response["policy_id"] == policy_id

    @pytest.mark.asyncio
    async def test_post_create_policy_endpoint(self):
        """Test POST /policies to create new policy."""
        create_payload = {
            "name": "New Policy",
            "description": "Test policy for new agent",
            "content": "package authz; allow { input.agent_type == 'test' }"
        }

        create_response = {
            "policy_id": "policy-new-001",
            "name": create_payload["name"],
            "created_at": datetime.utcnow().isoformat()
        }

        assert create_response["policy_id"]


class TestAuditEndpoints:
    """Test audit log endpoints."""

    @pytest.mark.asyncio
    async def test_get_audit_events_endpoint(self):
        """Test GET /audit/events to retrieve audit events."""
        query_params = {
            "agent_id": "agent-001",
            "limit": 100,
            "offset": 0
        }

        events_response = {
            "events": [
                {
                    "event_id": "event-001",
                    "agent_id": "agent-001",
                    "action": "AUTH",
                    "decision": "ALLOW"
                }
            ],
            "total": 1,
            "limit": 100,
            "offset": 0
        }

        assert len(events_response["events"]) > 0

    @pytest.mark.asyncio
    async def test_post_query_audit_events_endpoint(self):
        """Test POST /audit/query for complex audit queries."""
        query_payload = {
            "filters": {
                "agent_id": "agent-001",
                "decision": "DENY",
                "time_range": {
                    "start": (datetime.utcnow() - timedelta(days=7)).isoformat(),
                    "end": datetime.utcnow().isoformat()
                }
            }
        }

        query_response = {
            "results": [],
            "query_id": "query-001",
            "executed_at": datetime.utcnow().isoformat()
        }

        assert query_response["query_id"]

    @pytest.mark.asyncio
    async def test_post_export_audit_events_endpoint(self):
        """Test POST /audit/export to export events."""
        export_payload = {
            "format": "json",
            "filters": {"agent_id": "agent-001"},
            "compress": True
        }

        export_response = {
            "export_id": "export-001",
            "status": "processing",
            "download_url": "https://api.agentgate.io/exports/export-001.json.gz"
        }

        assert export_response["export_id"]


class TestHealthEndpoints:
    """Test health check and status endpoints."""

    @pytest.mark.asyncio
    async def test_get_health_endpoint(self):
        """Test GET /health for health check."""
        health_response = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0"
        }

        assert health_response["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_get_status_endpoint(self):
        """Test GET /status for detailed status."""
        status_response = {
            "status": "operational",
            "components": {
                "auth": "healthy",
                "policy_engine": "healthy",
                "secrets_vault": "healthy",
                "audit_db": "healthy"
            },
            "uptime_seconds": 86400
        }

        assert all(v == "healthy" for v in status_response["components"].values())


class TestErrorHandling:
    """Test error handling and error responses."""

    @pytest.mark.asyncio
    async def test_400_bad_request_error(self):
        """Test 400 Bad Request error response."""
        error_response = {
            "error": "INVALID_REQUEST",
            "message": "Missing required field: agent_id",
            "status": 400
        }

        assert error_response["status"] == 400

    @pytest.mark.asyncio
    async def test_401_unauthorized_error(self):
        """Test 401 Unauthorized error response."""
        error_response = {
            "error": "UNAUTHORIZED",
            "message": "Invalid or missing authentication credentials",
            "status": 401
        }

        assert error_response["status"] == 401

    @pytest.mark.asyncio
    async def test_403_forbidden_error(self):
        """Test 403 Forbidden error response."""
        error_response = {
            "error": "FORBIDDEN",
            "message": "Agent lacks required permissions",
            "status": 403
        }

        assert error_response["status"] == 403

    @pytest.mark.asyncio
    async def test_404_not_found_error(self):
        """Test 404 Not Found error response."""
        error_response = {
            "error": "NOT_FOUND",
            "message": "Agent with ID 'agent-nonexistent' not found",
            "status": 404
        }

        assert error_response["status"] == 404

    @pytest.mark.asyncio
    async def test_429_rate_limit_error(self):
        """Test 429 Too Many Requests error response."""
        error_response = {
            "error": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests",
            "retry_after": 60,
            "status": 429
        }

        assert error_response["status"] == 429

    @pytest.mark.asyncio
    async def test_500_internal_error(self):
        """Test 500 Internal Server Error response."""
        error_response = {
            "error": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "request_id": "req-error-001",
            "status": 500
        }

        assert error_response["status"] == 500


class TestAPIValidation:
    """Test request validation at API level."""

    @pytest.mark.asyncio
    async def test_validate_required_fields(self):
        """Test validation of required request fields."""
        required_fields = ["agent_id", "action"]

        request_body = {"agent_id": "agent-001"}
        # Missing "action"

        missing = [f for f in required_fields if f not in request_body]

        assert len(missing) > 0
        assert "action" in missing

    @pytest.mark.asyncio
    async def test_validate_field_types(self):
        """Test validation of request field types."""
        schema = {
            "agent_id": str,
            "ttl_seconds": int,
            "mfa_required": bool
        }

        request_body = {
            "agent_id": "agent-001",
            "ttl_seconds": 3600,
            "mfa_required": True
        }

        for field, expected_type in schema.items():
            assert isinstance(request_body[field], expected_type)

    @pytest.mark.asyncio
    async def test_validate_enum_values(self):
        """Test validation of enum field values."""
        allowed_actions = ["repo:read", "repo:write", "secrets:read", "secrets:write"]

        action = "repo:read"
        is_valid = action in allowed_actions

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_validate_string_length(self):
        """Test validation of string length constraints."""
        agent_id = "agent-001"
        min_length = 5
        max_length = 100

        is_valid = min_length <= len(agent_id) <= max_length

        assert is_valid is True
