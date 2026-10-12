"""
Database models package for EDRMS.
Exports Base and domain models for Alembic autogeneration and application queries.
"""
from app.database import Base
from app.models.user import User, UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus, ExtractionStatus
from app.models.document_content import DocumentFileContent
from app.models.audit import AuditLog, AuditOutcome
from app.models.ocr_job import OCRJob, OCRJobStatus
from app.models.workflow import ReviewWorkflow, ReviewAssignment, WorkflowState, ReviewDecision
from app.models.notification import Notification, NotificationType
from app.models.retention import (
    RetentionRule,
    LegalHold,
    RetentionPeriodUnit,
    RetentionTriggerEvent,
    LegalHoldStatus,
    DisposalEligibilityStatus,
)
from app.models.physical_file import (
    PhysicalFile,
    PhysicalRecordType,
    PhysicalFileStatus,
    VALID_STATUS_TRANSITIONS,
)
from app.models.storage_location import (
    StorageLocation,
    LocationType,
    PERMITTED_PARENT_TYPES,
)
from app.models.custody import (
    FileCustodyRecord,
    FileMovementHistory,
    CustodyStatus,
    PhysicalMovementType,
)

__all__ = [
    "Base",
    "User",
    "UserRole",
    "DigitalDocument",
    "DocumentVersion",
    "DocumentFileContent",
    "DocumentStatus",
    "ExtractionStatus",
    "AuditLog",
    "AuditOutcome",
    "OCRJob",
    "OCRJobStatus",
    "ReviewWorkflow",
    "ReviewAssignment",
    "WorkflowState",
    "ReviewDecision",
    "Notification",
    "NotificationType",
    "RetentionRule",
    "LegalHold",
    "RetentionPeriodUnit",
    "RetentionTriggerEvent",
    "LegalHoldStatus",
    "DisposalEligibilityStatus",
    "PhysicalFile",
    "PhysicalRecordType",
    "PhysicalFileStatus",
    "VALID_STATUS_TRANSITIONS",
    "StorageLocation",
    "LocationType",
    "PERMITTED_PARENT_TYPES",
    "FileCustodyRecord",
    "FileMovementHistory",
    "CustodyStatus",
    "PhysicalMovementType",
]

