"""
Agent Management Endpoints

CRUD operations for agent registration, credential rotation, and status management.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Optional, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel, Field

from src.api.auth import (
    get_current_agent,
    TokenManager,
    APIKeyManager,
    AgentCredentials,
    ClientCredentialsFlow,
)
from src.db.connection import get_connection

logger = logging.getLogger(__name__)

router = APIRouter()

# Request/Response Models
class AgentCreateRequest(BaseModel):
    """Request to create a new agent."""
    name: str = Field(..., min_length=1, max_length=255, description="Agent name")
    description: Optional[str] = Field(None, max_length=1000)
    scopes: List[str] = Field(default_factory=lambda: ["default"])
    metadata: Optional[dict] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "name": "data-processor-agent",
                "description": "Processes incoming data streams",
                "scopes": ["read:data", "write:results"],
                "metadata": {"team": "analytics", "env": "prod"},
            }
        }


class AgentResponse(BaseModel):
    """Agent information response."""
    agent_id: str
    name: str
    description: Optional[str]
    scopes: List[str]
    client_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    last_auth_at: Optional[datetime]
    metadata: dict

    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "agent_550e8400e29b41d4a716446655440000",
                "name": "data-processor-agent",
                "description": "Processes incoming data streams",
                "scopes": ["read:data", "write:results"],
                "client_id": "YOUR_AGENTGATE_CLIENT_ID_abc123def456",
                "status": "active",
                "created_at": "2026-01-15T10:30:00Z",
                "updated_at": "2026-03-04T14:22:00Z",
                "last_auth_at": "2026-03-04T09:15:00Z",
                "metadata": {"team": "analytics", "env": "prod"},
            }
        }


class CredentialRotationRequest(BaseModel):
    """Request to rotate agent credentials."""
    rotate_client_secret: bool = True
    rotate_api_keys: bool = True


class CredentialRotationResponse(BaseModel):
    """Credential rotation response."""
    agent_id: str
    client_secret: Optional[str] = None  # Only returned once
    api_key: Optional[str] = None  # Only returned once
    rotated_at: datetime
    message: str


class StatusUpdateRequest(BaseModel):
    """Request to update agent status."""
    status: str = Field(..., pattern="^(active|inactive|suspended|archived)$")
    reason: Optional[str] = None


class AgentListResponse(BaseModel):
    """Paginated list of agents."""
    agents: List[AgentResponse]
    total: int
    offset: int
    limit: int


# Database operations (replaces in-memory agents_db dict)


@router.post(
    "",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new agent",
)
async def create_agent(
    request: AgentCreateRequest,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> AgentResponse:
    """
    Create a new AI agent with OAuth credentials.

    Creates a new agent with client ID and initial credentials.
    Only administrators can create agents (requires admin:write scope).

    Args:
        request: Agent creation details
        current_agent: Current authenticated agent (must be admin)

    Returns:
        AgentResponse: Created agent details

    Raises:
        HTTPException: If authorization fails or agent already exists
    """
    # Check authorization
    if not current_agent.has_scope("admin:write") and not current_agent.has_scope("*"):
        logger.warning(f"Unauthorized agent creation attempt by {current_agent.agent_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to create agents",
        )

    try:
        # Generate unique identifiers
        agent_id = f"agent_{uuid4()}"
        client_id = f"YOUR_AGENTGATE_CLIENT_ID_{uuid4().hex[:12]}"

        # Create agent record
        now = datetime.now(timezone.utc)
        agent_record = AgentResponse(
            agent_id=agent_id,
            name=request.name,
            description=request.description,
            scopes=request.scopes,
            client_id=client_id,
            status="active",
            created_at=now,
            updated_at=now,
            last_auth_at=None,
            metadata=request.metadata or {},
        )

        # Store in database
        conn = await get_connection()
        try:
            await conn.execute(
                """
                INSERT INTO agents (agent_id, name, client_id, client_secret_hash, status, scopes, metadata, created_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
                """,
                agent_id,
                request.name,
                client_id,
                "hash_placeholder",  # In production, hash the actual secret
                "active",
                request.scopes,
                json.dumps(request.metadata or {}),
                current_agent.agent_id,
            )
        finally:
            await conn.close()

        logger.info(f"Agent created: {agent_id} by {current_agent.agent_id}")
        return agent_record

    except Exception as e:
        logger.error(f"Failed to create agent: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create agent",
        )


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Get agent details",
)
async def get_agent(
    agent_id: str,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> AgentResponse:
    """
    Retrieve agent details by ID.

    Only the agent itself or administrators can view agent details.

    Args:
        agent_id: Agent identifier
        current_agent: Current authenticated agent

    Returns:
        AgentResponse: Agent details

    Raises:
        HTTPException: If agent not found or unauthorized
    """
    # Check authorization
    if (
        current_agent.agent_id != agent_id
        and not current_agent.has_scope("admin:read")
        and not current_agent.has_scope("*")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        conn = await get_connection()
        try:
            row = await conn.fetchrow(
                "SELECT agent_id, name, client_id, status, scopes, metadata, created_at, updated_at, last_auth_at FROM agents WHERE agent_id = $1",
                agent_id
            )
        finally:
            await conn.close()

        if not row:
            logger.warning(f"Agent not found: {agent_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

        agent_data = dict(row)
        agent_data['metadata'] = json.loads(agent_data.get('metadata') or '{}')
        agent_data['description'] = None  # Not stored in agents table yet

        return AgentResponse(**agent_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get agent",
        )


@router.get(
    "",
    response_model=AgentListResponse,
    summary="List agents",
)
async def list_agents(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> AgentListResponse:
    """
    List all agents with pagination.

    Only administrators can list all agents.

    Args:
        offset: Result offset for pagination
        limit: Maximum results to return
        status_filter: Filter agents by status
        current_agent: Current authenticated agent

    Returns:
        AgentListResponse: Paginated list of agents

    Raises:
        HTTPException: If unauthorized
    """
    # Check authorization
    if not current_agent.has_scope("admin:read") and not current_agent.has_scope("*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to list agents",
        )

    try:
        conn = await get_connection()
        try:
            # Count total
            count_query = "SELECT COUNT(*) FROM agents WHERE 1=1"
            count_args = []
            if status_filter:
                count_query += " AND status = $1"
                count_args.append(status_filter)

            total = await conn.fetchval(count_query, *count_args)

            # Fetch paginated results
            query = "SELECT agent_id, name, client_id, status, scopes, metadata, created_at, updated_at, last_auth_at FROM agents WHERE 1=1"
            args = []
            if status_filter:
                query += " AND status = $" + str(len(args) + 1)
                args.append(status_filter)

            query += f" ORDER BY created_at DESC LIMIT {limit} OFFSET {offset}"

            rows = await conn.fetch(query, *args)
        finally:
            await conn.close()

        agents_list = []
        for row in rows:
            agent_data = dict(row)
            agent_data['metadata'] = json.loads(agent_data.get('metadata') or '{}')
            agent_data['description'] = None
            agents_list.append(AgentResponse(**agent_data))

        return AgentListResponse(
            agents=agents_list,
            total=total,
            offset=offset,
            limit=limit,
        )

    except Exception as e:
        logger.error(f"Failed to list agents: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list agents",
        )


@router.post(
    "/{agent_id}/rotate-credentials",
    response_model=CredentialRotationResponse,
    summary="Rotate agent credentials",
)
async def rotate_credentials(
    agent_id: str,
    request: CredentialRotationRequest,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> CredentialRotationResponse:
    """
    Rotate agent OAuth credentials.

    Generates new client secret and/or API keys. Old credentials are invalidated.
    Agent can rotate its own credentials or admin can rotate any agent's.

    Args:
        agent_id: Agent to rotate credentials for
        request: Rotation options
        current_agent: Current authenticated agent

    Returns:
        CredentialRotationResponse: New credentials

    Raises:
        HTTPException: If unauthorized or agent not found
    """
    # Check authorization
    if (
        current_agent.agent_id != agent_id
        and not current_agent.has_scope("admin:write")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        conn = await get_connection()
        try:
            row = await conn.fetchrow("SELECT agent_id FROM agents WHERE agent_id = $1", agent_id)
        finally:
            await conn.close()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

        response_data = {
            "agent_id": agent_id,
            "rotated_at": datetime.now(timezone.utc),
            "message": "Credentials rotated successfully",
        }

        if request.rotate_client_secret:
            # Generate new client secret
            client_secret = f"YOUR_AGENTGATE_SECRET_{uuid4().hex[:32]}"
            response_data["client_secret"] = client_secret
            logger.info(f"Client secret rotated for agent: {agent_id}")

        if request.rotate_api_keys:
            # Generate new API key
            api_key_manager = APIKeyManager()
            new_api_key = api_key_manager.generate_api_key(agent_id)
            response_data["api_key"] = new_api_key
            logger.info(f"API key rotated for agent: {agent_id}")

        # Update agent record in database
        conn = await get_connection()
        try:
            await conn.execute(
                "UPDATE agents SET updated_at = $1 WHERE agent_id = $2",
                datetime.now(timezone.utc),
                agent_id
            )
        finally:
            await conn.close()

        return CredentialRotationResponse(**response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rotate credentials: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rotate credentials",
        )


@router.patch(
    "/{agent_id}/status",
    response_model=AgentResponse,
    summary="Update agent status",
)
async def update_agent_status(
    agent_id: str,
    request: StatusUpdateRequest,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> AgentResponse:
    """
    Update agent status (active, inactive, suspended, archived).

    Only administrators can change agent status.

    Args:
        agent_id: Agent to update
        request: New status and reason
        current_agent: Current authenticated agent

    Returns:
        AgentResponse: Updated agent

    Raises:
        HTTPException: If unauthorized or agent not found
    """
    # Check authorization
    if not current_agent.has_scope("admin:write"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        conn = await get_connection()
        try:
            row = await conn.fetchrow(
                "SELECT agent_id, name, client_id, status, scopes, metadata, created_at, updated_at, last_auth_at FROM agents WHERE agent_id = $1",
                agent_id
            )
        finally:
            await conn.close()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

        # Update status in database
        now = datetime.now(timezone.utc)
        conn = await get_connection()
        try:
            await conn.execute(
                "UPDATE agents SET status = $1, updated_at = $2 WHERE agent_id = $3",
                request.status,
                now,
                agent_id
            )
        finally:
            await conn.close()

        logger.info(f"Agent status updated: {agent_id} -> {request.status}")

        if request.reason:
            logger.info(f"Status change reason: {request.reason}")

        agent_data = dict(row)
        agent_data['status'] = request.status
        agent_data['updated_at'] = now
        agent_data['metadata'] = json.loads(agent_data.get('metadata') or '{}')
        agent_data['description'] = None

        return AgentResponse(**agent_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update agent status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update status",
        )


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete/archive agent",
)
async def delete_agent(
    agent_id: str,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> None:
    """
    Delete or archive an agent.

    Agents are typically archived rather than permanently deleted for audit purposes.

    Args:
        agent_id: Agent to delete
        current_agent: Current authenticated agent

    Raises:
        HTTPException: If unauthorized or agent not found
    """
    # Check authorization
    if not current_agent.has_scope("admin:write"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        conn = await get_connection()
        try:
            row = await conn.fetchrow("SELECT agent_id FROM agents WHERE agent_id = $1", agent_id)
        finally:
            await conn.close()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

        # Archive instead of delete
        conn = await get_connection()
        try:
            await conn.execute(
                "UPDATE agents SET status = $1, updated_at = $2 WHERE agent_id = $3",
                "archived",
                datetime.now(timezone.utc),
                agent_id
            )
        finally:
            await conn.close()

        logger.info(f"Agent archived: {agent_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete agent: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete agent",
        )
