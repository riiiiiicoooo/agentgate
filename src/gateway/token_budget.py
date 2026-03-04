"""
Token Budget Management

Per-agent token budget tracking and enforcement for LLM API usage.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import time

logger = logging.getLogger(__name__)


class TokenBudget:
    """Tracks token usage for an agent."""

    def __init__(
        self,
        agent_id: str,
        monthly_limit: int,
        hourly_limit: Optional[int] = None,
    ):
        self.agent_id = agent_id
        self.monthly_limit = monthly_limit
        self.hourly_limit = hourly_limit
        self.created_at = datetime.now(timezone.utc)
        self.monthly_reset = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        self.hourly_reset = datetime.now(timezone.utc).replace(
            minute=0, second=0, microsecond=0
        ) + timedelta(hours=1)
        self.monthly_used = 0
        self.hourly_used = 0

    def add_tokens(self, count: int) -> None:
        """Add tokens to usage."""
        self.monthly_used += count
        self.hourly_used += count

    def reset_monthly_if_needed(self) -> None:
        """Reset monthly counter if period passed."""
        now = datetime.now(timezone.utc)

        if now >= self.monthly_reset:
            self.monthly_used = 0
            self.monthly_reset = now.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            # Set next month reset
            next_month = self.monthly_reset + timedelta(days=32)
            self.monthly_reset = next_month.replace(day=1)

    def reset_hourly_if_needed(self) -> None:
        """Reset hourly counter if period passed."""
        now = datetime.now(timezone.utc)

        if now >= self.hourly_reset:
            self.hourly_used = 0
            self.hourly_reset = now.replace(
                minute=0, second=0, microsecond=0
            ) + timedelta(hours=1)

    def can_use_tokens(self, count: int) -> bool:
        """Check if can use tokens."""
        self.reset_monthly_if_needed()
        self.reset_hourly_if_needed()

        # Check monthly limit
        if self.monthly_used + count > self.monthly_limit:
            return False

        # Check hourly limit
        if self.hourly_limit and (self.hourly_used + count) > self.hourly_limit:
            return False

        return True

    def get_remaining(self) -> Dict[str, int]:
        """Get remaining tokens."""
        self.reset_monthly_if_needed()
        self.reset_hourly_if_needed()

        remaining_monthly = self.monthly_limit - self.monthly_used
        remaining_hourly = None

        if self.hourly_limit:
            remaining_hourly = self.hourly_limit - self.hourly_used

        return {
            "monthly_remaining": max(0, remaining_monthly),
            "hourly_remaining": max(0, remaining_hourly) if remaining_hourly else None,
            "monthly_reset_at": self.monthly_reset.isoformat(),
            "hourly_reset_at": self.hourly_reset.isoformat(),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "monthly_limit": self.monthly_limit,
            "hourly_limit": self.hourly_limit,
            "monthly_used": self.monthly_used,
            "hourly_used": self.hourly_used,
            "created_at": self.created_at.isoformat(),
            "remaining": self.get_remaining(),
        }


class TokenBudgetManager:
    """
    Manages token budgets for all agents.

    Supports:
    - Per-agent monthly/hourly limits
    - Soft and hard limits
    - Budget overages (premium accounts)
    - Cost tracking
    """

    def __init__(self):
        self.budgets: Dict[str, TokenBudget] = {}
        self.default_monthly_limit = 100000
        self.default_hourly_limit = 10000

        logger.info("TokenBudgetManager initialized")

    def create_budget(
        self,
        agent_id: str,
        monthly_limit: Optional[int] = None,
        hourly_limit: Optional[int] = None,
    ) -> TokenBudget:
        """Create a new token budget."""
        budget = TokenBudget(
            agent_id=agent_id,
            monthly_limit=monthly_limit or self.default_monthly_limit,
            hourly_limit=hourly_limit or self.default_hourly_limit,
        )

        self.budgets[agent_id] = budget

        logger.info(
            f"Token budget created for {agent_id}: "
            f"monthly={budget.monthly_limit}, hourly={budget.hourly_limit}"
        )

        return budget

    def get_budget(self, agent_id: str) -> Optional[TokenBudget]:
        """Get agent's token budget."""
        if agent_id not in self.budgets:
            # Auto-create with defaults
            return self.create_budget(agent_id)

        return self.budgets[agent_id]

    async def check_and_use_tokens(self, agent_id: str, count: int) -> bool:
        """
        Check if agent can use tokens and deduct from budget.

        Args:
            agent_id: Agent ID
            count: Token count to use

        Returns:
            bool: True if allowed, False if would exceed

        Raises:
            ValueError: If agent not found
        """
        budget = self.get_budget(agent_id)

        if not budget:
            raise ValueError(f"Budget not found for agent: {agent_id}")

        if not budget.can_use_tokens(count):
            logger.warning(
                f"Token budget exceeded for {agent_id}: "
                f"requested {count}, monthly remaining {budget.monthly_limit - budget.monthly_used}"
            )
            return False

        budget.add_tokens(count)

        logger.debug(
            f"Tokens used for {agent_id}: {count} "
            f"(monthly: {budget.monthly_used}/{budget.monthly_limit})"
        )

        return True

    async def get_budget_info(self, agent_id: str) -> Dict[str, Any]:
        """Get detailed budget information."""
        budget = self.get_budget(agent_id)

        if not budget:
            raise ValueError(f"Budget not found for agent: {agent_id}")

        return budget.to_dict()

    def update_monthly_limit(self, agent_id: str, new_limit: int) -> None:
        """Update an agent's monthly limit."""
        budget = self.get_budget(agent_id)

        if budget:
            budget.monthly_limit = new_limit
            logger.info(f"Monthly limit updated for {agent_id}: {new_limit}")

    def update_hourly_limit(self, agent_id: str, new_limit: int) -> None:
        """Update an agent's hourly limit."""
        budget = self.get_budget(agent_id)

        if budget:
            budget.hourly_limit = new_limit
            logger.info(f"Hourly limit updated for {agent_id}: {new_limit}")

    def get_usage_report(self) -> Dict[str, Any]:
        """Get token usage report across all agents."""
        total_used = sum(b.monthly_used for b in self.budgets.values())
        total_limit = sum(b.monthly_limit for b in self.budgets.values())
        utilization = (total_used / total_limit * 100) if total_limit > 0 else 0

        high_usage = [
            (agent_id, budget.monthly_used)
            for agent_id, budget in self.budgets.items()
            if budget.monthly_used > budget.monthly_limit * 0.9
        ]

        return {
            "total_agents": len(self.budgets),
            "total_tokens_used": total_used,
            "total_tokens_limit": total_limit,
            "utilization_percent": utilization,
            "high_usage_agents": high_usage,
        }
