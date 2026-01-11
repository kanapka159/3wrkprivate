"""
Stats Calculator Service

Calculates and aggregates campaign statistics for dashboard display.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Campaign, CampaignAnalytics, Lead

logger = logging.getLogger(__name__)


class StatsCalculator:
    """Service for calculating campaign statistics."""

    def __init__(self, db: AsyncSession):
        """
        Initialize stats calculator.

        Args:
            db: Database session
        """
        self.db = db

    async def get_dashboard_stats(self) -> dict:
        """
        Get overall dashboard statistics.

        Returns:
            Dictionary with aggregated stats
        """
        # Get total campaigns
        total_campaigns = await self.db.scalar(
            select(func.count(Campaign.id))
        )

        # Get campaigns by status
        status_query = select(
            Campaign.status,
            func.count(Campaign.id)
        ).group_by(Campaign.status)
        result = await self.db.execute(status_query)
        campaigns_by_status = {row[0]: row[1] for row in result}

        # Get aggregate metrics from analytics
        metrics = await self.db.execute(
            select(
                func.sum(CampaignAnalytics.sent_count),
                func.sum(CampaignAnalytics.unique_sent_count),
                func.sum(CampaignAnalytics.open_count),
                func.sum(CampaignAnalytics.unique_open_count),
                func.sum(CampaignAnalytics.click_count),
                func.sum(CampaignAnalytics.unique_click_count),
                func.sum(CampaignAnalytics.reply_count),
                func.sum(CampaignAnalytics.unique_reply_count),
                func.sum(CampaignAnalytics.bounce_count),
            ).where(CampaignAnalytics.date.is_(None))  # Aggregate stats only
        )
        row = metrics.one()

        total_sent = row[1] or 0
        total_opens = row[3] or 0
        total_clicks = row[5] or 0
        total_replies = row[7] or 0
        total_bounces = row[8] or 0

        # Calculate rates
        open_rate = (total_opens / total_sent * 100) if total_sent > 0 else 0
        click_rate = (total_clicks / total_sent * 100) if total_sent > 0 else 0
        reply_rate = (total_replies / total_sent * 100) if total_sent > 0 else 0
        bounce_rate = (total_bounces / total_sent * 100) if total_sent > 0 else 0

        return {
            "total_campaigns": total_campaigns or 0,
            "campaigns_by_status": campaigns_by_status,
            "total_sent": total_sent,
            "total_opens": total_opens,
            "total_clicks": total_clicks,
            "total_replies": total_replies,
            "total_bounces": total_bounces,
            "open_rate": round(open_rate, 2),
            "click_rate": round(click_rate, 2),
            "reply_rate": round(reply_rate, 2),
            "bounce_rate": round(bounce_rate, 2),
        }

    async def get_campaign_stats(self, campaign_id: int) -> dict:
        """
        Get detailed statistics for a single campaign.

        Args:
            campaign_id: Local campaign ID

        Returns:
            Campaign statistics dictionary
        """
        # Get campaign
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        # Get aggregate analytics
        analytics_result = await self.db.execute(
            select(CampaignAnalytics).where(
                CampaignAnalytics.campaign_id == campaign_id,
                CampaignAnalytics.date.is_(None),
            )
        )
        analytics = analytics_result.scalar_one_or_none()

        return {
            "campaign": {
                "id": campaign.id,
                "smartlead_id": campaign.smartlead_id,
                "name": campaign.name,
                "status": campaign.status,
                "client_name": campaign.client_name,
                "last_synced_at": campaign.last_synced_at.isoformat() if campaign.last_synced_at else None,
            },
            "analytics": {
                "sent_count": analytics.sent_count if analytics else 0,
                "unique_sent_count": analytics.unique_sent_count if analytics else 0,
                "open_count": analytics.open_count if analytics else 0,
                "unique_open_count": analytics.unique_open_count if analytics else 0,
                "click_count": analytics.click_count if analytics else 0,
                "unique_click_count": analytics.unique_click_count if analytics else 0,
                "reply_count": analytics.reply_count if analytics else 0,
                "unique_reply_count": analytics.unique_reply_count if analytics else 0,
                "bounce_count": analytics.bounce_count if analytics else 0,
                "open_rate": analytics.open_rate if analytics else 0,
                "click_rate": analytics.click_rate if analytics else 0,
                "reply_rate": analytics.reply_rate if analytics else 0,
                "bounce_rate": analytics.bounce_rate if analytics else 0,
            },
        }

    async def get_top_performing_campaigns(self, limit: int = 10, metric: str = "reply_rate") -> list[dict]:
        """
        Get top performing campaigns by a specific metric.

        Args:
            limit: Number of campaigns to return
            metric: Metric to sort by (open_rate, click_rate, reply_rate)

        Returns:
            List of top campaigns
        """
        valid_metrics = ["open_rate", "click_rate", "reply_rate", "sent_count"]
        if metric not in valid_metrics:
            metric = "reply_rate"

        order_column = getattr(CampaignAnalytics, metric)

        query = (
            select(Campaign, CampaignAnalytics)
            .join(CampaignAnalytics, Campaign.id == CampaignAnalytics.campaign_id)
            .where(CampaignAnalytics.date.is_(None))
            .where(CampaignAnalytics.sent_count > 0)  # Only campaigns with sends
            .order_by(order_column.desc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        rows = result.all()

        return [
            {
                "campaign_id": campaign.id,
                "name": campaign.name,
                "status": campaign.status,
                "sent_count": analytics.sent_count,
                "open_rate": analytics.open_rate,
                "click_rate": analytics.click_rate,
                "reply_rate": analytics.reply_rate,
            }
            for campaign, analytics in rows
        ]

    async def get_campaigns_needing_attention(self) -> list[dict]:
        """
        Get campaigns that may need attention (low performance, high bounce, etc.)

        Returns:
            List of campaigns with issues
        """
        issues = []

        # High bounce rate (>5%)
        high_bounce_query = (
            select(Campaign, CampaignAnalytics)
            .join(CampaignAnalytics, Campaign.id == CampaignAnalytics.campaign_id)
            .where(CampaignAnalytics.date.is_(None))
            .where(CampaignAnalytics.bounce_rate > 5)
            .where(CampaignAnalytics.sent_count >= 100)  # Minimum sample size
        )
        result = await self.db.execute(high_bounce_query)
        for campaign, analytics in result.all():
            issues.append({
                "campaign_id": campaign.id,
                "name": campaign.name,
                "issue": "high_bounce_rate",
                "value": analytics.bounce_rate,
                "message": f"Bounce rate of {analytics.bounce_rate:.1f}% is above threshold",
            })

        # Low open rate (<10%)
        low_open_query = (
            select(Campaign, CampaignAnalytics)
            .join(CampaignAnalytics, Campaign.id == CampaignAnalytics.campaign_id)
            .where(CampaignAnalytics.date.is_(None))
            .where(CampaignAnalytics.open_rate < 10)
            .where(CampaignAnalytics.sent_count >= 100)
        )
        result = await self.db.execute(low_open_query)
        for campaign, analytics in result.all():
            issues.append({
                "campaign_id": campaign.id,
                "name": campaign.name,
                "issue": "low_open_rate",
                "value": analytics.open_rate,
                "message": f"Open rate of {analytics.open_rate:.1f}% is below average",
            })

        # Zero replies with significant sends
        no_replies_query = (
            select(Campaign, CampaignAnalytics)
            .join(CampaignAnalytics, Campaign.id == CampaignAnalytics.campaign_id)
            .where(CampaignAnalytics.date.is_(None))
            .where(CampaignAnalytics.reply_count == 0)
            .where(CampaignAnalytics.sent_count >= 50)
        )
        result = await self.db.execute(no_replies_query)
        for campaign, analytics in result.all():
            issues.append({
                "campaign_id": campaign.id,
                "name": campaign.name,
                "issue": "no_replies",
                "value": 0,
                "message": f"No replies after {analytics.sent_count} emails sent",
            })

        return issues
