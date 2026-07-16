"""
Pydantic request/response schemas.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

VALID_CHANNELS = {"app", "email", "twitter_dm"}
VALID_COMPLAINANT_TYPES = {"customer", "driver"}
VALID_STATUSES = {"open", "in_progress", "resolved"}
VALID_URGENCY = {"low", "medium", "high", "critical"}
VALID_TEAMS = {
    "support",
    "ops",
    "trust_and_safety",
    "finance",
    "hr_driver_relations",
    "legal",
    "none",
}


class ComplaintIngest(BaseModel):
    channel: str
    customer_identifier: str = Field(min_length=1, max_length=255)
    complainant_type: str
    raw_message: str = Field(min_length=1)

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v):
        if v not in VALID_CHANNELS:
            raise ValueError(
                f"channel must be one of {sorted(VALID_CHANNELS)}, got '{v}'"
            )
        return v

    @field_validator("complainant_type")
    @classmethod
    def validate_complainant_type(cls, v):
        if v not in VALID_COMPLAINANT_TYPES:
            raise ValueError(
                f"complainant_type must be one of {sorted(VALID_COMPLAINANT_TYPES)}, got '{v}'"
            )
        return v

    @field_validator("raw_message")
    @classmethod
    def validate_message_not_blank(cls, v):
        if not v or not v.strip():
            raise ValueError("raw_message cannot be empty or whitespace-only")
        return v


class ClassificationOut(BaseModel):
    id: str
    complaint_id: str
    sub_index: int
    category: str
    urgency: str
    routed_team: str
    reasoning: str
    is_noise: bool
    overridden: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ComplaintOut(BaseModel):
    id: str
    channel: str
    customer_identifier: str
    complainant_type: str
    raw_message: str
    status: str
    created_at: datetime
    updated_at: datetime
    classifications: List[ClassificationOut] = []

    class Config:
        from_attributes = True


class QueueItem(BaseModel):
    classification_id: str
    complaint_id: str
    sub_index: int
    category: str
    urgency: str
    routed_team: str
    reasoning: str
    is_noise: bool
    overridden: bool
    channel: str
    customer_identifier: str
    complainant_type: str
    raw_message: str
    status: str
    created_at: datetime


class StatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
        return v


class ClassificationOverride(BaseModel):
    category: Optional[str] = None
    urgency: Optional[str] = None
    routed_team: Optional[str] = None
    reasoning: Optional[str] = None
    is_noise: Optional[bool] = None

    @field_validator("urgency")
    @classmethod
    def validate_urgency(cls, v):
        if v is not None and v not in VALID_URGENCY:
            raise ValueError(f"urgency must be one of {sorted(VALID_URGENCY)}")
        return v

    @field_validator("routed_team")
    @classmethod
    def validate_team(cls, v):
        if v is not None and v not in VALID_TEAMS:
            raise ValueError(f"routed_team must be one of {sorted(VALID_TEAMS)}")
        return v
