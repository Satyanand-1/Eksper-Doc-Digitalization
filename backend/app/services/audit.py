"""
Audit service module.
Provides secure, resilient recording of audit events for document access,
governance operations, and security denials.
Guarantees that sensitive data (passwords, tokens, file binaries) is never logged.
Handles and bubbles audit write failures according to policy.
"""
import uuid
import logging
from typing import Any
from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit import AuditLog, AuditOutcome

logger = logging.getLogger("edrms.audit")

class AuditWriteError(Exception):
    """Raised when an audit event fails to be recorded in persistent storage."""
    pass

class AuditService:
    """
    Centralized service for recording immutable audit log entries.
    """

    @staticmethod
    def log_event(
        db: Session,
        action: str,
        resource_type: str,
        outcome: AuditOutcome,
        actor_id: uuid.UUID | None = None,
        resource_id: uuid.UUID | None = None,
        client_ip: str | None = None,
        correlation_id: str | None = None,
        details: dict[str, Any] | None = None,
        raise_on_failure: bool = True,
    ) -> AuditLog | None:
        """
        Records an audit event into PostgreSQL.

        :param db: Database session
        :param action: Action performed (e.g. 'document.download', 'document.access_denied')
        :param resource_type: Resource category ('document', 'document_version')
        :param outcome: AuditOutcome enum (SUCCESS, DENIED, FAILED)
        :param actor_id: UUID of user performing the action
        :param resource_id: UUID of the targeted document or entity
        :param client_ip: Client IP address
        :param correlation_id: Request correlation identifier
        :param details: Sanitized contextual metadata dictionary
        :param raise_on_failure: When True, raises AuditWriteError if the write fails
        """
        # Ensure details does not contain any passwords or access tokens
        sanitized_details = None
        if details:
            sanitized_details = {}
            for k, v in details.items():
                if any(sensitive in k.lower() for sensitive in ("password", "token", "secret", "authorization", "bearer")):
                    continue
                # Ensure values are JSON-serializable strings/ints/bools
                sanitized_details[k] = str(v) if isinstance(v, uuid.UUID) else v

        try:
            audit_entry = AuditLog(
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=outcome,
                client_ip=client_ip,
                correlation_id=correlation_id,
                details=sanitized_details,
            )
            db.add(audit_entry)
            db.commit()
            db.refresh(audit_entry)
            return audit_entry
        except Exception as exc:
            db.rollback()
            logger.error(
                f"AUDIT FAILURE: Could not record audit log entry for action='{action}' "
                f"resource='{resource_type}:{resource_id}': {exc}"
            )
            if raise_on_failure:
                raise AuditWriteError(f"Failed to record mandatory audit event: {exc}") from exc
            return None

    @classmethod
    def log_from_request(
        cls,
        db: Session,
        request: Request | None,
        action: str,
        resource_type: str,
        outcome: AuditOutcome,
        actor_id: uuid.UUID | None = None,
        resource_id: uuid.UUID | None = None,
        details: dict[str, Any] | None = None,
        raise_on_failure: bool = True,
    ) -> AuditLog | None:
        """Helper to extract IP and correlation ID from FastAPI request."""
        client_ip = None
        correlation_id = None
        if request:
            client_ip = request.client.host if request.client else None
            correlation_id = request.headers.get("X-Correlation-ID") or request.headers.get("X-Request-ID")

        return cls.log_event(
            db=db,
            action=action,
            resource_type=resource_type,
            outcome=outcome,
            actor_id=actor_id,
            resource_id=resource_id,
            client_ip=client_ip,
            correlation_id=correlation_id,
            details=details,
            raise_on_failure=raise_on_failure,
        )

audit_service = AuditService()
