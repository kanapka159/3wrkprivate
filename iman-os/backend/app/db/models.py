from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from .database import Base


class Campaign(Base):
    """Campaign model storing Smartlead campaign data."""
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    smartlead_id = Column(Integer, unique=True, index=True, nullable=False)
    name = Column(String(500), nullable=False)
    status = Column(String(50), default="draft")
    client_id = Column(Integer, nullable=True)
    client_name = Column(String(255), nullable=True)

    # Campaign settings
    timezone = Column(String(100), nullable=True)
    track_settings = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime, nullable=True)

    # Relationships
    analytics = relationship("CampaignAnalytics", back_populates="campaign", cascade="all, delete-orphan")
    leads = relationship("Lead", back_populates="campaign", cascade="all, delete-orphan")


class CampaignAnalytics(Base):
    """Campaign analytics/statistics model."""
    __tablename__ = "campaign_analytics"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    date = Column(DateTime, nullable=True)  # For daily analytics, null for aggregate

    # Core metrics
    sent_count = Column(Integer, default=0)
    unique_sent_count = Column(Integer, default=0)
    open_count = Column(Integer, default=0)
    unique_open_count = Column(Integer, default=0)
    click_count = Column(Integer, default=0)
    unique_click_count = Column(Integer, default=0)
    reply_count = Column(Integer, default=0)
    unique_reply_count = Column(Integer, default=0)
    bounce_count = Column(Integer, default=0)
    unsubscribe_count = Column(Integer, default=0)

    # Calculated rates (stored for quick access)
    open_rate = Column(Float, default=0.0)
    click_rate = Column(Float, default=0.0)
    reply_rate = Column(Float, default=0.0)
    bounce_rate = Column(Float, default=0.0)

    # Lead counts by category
    interested_count = Column(Integer, default=0)
    not_interested_count = Column(Integer, default=0)
    meeting_booked_count = Column(Integer, default=0)
    meeting_completed_count = Column(Integer, default=0)
    closed_count = Column(Integer, default=0)
    out_of_office_count = Column(Integer, default=0)
    wrong_person_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    campaign = relationship("Campaign", back_populates="analytics")


class Lead(Base):
    """Lead model for campaign statistics."""
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    smartlead_id = Column(Integer, unique=True, index=True, nullable=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)

    # Lead info
    email = Column(String(255), nullable=False, index=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    company_name = Column(String(255), nullable=True)

    # Status
    status = Column(String(50), default="active")
    lead_category = Column(String(100), nullable=True)

    # Engagement
    email_sent = Column(Boolean, default=False)
    email_opened = Column(Boolean, default=False)
    email_clicked = Column(Boolean, default=False)
    email_replied = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    campaign = relationship("Campaign", back_populates="leads")


class SyncLog(Base):
    """Log of sync operations for tracking and debugging."""
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True, index=True)
    sync_type = Column(String(50), nullable=False)  # full, campaigns, analytics, leads
    status = Column(String(20), nullable=False)  # started, completed, failed
    campaigns_synced = Column(Integer, default=0)
    leads_synced = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
