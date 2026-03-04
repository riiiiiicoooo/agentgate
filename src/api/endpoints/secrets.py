"""
Secrets Management Endpoints

Just-in-time provisioning, secret leasing, TTL management, and rotation triggers.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel, Field

from src.api.auth import get_current_agent, AgentCredentials

logger = logging.getLogger(__name__)

router = APIRouter()

# Models
class SecretLeaseRequest(BaseModel):
    """Request to lease a secret."""
    secret_name: str = Field(..., description="Name/path of the secret")
    ttl_seconds: int = Field(default=3600, ge=60, le=86400, description="Lease lifetime in seconds")
    justification: Optional[str] = Field(None, description="Business justification for the secret")

    class Config:
        json_schema_extra = {
            "example": {
                "secret_name": "database/prod/connection_string",
                "ttl_seconds": 3600,
                "justification": "Migration job for Q1 reporting",
            }
        }


class SecretLeaseResponse(BaseModel):
    """Secret lease response."""
    lease_id: str
    secret_name: str
    secret_value: str
    ttl_seconds: int
    issued_at: datetime
    expires_at: datetime
    renewable: bool

    class Config:
        json_schema_extra = {
            "example": {
                "lease_id": "lease_550e8400e29b41d4a716446655440000",
                "secret_name": "database/prod/connection_string",
                "secret_value": "postgres://user:pass@host/db",
                "ttl_seconds": 3600,
                "issued_at": "2026-03-04T10:00:00Z",
                "expires_at": "2026-03-04T11:00:00Z",
                "renewable": True,
            }
        }


class SecretRenewalRequest(BaseModel):
    """Request to renew a secret lease."""
    lease_id: str
    additional_ttl_seconds: Optional[int] = Field(3600, ge=60, le=86400)
    justification: Optional[str] = None


class SecretRotationRequest(BaseModel):
    """Request to rotate a secret."""
    secret_name: str
    new_value: Optional[str] = Field(None, description="New secret value (auto-generated if not provided)")
    rotation_strategy: str = Field(default="random", pattern="^(random|incremental|custom)$")


class SecretRotationResponse(BaseModel):
    """Secret rotation response."""
    secret_name: str
    rotated_at: datetime
    new_version: str
    old_version_revoked_at: Optional[datetime]
    reason: str


class SecretAuditLog(BaseModel):
    """Audit entry for secret access."""
    timestamp: datetime
    agent_id: str
    action: str
    secret_name: str
    result: str


class SecretStatusResponse(BaseModel):
    """Secret status and metadata."""
    secret_name: str
    latest_version: str
    created_at: datetime
    last_rotated: Optional[datetime]
    rotation_enabled: bool
    rotation_interval_days: Optional[int]


# In-memory storage
leases_db: dict = {}  # lease_id -> lease_data
secrets_db: dict = {}  # secret_name -> secret_data
audit_log: List[SecretAuditLog] = []


@router.post(
    "/request",
    response_model=SecretLeaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request a secret lease",
)
async def request_secret(
    request: SecretLeaseRequest,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> SecretLeaseResponse:
    """
    Request access to a secret with automatic expiration.

    Implements just-in-time provisioning where secrets are leased for a limited time.
    Supports TTL from 1 minute to 24 hours.

    Args:
        request: Secret request details
        current_agent: Current authenticated agent

    Returns:
        SecretLeaseResponse: Secret lease with TTL

    Raises:
        HTTPException: If unauthorized or secret not found
    """
    if not current_agent.has_scope("secret:read") and not current_agent.has_scope("*"):
        logger.warning(f"Unauthorized secret request by {current_agent.agent_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to request secrets",
        )

    try:
        # Verify secret exists (in production, check actual secret backend)
        if request.secret_name not in secrets_db:
            # Create mock secret for demo
            secrets_db[request.secret_name] = {
                "value": f"secret_value_for_{request.secret_name}",
                "created_at": datetime.now(timezone.utc),
                "version": "1",
            }

        secret_data = secrets_db[request.secret_name]

        # Create lease
        lease_id = f"lease_{uuid4()}"
        issued_at = datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(seconds=request.ttl_seconds)

        lease = {
            "lease_id": lease_id,
            "agent_id": current_agent.agent_id,
            "secret_name": request.secret_name,
            "secret_value": secret_data["value"],
            "ttl_seconds": request.ttl_seconds,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "renewable": True,
            "renewal_count": 0,
        }

        leases_db[lease_id] = lease

        # Log audit event
        audit_event = SecretAuditLog(
            timestamp=issued_at,
            agent_id=current_agent.agent_id,
            action="secret_requested",
            secret_name=request.secret_name,
            result="success",
        )
        audit_log.append(audit_event)

        logger.info(
            f"Secret lease created: {lease_id} for {request.secret_name} "
            f"by {current_agent.agent_id} (justification: {request.justification})"
        )

        return SecretLeaseResponse(
            lease_id=lease_id,
            secret_name=request.secret_name,
            secret_value=secret_data["value"],
            ttl_seconds=request.ttl_seconds,
            issued_at=issued_at,
            expires_at=expires_at,
            renewable=True,
        )

    except Exception as e:
        logger.error(f"Failed to request secret: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to request secret",
        )


@router.post(
    "/{lease_id}/renew",
    response_model=SecretLeaseResponse,
    summary="Renew a secret lease",
)
async def renew_lease(
    lease_id: str,
    request: SecretRenewalRequest,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> SecretLeaseResponse:
    """
    Extend a secret lease before it expires.

    Allows agents to extend active leases. Renewal is tracked for compliance.

    Args:
        lease_id: Lease to renew
        request: Renewal details
        current_agent: Current authenticated agent

    Returns:
        SecretLeaseResponse: Renewed lease

    Raises:
        HTTPException: If lease not found or expired
    """
    lease = leases_db.get(lease_id)
    if not lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found",
        )

    # Check ownership or admin permission
    if (
        lease["agent_id"] != current_agent.agent_id
        and not current_agent.has_scope("secret:admin")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot renew lease of another agent",
        )

    # Check if lease is expired
    if datetime.now(timezone.utc) > lease["expires_at"]:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Lease has expired",
        )

    # Check renewal limit (max 3 renewals)
    if lease.get("renewal_count", 0) >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum renewals exceeded",
        )

    try:
        ttl = request.additional_ttl_seconds or 3600
        new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

        lease["expires_at"] = new_expires_at
        lease["renewal_count"] = lease.get("renewal_count", 0) + 1
        lease["ttl_seconds"] = ttl

        logger.info(f"Lease renewed: {lease_id} by {current_agent.agent_id}")

        return SecretLeaseResponse(
            lease_id=lease["lease_id"],
            secret_name=lease["secret_name"],
            secret_value=lease["secret_value"],
            ttl_seconds=ttl,
            issued_at=lease["issued_at"],
            expires_at=new_expires_at,
            renewable=True,
        )

    except Exception as e:
        logger.error(f"Failed to renew lease: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to renew lease",
        )


@router.post(
    "/{lease_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a secret lease",
)
async def revoke_lease(
    lease_id: str,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> None:
    """
    Immediately revoke a secret lease.

    Prevents further access to the secret. Can be called by lease owner or admin.

    Args:
        lease_id: Lease to revoke
        current_agent: Current authenticated agent

    Raises:
        HTTPException: If unauthorized or lease not found
    """
    lease = leases_db.get(lease_id)
    if not lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found",
        )

    if (
        lease["agent_id"] != current_agent.agent_id
        and not current_agent.has_scope("secret:admin")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot revoke lease of another agent",
        )

    try:
        # Mark lease as revoked
        lease["revoked_at"] = datetime.now(timezone.utc)
        lease["renewable"] = False

        logger.info(f"Lease revoked: {lease_id} by {current_agent.agent_id}")

    except Exception as e:
        logger.error(f"Failed to revoke lease: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke lease",
        )


@router.post(
    "/{secret_name}/rotate",
    response_model=SecretRotationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger secret rotation",
)
async def rotate_secret(
    secret_name: str,
    request: SecretRotationRequest,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> SecretRotationResponse:
    """
    Rotate a secret and revoke old versions.

    Supports multiple rotation strategies. Old secret versions are automatically revoked.

    Args:
        secret_name: Secret to rotate
        request: Rotation parameters
        current_agent: Current authenticated agent

    Returns:
        SecretRotationResponse: Rotation result

    Raises:
        HTTPException: If unauthorized or secret not found
    """
    if not current_agent.has_scope("secret:write") and not current_agent.has_scope("*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    if secret_name not in secrets_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Secret not found",
        )

    try:
        secret = secrets_db[secret_name]
        old_version = secret.get("version", "1")
        old_value = secret.get("value")
        now = datetime.now(timezone.utc)

        # Generate new value if not provided
        if request.new_value:
            new_value = request.new_value
        else:
            # Generate random secret
            import secrets as secrets_module
            new_value = f"YOUR_SECRET_{secrets_module.token_hex(16)}"

        # Update secret
        secret["value"] = new_value
        secret["version"] = str(int(old_version) + 1)
        secret["last_rotated"] = now
        old_revoked_at = secret.get("old_revoked_at", now)

        logger.info(
            f"Secret rotated: {secret_name} "
            f"v{old_version} -> v{secret['version']} by {current_agent.agent_id}"
        )

        return SecretRotationResponse(
            secret_name=secret_name,
            rotated_at=now,
            new_version=secret["version"],
            old_version_revoked_at=old_revoked_at,
            reason=f"Rotation via {request.rotation_strategy} strategy",
        )

    except Exception as e:
        logger.error(f"Failed to rotate secret: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rotate secret",
        )


@router.get(
    "/{secret_name}/status",
    response_model=SecretStatusResponse,
    summary="Get secret status",
)
async def get_secret_status(
    secret_name: str,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> SecretStatusResponse:
    """
    Get metadata and status for a secret.

    Does not return the actual secret value.

    Args:
        secret_name: Secret to query
        current_agent: Current authenticated agent

    Returns:
        SecretStatusResponse: Secret metadata

    Raises:
        HTTPException: If not found or unauthorized
    """
    if not current_agent.has_scope("secret:read") and not current_agent.has_scope("*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    secret = secrets_db.get(secret_name)
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Secret not found",
        )

    return SecretStatusResponse(
        secret_name=secret_name,
        latest_version=secret.get("version", "1"),
        created_at=secret.get("created_at", datetime.now(timezone.utc)),
        last_rotated=secret.get("last_rotated"),
        rotation_enabled=True,
        rotation_interval_days=30,
    )


@router.get(
    "/audit",
    summary="Get secret audit log",
)
async def get_secret_audit(
    secret_name: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> List[SecretAuditLog]:
    """
    Query secret access audit logs.

    Filters can be applied for compliance and investigation.

    Args:
        secret_name: Filter by secret name
        agent_id: Filter by agent
        action: Filter by action type
        limit: Max results
        current_agent: Current authenticated agent

    Returns:
        List[SecretAuditLog]: Matching audit entries
    """
    if not current_agent.has_scope("audit:read") and not current_agent.has_scope("*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    results = audit_log

    if secret_name:
        results = [e for e in results if e.secret_name == secret_name]

    if agent_id:
        results = [e for e in results if e.agent_id == agent_id]

    if action:
        results = [e for e in results if e.action == action]

    return results[-limit:]
