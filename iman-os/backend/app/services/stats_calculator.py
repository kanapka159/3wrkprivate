"""
Stats Calculator Service

Calculates and aggregates campaign statistics for dashboard display.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Campaign, CampaignDailyStats, LeadReply

logger = logging.getLogger(__name__)


class StatsCalculator:
    """Service for calculating campaign statistics."""

    def __init__(self, db: AsyncSession):
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

        # Get aggregate metrics from daily stats
        metrics = await self.db.execute(
            select(
                func.sum(CampaignDailyStats.sent_count),
                func.sum(CampaignDailyStats.unique_sent),
                func.sum(CampaignDailyStats.open_count),
                func.sum(CampaignDailyStats.click_count),
                func.sum(CampaignDailyStats.reply_count),
                func.sum(CampaignDailyStats.unique_replied),
                func.sum(CampaignDailyStats.positive_replies),
                func.sum(CampaignDailyStats.bounce_count),
            )
        )
        row = metrics.one()

        total_sent = row[1] or 0  # unique_sent
        total_opens = row[2] or 0
        total_clicks = row[3] or 0
        total_replies = row[5] or 0  # unique_replied
        total_positive = row[6] or 0
        total_bounces = row[7] or 0

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
            "total_positive_replies": total_positive,
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

        # Get aggregate stats
        stats = await self.db.execute(
            select(
                func.sum(CampaignDailyStats.sent_count),
                func.sum(CampaignDailyStats.unique_sent),
                func.sum(CampaignDailyStats.open_count),
                func.sum(CampaignDailyStats.click_count),
                func.sum(CampaignDailyStats.reply_count),
                func.sum(CampaignDailyStats.unique_replied),
                func.sum(CampaignDailyStats.positive_replies),
                func.sum(CampaignDailyStats.bounce_count),
            ).where(CampaignDailyStats.campaign_id == campaign_id)
        )
        row = stats.one()

        sent = row[1] or 0
        opens = row[2] or 0
        clicks = row[3] or 0
        replies = row[5] or 0
        positive = row[6] or 0
        bounces = row[7] or 0

        # Calculate rates
        open_rate = (opens / sent * 100) if sent > 0 else 0
        click_rate = (clicks / sent * 100) if sent > 0 else 0
        reply_rate = (replies / sent * 100) if sent > 0 else 0
        bounce_rate = (bounces / sent * 100) if sent > 0 else 0

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
                "sent_count": sent,
                "open_count": opens,
                "click_count": clicks,
                "reply_count": replies,
                "positive_replies": positive,
                "bounce_count": bounces,
                "open_rate": round(open_rate, 2),
                "click_rate": round(click_rate, 2),
                "reply_rate": round(reply_rate, 2),
                "bounce_rate": round(bounce_rate, 2),
            },
        }

    async def get_campaign_daily_stats(
        self,
        campaign_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Get daily statistics for a campaign.

        Args:
            campaign_id: Local campaign ID
            start_date: Start date filter
            end_date: End date filter

        Returns:
            List of daily stats
        """
        query = select(CampaignDailyStats).where(
            CampaignDailyStats.campaign_id == campaign_id
        )

        if start_date:
            query = query.where(CampaignDailyStats.date >= start_date)
        if end_date:
            query = query.where(CampaignDailyStats.date <= end_date)

        query = query.order_by(CampaignDailyStats.date.desc())

        result = await self.db.execute(query)
        daily_stats = result.scalars().all()

        return [
            {
                "date": ds.date.strftime("%Y-%m-%d") if ds.date else None,
                "sent_count": ds.sent_count,
                "unique_sent": ds.unique_sent,
                "open_count": ds.open_count,
                "click_count": ds.click_count,
                "reply_count": ds.reply_count,
                "unique_replied": ds.unique_replied,
                "positive_replies": ds.positive_replies,
                "bounce_count": ds.bounce_count,
            }
            for ds in daily_stats
        ]

    async def get_top_performing_campaigns(self, limit: int = 10, metric: str = "reply_rate") -> list[dict]:
        """
        Get top performing campaigns by a specific metric.

        Args:
            limit: Number of campaigns to return
            metric: Metric to sort by

        Returns:
            List of top campaigns
        """
        # Get campaign stats aggregated
        subquery = (
            select(
                CampaignDailyStats.campaign_id,
                func.sum(CampaignDailyStats.unique_sent).label("total_sent"),
                func.sum(CampaignDailyStats.open_count).label("total_opens"),
                func.sum(CampaignDailyStats.click_count).label("total_clicks"),
                func.sum(CampaignDailyStats.unique_replied).label("total_replies"),
                func.sum(CampaignDailyStats.bounce_count).label("total_bounces"),
            )
            .group_by(CampaignDailyStats.campaign_id)
            .subquery()
        )

        query = (
            select(Campaign, subquery)
            .join(subquery, Campaign.id == subquery.c.campaign_id)
            .where(subquery.c.total_sent > 0)
        )

        result = await self.db.execute(query)
        rows = result.all()

        # Calculate rates and sort
        campaigns_with_rates = []
        for row in rows:
            campaign = row[0]
            sent = row.total_sent or 0
            opens = row.total_opens or 0
            clicks = row.total_clicks or 0
            replies = row.total_replies or 0
            bounces = row.total_bounces or 0

            campaigns_with_rates.append({
                "campaign_id": campaign.id,
                "name": campaign.name,
                "status": campaign.status,
                "sent_count": sent,
                "open_rate": round((opens / sent * 100), 2) if sent > 0 else 0,
                "click_rate": round((clicks / sent * 100), 2) if sent > 0 else 0,
                "reply_rate": round((replies / sent * 100), 2) if sent > 0 else 0,
                "bounce_rate": round((bounces / sent * 100), 2) if sent > 0 else 0,
            })

        # Sort by metric
        valid_metrics = ["open_rate", "click_rate", "reply_rate", "sent_count"]
        if metric not in valid_metrics:
            metric = "reply_rate"

        campaigns_with_rates.sort(key=lambda x: x.get(metric, 0), reverse=True)

        return campaigns_with_rates[:limit]

    async def get_campaigns_needing_attention(self) -> list[dict]:
        """
        Get campaigns that may need attention.

        Returns:
            List of campaigns with issues
        """
        # Get all campaigns with aggregated stats
        campaigns_stats = await self.get_top_performing_campaigns(limit=1000, metric="sent_count")

        issues = []
        for cs in campaigns_stats:
            if cs["sent_count"] < 50:
                continue  # Skip campaigns with too few sends

            # High bounce rate (>5%)
            if cs["bounce_rate"] > 5:
                issues.append({
                    "campaign_id": cs["campaign_id"],
                    "name": cs["name"],
                    "issue": "high_bounce_rate",
                    "value": cs["bounce_rate"],
                    "message": f"Bounce rate of {cs['bounce_rate']:.1f}% is above threshold",
                })

            # Low open rate (<10%)
            if cs["open_rate"] < 10:
                issues.append({
                    "campaign_id": cs["campaign_id"],
                    "name": cs["name"],
                    "issue": "low_open_rate",
                    "value": cs["open_rate"],
                    "message": f"Open rate of {cs['open_rate']:.1f}% is below average",
                })

            # Zero replies
            if cs["reply_rate"] == 0:
                issues.append({
                    "campaign_id": cs["campaign_id"],
                    "name": cs["name"],
                    "issue": "no_replies",
                    "value": 0,
                    "message": f"No replies after {cs['sent_count']} emails sent",
                })

        return issues

    async def get_lead_replies_by_category(self, campaign_id: Optional[int] = None) -> dict:
        """
        Get lead replies grouped by category.

        Args:
            campaign_id: Optional campaign filter

        Returns:
            Replies grouped by category
        """
        query = select(
            LeadReply.lead_category,
            func.count(LeadReply.id),
            func.sum(func.cast(LeadReply.is_positive, Integer)),
        ).group_by(LeadReply.lead_category)

        if campaign_id:
            query = query.where(LeadReply.campaign_id == campaign_id)

        result = await self.db.execute(query)
        rows = result.all()

        return {
            "categories": [
                {
                    "category": row[0] or "Uncategorized",
                    "count": row[1],
                    "positive_count": row[2] or 0,
                }
                for row in rows
            ]
        }
