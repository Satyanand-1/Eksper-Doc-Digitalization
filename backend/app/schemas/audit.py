"""
Pydantic schemas for the Audit Log Viewer and Reporting.
Task 5.11: Audit Log Viewer and Administrative Reports.
"""
import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, ConfigDict
from app.models.audit import AuditOutcome


class AuditActorInfo(BaseModel):
    """Safe, non-sensitive actor presentation model."""
    id: uuid.UUID
    email: str
    full_name: str
    department: str | None = None
    role: str

    model_config = ConfigDict(from_attributes=True)


class AuditLogSummaryResponse(BaseModel):
    """
    Structured summary of an audit log entry for list views.
    Never exposes internal storage keys, raw file blobs, tokens, or password hashes.
    """
    id: uuid.UUID = Field(..., description="Unique audit event UUID")
    action: str = Field(..., description="Action performed (e.g. 'document.upload', 'workflow.approved')")
    resource_type: str = Field(..., description="Resource category ('document', 'workflow', 'user', etc.)")
    resource_id: uuid.UUID | None = Field(None, description="Target resource UUID")
    outcome: AuditOutcome = Field(..., description="Action outcome ('success', 'denied', 'failed')")
    actor_id: uuid.UUID | None = Field(None, description="Actor user UUID if authenticated")
    actor: AuditActorInfo | None = Field(None, description="Safe actor profile details")
    client_ip: str | None = Field(None, description="Client IP address if available")
    correlation_id: str | None = Field(None, description="Request correlation identifier")
    created_at: datetime = Field(..., description="Timestamp of the event in UTC")

    model_config = ConfigDict(from_attributes=True)


class AuditLogDetailResponse(AuditLogSummaryResponse):
    """
    Detailed audit log event including sanitized structured context details.
    """
    details: dict[str, Any] | None = Field(None, description="Sanitized contextual metadata dictionary")


class PaginatedAuditLogsResponse(BaseModel):
    """
    Paginated audit log listing response.
    """
    items: list[AuditLogSummaryResponse] = Field(..., description="List of audit records on the current page")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Page size limit")
    total: int = Field(..., description="Total matching audit records count")
    total_pages: int = Field(..., description="Total pages available")

    model_config = ConfigDict(from_attributes=True)


class AuditReportSummaryResponse(BaseModel):
    """
    Aggregate summary metrics for the audit log viewer.
    """
    total_events: int = Field(..., description="Total audit events matching the criteria")
    events_by_action: dict[str, int] = Field(default_factory=dict, description="Event counts grouped by action type")
    events_by_outcome: dict[str, int] = Field(default_factory=dict, description="Event counts grouped by outcome")
    recent_security_events: list[AuditLogSummaryResponse] = Field(
        default_factory=list,
        description="Recent security-sensitive administrative or denial actions",
    )
