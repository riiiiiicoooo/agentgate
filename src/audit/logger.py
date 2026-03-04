"""
Audit Logger

Structured audit event capture with context enrichment and multi-sink export.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from uuid import uuid4
from collections import deque

logger = logging.getLogger(__name__)


class AuditEvent:
    """Represents an audit log entry."""

    def __init__(
        self,
        event_type: str,
        actor: str,
        resource: str,
        action: str,
        result: str,
        details: Optional[Dict[str, Any]] = None,
        severity: str = "info",
    ):
        self.event_id = f"evt_{uuid4()}"
        self.timestamp = datetime.now(timezone.utc)
        self.event_type = event_type
        self.actor = actor
        self.resource = resource
        self.action = action
        self.result = result
        self.details = details or {}
        self.severity = severity

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "actor": self.actor,
            "resource": self.resource,
            "action": self.action,
            "result": self.result,
            "severity": self.severity,
            "details": self.details,
        }

    def to_json(self) -> str:
        """Convert to JSON."""
        return json.dumps(self.to_dict())


class AuditBuffer:
    """In-memory buffer for audit events."""

    def __init__(self, max_size: int = 10000):
        self.buffer: deque = deque(maxlen=max_size)
        self.max_size = max_size

    def append(self, event: AuditEvent) -> None:
        """Add event to buffer."""
        self.buffer.append(event)

    def get_all(self) -> List[AuditEvent]:
        """Get all events in buffer."""
        return list(self.buffer)

    def get_since(self, timestamp: datetime) -> List[AuditEvent]:
        """Get events since timestamp."""
        return [e for e in self.buffer if e.timestamp >= timestamp]

    def clear(self) -> None:
        """Clear buffer."""
        self.buffer.clear()

    def size(self) -> int:
        """Get buffer size."""
        return len(self.buffer)


class AuditLogger:
    """
    Structured audit logging system.

    Captures:
    - Authentication events
    - Authorization decisions
    - Resource access
    - Configuration changes
    - Security events

    Exports to:
    - Local buffer
    - SIEM (Splunk, Datadog)
    - S3 for compliance
    """

    def __init__(self, buffer_size: int = 10000):
        self.buffer = AuditBuffer(max_size=buffer_size)
        self.exporters: Dict[str, Any] = {}
        self.is_initialized = False

        logger.info(f"AuditLogger initialized with buffer size {buffer_size}")

    async def init(self) -> None:
        """Initialize audit system."""
        self.is_initialized = True
        logger.info("Audit system initialized")

    async def log(
        self,
        event_type: str,
        actor: str,
        resource: str,
        action: str,
        result: str,
        details: Optional[Dict[str, Any]] = None,
        severity: str = "info",
    ) -> str:
        """
        Log an audit event.

        Args:
            event_type: Type of event (auth, access, change, etc.)
            actor: Actor (agent ID or user)
            resource: Resource affected
            action: Action performed
            result: Result (success, failure)
            details: Additional details
            severity: Severity level (info, warning, error, critical)

        Returns:
            str: Event ID
        """
        event = AuditEvent(
            event_type=event_type,
            actor=actor,
            resource=resource,
            action=action,
            result=result,
            details=details,
            severity=severity,
        )

        # Add to buffer
        self.buffer.append(event)

        # Export to sinks
        await self._export_event(event)

        logger.debug(f"Audit event logged: {event.event_id}")

        return event.event_id

    async def _export_event(self, event: AuditEvent) -> None:
        """Export event to configured exporters."""
        for name, exporter in self.exporters.items():
            try:
                await exporter.export(event)
            except Exception as e:
                logger.error(f"Export failed ({name}): {e}")

    def register_exporter(self, name: str, exporter: Any) -> None:
        """Register an exporter."""
        self.exporters[name] = exporter
        logger.info(f"Exporter registered: {name}")

    def get_events(
        self,
        event_type: Optional[str] = None,
        actor: Optional[str] = None,
        resource: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query audit events.

        Args:
            event_type: Filter by event type
            actor: Filter by actor
            resource: Filter by resource
            severity: Filter by severity
            limit: Max results

        Returns:
            List of matching events
        """
        events = self.buffer.get_all()

        # Apply filters
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if actor:
            events = [e for e in events if e.actor == actor]
        if resource:
            events = [e for e in events if e.resource == resource]
        if severity:
            events = [e for e in events if e.severity == severity]

        # Return last N events (most recent first)
        return [e.to_dict() for e in reversed(events[-limit:])]

    async def flush(self) -> None:
        """Flush all events to exporters."""
        logger.info(f"Flushing {self.buffer.size()} audit events")

        for event in self.buffer.get_all():
            await self._export_event(event)

    def get_stats(self) -> Dict[str, Any]:
        """Get audit statistics."""
        events = self.buffer.get_all()

        return {
            "total_events": len(events),
            "event_types": self._count_by_field(events, "event_type"),
            "actors": self._count_by_field(events, "actor"),
            "severities": self._count_by_field(events, "severity"),
            "success_count": len([e for e in events if e.result == "success"]),
            "failure_count": len([e for e in events if e.result == "failure"]),
        }

    @staticmethod
    def _count_by_field(events: List[AuditEvent], field: str) -> Dict[str, int]:
        """Count events by field value."""
        counts = {}
        for event in events:
            value = getattr(event, field)
            counts[value] = counts.get(value, 0) + 1
        return counts


class SplunkExporter:
    """Export events to Splunk."""

    def __init__(self, hec_url: str, hec_token: str):
        self.hec_url = hec_url
        self.hec_token = hec_token

    async def export(self, event: AuditEvent) -> None:
        """Export event to Splunk."""
        # In production, use splunk_sdk
        logger.debug(f"Exporting event to Splunk: {event.event_id}")


class DatadogExporter:
    """Export events to Datadog."""

    def __init__(self, api_key: str, site: str = "datadoghq.com"):
        self.api_key = api_key
        self.site = site

    async def export(self, event: AuditEvent) -> None:
        """Export event to Datadog."""
        # In production, use datadog SDK
        logger.debug(f"Exporting event to Datadog: {event.event_id}")


class S3Exporter:
    """Export events to S3 for compliance."""

    def __init__(self, bucket: str, prefix: str = "audit-logs"):
        self.bucket = bucket
        self.prefix = prefix
        self.batch_size = 1000
        self.batch: List[AuditEvent] = []

    async def export(self, event: AuditEvent) -> None:
        """Buffer event for S3 export."""
        self.batch.append(event)

        if len(self.batch) >= self.batch_size:
            await self._flush_batch()

    async def _flush_batch(self) -> None:
        """Write batch to S3."""
        if not self.batch:
            return

        # In production, upload to S3
        logger.info(f"Flushing {len(self.batch)} events to S3")
        self.batch.clear()


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


async def init():
    """Initialize global audit logger."""
    global _audit_logger
    _audit_logger = AuditLogger()
    await _audit_logger.init()


def get_logger() -> AuditLogger:
    """Get global audit logger."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


async def log_event(
    event_type: str,
    actor: str,
    resource: str,
    action: str,
    result: str,
    details: Optional[Dict[str, Any]] = None,
    severity: str = "info",
) -> str:
    """Log an event using global logger."""
    logger_instance = get_logger()
    return await logger_instance.log(
        event_type=event_type,
        actor=actor,
        resource=resource,
        action=action,
        result=result,
        details=details,
        severity=severity,
    )
