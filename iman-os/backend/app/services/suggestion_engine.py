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

    # Thresholds for campaign actions (PROMPT 4 logic)
    WAIT_SENT_THRESHOLD = 100  # Minimum 7D sends before making suggestions

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

        PROMPT 4 Logic:
        - WAIT: sent7d < 100 (not enough data)
        - PAUSE: reply14d < 0.5 OR (reply7d < 0.8 AND positive < 5)
        - KEEP: reply7d > 3 AND positive > 40
        - MONITOR: reply7d >= 1 AND reply7d <= 3
        - Default: MONITOR

        Args:
            campaign_data: Dictionary with campaign metrics including:
                - sent_7d: Emails sent in last 7 days
                - reply_rate_7d: 7-day reply rate as percentage
                - reply_rate_14d: 14-day reply rate as percentage
                - positive_rate: Positive reply ratio (interested/totalReplies)

        Returns:
            Dictionary with suggestion, reason, and color
        """
        # Extract metrics
        sent_7d = campaign_data.get("sent_7d", 0)
        reply_7d = float(campaign_data.get("reply_rate_7d", 0))
        reply_14d = float(campaign_data.get("reply_rate_14d", 0))
        positive = float(campaign_data.get("positive_rate", 0))

        # WAIT: Just launched, not enough data
        if sent_7d == 0 or sent_7d < self.WAIT_SENT_THRESHOLD:
            return {
                "suggestion": "WAIT",
                "reason": f"Only {sent_7d} emails sent in 7 days. Need {self.WAIT_SENT_THRESHOLD} for reliable analysis.",
                "color": self.COLOR_GRAY,
            }

        # PAUSE: Very poor performance
        if reply_14d < 0.5 or (reply_7d < 0.8 and positive < 5):
            reasons = []
            if reply_14d < 0.5:
                reasons.append(f"14D reply rate too low ({reply_14d:.2f}%)")
            if reply_7d < 0.8 and positive < 5:
                reasons.append(f"7D reply ({reply_7d:.2f}%) and positive ({positive:.1f}%) both low")
            return {
                "suggestion": "PAUSE",
                "reason": ". ".join(reasons) + ". Consider pausing to optimize.",
                "color": self.COLOR_ORANGE,
            }

        # KEEP: Good performance
        if reply_7d > 3 and positive > 40:
            return {
                "suggestion": "KEEP",
                "reason": f"Strong performance: {reply_7d:.2f}% reply rate, {positive:.1f}% positive. Keep running.",
                "color": self.COLOR_GREEN,
            }

        # MONITOR: Okay performance (reply7d between 1 and 3)
        if reply_7d >= 1 and reply_7d <= 3:
            return {
                "suggestion": "MONITOR",
                "reason": f"Reply rate at {reply_7d:.2f}%. Monitor closely for improvement.",
                "color": self.COLOR_YELLOW,
            }

        # Default: MONITOR
        return {
            "suggestion": "MONITOR",
            "reason": f"Performance needs watching. 7D reply: {reply_7d:.2f}%, positive: {positive:.1f}%.",
            "color": self.COLOR_YELLOW,
        }

    def generate_warnings(self, campaign_data: dict) -> list[str]:
        """
        Generate warning messages based on campaign data.

        PROMPT 4 Logic:
        - Low Reply Rate: reply7d < 1 OR reply14d < 1 OR reply28d < 1
        - Low Quality: positive < 20 AND positive > 0
        - Declining Performance: reply7d < reply14d - 0.5
        - No Positive Replies: positive === 0

        Args:
            campaign_data: Dictionary with campaign metrics including:
                - sent_7d: Emails sent in last 7 days
                - reply_rate_7d: 7-day reply rate
                - reply_rate_14d: 14-day reply rate
                - reply_rate_28d: 28-day reply rate
                - positive_rate: Positive reply ratio

        Returns:
            List of warning strings
        """
        warnings = []

        # Extract metrics
        sent_7d = campaign_data.get("sent_7d", 0)
        reply_7d = float(campaign_data.get("reply_rate_7d", 0))
        reply_14d = float(campaign_data.get("reply_rate_14d", 0))
        reply_28d = float(campaign_data.get("reply_rate_28d", 0))
        positive = float(campaign_data.get("positive_rate", 0))

        # Skip warnings if not enough data
        if sent_7d < self.WAIT_SENT_THRESHOLD:
            return warnings

        # Low Reply Rate
        if reply_7d < 1 or reply_14d < 1 or reply_28d < 1:
            warnings.append("Low Reply Rate")

        # Low Quality (positive < 20 but > 0)
        if positive < 20 and positive > 0:
            warnings.append("Low Quality")

        # Declining Performance (7D rate dropped more than 0.5 from 14D)
        if reply_7d < reply_14d - 0.5:
            warnings.append("Declining Performance")

        # No Positive Replies
        if positive == 0:
            warnings.append("No Positive Replies")

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
