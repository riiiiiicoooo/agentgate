"""
Audit & Compliance Endpoints

Audit log queries, exports, and compliance report generation (SOC 2, HIPAA, etc.)
"""

import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from enum import Enum

from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.auth import get_current_agent, AgentCredentials

logger = logging.getLogger(__name__)

router = APIRouter()

# Models
class AuditEventType(str, Enum):
    """Types of auditabl events."""
    AGENT_CREATED = "agent_created"
    AGENT_DELETED = "agent_deleted"
    AGENT_CREDENTIAL_ROTATED = "agent_credential_rotated"
    POLICY_CREATED = "policy_created"
    POLICY_UPDATED = "policy_updated"
    POLICY_DELETED = "policy_deleted"
    POLICY_EVALUATED = "policy_evaluated"
    SECRET_REQUESTED = "secret_requested"
    SECRET_ROTATED = "secret_rotated"
    SECRET_REVOKED = "secret_revoked"
    SECRET_ACCESSED = "secret_accessed"
    AUTH_FAILED = "auth_failed"
    AUTH_SUCCESS = "auth_success"
    POLICY_VIOLATION = "policy_violation"


class AuditEvent(BaseModel):
    """Audit event record."""
    event_id: str
    timestamp: datetime
    event_type: str
    actor_agent_id: str
    actor_ip: Optional[str]
    resource_type: str
    resource_id: str
    action: str
    status: str = Field(..., pattern="^(success|failure)$")
    details: dict
    severity: str = Field(..., pattern="^(info|warning|error|critical)$")

    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "evt_550e8400e29b41d4a716446655440000",
                "timestamp": "2026-03-04T14:30:00Z",
                "event_type": "secret_accessed",
                "actor_agent_id": "agent_123",
                "actor_ip": "192.168.1.1",
                "resource_type": "secret",
                "resource_id": "database/prod/password",
                "action": "read",
                "status": "success",
                "details": {
                    "lease_id": "lease_456",
                    "ttl_seconds": 3600,
                },
                "severity": "info",
            }
        }


class AuditQueryRequest(BaseModel):
    """Query parameters for audit logs."""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    event_type: Optional[str] = None
    actor_agent_id: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    status: Optional[str] = None
    severity: Optional[str] = None
    limit: int = Field(100, ge=1, le=10000)
    offset: int = Field(0, ge=0)


class AuditQueryResponse(BaseModel):
    """Paginated audit query results."""
    events: List[AuditEvent]
    total: int
    offset: int
    limit: int
    query_time_ms: float


class ComplianceReport(BaseModel):
    """Compliance report."""
    report_id: str
    generated_at: datetime
    compliance_framework: str
    organization: str
    period_start: datetime
    period_end: datetime
    findings: dict
    evidence_count: int
    summary: str


class SecurityIncident(BaseModel):
    """Security incident report."""
    incident_id: str
    timestamp: datetime
    severity: str
    incident_type: str
    description: str
    affected_resources: List[str]
    actor_agent_id: Optional[str]
    remediation_status: str


# In-memory audit storage
audit_events_db: List[AuditEvent] = []


def log_audit_event(
    event_type: str,
    actor_agent_id: str,
    resource_type: str,
    resource_id: str,
    action: str,
    status: str,
    details: dict,
    severity: str = "info",
    actor_ip: Optional[str] = None,
) -> str:
    """
    Internal function to log audit events.

    Args:
        event_type: Type of event
        actor_agent_id: Agent performing action
        resource_type: Type of resource affected
        resource_id: ID of resource
        action: Action performed
        status: Success or failure
        details: Additional details
        severity: Event severity level
        actor_ip: IP address of actor

    Returns:
        str: Event ID
    """
    from uuid import uuid4

    event_id = f"evt_{uuid4()}"
    now = datetime.now(timezone.utc)

    event = AuditEvent(
        event_id=event_id,
        timestamp=now,
        event_type=event_type,
        actor_agent_id=actor_agent_id,
        actor_ip=actor_ip,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        status=status,
        details=details,
        severity=severity,
    )

    audit_events_db.append(event)

    logger.info(
        f"Audit event logged: {event_type} on {resource_type}:{resource_id} "
        f"by {actor_agent_id} - {status}"
    )

    return event_id


@router.post(
    "/query",
    response_model=AuditQueryResponse,
    summary="Query audit logs",
)
async def query_audit_logs(
    request: AuditQueryRequest,
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> AuditQueryResponse:
    """
    Query audit logs with filtering and pagination.

    Requires audit:read permission.

    Args:
        request: Query parameters
        current_agent: Current authenticated agent

    Returns:
        AuditQueryResponse: Matching audit events

    Raises:
        HTTPException: If unauthorized
    """
    if not current_agent.has_scope("audit:read") and not current_agent.has_scope("*"):
        logger.warning(f"Unauthorized audit query by {current_agent.agent_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to query audit logs",
        )

    try:
        import time
        start_time = time.time()

        # Apply filters
        results = audit_events_db

        if request.start_time:
            results = [e for e in results if e.timestamp >= request.start_time]

        if request.end_time:
            results = [e for e in results if e.timestamp <= request.end_time]

        if request.event_type:
            results = [e for e in results if e.event_type == request.event_type]

        if request.actor_agent_id:
            results = [e for e in results if e.actor_agent_id == request.actor_agent_id]

        if request.resource_type:
            results = [e for e in results if e.resource_type == request.resource_type]

        if request.resource_id:
            results = [e for e in results if e.resource_id == request.resource_id]

        if request.status:
            results = [e for e in results if e.status == request.status]

        if request.severity:
            results = [e for e in results if e.severity == request.severity]

        total = len(results)
        paginated = results[request.offset : request.offset + request.limit]

        elapsed = (time.time() - start_time) * 1000  # ms

        logger.info(
            f"Audit query executed: {total} events found "
            f"by {current_agent.agent_id} ({elapsed:.2f}ms)"
        )

        return AuditQueryResponse(
            events=paginated,
            total=total,
            offset=request.offset,
            limit=request.limit,
            query_time_ms=elapsed,
        )

    except Exception as e:
        logger.error(f"Audit query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query audit logs",
        )


@router.get(
    "/export/csv",
    summary="Export audit logs as CSV",
)
async def export_audit_csv(
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    event_type: Optional[str] = Query(None),
    current_agent: AgentCredentials = Depends(get_current_agent),
):
    """
    Export audit logs in CSV format.

    Useful for SIEM ingestion, compliance audits, and analysis.

    Args:
        start_time: Filter by start time
        end_time: Filter by end time
        event_type: Filter by event type
        current_agent: Current authenticated agent

    Returns:
        StreamingResponse: CSV file

    Raises:
        HTTPException: If unauthorized
    """
    if not current_agent.has_scope("audit:read") and not current_agent.has_scope("*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        import csv
        import io

        # Apply filters
        events = audit_events_db

        if start_time:
            events = [e for e in events if e.timestamp >= start_time]
        if end_time:
            events = [e for e in events if e.timestamp <= end_time]
        if event_type:
            events = [e for e in events if e.event_type == event_type]

        # Generate CSV
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "event_id",
                "timestamp",
                "event_type",
                "actor_agent_id",
                "resource_type",
                "resource_id",
                "action",
                "status",
                "severity",
            ],
        )

        writer.writeheader()
        for event in events:
            writer.writerow({
                "event_id": event.event_id,
                "timestamp": event.timestamp.isoformat(),
                "event_type": event.event_type,
                "actor_agent_id": event.actor_agent_id,
                "resource_type": event.resource_type,
                "resource_id": event.resource_id,
                "action": event.action,
                "status": event.status,
                "severity": event.severity,
            })

        logger.info(f"Audit CSV exported ({len(events)} events) by {current_agent.agent_id}")

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_export.csv"},
        )

    except Exception as e:
        logger.error(f"Audit export failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export audit logs",
        )


@router.post(
    "/compliance/generate",
    response_model=ComplianceReport,
    summary="Generate compliance report",
)
async def generate_compliance_report(
    framework: str = Query(..., description="SOC2, HIPAA, PCI-DSS, etc."),
    organization: str = Query(...),
    period_days: int = Query(30, ge=1, le=365),
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> ComplianceReport:
    """
    Generate compliance report from audit logs.

    Generates evidence for SOC 2, HIPAA, PCI-DSS, and other frameworks.

    Args:
        framework: Compliance framework
        organization: Organization name
        period_days: Report period in days
        current_agent: Current authenticated agent

    Returns:
        ComplianceReport: Compliance evidence report

    Raises:
        HTTPException: If unauthorized
    """
    if not current_agent.has_scope("audit:read") and not current_agent.has_scope("*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        from uuid import uuid4

        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=period_days)

        # Filter events from period
        period_events = [e for e in audit_events_db if e.timestamp >= period_start]

        # Generate framework-specific findings
        findings = {
            "total_events": len(period_events),
            "authentication_events": len([e for e in period_events if "auth" in e.event_type]),
            "policy_violations": len([e for e in period_events if e.severity == "critical"]),
            "credential_rotations": len([e for e in period_events if "credential_rotated" in e.event_type]),
            "access_control_changes": len([e for e in period_events if "policy" in e.event_type]),
        }

        report = ComplianceReport(
            report_id=f"report_{uuid4()}",
            generated_at=now,
            compliance_framework=framework,
            organization=organization,
            period_start=period_start,
            period_end=now,
            findings=findings,
            evidence_count=len(period_events),
            summary=f"Compliance report for {framework} covering {period_days} days. "
                   f"{findings['total_events']} audit events recorded. "
                   f"{findings['policy_violations']} policy violations detected.",
        )

        logger.info(
            f"Compliance report generated: {framework} for {organization} "
            f"by {current_agent.agent_id}"
        )

        return report

    except Exception as e:
        logger.error(f"Report generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate report",
        )


@router.get(
    "/incidents",
    response_model=List[SecurityIncident],
    summary="Get security incidents",
)
async def get_security_incidents(
    severity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=1000),
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> List[SecurityIncident]:
    """
    Retrieve security incidents and anomalies.

    Aggregates high-severity audit events into incidents for investigation.

    Args:
        severity: Filter by severity
        limit: Max results
        current_agent: Current authenticated agent

    Returns:
        List[SecurityIncident]: Security incidents

    Raises:
        HTTPException: If unauthorized
    """
    if not current_agent.has_scope("audit:read") and not current_agent.has_scope("*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        from uuid import uuid4

        # Create incidents from critical/error events
        incidents = []
        critical_events = [
            e for e in audit_events_db
            if e.severity in ["critical", "error"]
        ]

        if severity:
            critical_events = [e for e in critical_events if e.severity == severity]

        for event in critical_events[:limit]:
            incident = SecurityIncident(
                incident_id=f"incident_{uuid4()}",
                timestamp=event.timestamp,
                severity=event.severity,
                incident_type=event.event_type,
                description=f"{event.event_type}: {event.action} on {event.resource_id}",
                affected_resources=[event.resource_id],
                actor_agent_id=event.actor_agent_id,
                remediation_status="open",
            )
            incidents.append(incident)

        logger.info(f"Security incidents retrieved ({len(incidents)}) by {current_agent.agent_id}")

        return incidents

    except Exception as e:
        logger.error(f"Failed to get incidents: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get incidents",
        )


@router.get(
    "/stats",
    summary="Get audit statistics",
)
async def get_audit_statistics(
    current_agent: AgentCredentials = Depends(get_current_agent),
) -> dict:
    """
    Get audit log statistics.

    Provides high-level overview of audit activity.

    Args:
        current_agent: Current authenticated agent

    Returns:
        dict: Audit statistics

    Raises:
        HTTPException: If unauthorized
    """
    if not current_agent.has_scope("audit:read") and not current_agent.has_scope("*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        total_events = len(audit_events_db)
        success_count = len([e for e in audit_events_db if e.status == "success"])
        failure_count = len([e for e in audit_events_db if e.status == "failure"])

        event_types = {}
        for event in audit_events_db:
            event_types[event.event_type] = event_types.get(event.event_type, 0) + 1

        stats = {
            "total_events": total_events,
            "success_events": success_count,
            "failure_events": failure_count,
            "success_rate": (success_count / total_events * 100) if total_events > 0 else 0,
            "event_types": event_types,
            "unique_actors": len(set(e.actor_agent_id for e in audit_events_db)),
        }

        return stats

    except Exception as e:
        logger.error(f"Failed to get statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get statistics",
        )
