"""
AI Gateway Proxy Endpoints

LLM API proxy with rate limiting, token budget enforcement, and prompt injection detection.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, status, Depends, Request
from pydantic import BaseModel, Field

from src.api.auth import get_current_agent, AgentCredentials

logger = logging.getLogger(__name__)

router = APIRouter()

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


# Token budgets per agent (tokens per hour)
token_budgets = {
    "default": 10000,
    "restricted": 1000,
    "unlimited": None,
}

# Agent usage tracking
agent_usage = {}  # agent_id -> {"tokens_used": int, "last_reset": datetime}


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
    Get remaining token budget for an agent.

    Args:
        agent_id: Agent identifier

    Returns:
        int: Remaining tokens this hour

    Raises:
        ValueError: If agent has exceeded quota
    """
    now = datetime.now(timezone.utc)

    if agent_id not in agent_usage:
        agent_usage[agent_id] = {
            "tokens_used": 0,
            "last_reset": now,
        }

    # Reset hourly budget
    last_reset = agent_usage[agent_id]["last_reset"]
    if (now - last_reset).total_seconds() > 3600:
        agent_usage[agent_id]["tokens_used"] = 0
        agent_usage[agent_id]["last_reset"] = now

    # Get budget tier (default to "default")
    budget_limit = token_budgets.get("default", 10000)

    if budget_limit is None:  # unlimited
        return 999999

    used = agent_usage[agent_id]["tokens_used"]
    remaining = budget_limit - used

    if remaining <= 0:
        raise ValueError(f"Token budget exhausted ({used}/{budget_limit})")

    return remaining


@router.post(
    "/chat/completions",
    response_model=LLMResponse,
    summary="Proxy to LLM API",
)
async def proxy_llm_request(
    request: LLMRequest,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> LLMResponse:
    """
    Proxy requests to LLM APIs with rate limiting and safety checks.

    Features:
    - Prompt injection detection
    - Token budget enforcement
    - Rate limiting
    - Cost estimation
    - Request logging

    Args:
        request: LLM API request
        current_agent: Current authenticated agent

    Returns:
        LLMResponse: LLM response with usage info

    Raises:
        HTTPException: If rate limit exceeded or injection detected
    """
    if not current_agent.has_scope("llm:write") and not current_agent.has_scope("*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to access LLM",
        )

    try:
        from uuid import uuid4

        request_id = f"req_{uuid4()}"

        # Check token budget
        try:
            remaining_budget = await get_agent_token_budget(current_agent.agent_id)
        except ValueError as e:
            logger.warning(f"Token budget exceeded for {current_agent.agent_id}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(e),
            )

        # Concatenate messages for injection detection
        full_prompt = " ".join([msg.get("content", "") for msg in request.messages])

        # Detect prompt injection
        injection = check_prompt_injection(full_prompt)
        if injection and injection["detected"]:
            logger.error(
                f"Prompt injection detected in request {request_id}: {injection['type']}"
            )

            # Log security event
            from src.api.endpoints.audit import log_audit_event
            log_audit_event(
                event_type="policy_violation",
                actor_agent_id=current_agent.agent_id,
                resource_type="llm_request",
                resource_id=request_id,
                action="prompt_injection_detected",
                status="failure",
                details={
                    "injection_type": injection["type"],
                    "model": request.model,
                },
                severity="critical",
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Prompt injection detected. Request blocked.",
            )

        # Estimate tokens (rough calculation)
        # In production, use tiktoken or similar library
        estimated_tokens = len(full_prompt) // 4 + (request.max_tokens or 100)

        if estimated_tokens > remaining_budget:
            logger.warning(
                f"Request would exceed token budget for {current_agent.agent_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Request tokens ({estimated_tokens}) exceeds budget ({remaining_budget})",
            )

        # In production, actually call LLM API here (OpenAI, Anthropic, etc.)
        # For this demo, return mock response
        mock_response = {
            "request_id": request_id,
            "model": request.model,
            "content": "This is a mock LLM response. In production, this would call the actual API.",
            "tokens_used": estimated_tokens,
            "tokens_remaining": remaining_budget - estimated_tokens,
            "cost_estimate": (estimated_tokens * 0.00002),  # Rough estimate
        }

        # Update agent usage
        agent_usage[current_agent.agent_id]["tokens_used"] += estimated_tokens

        # Log successful request
        from src.api.endpoints.audit import log_audit_event
        log_audit_event(
            event_type="agent_llm_request",
            actor_agent_id=current_agent.agent_id,
            resource_type="llm_model",
            resource_id=request.model,
            action="completion",
            status="success",
            details={
                "request_id": request_id,
                "tokens_used": estimated_tokens,
                "model": request.model,
            },
            severity="info",
        )

        logger.info(
            f"LLM request processed: {request_id} "
            f"model={request.model} tokens={estimated_tokens} "
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
        remaining = await get_agent_token_budget(agent_id)
        used = agent_usage.get(agent_id, {}).get("tokens_used", 0)
        budget_limit = token_budgets.get("default", 10000)

        return {
            "agent_id": agent_id,
            "budget_limit": budget_limit,
            "tokens_used": used,
            "tokens_remaining": remaining,
            "reset_at": (
                agent_usage[agent_id]["last_reset"] + datetime.timedelta(hours=1)
            ).isoformat(),
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
