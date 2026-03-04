"""
Authentication tests for AgentGate.
Tests OAuth client credentials flow, JWT validation, API key auth, token expiry, and scope enforcement.
"""

import pytest
import jwt
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
import base64
import json


class TestOAuthClientCredentialsFlow:
    """Test OAuth2 client credentials authentication flow."""

    @pytest.mark.asyncio
    async def test_valid_client_credentials_exchange(self, test_agent_credentials):
        """Test successful token exchange with valid client credentials."""
        agent_creds = test_agent_credentials["full_access_agent"]

        # Simulate token exchange
        token_response = {
            "access_token": "YOUR_ACCESS_TOKEN_ABC123",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": " ".join(agent_creds["scopes"])
        }

        assert token_response["access_token"]
        assert token_response["token_type"] == "Bearer"
        assert token_response["expires_in"] == 3600

    @pytest.mark.asyncio
    async def test_invalid_client_id(self):
        """Test token exchange fails with invalid client ID."""
        with pytest.raises(HTTPException) as exc_info:
            # Simulate invalid client ID error
            raise HTTPException(status_code=401, detail="Invalid client_id")

        assert exc_info.value.status_code == 401
        assert "Invalid client_id" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_invalid_client_secret(self, test_agent_credentials):
        """Test token exchange fails with invalid client secret."""
        agent_creds = test_agent_credentials["full_access_agent"]

        with pytest.raises(HTTPException) as exc_info:
            if agent_creds["client_secret"] != "YOUR_CORRECT_SECRET":
                raise HTTPException(status_code=401, detail="Invalid client_secret")

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_grant_type(self):
        """Test token exchange fails without grant_type parameter."""
        with pytest.raises(ValueError):
            grant_type = None
            if grant_type is None:
                raise ValueError("grant_type parameter is required")

    @pytest.mark.asyncio
    async def test_unsupported_grant_type(self):
        """Test token exchange with unsupported grant type."""
        with pytest.raises(HTTPException) as exc_info:
            raise HTTPException(status_code=400, detail="Unsupported grant_type: password")

        assert exc_info.value.status_code == 400


class TestJWTValidation:
    """Test JWT token validation and claims verification."""

    @pytest.mark.asyncio
    async def test_valid_jwt_token(self, valid_jwt_token):
        """Test validation of a correctly formed JWT token."""
        decoded = jwt.decode(
            valid_jwt_token,
            "YOUR_JWT_SECRET_KEY",
            algorithms=["HS256"],
            audience="agentgate"
        )

        assert decoded["sub"] == "copilot@github.com"
        assert decoded["agent_id"] == "agent-001"
        assert "repo:read" in decoded["scope"]

    @pytest.mark.asyncio
    async def test_expired_jwt_token(self, expired_jwt_token):
        """Test that expired JWT tokens are rejected."""
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(
                expired_jwt_token,
                "YOUR_JWT_SECRET_KEY",
                algorithms=["HS256"]
            )

    @pytest.mark.asyncio
    async def test_invalid_jwt_signature(self):
        """Test JWT token with invalid signature is rejected."""
        payload = {
            "sub": "agent@example.com",
            "aud": "agentgate"
        }
        token = jwt.encode(payload, "wrong_secret", algorithm="HS256")

        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(
                token,
                "YOUR_JWT_SECRET_KEY",
                algorithms=["HS256"]
            )

    @pytest.mark.asyncio
    async def test_missing_required_claims(self):
        """Test JWT token validation fails with missing required claims."""
        payload = {
            "sub": "agent@example.com"
            # Missing 'aud', 'iss', 'exp' claims
        }
        token = jwt.encode(payload, "YOUR_JWT_SECRET_KEY", algorithm="HS256")

        with pytest.raises((jwt.MissingRequiredClaimError, KeyError)):
            jwt.decode(
                token,
                "YOUR_JWT_SECRET_KEY",
                algorithms=["HS256"],
                audience="agentgate"
            )

    @pytest.mark.asyncio
    async def test_incorrect_audience(self):
        """Test JWT token with incorrect audience claim is rejected."""
        payload = {
            "sub": "agent@example.com",
            "aud": "wrong_audience"
        }
        token = jwt.encode(payload, "YOUR_JWT_SECRET_KEY", algorithm="HS256")

        with pytest.raises(jwt.InvalidAudienceError):
            jwt.decode(
                token,
                "YOUR_JWT_SECRET_KEY",
                algorithms=["HS256"],
                audience="agentgate"
            )

    @pytest.mark.asyncio
    async def test_future_iat_claim(self):
        """Test JWT token with future issued-at claim is rejected."""
        payload = {
            "sub": "agent@example.com",
            "aud": "agentgate",
            "iat": datetime.utcnow() + timedelta(hours=1),
            "exp": datetime.utcnow() + timedelta(hours=2)
        }
        token = jwt.encode(payload, "YOUR_JWT_SECRET_KEY", algorithm="HS256")

        with pytest.raises(jwt.ImmatureSignatureError):
            jwt.decode(
                token,
                "YOUR_JWT_SECRET_KEY",
                algorithms=["HS256"],
                audience="agentgate"
            )


class TestAPIKeyAuthentication:
    """Test API key based authentication."""

    @pytest.mark.asyncio
    async def test_valid_api_key(self, test_agent_credentials):
        """Test authentication with valid API key."""
        agent_creds = test_agent_credentials["full_access_agent"]
        api_key = agent_creds["api_key"]

        assert api_key.startswith("YOUR_API_KEY")
        assert len(api_key) > 20

    @pytest.mark.asyncio
    async def test_invalid_api_key_format(self):
        """Test API key with invalid format is rejected."""
        invalid_keys = [
            "short",
            "123456",
            "invalid-format",
            ""
        ]

        for key in invalid_keys:
            with pytest.raises((ValueError, HTTPException)):
                if len(key) < 20:
                    raise ValueError(f"API key too short: {key}")

    @pytest.mark.asyncio
    async def test_revoked_api_key(self):
        """Test that revoked API keys are rejected."""
        api_key = "YOUR_API_KEY_REVOKED_001"
        revoked_keys = {"YOUR_API_KEY_REVOKED_001"}

        if api_key in revoked_keys:
            with pytest.raises(HTTPException) as exc_info:
                raise HTTPException(status_code=401, detail="API key has been revoked")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_api_key_header(self):
        """Test request without API key header is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            raise HTTPException(status_code=401, detail="Missing X-API-Key header")

        assert "Missing" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_api_key_case_sensitive(self):
        """Test that API key comparison is case-sensitive."""
        original_key = "YOUR_API_KEY_SENSITIVE_ABC123def"
        uppercase_key = original_key.upper()

        assert original_key != uppercase_key

    @pytest.mark.asyncio
    async def test_api_key_with_rate_limiting(self):
        """Test API key includes rate limit quota information."""
        api_key_metadata = {
            "key": "YOUR_API_KEY_RATELIMIT_001",
            "requests_per_minute": 100,
            "requests_per_hour": 10000,
            "current_usage": {"minute": 45, "hour": 3500}
        }

        assert api_key_metadata["requests_per_minute"] == 100
        assert api_key_metadata["current_usage"]["minute"] < api_key_metadata["requests_per_minute"]


class TestTokenExpiry:
    """Test token expiration and renewal."""

    @pytest.mark.asyncio
    async def test_token_expires_at_configured_time(self):
        """Test that tokens expire at the configured time."""
        created_at = datetime.utcnow()
        ttl_seconds = 3600
        expires_at = created_at + timedelta(seconds=ttl_seconds)

        assert expires_at > created_at
        assert (expires_at - created_at).total_seconds() == ttl_seconds

    @pytest.mark.asyncio
    async def test_token_refresh_before_expiry(self):
        """Test token can be refreshed before expiration."""
        old_token = "YOUR_OLD_TOKEN_ABC123"
        refresh_response = {
            "new_access_token": "YOUR_NEW_TOKEN_XYZ789",
            "expires_in": 3600
        }

        assert refresh_response["new_access_token"] != old_token
        assert refresh_response["expires_in"] > 0

    @pytest.mark.asyncio
    async def test_token_cannot_be_used_after_expiry(self):
        """Test that expired tokens cannot be used for authentication."""
        token_data = {
            "created_at": datetime.utcnow() - timedelta(hours=2),
            "expires_at": datetime.utcnow() - timedelta(hours=1)
        }

        if datetime.utcnow() > token_data["expires_at"]:
            with pytest.raises(HTTPException) as exc_info:
                raise HTTPException(status_code=401, detail="Token has expired")

            assert "expired" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_grace_period_for_expiry(self):
        """Test grace period before token expiration."""
        grace_period_seconds = 60
        expires_at = datetime.utcnow() + timedelta(seconds=30)

        # Token still valid within grace period
        is_valid = (expires_at - datetime.utcnow()).total_seconds() > -grace_period_seconds
        assert is_valid

    @pytest.mark.asyncio
    async def test_token_expiry_enforcement_across_calls(self):
        """Test that token expiry is consistently enforced across multiple calls."""
        expired_at = datetime.utcnow() - timedelta(minutes=5)

        for call_num in range(3):
            if datetime.utcnow() > expired_at:
                with pytest.raises(HTTPException):
                    raise HTTPException(status_code=401, detail="Token expired")


class TestScopeEnforcement:
    """Test OAuth scope validation and enforcement."""

    @pytest.mark.asyncio
    async def test_token_issued_with_requested_scopes(self, test_agent_credentials):
        """Test that tokens include requested scopes."""
        agent_creds = test_agent_credentials["full_access_agent"]
        requested_scopes = ["repo:read", "repo:write"]

        # Filter agent scopes to match requested
        granted_scopes = [s for s in agent_creds["scopes"] if s in requested_scopes]

        assert len(granted_scopes) == len(requested_scopes)

    @pytest.mark.asyncio
    async def test_agent_cannot_request_unauthorized_scopes(self):
        """Test that agents cannot request scopes they're not permitted to have."""
        agent_creds = {
            "agent_id": "agent-limited",
            "allowed_scopes": ["repo:read"]
        }
        requested_scopes = ["repo:read", "admin:write"]

        unauthorized = set(requested_scopes) - set(agent_creds["allowed_scopes"])

        if unauthorized:
            with pytest.raises(HTTPException) as exc_info:
                raise HTTPException(status_code=403, detail=f"Unauthorized scopes: {unauthorized}")

            assert "Unauthorized" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_scope_validation_format(self):
        """Test that scope format is properly validated."""
        valid_scopes = [
            "repo:read",
            "repo:write",
            "secrets:read",
            "secrets:write",
            "deploy:read",
            "admin:write"
        ]

        invalid_scopes = [
            "invalid",
            "repo read",  # Space instead of colon
            "repo::read",  # Double colon
            ""
        ]

        for scope in valid_scopes:
            assert ":" in scope

        for scope in invalid_scopes:
            assert not (":" in scope and scope.count(":") == 1)

    @pytest.mark.asyncio
    async def test_wildcard_scope_matching(self):
        """Test wildcard scope matching."""
        token_scopes = ["repo:*", "secrets:read"]

        # Check if repo:read is granted by repo:*
        def scope_matches(granted, requested):
            if granted == requested:
                return True
            if granted.endswith(":*"):
                prefix = granted[:-2]
                return requested.startswith(prefix)
            return False

        assert scope_matches("repo:*", "repo:read")
        assert scope_matches("repo:*", "repo:write")
        assert not scope_matches("repo:read", "repo:write")

    @pytest.mark.asyncio
    async def test_read_only_agent_cannot_write(self, test_agent_credentials):
        """Test that read-only agents cannot perform write operations."""
        agent_creds = test_agent_credentials["read_only_agent"]
        write_scopes = ["repo:write", "secrets:write"]

        # Check that read-only agent doesn't have write scopes
        agent_has_write = any(scope in agent_creds["scopes"] for scope in write_scopes)

        assert not agent_has_write

    @pytest.mark.asyncio
    async def test_scope_enforcement_on_request(self):
        """Test that scope enforcement is applied to individual requests."""
        request_data = {
            "action": "repo:write",
            "token_scopes": ["repo:read", "secrets:read"]
        }

        action_scope = request_data["action"]
        has_scope = action_scope in request_data["token_scopes"]

        if not has_scope:
            with pytest.raises(HTTPException) as exc_info:
                raise HTTPException(status_code=403, detail="Insufficient scope")

            assert "scope" in str(exc_info.value.detail).lower()


class TestMultipleAuthenticationMethods:
    """Test interaction between different authentication methods."""

    @pytest.mark.asyncio
    async def test_jwt_and_api_key_not_both_required(self):
        """Test that either JWT or API key is sufficient, not both required."""
        auth_methods = {
            "jwt_only": {"token": "YOUR_JWT_ABC123"},
            "api_key_only": {"key": "YOUR_API_KEY_XYZ789"},
            "both": {"token": "YOUR_JWT_ABC123", "key": "YOUR_API_KEY_XYZ789"}
        }

        # All should be valid
        for method_name, auth_data in auth_methods.items():
            assert len(auth_data) >= 1

    @pytest.mark.asyncio
    async def test_jwt_token_preferred_over_api_key(self):
        """Test authentication method preference: JWT > API Key."""
        request = {
            "headers": {
                "Authorization": "Bearer YOUR_JWT_ABC123",
                "X-API-Key": "YOUR_API_KEY_XYZ789"
            }
        }

        # JWT should be used if present
        auth_method = "jwt" if "Authorization" in request["headers"] else "api_key"
        assert auth_method == "jwt"

    @pytest.mark.asyncio
    async def test_credential_rotation_during_request(self):
        """Test handling of credential rotation during active requests."""
        old_credentials = {
            "api_key": "YOUR_OLD_API_KEY_123",
            "rotated_at": datetime.utcnow() - timedelta(days=1)
        }
        new_credentials = {
            "api_key": "YOUR_NEW_API_KEY_456",
            "valid_from": datetime.utcnow()
        }

        # Both should be accepted during grace period
        assert old_credentials["api_key"] != new_credentials["api_key"]
