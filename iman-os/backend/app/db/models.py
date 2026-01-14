"""
IMAN OS Database Models

SQLAlchemy models for campaign analytics dashboard.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, Boolean,
    ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from .database import Base


class Campaign(Base):
    """Campaign model storing Smartlead campaign data."""
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    smartlead_id = Column(Integer, unique=True, index=True, nullable=False)
    name = Column(String(500), nullable=False)
    status = Column(String(50), default="draft")
    client_id = Column(Integer, nullable=True, index=True)
    client_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=True)  # Actual creation date from Smartlead
    local_created_at = Column(DateTime, default=datetime.utcnow)  # When added to our DB
    last_synced_at = Column(DateTime, nullable=True)
    is_hidden = Column(Boolean, default=False, index=True)

    # Relationships
    daily_stats = relationship("CampaignDailyStats", back_populates="campaign", cascade="all, delete-orphan")
    sequences = relationship("Sequence", back_populates="campaign", cascade="all, delete-orphan")
    lead_replies = relationship("LeadReply", back_populates="campaign", cascade="all, delete-orphan")
    suggestions = relationship("Suggestion", back_populates="campaign", cascade="all, delete-orphan")


class CampaignDailyStats(Base):
    """Daily statistics for campaigns."""
    __tablename__ = "campaign_daily_stats"
    __table_args__ = (
        UniqueConstraint("campaign_id", "date", name="uq_campaign_date"),
        Index("ix_campaign_daily_stats_date", "date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(DateTime, nullable=False)

    # Core metrics
    sent_count = Column(Integer, default=0)
    reply_count = Column(Integer, default=0)
    unique_sent = Column(Integer, default=0)
    unique_replied = Column(Integer, default=0)
    positive_replies = Column(Integer, default=0)
    bounce_count = Column(Integer, default=0)
    open_count = Column(Integer, default=0)
    click_count = Column(Integer, default=0)

    # Relationships
    campaign = relationship("Campaign", back_populates="daily_stats")


class Sequence(Base):
    """Email sequences for campaigns."""
    __tablename__ = "sequences"

    id = Column(Integer, primary_key=True, index=True)
    smartlead_id = Column(Integer, nullable=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    seq_number = Column(Integer, nullable=False)
    variant_label = Column(String(100), nullable=True)
    subject = Column(String(1000), nullable=True)
    email_body = Column(Text, nullable=True)
    sent_count = Column(Integer, default=0)
    reply_count = Column(Integer, default=0)

    # Relationships
    campaign = relationship("Campaign", back_populates="sequences")


class LeadReply(Base):
    """Lead replies tracking."""
    __tablename__ = "lead_replies"
    __table_args__ = (
        UniqueConstraint("campaign_id", "lead_email", name="uq_campaign_lead_email"),
        Index("ix_lead_replies_category", "lead_category"),
    )

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_email = Column(String(255), nullable=False, index=True)
    lead_name = Column(String(255), nullable=True)
    lead_category = Column(String(100), nullable=True)
    first_reply_time = Column(DateTime, nullable=True)
    is_positive = Column(Boolean, default=False)
    sequence_number = Column(Integer, nullable=True)
    variant_id = Column(Integer, nullable=True)

    # Relationships
    campaign = relationship("Campaign", back_populates="lead_replies")


class SyncLog(Base):
    """Log of sync operations."""
    __tablename__ = "sync_log"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="started")  # started, completed, failed
    campaigns_synced = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)


class Suggestion(Base):
    """AI-generated suggestions for campaign improvement."""
    __tablename__ = "suggestions"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    suggestion = Column(Text, nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    applied_at = Column(DateTime, nullable=True)
    applied = Column(Boolean, default=False)

    # Relationships
    campaign = relationship("Campaign", back_populates="suggestions")
