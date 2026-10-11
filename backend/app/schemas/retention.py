import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.models.retention import (
    RetentionPeriodUnit,
    RetentionTriggerEvent,
    LegalHoldStatus,
    DisposalEligibilityStatus,
)


class RetentionRuleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Unique human-readable rule name")
    description: str | None = Field(None, max_length=1000, description="Optional rule description")
    classification: str | None = Field(None, max_length=100, description="Optional target document classification")
    retention_period_unit: RetentionPeriodUnit = Field(..., description="Duration unit: days, months, or years")
    retention_period_value: int = Field(..., gt=0, le=100000, description="Positive duration count")
    trigger_event: RetentionTriggerEvent = Field(..., description="Triggering lifecycle event (creation or approval)")


class RetentionRuleUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = Field(None, max_length=1000)
    classification: str | None = Field(None, max_length=100)
    retention_period_unit: RetentionPeriodUnit | None = None
    retention_period_value: int | None = Field(None, gt=0, le=100000)
    trigger_event: RetentionTriggerEvent | None = None
    is_active: bool | None = None


class RetentionRuleStatusUpdate(BaseModel):
    is_active: bool = Field(..., description="Active or inactive status")


class RetentionRuleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    classification: str | None = None
    retention_period_unit: RetentionPeriodUnit
    retention_period_value: int
    trigger_event: RetentionTriggerEvent
    is_active: bool
    created_by_id: uuid.UUID
    updated_by_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedRetentionRulesResponse(BaseModel):
    items: list[RetentionRuleResponse]
    page: int
    page_size: int
    total: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)


# Document Retention Assignment
class AssignRetentionRuleRequest(BaseModel):
    retention_rule_id: uuid.UUID = Field(..., description="UUID of the retention rule to assign")
    override_start_date: datetime | None = Field(None, description="Optional manual start date override")


class DocumentRetentionInfoResponse(BaseModel):
    document_id: uuid.UUID
    retention_rule: RetentionRuleResponse | None = None
    retention_trigger_date: datetime | None = None
    retention_start_date: datetime | None = None
    retention_end_date: datetime | None = None
    retention_assigned_at: datetime | None = None
    retention_assigned_by_id: uuid.UUID | None = None
    active_legal_hold_count: int = 0
    eligibility_status: DisposalEligibilityStatus
    eligibility_explanation: str

    model_config = ConfigDict(from_attributes=True)


# Legal Hold Schemas
class CreateLegalHoldRequest(BaseModel):
    hold_reason: str = Field(..., min_length=5, max_length=2000, description="Mandatory detailed reason for placing legal hold")


class ReleaseLegalHoldRequest(BaseModel):
    release_reason: str = Field(..., min_length=5, max_length=2000, description="Mandatory detailed reason for releasing legal hold")


class LegalHoldResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    hold_reason: str
    status: LegalHoldStatus
    placed_by_id: uuid.UUID
    placed_at: datetime
    released_by_id: uuid.UUID | None = None
    released_at: datetime | None = None
    release_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


# Disposal Eligibility Schemas
class DisposalEligibilityItemResponse(BaseModel):
    document_id: uuid.UUID
    document_reference: str
    title: str
    department: str
    classification: str
    status: str
    created_at: datetime
    retention_rule_id: uuid.UUID | None = None
    retention_rule_name: str | None = None
    retention_start_date: datetime | None = None
    retention_end_date: datetime | None = None
    is_expired: bool = False
    has_active_hold: bool = False
    active_hold_count: int = 0
    eligibility_status: DisposalEligibilityStatus
    eligibility_explanation: str

    model_config = ConfigDict(from_attributes=True)


class PaginatedDisposalEligibilityResponse(BaseModel):
    items: list[DisposalEligibilityItemResponse]
    page: int
    page_size: int
    total: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)
