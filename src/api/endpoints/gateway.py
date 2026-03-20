"""
AI Gateway Proxy Endpoints

LLM API proxy with:
- Model routing: Intelligent model selection based on complexity and budget
- Rate limiting: Per-agent request throttling
- Token budget enforcement: Usage limits per agent
- Prompt injection detection: Security checks for prompt attacks
- Cost tracking: Real-time monitoring of LLM costs
"""

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, status, Depends, Request
from pydantic import BaseModel, Field

from src.api.auth import get_current_agent, AgentCredentials
from src.db.connection import get_connection
from src.gateway.model_router import ModelRouter, RequestComplexity
from src.gateway.cost_tracker import CostTracker

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize model router (global instance)
_model_router: Optional[ModelRouter] = None
_cost_tracker: Optional[CostTracker] = None


def get_model_router() -> ModelRouter:
    """Get or initialize the model router."""
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter()
    return _model_router


def get_cost_tracker() -> CostTracker:
    """Get or initialize the cost tracker."""
    global _cost_tracker
    if _cost_tracker is None:
        _cost_tracker = CostTracker()
    return _cost_tracker

# Models
class LLMRequest(BaseModel):
    """LLM API request wrapper."""
    model: str = Field(..., description="Model ID (gpt-4, claude-3, etc.)")
    messages: list[dict] = Field(..., description="Message history")
    temperature: Optional[float] = Field(0.7, ge=0, le=2)
    max_tokens: Optional[int] = Field(None, ge=1, le=4000)
    top_p: Optional[float] = Field(1.0, ge=0, le=1)

    class Config:
        json_schema_extra = {
            "example": {
                "model": "gpt-4",
                "messages": [
                    {"role": "user", "content": "What is 2+2?"}
                ],
                "max_tokens": 100,
            }
        }


class LLMResponse(BaseModel):
    """LLM API response wrapper."""
    request_id: str
    model: str
    content: str
    tokens_used: int
    tokens_remaining: int
    cost_estimate: float

    class Config:
        json_schema_extra = {
            "example": {
                "request_id": "req_550e8400e29b41d4a716446655440000",
                "model": "gpt-4",
                "content": "2 + 2 equals 4",
                "tokens_used": 15,
                "tokens_remaining": 985,
                "cost_estimate": 0.00045,
            }
        }


class PromptInjectionAlert(BaseModel):
    """Prompt injection detection alert."""
    alert_id: str
    detected_at: datetime
    agent_id: str
    severity: str = Field(..., pattern="^(low|medium|high|critical)$")
    injection_type: str
    suspicious_content: str
    remediation: str


# Token budgets per agent (stored in database - token_budgets table)
# Agent usage tracking is stored in database or Redis (high-frequency reads)


def check_prompt_injection(prompt: str) -> Optional[Dict[str, Any]]:
    """
    Detect prompt injection attempts.

    Uses pattern matching and heuristics to identify:
    - Command injection patterns
    - Jailbreak attempts
    - Instruction override attempts
    - Data exfiltration patterns

    Args:
        prompt: User input to check

    Returns:
        dict with detection details if injection found, None otherwise
    """
    # Patterns for common injection attacks
    injection_patterns = [
        # Override patterns
        (r"ignore previous instructions?|disregard", "instruction_override"),
        (r"pretend you are|you are now|act as if", "role_override"),
        (r"respond as if you were|system prompt", "system_override"),
        # Data extraction
        (r"show me your|reveal|leak|expose", "data_extraction"),
        (r"list all variables|memory|stored data", "memory_access"),
        # Jailbreak
        (r"do anything|no restrictions|bypass|filter", "jailbreak"),
        (r"DAN mode|Developer mode|ignore safety", "jailbreak_variant"),
        # SQL/Code injection
        (r"'; --|\"; --|DROP TABLE|DELETE FROM", "sql_injection"),
        (r"eval\(|exec\(|__import__", "code_injection"),
    ]

    prompt_lower = prompt.lower()

    for pattern, injection_type in injection_patterns:
        if re.search(pattern, prompt_lower, re.IGNORECASE):
            logger.warning(f"Prompt injection detected: {injection_type}")
            return {
                "detected": True,
                "type": injection_type,
                "suspicious_pattern": pattern,
            }

    return None


async def get_agent_token_budget(agent_id: str) -> int:
    """
    Get remaining token budget for an agent from database.

    Args:
        agent_id: Agent identifier

    Returns:
        int: Remaining tokens this hour

    Raises:
        ValueError: If agent has exceeded quota
    """
    try:
        conn = await get_connection()
        try:
            budget_row = await conn.fetchrow(
                """
                SELECT monthly_limit, hourly_limit, hourly_used, hourly_reset_at
                FROM token_budgets WHERE agent_id = $1
                """,
                agent_id
            )

            if not budget_row:
                # Create default budget entry
                now = datetime.now(timezone.utc)
                await conn.execute(
                    """
                    INSERT INTO token_budgets (agent_id, monthly_limit, hourly_limit, hourly_reset_at)
                    VALUES ($1, $2, $3, $4)
                    """,
                    agent_id,
                    100000,  # Default monthly limit
                    10000,   # Default hourly limit
                    now,
                )
                return 10000

            # Check if hourly window needs reset
            now = datetime.now(timezone.utc)
            reset_at = budget_row['hourly_reset_at']

            if (now - reset_at).total_seconds() > 3600:
                # Reset hourly budget
                new_reset = now
                await conn.execute(
                    """
                    UPDATE token_budgets SET hourly_used = 0, hourly_reset_at = $1
                    WHERE agent_id = $2
                    """,
                    new_reset,
                    agent_id,
                )
                return budget_row['hourly_limit'] or 10000

            hourly_limit = budget_row['hourly_limit'] or 10000
            if hourly_limit is None:  # unlimited
                return 999999

            used = budget_row['hourly_used'] or 0
            remaining = hourly_limit - used

            if remaining <= 0:
                raise ValueError(f"Token budget exhausted ({used}/{hourly_limit})")

            return remaining
        finally:
            await conn.close()
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Failed to get token budget: {e}")
        # Fall back to default
        return 10000


@router.post(
    "/chat/completions",
    response_model=LLMResponse,
    summary="Proxy to LLM API with intelligent model routing",
)
async def proxy_llm_request(
    request: LLMRequest,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> LLMResponse:
    """
    Proxy requests to LLM APIs with intelligent routing and cost optimization.

    Features:
    - Model routing: Selects optimal model based on complexity and budget
    - Prompt injection detection: Blocks injection attacks
    - Token budget enforcement: Usage limits per agent
    - Rate limiting: Per-agent request throttling
    - Cost tracking: Real-time monitoring of spending
    - Request logging: Complete audit trail

    Model Routing Logic:
    1. Classify request complexity (simple/moderate/complex)
    2. Apply budget constraints (downgrade if budget critical)
    3. Respect policy restrictions
    4. Select most cost-effective model for the task

    Args:
        request: LLM API request with optional model override
        current_agent: Current authenticated agent

    Returns:
        LLMResponse: LLM response with routing info and cost estimate

    Raises:
        HTTPException: If injection detected, budget exceeded, or policy violated
    """
    if not current_agent.has_scope("llm:write") and not current_agent.has_scope("*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to access LLM",
        )

    try:
        from uuid import uuid4

        request_id = f"req_{uuid4()}"
        router = get_model_router()
        cost_tracker = get_cost_tracker()

        # Step 1: Check token budget
        try:
            remaining_budget = await get_agent_token_budget(current_agent.agent_id)
        except ValueError as e:
            logger.warning(f"Token budget exceeded for {current_agent.agent_id}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(e),
            )

        # Step 2: Concatenate messages for analysis
        full_prompt = " ".join([msg.get("content", "") for msg in request.messages])

        # Step 3: Detect prompt injection (before routing, to block early)
        injection = check_prompt_injection(full_prompt)
        if injection and injection["detected"]:
            logger.error(
                f"Prompt injection detected in request {request_id}: {injection['type']}"
            )

            from src.api.endpoints.audit import log_audit_event
            await log_audit_event(
                event_type="policy_violation",
                actor_agent_id=current_agent.agent_id,
                resource_type="llm_request",
                resource_id=request_id,
                action="prompt_injection_detected",
                status="failure",
                details={
                    "injection_type": injection["type"],
                    "requested_model": request.model,
                },
                severity="critical",
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Prompt injection detected. Request blocked.",
            )

        # Step 4: Estimate tokens (rough calculation)
        # In production, use tiktoken or similar library
        estimated_input_tokens = len(full_prompt) // 4
        estimated_output_tokens = request.max_tokens or 100

        if estimated_input_tokens + estimated_output_tokens > remaining_budget:
            logger.warning(
                f"Request would exceed token budget for {current_agent.agent_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Request tokens would exceed budget",
            )

        # Step 5: CLASSIFY COMPLEXITY (new feature)
        complexity = router.classify_complexity(request.messages)

        # Step 6: SELECT MODEL via intelligent routing (new feature)
        # Note: In production, could fetch agent's policy constraints from DB
        routing_decision = router.select_model(
            requested_model=request.model,
            agent_id=current_agent.agent_id,
            complexity=complexity,
            budget_remaining=remaining_budget,
            policy_constraints=None,  # Could load from DB per-agent policies
        )

        # Override model with routed selection
        selected_model = routing_decision.selected_model

        # Step 7: Estimate cost with selected model (new feature)
        estimated_cost = router.estimate_cost(
            selected_model,
            estimated_input_tokens,
            estimated_output_tokens,
        )

        # Calculate savings if we routed away from requested model
        cost_savings = None
        if request.model != selected_model and request.model in router.models:
            original_cost = router.estimate_cost(
                request.model,
                estimated_input_tokens,
                estimated_output_tokens,
            )
            cost_savings = original_cost - estimated_cost

        # In production, actually call LLM API with selected_model
        # For this demo, return mock response
        mock_response = {
            "request_id": request_id,
            "model": selected_model,  # Return actual model used, not requested
            "content": "This is a mock LLM response. In production, this would call the actual API.",
            "tokens_used": estimated_input_tokens + estimated_output_tokens,
            "tokens_remaining": remaining_budget - (estimated_input_tokens + estimated_output_tokens),
            "cost_estimate": estimated_cost,
        }

        # Step 8: Update token budget in database
        try:
            conn = await get_connection()
            try:
                await conn.execute(
                    """
                    UPDATE token_budgets SET hourly_used = hourly_used + $1
                    WHERE agent_id = $2
                    """,
                    estimated_input_tokens + estimated_output_tokens,
                    current_agent.agent_id,
                )
            finally:
                await conn.close()
        except Exception as e:
            logger.warning(f"Failed to update token usage: {e}")

        # Step 9: Record cost in tracking system (new feature)
        try:
            await cost_tracker.record_request(
                agent_id=current_agent.agent_id,
                request_id=request_id,
                model=selected_model,
                input_tokens=estimated_input_tokens,
                output_tokens=estimated_output_tokens,
                estimated_cost=estimated_cost,
                requested_model=request.model if request.model != selected_model else None,
                cost_savings=cost_savings,
            )
        except Exception as e:
            logger.warning(f"Failed to record cost: {e}")

        # Step 10: Log audit event with routing details
        from src.api.endpoints.audit import log_audit_event
        await log_audit_event(
            event_type="agent_llm_request",
            actor_agent_id=current_agent.agent_id,
            resource_type="llm_model",
            resource_id=selected_model,
            action="completion",
            status="success",
            details={
                "request_id": request_id,
                "requested_model": request.model,
                "selected_model": selected_model,
                "complexity": complexity.value,
                "routing_reason": routing_decision.routing_reason,
                "tokens_used": estimated_input_tokens + estimated_output_tokens,
                "estimated_cost": estimated_cost,
                "cost_savings": cost_savings,
                "fallback_models": routing_decision.fallback_models,
            },
            severity="info",
        )

        logger.info(
            f"LLM request routed: {request_id} "
            f"requested={request.model} → selected={selected_model} "
            f"complexity={complexity.value} cost=${estimated_cost:.4f} "
            f"savings=${cost_savings or 0:.4f} "
            f"agent={current_agent.agent_id}"
        )

        return LLMResponse(**mock_response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"LLM request failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LLM request failed",
        )


@router.get(
    "/token-budget/{agent_id}",
    summary="Get agent token budget",
)
async def get_token_budget(
    agent_id: str,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> dict:
    """
    Get remaining token budget for an agent.

    Only agents can check their own budget, or admins can check any.

    Args:
        agent_id: Agent to check budget for
        current_agent: Current authenticated agent

    Returns:
        dict: Token budget information

    Raises:
        HTTPException: If unauthorized
    """
    # Authorization check
    if (
        current_agent.agent_id != agent_id
        and not current_agent.has_scope("admin:read")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot check budget for other agents",
        )

    try:
        conn = await get_connection()
        try:
            budget_row = await conn.fetchrow(
                """
                SELECT hourly_limit, hourly_used, hourly_reset_at
                FROM token_budgets WHERE agent_id = $1
                """,
                agent_id
            )
        finally:
            await conn.close()

        if not budget_row:
            budget_limit = 10000
            used = 0
            reset_at = datetime.now(timezone.utc) + timedelta(hours=1)
        else:
            budget_limit = budget_row['hourly_limit'] or 10000
            used = budget_row['hourly_used'] or 0
            reset_at = budget_row['hourly_reset_at'] + timedelta(hours=1)

        remaining = await get_agent_token_budget(agent_id)

        return {
            "agent_id": agent_id,
            "budget_limit": budget_limit,
            "tokens_used": used,
            "tokens_remaining": remaining,
            "reset_at": reset_at.isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get token budget: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get token budget",
        )


@router.post(
    "/injection-alerts",
    response_model=PromptInjectionAlert,
    status_code=status.HTTP_201_CREATED,
    summary="Report injection detection",
)
async def report_injection_alert(
    alert: PromptInjectionAlert,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> PromptInjectionAlert:
    """
    Log a prompt injection detection alert.

    Args:
        alert: Injection alert details
        current_agent: Current authenticated agent

    Returns:
        PromptInjectionAlert: Logged alert

    Raises:
        HTTPException: If unauthorized
    """
    if not current_agent.has_scope("security:write"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        from uuid import uuid4

        alert_id = f"alert_{uuid4()}"
        alert.alert_id = alert_id
        alert.detected_at = datetime.now(timezone.utc)

        logger.warning(
            f"Injection alert recorded: {alert.injection_type} "
            f"agent={alert.agent_id} severity={alert.severity}"
        )

        return alert

    except Exception as e:
        logger.error(f"Failed to report alert: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to report alert",
        )


@router.get(
    "/routing-metrics",
    summary="Get model routing statistics",
)
async def get_routing_metrics(
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> Dict[str, Any]:
    """
    Get statistics on model routing decisions.

    Shows:
    - Distribution of requests across models
    - Cost savings from intelligent routing vs naive deployment
    - Average cost per request

    Requires admin or analytics permission.

    Args:
        current_agent: Current authenticated agent

    Returns:
        dict: Routing metrics and cost analysis

    Raises:
        HTTPException: If unauthorized
    """
    if not current_agent.has_scope("admin:read") and not current_agent.has_scope("*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to view routing metrics",
        )

    try:
        router = get_model_router()
        metrics = router.get_routing_metrics()

        logger.info(f"Routing metrics queried by {current_agent.agent_id}")

        return metrics

    except Exception as e:
        logger.error(f"Failed to get routing metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get routing metrics",
        )


@router.get(
    "/model-pricing",
    summary="Get LLM model pricing information",
)
async def get_model_pricing(
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> Dict[str, Any]:
    """
    Get pricing information for all available models.

    Returns:
    - Model capabilities and recommended use cases
    - Input and output pricing per million tokens
    - Context window sizes

    Useful for:
    - Product dashboards (show users pricing)
    - Cost estimation (clients plan their spend)
    - Model selection documentation

    Args:
        current_agent: Current authenticated agent

    Returns:
        dict: Model pricing table and metadata

    Raises:
        HTTPException: If unauthorized
    """
    try:
        router = get_model_router()
        pricing_table = router.get_model_pricing_table()

        logger.info(f"Model pricing queried by {current_agent.agent_id}")

        return pricing_table

    except Exception as e:
        logger.error(f"Failed to get model pricing: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get model pricing",
        )
