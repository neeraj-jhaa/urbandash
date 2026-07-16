"""
ORM models.

Complaint  -> the raw inbound message (one per customer/driver message).
Classification -> one or more classified "issues" extracted from a
                   complaint by Groq. A single complaint can yield
                   multiple linked Classification rows when it bundles
                   more than one distinct issue.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Enum as SAEnum,
)
from sqlalchemy.orm import relationship

from .database import Base


def gen_id() -> str:
    return uuid.uuid4().hex[:12]


class Channel(str, enum.Enum):
    app = "app"
    email = "email"
    twitter_dm = "twitter_dm"


class ComplainantType(str, enum.Enum):
    customer = "customer"
    driver = "driver"


class ComplaintStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"


class Urgency(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(String, primary_key=True, default=gen_id)
    channel = Column(SAEnum(Channel, native_enum=False), nullable=False)
    customer_identifier = Column(String, nullable=False)
    complainant_type = Column(
        SAEnum(ComplainantType, native_enum=False), nullable=False
    )
    raw_message = Column(Text, nullable=False)
    status = Column(
        SAEnum(ComplaintStatus, native_enum=False),
        nullable=False,
        default=ComplaintStatus.open,
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    classifications = relationship(
        "Classification",
        back_populates="complaint",
        cascade="all, delete-orphan",
        order_by="Classification.sub_index",
    )


class Classification(Base):
    __tablename__ = "classifications"

    id = Column(String, primary_key=True, default=gen_id)
    complaint_id = Column(String, ForeignKey("complaints.id"), nullable=False)
    sub_index = Column(Integer, nullable=False, default=0)

    category = Column(String, nullable=False)
    urgency = Column(SAEnum(Urgency, native_enum=False), nullable=False)
    routed_team = Column(String, nullable=False)
    reasoning = Column(Text, nullable=False)

    # True for praise / test-QA noise / low-signal messages that should
    # NOT be routed to an internal team, just surfaced in a separate view.
    is_noise = Column(Boolean, default=False, nullable=False)

    # Set to True once a human has manually reassigned this classification.
    overridden = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    complaint = relationship("Complaint", back_populates="classifications")
