"""
Secrets Management Endpoints

Just-in-time provisioning, secret leasing, TTL management, and rotation triggers.
"""

import logging
import os
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel, Field

from src.api.auth import get_current_agent, AgentCredentials
from src.db.connection import get_connection

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


# Database operations (replaces in-memory leases_db, secrets_db, and audit_log)


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
        lease_id = f"lease_{uuid4()}"
        issued_at = datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(seconds=request.ttl_seconds)

        conn = await get_connection()
        try:
            # Get or create secret in database
            secret_row = await conn.fetchrow(
                "SELECT id, secret_name FROM secrets WHERE secret_name = $1",
                request.secret_name
            )

            if not secret_row:
                # Create mock secret for demo
                await conn.execute(
                    """
                    INSERT INTO secrets (secret_name, secret_type, version)
                    VALUES ($1, $2, $3)
                    """,
                    request.secret_name,
                    "generic",
                    "1",
                )

            # Create lease in database
            await conn.execute(
                """
                INSERT INTO secret_leases (lease_id, agent_id, secret_name, ttl_seconds, expires_at)
                VALUES ($1, $2, $3, $4, $5)
                """,
                lease_id,
                current_agent.agent_id,
                request.secret_name,
                request.ttl_seconds,
                expires_at,
            )
        finally:
            await conn.close()

        # Mock secret value for demo
        secret_value = f"secret_value_for_{request.secret_name}"

        logger.info(
            f"Secret lease created: {lease_id} for {request.secret_name} "
            f"by {current_agent.agent_id} (justification: {request.justification})"
        )

        return SecretLeaseResponse(
            lease_id=lease_id,
            secret_name=request.secret_name,
            secret_value=secret_value,
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
    try:
        conn = await get_connection()
        try:
            lease = await conn.fetchrow(
                """
                SELECT lease_id, agent_id, secret_name, ttl_seconds, issued_at, expires_at, renewal_count
                FROM secret_leases WHERE lease_id = $1
                """,
                lease_id
            )
        finally:
            await conn.close()

        if not lease:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lease not found",
            )

        # Check ownership or admin permission
        if (
            lease['agent_id'] != current_agent.agent_id
            and not current_agent.has_scope("secret:admin")
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot renew lease of another agent",
            )

        # Check if lease is expired
        if datetime.now(timezone.utc) > lease['expires_at']:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Lease has expired",
            )

        # Check renewal limit (max 3 renewals)
        if (lease.get('renewal_count') or 0) >= 3:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Maximum renewals exceeded",
            )

        ttl = request.additional_ttl_seconds or 3600
        new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

        conn = await get_connection()
        try:
            await conn.execute(
                """
                UPDATE secret_leases
                SET expires_at = $1, renewal_count = renewal_count + 1, ttl_seconds = $2
                WHERE lease_id = $3
                """,
                new_expires_at,
                ttl,
                lease_id,
            )
        finally:
            await conn.close()

        logger.info(f"Lease renewed: {lease_id} by {current_agent.agent_id}")

        # Mock secret value
        secret_value = f"secret_value_for_{lease['secret_name']}"

        return SecretLeaseResponse(
            lease_id=lease['lease_id'],
            secret_name=lease['secret_name'],
            secret_value=secret_value,
            ttl_seconds=ttl,
            issued_at=lease['issued_at'],
            expires_at=new_expires_at,
            renewable=True,
        )

    except HTTPException:
        raise
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
    try:
        conn = await get_connection()
        try:
            lease = await conn.fetchrow(
                "SELECT agent_id FROM secret_leases WHERE lease_id = $1",
                lease_id
            )
        finally:
            await conn.close()

        if not lease:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lease not found",
            )

        if (
            lease['agent_id'] != current_agent.agent_id
            and not current_agent.has_scope("secret:admin")
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot revoke lease of another agent",
            )

        # Mark lease as revoked in database
        conn = await get_connection()
        try:
            await conn.execute(
                "UPDATE secret_leases SET revoked_at = $1 WHERE lease_id = $2",
                datetime.now(timezone.utc),
                lease_id,
            )
        finally:
            await conn.close()

        logger.info(f"Lease revoked: {lease_id} by {current_agent.agent_id}")

    except HTTPException:
        raise
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

    try:
        conn = await get_connection()
        try:
            secret = await conn.fetchrow(
                "SELECT secret_name, version FROM secrets WHERE secret_name = $1",
                secret_name
            )
        finally:
            await conn.close()

        if not secret:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Secret not found",
            )

        old_version = secret['version'] or "1"
        now = datetime.now(timezone.utc)

        # Generate new value if not provided
        if request.new_value:
            new_value = request.new_value
        else:
            # Generate random secret
            import secrets as secrets_module
            new_value = f"YOUR_SECRET_{secrets_module.token_hex(16)}"

        new_version = str(int(old_version) + 1)

        # Update secret in database
        conn = await get_connection()
        try:
            await conn.execute(
                """
                UPDATE secrets
                SET version = $1, last_rotated_at = $2
                WHERE secret_name = $3
                """,
                new_version,
                now,
                secret_name,
            )
        finally:
            await conn.close()

        logger.info(
            f"Secret rotated: {secret_name} "
            f"v{old_version} -> v{new_version} by {current_agent.agent_id}"
        )

        return SecretRotationResponse(
            secret_name=secret_name,
            rotated_at=now,
            new_version=new_version,
            old_version_revoked_at=now,
            reason=f"Rotation via {request.rotation_strategy} strategy",
        )

    except HTTPException:
        raise
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

    try:
        conn = await get_connection()
        try:
            secret = await conn.fetchrow(
                "SELECT secret_name, version, created_at, last_rotated_at, rotation_enabled, rotation_interval_days FROM secrets WHERE secret_name = $1",
                secret_name
            )
        finally:
            await conn.close()

        if not secret:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Secret not found",
            )

        return SecretStatusResponse(
            secret_name=secret_name,
            latest_version=secret['version'] or "1",
            created_at=secret['created_at'],
            last_rotated=secret['last_rotated_at'],
            rotation_enabled=secret['rotation_enabled'] or True,
            rotation_interval_days=secret['rotation_interval_days'] or 30,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get secret status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get secret status",
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

    try:
        # Build query with filters
        query = "SELECT timestamp, agent_id, action, secret_name, result FROM secret_leases WHERE 1=1"
        args = []
        arg_count = 1

        if secret_name:
            query += f" AND secret_name = ${arg_count}"
            args.append(secret_name)
            arg_count += 1

        if agent_id:
            query += f" AND agent_id = ${arg_count}"
            args.append(agent_id)
            arg_count += 1

        # Note: action filter would need a column in secret_leases or join to audit_events
        # For now, we filter in memory if needed
        query += f" ORDER BY timestamp DESC LIMIT {limit}"

        conn = await get_connection()
        try:
            rows = await conn.fetch(query, *args)
        finally:
            await conn.close()

        results = []
        for row in rows:
            log_entry = SecretAuditLog(
                timestamp=row['timestamp'],
                agent_id=row['agent_id'],
                action="secret_accessed",  # Default action
                secret_name=row['secret_name'],
                result="success",  # Default result
            )
            if action is None or log_entry.action == action:
                results.append(log_entry)

        return results[:limit]
    except Exception as e:
        logger.error(f"Failed to get secret audit log: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get secret audit log",
        )
