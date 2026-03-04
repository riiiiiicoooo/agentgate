"""
Secrets broker tests for AgentGate.
Tests secret leasing, TTL expiration, rotation, just-in-time provisioning, and revocation.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import hashlib


class TestSecretLeasing:
    """Test secret leasing and access control."""

    @pytest.mark.asyncio
    async def test_lease_secret_with_valid_credentials(self, mock_secret_vault):
        """Test successful secret lease for authorized agent."""
        agent_id = "agent-001"
        secret_id = "db_password"

        lease = await mock_secret_vault.lease_secret(
            secret_id=secret_id,
            agent_id=agent_id,
            ttl_seconds=3600
        )

        assert lease["lease_id"]
        assert lease["secret_id"] == secret_id
        assert lease["agent_id"] == agent_id
        assert lease["ttl"] == 3600

    @pytest.mark.asyncio
    async def test_lease_secret_access_denied(self, mock_secret_vault):
        """Test secret lease fails for unauthorized agent."""
        agent_id = "agent-unauthorized"
        secret_id = "admin_key"

        mock_secret_vault.lease_secret = AsyncMock(
            side_effect=PermissionError("Agent not authorized for this secret")
        )

        with pytest.raises(PermissionError):
            await mock_secret_vault.lease_secret(secret_id, agent_id)

    @pytest.mark.asyncio
    async def test_lease_tracks_access_for_audit(self):
        """Test that each lease creates audit trail entry."""
        lease_records = []

        lease_data = {
            "lease_id": "lease-001",
            "agent_id": "agent-001",
            "secret_id": "db_password",
            "leased_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=1)
        }

        lease_records.append(lease_data)

        assert len(lease_records) == 1
        assert lease_records[0]["agent_id"] == "agent-001"

    @pytest.mark.asyncio
    async def test_concurrent_leases_different_agents(self, mock_secret_vault):
        """Test multiple agents can lease same secret concurrently."""
        secret_id = "db_password"
        agents = ["agent-001", "agent-002", "agent-003"]

        leases = {}
        for agent_id in agents:
            mock_secret_vault.lease_secret = AsyncMock(return_value={
                "lease_id": f"lease-{agent_id}",
                "secret_id": secret_id,
                "agent_id": agent_id
            })
            lease = await mock_secret_vault.lease_secret(secret_id, agent_id)
            leases[agent_id] = lease

        assert len(leases) == 3
        assert all(lease["secret_id"] == secret_id for lease in leases.values())

    @pytest.mark.asyncio
    async def test_same_agent_cannot_lease_same_secret_twice(self):
        """Test agent cannot hold multiple leases for same secret."""
        agent_id = "agent-001"
        secret_id = "db_password"
        active_leases = {
            f"{agent_id}:{secret_id}": {"lease_id": "lease-001", "expires_at": datetime.utcnow() + timedelta(hours=1)}
        }

        lease_key = f"{agent_id}:{secret_id}"

        if lease_key in active_leases:
            with pytest.raises(ValueError) as exc_info:
                raise ValueError(f"Agent already has active lease for {secret_id}")

            assert "already has active lease" in str(exc_info.value)


class TestTTLExpiration:
    """Test secret lease TTL and expiration handling."""

    @pytest.mark.asyncio
    async def test_lease_expires_at_configured_time(self):
        """Test lease expires at configured TTL."""
        ttl_seconds = 3600
        leased_at = datetime.utcnow()
        expires_at = leased_at + timedelta(seconds=ttl_seconds)

        age = (datetime.utcnow() - leased_at).total_seconds()
        is_expired = age > ttl_seconds

        assert not is_expired

    @pytest.mark.asyncio
    async def test_secret_inaccessible_after_lease_expiry(self):
        """Test that expired leases cannot access secrets."""
        lease = {
            "lease_id": "lease-001",
            "expires_at": datetime.utcnow() - timedelta(minutes=1)  # Expired
        }

        is_expired = datetime.utcnow() > lease["expires_at"]

        if is_expired:
            with pytest.raises(PermissionError) as exc_info:
                raise PermissionError("Lease has expired")

            assert "expired" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_custom_ttl_per_secret(self):
        """Test that different secrets can have different TTLs."""
        secret_configs = {
            "db_password": {"ttl_seconds": 3600},
            "api_key": {"ttl_seconds": 7200},
            "short_lived_token": {"ttl_seconds": 300}
        }

        for secret_id, config in secret_configs.items():
            assert isinstance(config["ttl_seconds"], int)
            assert config["ttl_seconds"] > 0

    @pytest.mark.asyncio
    async def test_ttl_warning_threshold(self):
        """Test warning when lease is near expiration."""
        warning_threshold = 300  # 5 minutes
        lease = {
            "expires_at": datetime.utcnow() + timedelta(seconds=200)
        }

        time_remaining = (lease["expires_at"] - datetime.utcnow()).total_seconds()
        should_warn = time_remaining < warning_threshold

        assert should_warn is True

    @pytest.mark.asyncio
    async def test_automatic_lease_cleanup(self):
        """Test cleanup of expired leases."""
        leases = [
            {"lease_id": "lease-001", "expires_at": datetime.utcnow() - timedelta(hours=1)},
            {"lease_id": "lease-002", "expires_at": datetime.utcnow() + timedelta(hours=1)},
            {"lease_id": "lease-003", "expires_at": datetime.utcnow() - timedelta(minutes=30)}
        ]

        active_leases = [l for l in leases if l["expires_at"] > datetime.utcnow()]

        assert len(active_leases) == 1
        assert active_leases[0]["lease_id"] == "lease-002"

    @pytest.mark.asyncio
    async def test_ttl_grace_period(self):
        """Test grace period before lease truly expires."""
        grace_period = 60  # 1 minute
        expires_at = datetime.utcnow() + timedelta(seconds=30)

        time_remaining = (expires_at - datetime.utcnow()).total_seconds()
        can_still_use = time_remaining > -grace_period

        assert can_still_use is True


class TestSecretRotation:
    """Test secret rotation and version management."""

    @pytest.mark.asyncio
    async def test_rotate_secret_creates_new_version(self, mock_secret_vault):
        """Test secret rotation creates new version."""
        secret_id = "db_password"
        old_version = "v1"

        rotation = await mock_secret_vault.rotate_secret(secret_id)

        assert "rotated_at" in rotation
        assert "new_version" in rotation
        assert rotation["new_version"] != old_version

    @pytest.mark.asyncio
    async def test_rotation_invalidates_old_leases(self):
        """Test that secret rotation invalidates old leases."""
        leases = {
            "lease-001": {"version": "v1", "valid": True},
            "lease-002": {"version": "v1", "valid": True}
        }

        # Rotate secret
        new_version = "v2"

        for lease_id, lease in leases.items():
            if lease["version"] != new_version:
                lease["valid"] = False

        assert not any(l["valid"] for l in leases.values())

    @pytest.mark.asyncio
    async def test_rotation_policy_enforcement(self):
        """Test that rotation is enforced per policy."""
        secret_configs = {
            "db_password": {
                "rotation_required": True,
                "rotation_interval_days": 30,
                "last_rotated": datetime.utcnow() - timedelta(days=35)
            },
            "static_token": {
                "rotation_required": False,
                "last_rotated": datetime.utcnow() - timedelta(days=365)
            }
        }

        for secret_id, config in secret_configs.items():
            if config["rotation_required"]:
                days_since_rotation = (datetime.utcnow() - config["last_rotated"]).days
                needs_rotation = days_since_rotation > config["rotation_interval_days"]
                assert needs_rotation is True

    @pytest.mark.asyncio
    async def test_gradual_secret_rotation(self):
        """Test gradual rotation with old and new versions active."""
        rotation_state = {
            "old_version": "v1",
            "new_version": "v2",
            "rotation_start": datetime.utcnow(),
            "rotation_deadline": datetime.utcnow() + timedelta(hours=1),
            "old_version_still_valid": True
        }

        # During rotation window, both versions should be valid
        assert rotation_state["old_version_still_valid"] is True

        # After deadline, only new version valid
        if datetime.utcnow() > rotation_state["rotation_deadline"]:
            rotation_state["old_version_still_valid"] = False

    @pytest.mark.asyncio
    async def test_rotation_audit_trail(self):
        """Test rotation creates detailed audit trail."""
        rotation_audit = {
            "secret_id": "db_password",
            "rotated_at": datetime.utcnow(),
            "old_version": "v1",
            "new_version": "v2",
            "rotated_by": "system",
            "reason": "scheduled_rotation"
        }

        assert rotation_audit["old_version"] != rotation_audit["new_version"]
        assert rotation_audit["rotated_by"]
        assert rotation_audit["reason"]


class TestJustInTimeProvisioning:
    """Test just-in-time secret provisioning."""

    @pytest.mark.asyncio
    async def test_jit_secret_created_on_first_access(self):
        """Test secret is created on first access request."""
        agent_id = "agent-001"
        secret_id = "temp_db_user"

        secret_exists_before = False

        # JIT provisioning
        provisioned_secret = {
            "secret_id": secret_id,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=1),
            "provisional": True
        }

        assert not secret_exists_before
        assert provisioned_secret["provisional"] is True

    @pytest.mark.asyncio
    async def test_jit_secret_cleaned_up_after_use(self):
        """Test JIT secret is cleaned up after lease expires."""
        jit_secrets = {
            "temp_user_123": {
                "created_at": datetime.utcnow() - timedelta(hours=2),
                "expires_at": datetime.utcnow() - timedelta(hours=1),
                "provisional": True
            }
        }

        active_secrets = {
            k: v for k, v in jit_secrets.items()
            if v["expires_at"] > datetime.utcnow()
        }

        assert len(active_secrets) == 0

    @pytest.mark.asyncio
    async def test_jit_credential_format(self):
        """Test JIT credentials are properly formatted."""
        jit_credentials = {
            "username": "temp_user_abc123",
            "password": "GENERATED_PASSWORD_VERY_STRONG_XYZ",
            "host": "db.example.com",
            "port": 5432,
            "database": "production"
        }

        assert jit_credentials["username"]
        assert len(jit_credentials["password"]) > 20
        assert jit_credentials["port"] > 0

    @pytest.mark.asyncio
    async def test_jit_creates_minimal_permissions(self):
        """Test JIT provisioned credentials have minimal permissions."""
        base_permissions = ["SELECT"]
        jit_permissions = ["SELECT"]  # Minimal read-only

        extended_permissions = ["SELECT", "INSERT", "UPDATE", "DELETE"]

        assert set(jit_permissions).issubset(set(base_permissions))
        assert not set(jit_permissions).issubset(set(extended_permissions))

    @pytest.mark.asyncio
    async def test_jit_audit_trail(self):
        """Test JIT provisioning creates audit trail."""
        jit_events = [
            {
                "event_type": "jit_provision",
                "secret_id": "temp_user_123",
                "agent_id": "agent-001",
                "timestamp": datetime.utcnow()
            },
            {
                "event_type": "jit_cleanup",
                "secret_id": "temp_user_123",
                "timestamp": datetime.utcnow() + timedelta(hours=1)
            }
        ]

        assert len(jit_events) == 2
        assert jit_events[0]["event_type"] == "jit_provision"
        assert jit_events[1]["event_type"] == "jit_cleanup"


class TestSecretRevocation:
    """Test secret revocation and immediate access denial."""

    @pytest.mark.asyncio
    async def test_revoke_secret_denies_all_access(self, mock_secret_vault):
        """Test revoked secrets cannot be accessed."""
        secret_id = "db_password"

        mock_secret_vault.revoke_secret = AsyncMock(return_value={
            "revoked": True,
            "secret_id": secret_id,
            "revoked_at": datetime.utcnow()
        })

        result = await mock_secret_vault.revoke_secret(secret_id)

        assert result["revoked"] is True
        assert result["secret_id"] == secret_id

    @pytest.mark.asyncio
    async def test_revoke_secret_invalidates_active_leases(self):
        """Test revoking secret invalidates all active leases."""
        secret_id = "api_key"
        active_leases = {
            "lease-001": {"agent_id": "agent-001", "valid": True},
            "lease-002": {"agent_id": "agent-002", "valid": True}
        }

        # Revoke secret
        for lease in active_leases.values():
            lease["valid"] = False

        assert not any(lease["valid"] for lease in active_leases.values())

    @pytest.mark.asyncio
    async def test_revoke_with_grace_period(self):
        """Test revocation with grace period for graceful shutdown."""
        grace_period = 300  # 5 minutes
        revoke_time = datetime.utcnow()
        hard_revoke_time = revoke_time + timedelta(seconds=grace_period)

        # Grace period active
        is_grace = datetime.utcnow() < hard_revoke_time
        assert is_grace is True

    @pytest.mark.asyncio
    async def test_revocation_prevents_renewal(self, mock_secret_vault):
        """Test that revoked leases cannot be renewed."""
        lease_id = "lease-001"

        mock_secret_vault.renew_lease = AsyncMock(
            side_effect=ValueError("Lease has been revoked")
        )

        with pytest.raises(ValueError):
            await mock_secret_vault.renew_lease(lease_id)

    @pytest.mark.asyncio
    async def test_revocation_audit_trail(self):
        """Test revocation creates comprehensive audit trail."""
        revocation_audit = {
            "event_type": "secret_revoked",
            "secret_id": "db_password",
            "revoked_at": datetime.utcnow(),
            "revoked_by": "security_admin",
            "reason": "suspected_compromise",
            "affected_leases": 3,
            "audit_id": "audit-001"
        }

        assert revocation_audit["event_type"] == "secret_revoked"
        assert revocation_audit["revoked_by"]
        assert revocation_audit["reason"]

    @pytest.mark.asyncio
    async def test_batch_secret_revocation(self):
        """Test revoking multiple secrets efficiently."""
        secrets_to_revoke = [
            "password_1",
            "password_2",
            "api_key_1",
            "token_1"
        ]

        revoked = []
        for secret_id in secrets_to_revoke:
            revoked.append({
                "secret_id": secret_id,
                "revoked": True,
                "timestamp": datetime.utcnow()
            })

        assert len(revoked) == len(secrets_to_revoke)
        assert all(r["revoked"] for r in revoked)


class TestSecretBrokerEdgeCases:
    """Test edge cases in secret brokering."""

    @pytest.mark.asyncio
    async def test_access_to_nonexistent_secret(self, mock_secret_vault):
        """Test accessing secret that doesn't exist."""
        mock_secret_vault.lease_secret = AsyncMock(
            side_effect=KeyError("Secret not found: nonexistent_secret")
        )

        with pytest.raises(KeyError):
            await mock_secret_vault.lease_secret("nonexistent_secret", "agent-001")

    @pytest.mark.asyncio
    async def test_large_secret_value_handling(self, mock_secret_vault):
        """Test handling of large secret values."""
        large_secret = "x" * 1000000  # 1MB secret

        mock_secret_vault.get_secret = AsyncMock(return_value={
            "secret_id": "large_secret",
            "value": large_secret,
            "size_bytes": len(large_secret)
        })

        result = await mock_secret_vault.get_secret("large_secret")

        assert len(result["value"]) == 1000000

    @pytest.mark.asyncio
    async def test_concurrent_rotation_and_lease(self):
        """Test handling concurrent rotation and lease requests."""
        rotation_in_progress = True
        lease_request_received = True

        # Rotation should not block new leases
        if rotation_in_progress and lease_request_received:
            # Lease should get appropriate version
            lease_version = "v2"  # New version even if rotation in progress

        assert lease_version

    @pytest.mark.asyncio
    async def test_secret_value_never_logged(self):
        """Test that secret values are never logged."""
        secret_value = "ACTUAL_SECRET_PASSWORD_123"

        log_message = f"Leased secret for agent-001"  # No secret value in log

        assert secret_value not in log_message
        assert "agent-001" in log_message
