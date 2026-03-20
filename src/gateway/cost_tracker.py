"""
Cost Tracking & Billing System

Tracks LLM usage costs per agent, per model, and across the system.
Provides real-time insights into spending patterns and cost optimization opportunities.

Uses Redis for high-frequency tracking (low latency) and PostgreSQL for
persistent historical records and detailed analytics.

PRODUCT VALUE: Enables agents to understand their costs, detect anomalies,
and optimize spending. Provides visibility for cost allocation and chargeback.
"""

import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, asdict
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class AgentCostRecord:
    """Cost record for an agent's request."""
    agent_id: str
    request_id: str
    model: str
    timestamp: datetime
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    actual_cost: Optional[float] = None
    requested_model: Optional[str] = None  # Model user asked for
    cost_savings: Optional[float] = None  # What we saved by routing


class CostTracker:
    """
    Tracks and reports on LLM usage costs.

    Provides:
    - Per-agent daily/weekly/monthly costs
    - Per-model cost breakdown
    - Savings from intelligent routing vs naive model selection
    - Cost anomaly detection
    - Billing and chargeback data

    Product Rationale:
    - Real-time: Redis for immediate access to current costs
    - Persistent: PostgreSQL for audit trail and historical analysis
    - Actionable: Clear cost reports enable optimization decisions
    """

    def __init__(self, redis_client=None, db_connection=None):
        """
        Initialize cost tracker.

        Args:
            redis_client: Redis async client for real-time tracking
            db_connection: Database connection for persistence
        """
        self.redis = redis_client
        self.db = db_connection

    async def record_request(
        self,
        agent_id: str,
        request_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        estimated_cost: float,
        requested_model: Optional[str] = None,
        cost_savings: Optional[float] = None,
    ) -> None:
        """
        Record a request cost.

        Args:
            agent_id: Agent making the request
            request_id: Unique request ID
            model: Model used
            input_tokens: Input token count
            output_tokens: Output token count
            estimated_cost: Estimated cost in dollars
            requested_model: Model that was originally requested
            cost_savings: How much we saved by routing

        PRODUCT VALUE: Every request tracked for complete visibility.
        """
        now = datetime.now(timezone.utc)

        record = AgentCostRecord(
            agent_id=agent_id,
            request_id=request_id,
            model=model,
            timestamp=now,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=estimated_cost,
            requested_model=requested_model,
            cost_savings=cost_savings,
        )

        # Real-time Redis tracking (for dashboards, alerts)
        if self.redis:
            try:
                await self._record_to_redis(record)
            except Exception as e:
                logger.warning(f"Failed to record cost to Redis: {e}")

        # Persistent PostgreSQL tracking (for audit, billing)
        if self.db:
            try:
                await self._record_to_postgres(record)
            except Exception as e:
                logger.warning(f"Failed to record cost to PostgreSQL: {e}")

    async def _record_to_redis(self, record: AgentCostRecord) -> None:
        """Store in Redis for high-frequency access and aggregation."""
        # Per-agent daily costs (for dashboard)
        daily_key = f"cost:daily:{record.agent_id}:{record.timestamp.date()}"
        await self.redis.incrbyfloat(daily_key, record.estimated_cost)
        await self.redis.expire(daily_key, 90 * 24 * 3600)  # 90 days

        # Per-model costs today (for routing decisions)
        model_key = f"cost:model:{record.model}:{record.timestamp.date()}"
        await self.redis.incrbyfloat(model_key, record.estimated_cost)
        await self.redis.expire(model_key, 90 * 24 * 3600)

        # Total cost across all agents today
        total_key = f"cost:total:{record.timestamp.date()}"
        await self.redis.incrbyfloat(total_key, record.estimated_cost)
        await self.redis.expire(total_key, 90 * 24 * 3600)

        # Total savings from routing
        if record.cost_savings:
            savings_key = f"cost:savings:{record.timestamp.date()}"
            await self.redis.incrbyfloat(savings_key, record.cost_savings)
            await self.redis.expire(savings_key, 90 * 24 * 3600)

        logger.debug(f"Cost recorded to Redis: agent={record.agent_id}, cost=${record.estimated_cost:.4f}")

    async def _record_to_postgres(self, record: AgentCostRecord) -> None:
        """Store in PostgreSQL for persistent audit trail."""
        # Note: Assumes cost_records table exists (created in migrations)
        await self.db.execute(
            """
            INSERT INTO cost_records
            (agent_id, request_id, model, input_tokens, output_tokens,
             estimated_cost, requested_model, cost_savings, recorded_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            record.agent_id,
            record.request_id,
            record.model,
            record.input_tokens,
            record.output_tokens,
            record.estimated_cost,
            record.requested_model,
            record.cost_savings,
            record.timestamp,
        )

        logger.debug(f"Cost persisted to PostgreSQL: agent={record.agent_id}, cost=${record.estimated_cost:.4f}")

    async def get_agent_daily_cost(self, agent_id: str, date: Optional[datetime] = None) -> float:
        """
        Get total cost for an agent on a specific day.

        Args:
            agent_id: Agent ID
            date: Date (defaults to today)

        Returns:
            float: Total cost in dollars
        """
        if date is None:
            date = datetime.now(timezone.utc).date()
        else:
            date = date.date() if isinstance(date, datetime) else date

        if not self.redis:
            return 0.0

        key = f"cost:daily:{agent_id}:{date}"
        cost = await self.redis.get(key)
        return float(cost) if cost else 0.0

    async def get_agent_weekly_cost(self, agent_id: str, weeks_back: int = 0) -> float:
        """
        Get total cost for an agent in a specific week.

        Args:
            agent_id: Agent ID
            weeks_back: How many weeks back (0 = current week)

        Returns:
            float: Total cost in dollars
        """
        if not self.redis:
            return 0.0

        # Calculate date range for the week
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(weeks=weeks_back, days=now.weekday())
        total_cost = 0.0

        for i in range(7):
            date = (week_start + timedelta(days=i)).date()
            daily_cost = await self.get_agent_daily_cost(agent_id, date)
            total_cost += daily_cost

        return total_cost

    async def get_agent_monthly_cost(self, agent_id: str, months_back: int = 0) -> float:
        """
        Get total cost for an agent in a specific month.

        Args:
            agent_id: Agent ID
            months_back: How many months back (0 = current month)

        Returns:
            float: Total cost in dollars
        """
        if not self.redis:
            return 0.0

        # Calculate date range for the month
        now = datetime.now(timezone.utc)
        month_start = (now - timedelta(days=now.day - 1)).replace(day=1)

        # Go back the required number of months
        for _ in range(months_back):
            month_start = month_start - timedelta(days=1)
            month_start = month_start.replace(day=1)

        # Calculate end of month
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1, day=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1, day=1)

        # Sum daily costs for the month
        total_cost = 0.0
        current = month_start
        while current < month_end:
            daily_cost = await self.get_agent_daily_cost(agent_id, current)
            total_cost += daily_cost
            current = current + timedelta(days=1)

        return total_cost

    async def get_cost_report(
        self,
        agent_id: str,
        period: str = "monthly",  # daily, weekly, monthly
    ) -> Dict[str, Any]:
        """
        Get detailed cost report for an agent.

        Args:
            agent_id: Agent ID
            period: Reporting period

        Returns:
            dict: Cost breakdown by model, period, etc.

        PRODUCT VALUE: Actionable cost insights for agents and managers.
        """
        now = datetime.now(timezone.utc)

        if period == "daily":
            period_cost = await self.get_agent_daily_cost(agent_id, now)
            period_label = now.date().isoformat()
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            period_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif period == "weekly":
            period_cost = await self.get_agent_weekly_cost(agent_id, 0)
            week_start = now - timedelta(days=now.weekday())
            period_label = f"{week_start.date()} to {now.date()}"
            period_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            period_end = now
        else:  # monthly
            period_cost = await self.get_agent_monthly_cost(agent_id, 0)
            period_label = f"{now.year}-{now.month:02d}"
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if now.month == 12:
                period_end = now.replace(year=now.year + 1, month=1, day=1)
            else:
                period_end = now.replace(month=now.month + 1, day=1)

        # Get model breakdown from database
        model_breakdown = {}
        if self.db:
            try:
                rows = await self.db.fetch(
                    """
                    SELECT model, SUM(estimated_cost) as total_cost, COUNT(*) as request_count
                    FROM cost_records
                    WHERE agent_id = $1 AND recorded_at >= $2 AND recorded_at < $3
                    GROUP BY model
                    ORDER BY total_cost DESC
                    """,
                    agent_id,
                    period_start,
                    period_end,
                )
                model_breakdown = {
                    row["model"]: {
                        "cost": float(row["total_cost"]),
                        "requests": row["request_count"],
                    }
                    for row in rows
                }
            except Exception as e:
                logger.warning(f"Failed to fetch model breakdown: {e}")

        # Get cost savings from routing
        cost_savings = 0.0
        if self.db:
            try:
                result = await self.db.fetchval(
                    """
                    SELECT COALESCE(SUM(cost_savings), 0)
                    FROM cost_records
                    WHERE agent_id = $1 AND cost_savings IS NOT NULL
                    AND recorded_at >= $2 AND recorded_at < $3
                    """,
                    agent_id,
                    period_start,
                    period_end,
                )
                cost_savings = float(result) if result else 0.0
            except Exception as e:
                logger.warning(f"Failed to fetch cost savings: {e}")

        report = {
            "agent_id": agent_id,
            "period": period,
            "period_label": period_label,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "total_cost": round(period_cost, 2),
            "cost_savings_from_routing": round(cost_savings, 2),
            "model_breakdown": model_breakdown,
            "generated_at": now.isoformat(),
        }

        logger.info(
            f"Cost report generated: agent={agent_id}, period={period}, "
            f"total_cost=${period_cost:.2f}, savings=${cost_savings:.2f}"
        )

        return report

    async def get_savings_report(self) -> Dict[str, Any]:
        """
        Get system-wide report on cost savings from intelligent routing.

        PRODUCT VALUE: Demonstrates ROI of the routing system.
        """
        now = datetime.now(timezone.utc)

        if not self.db:
            return {"error": "Database not available"}

        try:
            # Get total savings
            total_savings = await self.db.fetchval(
                """
                SELECT COALESCE(SUM(cost_savings), 0)
                FROM cost_records
                WHERE cost_savings IS NOT NULL
                """
            )

            # Get by model
            model_stats = await self.db.fetch(
                """
                SELECT
                    requested_model,
                    model,
                    COUNT(*) as routed_count,
                    SUM(cost_savings) as total_savings
                FROM cost_records
                WHERE cost_savings IS NOT NULL AND requested_model IS NOT NULL
                GROUP BY requested_model, model
                ORDER BY total_savings DESC
                """
            )

            # Get top agents by savings
            top_agents = await self.db.fetch(
                """
                SELECT
                    agent_id,
                    SUM(cost_savings) as total_savings,
                    COUNT(*) as routed_requests
                FROM cost_records
                WHERE cost_savings IS NOT NULL
                GROUP BY agent_id
                ORDER BY total_savings DESC
                LIMIT 10
                """
            )

            # Get daily trend
            daily_trend = await self.db.fetch(
                """
                SELECT
                    DATE(recorded_at) as date,
                    SUM(cost_savings) as daily_savings,
                    COUNT(*) as request_count
                FROM cost_records
                WHERE cost_savings IS NOT NULL
                GROUP BY DATE(recorded_at)
                ORDER BY date DESC
                LIMIT 30
                """
            )

            return {
                "total_system_savings": round(float(total_savings) if total_savings else 0, 2),
                "routing_decisions": [
                    {
                        "requested_model": row["requested_model"],
                        "routed_to": row["model"],
                        "count": row["routed_count"],
                        "total_savings": round(float(row["total_savings"]), 2),
                    }
                    for row in model_stats
                ],
                "top_agents": [
                    {
                        "agent_id": row["agent_id"],
                        "total_savings": round(float(row["total_savings"]), 2),
                        "routed_requests": row["routed_requests"],
                    }
                    for row in top_agents
                ],
                "daily_trend": [
                    {
                        "date": row["date"].isoformat(),
                        "savings": round(float(row["daily_savings"]), 2),
                        "requests": row["request_count"],
                    }
                    for row in daily_trend
                ],
                "generated_at": now.isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to generate savings report: {e}")
            return {
                "error": str(e),
                "generated_at": now.isoformat(),
            }

    async def get_system_daily_cost(self) -> float:
        """Get total system cost for today."""
        if not self.redis:
            return 0.0

        today = datetime.now(timezone.utc).date()
        key = f"cost:total:{today}"
        cost = await self.redis.get(key)
        return float(cost) if cost else 0.0

    async def detect_cost_anomaly(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Detect unusual spending patterns for an agent.

        Product Rationale: Alerts to potential runaway processes or abuse.

        Returns anomaly info if detected, None otherwise.
        """
        if not self.db:
            return None

        try:
            # Get agent's weekly average
            weekly_average = await self.get_agent_weekly_cost(agent_id, weeks_back=4)
            avg_per_week = weekly_average / 4

            # Get current week cost
            current_week = await self.get_agent_weekly_cost(agent_id, weeks_back=0)

            # Threshold: 3x normal spending
            threshold = avg_per_week * 3

            if current_week > threshold:
                return {
                    "agent_id": agent_id,
                    "anomaly_type": "high_spending",
                    "current_week_cost": round(current_week, 2),
                    "average_week_cost": round(avg_per_week, 2),
                    "threshold": round(threshold, 2),
                    "increase_percent": round(
                        ((current_week - avg_per_week) / avg_per_week * 100), 1
                    ),
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }

            return None

        except Exception as e:
            logger.warning(f"Anomaly detection failed for {agent_id}: {e}")
            return None
