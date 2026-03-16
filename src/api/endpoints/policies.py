"""
Policy Management Endpoints

Policy CRUD operations, agent-to-policy binding, and policy simulation.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Optional, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel, Field

from src.api.auth import get_current_agent, AgentCredentials
from src.db.connection import get_connection

logger = logging.getLogger(__name__)

router = APIRouter()

# Models
class PolicyCondition(BaseModel):
    """Policy condition for rule evaluation."""
    field: str = Field(..., description="Field to evaluate (e.g., 'resource.type')")
    operator: str = Field(..., pattern="^(eq|neq|in|contains|matches)$")
    value: str

    class Config:
        json_schema_extra = {
            "example": {
                "field": "resource.type",
                "operator": "eq",
                "value": "secret",
            }
        }


class PolicyRule(BaseModel):
    """Single policy rule."""
    effect: str = Field(..., pattern="^(allow|deny)$")
    actions: List[str] = Field(..., min_items=1, description="Allowed actions (e.g., 'read', 'write')")
    resources: List[str] = Field(..., min_items=1, description="Resource patterns")
    conditions: Optional[List[PolicyCondition]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "effect": "allow",
                "actions": ["read", "write"],
                "resources": ["secret:database/*"],
                "conditions": [
                    {
                        "field": "agent.team",
                        "operator": "eq",
                        "value": "backend",
                    }
                ],
            }
        }


class PolicyCreateRequest(BaseModel):
    """Request to create a policy."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    rules: List[PolicyRule] = Field(..., min_items=1)
    tags: Optional[List[str]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "backend-read-only",
                "description": "Allow backend agents read-only access",
                "rules": [
                    {
                        "effect": "allow",
                        "actions": ["read"],
                        "resources": ["secret:*"],
                        "conditions": [
                            {
                                "field": "agent.team",
                                "operator": "eq",
                                "value": "backend",
                            }
                        ],
                    }
                ],
                "tags": ["backend", "read-only"],
            }
        }


class PolicyResponse(BaseModel):
    """Policy details response."""
    policy_id: str
    name: str
    description: Optional[str]
    rules: List[PolicyRule]
    tags: Optional[List[str]]
    created_at: datetime
    updated_at: datetime
    created_by: str

    class Config:
        json_schema_extra = {
            "example": {
                "policy_id": "policy_550e8400e29b41d4a716446655440000",
                "name": "backend-read-only",
                "description": "Allow backend agents read-only access",
                "rules": [...],
                "tags": ["backend", "read-only"],
                "created_at": "2026-01-15T10:30:00Z",
                "updated_at": "2026-03-04T14:22:00Z",
                "created_by": "admin_agent_001",
            }
        }


class PolicySimulationRequest(BaseModel):
    """Request to simulate policy evaluation."""
    agent_id: str
    action: str
    resource: str
    context: Optional[dict] = None


class PolicySimulationResult(BaseModel):
    """Policy simulation result."""
    agent_id: str
    action: str
    resource: str
    decision: str = Field(..., pattern="^(allow|deny|no_match)$")
    matching_rules: List[PolicyRule]
    reason: str


class PolicyBindingRequest(BaseModel):
    """Request to bind policy to agent."""
    policy_ids: List[str] = Field(..., min_items=1)


class PolicyListResponse(BaseModel):
    """Paginated list of policies."""
    policies: List[PolicyResponse]
    total: int
    offset: int
    limit: int


# Database operations (replaces in-memory policies_db and bindings_db dicts)


@router.post(
    "",
    response_model=PolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new policy",
)
async def create_policy(
    request: PolicyCreateRequest,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> PolicyResponse:
    """
    Create a new access control policy.

    Policies define allow/deny rules for resources and actions.

    Args:
        request: Policy definition
        current_agent: Current authenticated agent

    Returns:
        PolicyResponse: Created policy

    Raises:
        HTTPException: If unauthorized
    """
    if not current_agent.has_scope("policy:write") and not current_agent.has_scope("*"):
        logger.warning(f"Unauthorized policy creation by {current_agent.agent_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        policy_id = f"policy_{uuid4()}"
        now = datetime.now(timezone.utc)

        policy_record = PolicyResponse(
            policy_id=policy_id,
            name=request.name,
            description=request.description,
            rules=request.rules,
            tags=request.tags or [],
            created_at=now,
            updated_at=now,
            created_by=current_agent.agent_id,
        )

        # Store in database
        conn = await get_connection()
        try:
            await conn.execute(
                """
                INSERT INTO policies (policy_id, name, description, rules, tags, created_by)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6)
                """,
                policy_id,
                request.name,
                request.description,
                json.dumps([rule.dict() for rule in request.rules]),
                request.tags or [],
                current_agent.agent_id,
            )
        finally:
            await conn.close()

        logger.info(f"Policy created: {policy_id} by {current_agent.agent_id}")
        return policy_record

    except Exception as e:
        logger.error(f"Failed to create policy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create policy",
        )


@router.get(
    "/{policy_id}",
    response_model=PolicyResponse,
    summary="Get policy details",
)
async def get_policy(
    policy_id: str,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> PolicyResponse:
    """
    Retrieve policy details by ID.

    Args:
        policy_id: Policy identifier
        current_agent: Current authenticated agent

    Returns:
        PolicyResponse: Policy details

    Raises:
        HTTPException: If not found
    """
    if not current_agent.has_scope("policy:read") and not current_agent.has_scope("*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        conn = await get_connection()
        try:
            row = await conn.fetchrow(
                "SELECT policy_id, name, description, rules, tags, created_at, updated_at, created_by FROM policies WHERE policy_id = $1",
                policy_id
            )
        finally:
            await conn.close()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policy not found",
            )

        policy_data = dict(row)
        policy_data['rules'] = [PolicyRule(**rule) for rule in json.loads(policy_data.get('rules') or '[]')]

        return PolicyResponse(**policy_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get policy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get policy",
        )


@router.get(
    "",
    response_model=PolicyListResponse,
    summary="List policies",
)
async def list_policies(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> PolicyListResponse:
    """
    List policies with pagination.

    Args:
        offset: Pagination offset
        limit: Max results
        tag: Optional tag filter
        current_agent: Current authenticated agent

    Returns:
        PolicyListResponse: Paginated policies
    """
    if not current_agent.has_scope("policy:read") and not current_agent.has_scope("*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        conn = await get_connection()
        try:
            # Count total
            count_query = "SELECT COUNT(*) FROM policies WHERE 1=1"
            count_args = []
            if tag:
                count_query += " AND $1 = ANY(tags)"
                count_args.append(tag)

            total = await conn.fetchval(count_query, *count_args)

            # Fetch paginated results
            query = "SELECT policy_id, name, description, rules, tags, created_at, updated_at, created_by FROM policies WHERE 1=1"
            args = []
            if tag:
                query += " AND $1 = ANY(tags)"
                args.append(tag)

            query += f" ORDER BY created_at DESC LIMIT {limit} OFFSET {offset}"

            rows = await conn.fetch(query, *args)
        finally:
            await conn.close()

        policies_list = []
        for row in rows:
            policy_data = dict(row)
            policy_data['rules'] = [PolicyRule(**rule) for rule in json.loads(policy_data.get('rules') or '[]')]
            policies_list.append(PolicyResponse(**policy_data))

        return PolicyListResponse(
            policies=policies_list,
            total=total,
            offset=offset,
            limit=limit,
        )

    except Exception as e:
        logger.error(f"Failed to list policies: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list policies",
        )


@router.put(
    "/{policy_id}",
    response_model=PolicyResponse,
    summary="Update policy",
)
async def update_policy(
    policy_id: str,
    request: PolicyCreateRequest,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> PolicyResponse:
    """
    Update an existing policy.

    Args:
        policy_id: Policy to update
        request: Updated policy definition
        current_agent: Current authenticated agent

    Returns:
        PolicyResponse: Updated policy

    Raises:
        HTTPException: If unauthorized or not found
    """
    if not current_agent.has_scope("policy:write") and not current_agent.has_scope("*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        conn = await get_connection()
        try:
            row = await conn.fetchrow(
                "SELECT policy_id, name, description, rules, tags, created_at, updated_at, created_by FROM policies WHERE policy_id = $1",
                policy_id
            )
        finally:
            await conn.close()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policy not found",
            )

        now = datetime.now(timezone.utc)
        conn = await get_connection()
        try:
            await conn.execute(
                """
                UPDATE policies SET name = $1, description = $2, rules = $3::jsonb, tags = $4, updated_at = $5
                WHERE policy_id = $6
                """,
                request.name,
                request.description,
                json.dumps([rule.dict() for rule in request.rules]),
                request.tags or [],
                now,
                policy_id,
            )
        finally:
            await conn.close()

        logger.info(f"Policy updated: {policy_id}")

        policy_data = dict(row)
        policy_data['name'] = request.name
        policy_data['description'] = request.description
        policy_data['rules'] = request.rules
        policy_data['tags'] = request.tags or []
        policy_data['updated_at'] = now

        return PolicyResponse(**policy_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update policy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update policy",
        )


@router.post(
    "/{policy_id}/simulate",
    response_model=PolicySimulationResult,
    summary="Simulate policy evaluation",
)
async def simulate_policy(
    policy_id: str,
    request: PolicySimulationRequest,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> PolicySimulationResult:
    """
    Dry-run a policy to test rules.

    Evaluates policy against test inputs without enforcing.

    Args:
        policy_id: Policy to test
        request: Simulation inputs
        current_agent: Current authenticated agent

    Returns:
        PolicySimulationResult: Evaluation result

    Raises:
        HTTPException: If policy not found
    """
    if not current_agent.has_scope("policy:read") and not current_agent.has_scope("*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        conn = await get_connection()
        try:
            row = await conn.fetchrow(
                "SELECT rules FROM policies WHERE policy_id = $1",
                policy_id
            )
        finally:
            await conn.close()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policy not found",
            )

        matching_rules = []
        decision = "no_match"
        reason = "No rules matched the request"

        # Simple policy evaluation
        rules_data = json.loads(row['rules'] or '[]')
        for rule_dict in rules_data:
            rule = PolicyRule(**rule_dict)

            # Check if action matches
            if request.action not in rule.actions:
                continue

            # Check if resource matches (simple glob support)
            resource_matched = False
            for pattern in rule.resources:
                if "*" in pattern:
                    prefix = pattern.split("*")[0]
                    if request.resource.startswith(prefix):
                        resource_matched = True
                        break
                elif pattern == request.resource:
                    resource_matched = True
                    break

            if not resource_matched:
                continue

            # Check conditions
            conditions_met = True
            if rule.conditions:
                for condition in rule.conditions:
                    # Simplified condition evaluation
                    if request.context and condition.field in request.context:
                        field_value = str(request.context[condition.field])
                        if condition.operator == "eq" and field_value != condition.value:
                            conditions_met = False
                            break

            if conditions_met:
                matching_rules.append(rule)
                decision = rule.effect
                reason = f"Rule matched: {request.action} on {request.resource}"

        logger.info(
            f"Policy simulation: {policy_id} - "
            f"{request.agent_id}:{request.action}:{request.resource} -> {decision}"
        )

        return PolicySimulationResult(
            agent_id=request.agent_id,
            action=request.action,
            resource=request.resource,
            decision=decision,
            matching_rules=matching_rules,
            reason=reason,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Policy simulation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Simulation failed",
        )


@router.post(
    "/{policy_id}/bind/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Bind policy to agent",
)
async def bind_policy_to_agent(
    policy_id: str,
    agent_id: str,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> None:
    """
    Attach a policy to an agent.

    Args:
        policy_id: Policy to bind
        agent_id: Target agent
        current_agent: Current authenticated agent

    Raises:
        HTTPException: If unauthorized or not found
    """
    if not current_agent.has_scope("policy:write"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        conn = await get_connection()
        try:
            # Check if policy exists
            policy_exists = await conn.fetchval("SELECT 1 FROM policies WHERE policy_id = $1", policy_id)
            if not policy_exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Policy not found",
                )

            # Check if binding already exists
            binding_exists = await conn.fetchval(
                "SELECT 1 FROM policy_bindings WHERE agent_id = $1 AND policy_id = $2",
                agent_id,
                policy_id
            )

            if not binding_exists:
                await conn.execute(
                    "INSERT INTO policy_bindings (agent_id, policy_id) VALUES ($1, $2)",
                    agent_id,
                    policy_id
                )
                logger.info(f"Policy {policy_id} bound to agent {agent_id}")
        finally:
            await conn.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to bind policy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to bind policy",
        )


@router.delete(
    "/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete policy",
)
async def delete_policy(
    policy_id: str,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> None:
    """
    Delete a policy.

    Args:
        policy_id: Policy to delete
        current_agent: Current authenticated agent

    Raises:
        HTTPException: If unauthorized or not found
    """
    if not current_agent.has_scope("policy:write"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        conn = await get_connection()
        try:
            # Check if policy exists
            policy_exists = await conn.fetchval("SELECT 1 FROM policies WHERE policy_id = $1", policy_id)
            if not policy_exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Policy not found",
                )

            await conn.execute("DELETE FROM policies WHERE policy_id = $1", policy_id)
            logger.info(f"Policy deleted: {policy_id}")
        finally:
            await conn.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete policy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete policy",
        )
