"""
Suggestion Engine Service

Generates actionable suggestions for campaign management based on performance thresholds.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Campaign, CampaignDailyStats, Suggestion

logger = logging.getLogger(__name__)


class SuggestionEngine:
    """Service for generating campaign improvement suggestions."""

    # Thresholds for campaign actions
    LOW_DATA_THRESHOLD = 200  # Minimum sends before making suggestions
    KEEP_THRESHOLD = 2.0      # >= 2% reply rate = green (keep running)
    MONITOR_THRESHOLD = 1.0   # >= 1% reply rate = yellow (monitor)
    PAUSE_THRESHOLD = 0.5     # >= 0.5% reply rate = orange (pause)
    # < 0.5% reply rate = red (kill)

    # Colors for suggestions
    COLOR_GREEN = "green"
    COLOR_YELLOW = "yellow"
    COLOR_ORANGE = "orange"
    COLOR_RED = "red"
    COLOR_GRAY = "gray"

    def __init__(self, db: AsyncSession):
        self.db = db

    def generate_suggestion(self, campaign_data: dict) -> dict:
        """
        Generate a suggestion based on campaign performance data.

        Args:
            campaign_data: Dictionary with campaign metrics including:
                - sent_count: Total emails sent
                - reply_rate: Reply rate as percentage
                - positive_rate: Positive reply rate (optional)
                - trend: "up", "down", or "flat" (optional)

        Returns:
            Dictionary with suggestion, reason, and color
        """
        sent_count = campaign_data.get("sent_count", 0)
        reply_rate = campaign_data.get("reply_rate", 0)

        # Not enough data
        if sent_count < self.LOW_DATA_THRESHOLD:
            return {
                "suggestion": "WAIT",
                "reason": f"Only {sent_count} emails sent. Need {self.LOW_DATA_THRESHOLD} for reliable analysis.",
                "color": self.COLOR_GRAY,
            }

        # KEEP - Green (>= 2% reply rate)
        if reply_rate >= self.KEEP_THRESHOLD:
            return {
                "suggestion": "KEEP",
                "reason": f"Strong performance with {reply_rate:.2f}% reply rate. Keep running.",
                "color": self.COLOR_GREEN,
            }

        # MONITOR - Yellow (>= 1% reply rate)
        if reply_rate >= self.MONITOR_THRESHOLD:
            return {
                "suggestion": "MONITOR",
                "reason": f"Reply rate at {reply_rate:.2f}%. Monitor closely for improvement.",
                "color": self.COLOR_YELLOW,
            }

        # PAUSE - Orange (>= 0.5% reply rate)
        if reply_rate >= self.PAUSE_THRESHOLD:
            return {
                "suggestion": "PAUSE",
                "reason": f"Low reply rate ({reply_rate:.2f}%). Consider pausing to optimize.",
                "color": self.COLOR_ORANGE,
            }

        # KILL - Red (< 0.5% reply rate)
        return {
            "suggestion": "KILL",
            "reason": f"Very low reply rate ({reply_rate:.2f}%). Stop campaign immediately.",
            "color": self.COLOR_RED,
        }

    def generate_warnings(self, campaign_data: dict) -> list[str]:
        """
        Generate warning messages based on campaign data.

        Args:
            campaign_data: Dictionary with campaign metrics including:
                - reply_rate: Current reply rate
                - previous_reply_rate: Reply rate from previous period (optional)
                - positive_rate: Positive reply rate (optional)
                - days_since_last_reply: Days since last reply (optional)
                - sent_count: Total emails sent

        Returns:
            List of warning strings
        """
        warnings = []
        sent_count = campaign_data.get("sent_count", 0)
        reply_rate = campaign_data.get("reply_rate", 0)
        previous_reply_rate = campaign_data.get("previous_reply_rate")
        positive_rate = campaign_data.get("positive_rate", 0)
        days_since_last_reply = campaign_data.get("days_since_last_reply")

        # Skip warnings if not enough data
        if sent_count < self.LOW_DATA_THRESHOLD:
            return warnings

        # Low Reply Rate warning
        if reply_rate < self.MONITOR_THRESHOLD:
            warnings.append("Low Reply Rate")

        # Declining warning - reply rate dropped significantly
        if previous_reply_rate is not None and previous_reply_rate > 0:
            decline_pct = ((previous_reply_rate - reply_rate) / previous_reply_rate) * 100
            if decline_pct >= 25:  # 25% or more decline
                warnings.append("Declining")

        # Low Quality warning - low positive rate among replies
        if reply_rate > 0 and positive_rate < 30:  # Less than 30% positive
            warnings.append("Low Quality")

        # Stalled warning - no replies in a while
        if days_since_last_reply is not None and days_since_last_reply >= 7:
            warnings.append("Stalled")

        return warnings

    async def get_campaign_data(self, campaign_id: int) -> Optional[dict]:
        """
        Get campaign data needed for suggestion generation.

        Args:
            campaign_id: Local campaign ID

        Returns:
            Dictionary with campaign metrics or None if not found
        """
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign:
            return None

        # Get aggregated stats
        stats = await self.db.execute(
            select(
                func.sum(CampaignDailyStats.unique_sent),
                func.sum(CampaignDailyStats.unique_replied),
                func.sum(CampaignDailyStats.positive_replies),
            ).where(CampaignDailyStats.campaign_id == campaign_id)
        )
        row = stats.one()

        sent = row[0] or 0
        replied = row[1] or 0
        positive = row[2] or 0

        reply_rate = (replied / sent * 100) if sent > 0 else 0
        positive_rate = (positive / replied * 100) if replied > 0 else 0

        # Get previous period stats (7-14 days ago) for trend
        cutoff_current = datetime.utcnow() - timedelta(days=7)
        cutoff_previous = datetime.utcnow() - timedelta(days=14)

        prev_stats = await self.db.execute(
            select(
                func.sum(CampaignDailyStats.unique_sent),
                func.sum(CampaignDailyStats.unique_replied),
            ).where(
                CampaignDailyStats.campaign_id == campaign_id,
                CampaignDailyStats.date >= cutoff_previous,
                CampaignDailyStats.date < cutoff_current,
            )
        )
        prev_row = prev_stats.one()
        prev_sent = prev_row[0] or 0
        prev_replied = prev_row[1] or 0
        previous_reply_rate = (prev_replied / prev_sent * 100) if prev_sent > 0 else None

        # Get days since last reply
        last_reply = await self.db.execute(
            select(func.max(CampaignDailyStats.date)).where(
                CampaignDailyStats.campaign_id == campaign_id,
                CampaignDailyStats.unique_replied > 0,
            )
        )
        last_reply_date = last_reply.scalar()
        days_since_last_reply = None
        if last_reply_date:
            days_since_last_reply = (datetime.utcnow().date() - last_reply_date).days

        return {
            "campaign_id": campaign_id,
            "campaign_name": campaign.name,
            "status": campaign.status,
            "sent_count": sent,
            "reply_count": replied,
            "positive_count": positive,
            "reply_rate": round(reply_rate, 2),
            "positive_rate": round(positive_rate, 2),
            "previous_reply_rate": round(previous_reply_rate, 2) if previous_reply_rate else None,
            "days_since_last_reply": days_since_last_reply,
        }

    async def get_campaigns_needing_action(self) -> list[dict]:
        """
        Get all campaigns that need attention with suggestions.

        Returns:
            List of campaigns with their suggestions and warnings
        """
        # Get all campaigns with stats
        subquery = (
            select(
                CampaignDailyStats.campaign_id,
                func.sum(CampaignDailyStats.unique_sent).label("total_sent"),
                func.sum(CampaignDailyStats.unique_replied).label("total_replied"),
                func.sum(CampaignDailyStats.positive_replies).label("total_positive"),
            )
            .group_by(CampaignDailyStats.campaign_id)
            .subquery()
        )

        result = await self.db.execute(
            select(Campaign, subquery)
            .join(subquery, Campaign.id == subquery.c.campaign_id)
            .where(Campaign.status == "STARTED")  # Only active campaigns
        )
        rows = result.all()

        campaigns_needing_action = []

        for row in rows:
            campaign = row[0]
            sent = row.total_sent or 0
            replied = row.total_replied or 0
            positive = row.total_positive or 0

            reply_rate = (replied / sent * 100) if sent > 0 else 0
            positive_rate = (positive / replied * 100) if replied > 0 else 0

            campaign_data = {
                "campaign_id": campaign.id,
                "campaign_name": campaign.name,
                "sent_count": sent,
                "reply_rate": reply_rate,
                "positive_rate": positive_rate,
            }

            suggestion = self.generate_suggestion(campaign_data)
            warnings = self.generate_warnings(campaign_data)

            # Only include campaigns that need action (not green/keep)
            if suggestion["color"] != self.COLOR_GREEN or warnings:
                campaigns_needing_action.append({
                    "campaign_id": campaign.id,
                    "smartlead_id": campaign.smartlead_id,
                    "campaign_name": campaign.name,
                    "status": campaign.status,
                    "sent_count": sent,
                    "reply_count": replied,
                    "reply_rate": round(reply_rate, 2),
                    "positive_rate": round(positive_rate, 2),
                    "suggestion": suggestion,
                    "warnings": warnings,
                })

        # Sort by severity (red first, then orange, yellow, gray)
        color_order = {
            self.COLOR_RED: 0,
            self.COLOR_ORANGE: 1,
            self.COLOR_YELLOW: 2,
            self.COLOR_GRAY: 3,
            self.COLOR_GREEN: 4,
        }
        campaigns_needing_action.sort(
            key=lambda x: color_order.get(x["suggestion"]["color"], 5)
        )

        return campaigns_needing_action

    async def save_suggestion(
        self,
        campaign_id: int,
        suggestion_text: str,
        reason: str,
    ) -> Suggestion:
        """Save a suggestion to the database."""
        suggestion = Suggestion(
            campaign_id=campaign_id,
            suggestion=suggestion_text,
            reason=reason,
        )
        self.db.add(suggestion)
        await self.db.flush()
        return suggestion

    async def mark_suggestion_applied(self, suggestion_id: int) -> Optional[Suggestion]:
        """Mark a suggestion as applied."""
        result = await self.db.execute(
            select(Suggestion).where(Suggestion.id == suggestion_id)
        )
        suggestion = result.scalar_one_or_none()

        if suggestion:
            suggestion.applied = True
            suggestion.applied_at = datetime.utcnow()

        return suggestion
