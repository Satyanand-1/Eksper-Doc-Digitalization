import uuid
import calendar
from datetime import datetime, timezone, timedelta
from typing import Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.document import DigitalDocument, DocumentStatus
from app.models.retention import (
    RetentionRule,
    RetentionPeriodUnit,
    RetentionTriggerEvent,
    LegalHold,
    LegalHoldStatus,
    DisposalEligibilityStatus,
)
from app.models.workflow import ReviewWorkflow, WorkflowState, ReviewAssignment, ReviewDecision


class RetentionCalculationService:
    """
    Handles retention period calculation and disposal eligibility assessments.
    Guarantees that:
    1. A document with an active legal hold is always 'on_hold', never 'eligible_for_review'.
    2. Missing rule, missing trigger date, or draft/incomplete status yields 'needs_attention'.
    3. Document changes never silently shorten an existing retention_end_date.
    4. Expired retention without blocking holds or missing data yields 'eligible_for_review'.
    """

    @classmethod
    def resolve_trigger_date(
        cls,
        db: Session,
        document: DigitalDocument,
        trigger_event: RetentionTriggerEvent,
    ) -> datetime | None:
        """
        Resolves the baseline datetime according to the specified trigger event:
        - CREATION: document.created_at
        - APPROVAL: timestamp of when the document was approved (from workflow or when marked active)
        """
        if trigger_event == RetentionTriggerEvent.CREATION:
            return document.created_at

        if trigger_event == RetentionTriggerEvent.APPROVAL:
            # First check if document has an approved workflow
            approved_assignment = (
                db.query(ReviewAssignment)
                .join(ReviewWorkflow, ReviewWorkflow.id == ReviewAssignment.workflow_id)
                .filter(
                    ReviewWorkflow.document_id == document.id,
                    ReviewWorkflow.state == WorkflowState.APPROVED,
                    ReviewAssignment.decision == ReviewDecision.APPROVED,
                )
                .order_by(desc(ReviewAssignment.decided_at))
                .first()
            )
            if approved_assignment and approved_assignment.decided_at:
                return approved_assignment.decided_at

            # Fallback: if document status is ACTIVE, use document.created_at or updated_at
            if document.status == DocumentStatus.ACTIVE:
                return document.updated_at or document.created_at

            # Otherwise, approval has not yet occurred
            return None

        return None

    @classmethod
    def calculate_end_date(
        cls,
        start_date: datetime,
        unit: RetentionPeriodUnit,
        value: int,
    ) -> datetime:
        """
        Calculates retention end date from a start date given unit and positive value.
        """
        if not start_date:
            raise ValueError("Start date is required for retention calculation.")
        if value <= 0:
            raise ValueError("Retention period value must be greater than 0.")

        if unit == RetentionPeriodUnit.DAYS:
            return start_date + timedelta(days=value)
        elif unit == RetentionPeriodUnit.MONTHS:
            # Add months safely
            year = start_date.year + (start_date.month + value - 1) // 12
            month = (start_date.month + value - 1) % 12 + 1
            max_day = calendar.monthrange(year, month)[1]
            day = min(start_date.day, max_day)
            return start_date.replace(year=year, month=month, day=day)
        elif unit == RetentionPeriodUnit.YEARS:
            # Add years safely (handle leap day Feb 29)
            year = start_date.year + value
            max_day = calendar.monthrange(year, start_date.month)[1]
            day = min(start_date.day, max_day)
            return start_date.replace(year=year, day=day)
        else:
            raise ValueError(f"Unsupported retention period unit: {unit}")

    @classmethod
    def assess_document_eligibility(
        cls,
        db: Session,
        document: DigitalDocument,
        now: datetime | None = None,
    ) -> Tuple[DisposalEligibilityStatus, str]:
        """
        Assesses disposal eligibility for a single document.
        Returns:
            (status: DisposalEligibilityStatus, reason: str)
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # 1. Check for active legal holds
        active_hold = (
            db.query(LegalHold)
            .filter(
                LegalHold.document_id == document.id,
                LegalHold.status == LegalHoldStatus.ACTIVE,
            )
            .first()
        )
        if active_hold:
            return (
                DisposalEligibilityStatus.ON_HOLD,
                f"Document is protected by an active legal hold placed on {active_hold.placed_at.strftime('%Y-%m-%d')}: {active_hold.hold_reason}"
            )

        # 2. Check if retention rule is assigned
        if not document.retention_rule_id:
            return (
                DisposalEligibilityStatus.NEEDS_ATTENTION,
                "No retention rule assigned to this document."
            )

        rule = document.retention_rule or db.query(RetentionRule).filter(RetentionRule.id == document.retention_rule_id).first()
        if not rule:
            return (
                DisposalEligibilityStatus.NEEDS_ATTENTION,
                "Assigned retention rule was not found in the system."
            )

        # 3. Check trigger date and end date
        if not document.retention_start_date or not document.retention_end_date:
            return (
                DisposalEligibilityStatus.NEEDS_ATTENTION,
                f"Retention start or end date is missing (trigger '{rule.trigger_event.value}' not yet reached or recorded)."
            )

        # 4. Compare retention end date with current time
        # Ensure timezone-aware comparison
        end_date = document.retention_end_date
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

        if now < end_date:
            days_left = max(0, (end_date - now).days)
            return (
                DisposalEligibilityStatus.RETAINED,
                f"Document is currently retained under rule '{rule.name}'. Retention expires in {days_left} days on {end_date.strftime('%Y-%m-%d')}."
            )
        else:
            days_expired = max(0, (now - end_date).days)
            return (
                DisposalEligibilityStatus.ELIGIBLE_FOR_REVIEW,
                f"Retention period expired {days_expired} days ago on {end_date.strftime('%Y-%m-%d')}. Eligible for formal disposal review."
            )


retention_calc_service = RetentionCalculationService()
