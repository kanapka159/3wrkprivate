"""
Sync Service

Handles synchronization between Smartlead API and local database.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Campaign, CampaignAnalytics, Lead, SyncLog
from .smartlead import SmartleadClient, SmartleadAPIError

logger = logging.getLogger(__name__)


class SyncService:
    """Service for syncing Smartlead data to local database."""

    def __init__(self, db: AsyncSession):
        """
        Initialize sync service.

        Args:
            db: Database session
        """
        self.db = db

    async def _create_sync_log(self, sync_type: str) -> SyncLog:
        """Create a new sync log entry."""
        sync_log = SyncLog(
            sync_type=sync_type,
            status="started",
            started_at=datetime.utcnow(),
        )
        self.db.add(sync_log)
        await self.db.flush()
        return sync_log

    async def _complete_sync_log(
        self,
        sync_log: SyncLog,
        status: str = "completed",
        campaigns_synced: int = 0,
        leads_synced: int = 0,
        error_message: Optional[str] = None,
    ):
        """Update sync log on completion."""
        sync_log.status = status
        sync_log.campaigns_synced = campaigns_synced
        sync_log.leads_synced = leads_synced
        sync_log.error_message = error_message
        sync_log.completed_at = datetime.utcnow()

    async def sync_campaigns(self) -> dict:
        """
        Sync all campaigns from Smartlead.

        Returns:
            Sync result summary
        """
        sync_log = await self._create_sync_log("campaigns")
        campaigns_synced = 0

        try:
            async with SmartleadClient() as client:
                campaigns_data = await client.get_all_campaigns()

                for campaign_data in campaigns_data:
                    await self._upsert_campaign(campaign_data)
                    campaigns_synced += 1

            await self._complete_sync_log(sync_log, campaigns_synced=campaigns_synced)
            logger.info(f"Campaign sync completed: {campaigns_synced} campaigns")

            return {
                "status": "success",
                "campaigns_synced": campaigns_synced,
            }

        except SmartleadAPIError as e:
            logger.error(f"Campaign sync failed: {e.message}")
            await self._complete_sync_log(sync_log, status="failed", error_message=e.message)
            raise

        except Exception as e:
            logger.error(f"Campaign sync failed: {str(e)}")
            await self._complete_sync_log(sync_log, status="failed", error_message=str(e))
            raise

    async def _upsert_campaign(self, campaign_data: dict) -> Campaign:
        """Insert or update a campaign."""
        smartlead_id = campaign_data.get("id")

        # Check if campaign exists
        result = await self.db.execute(
            select(Campaign).where(Campaign.smartlead_id == smartlead_id)
        )
        campaign = result.scalar_one_or_none()

        if campaign:
            # Update existing
            campaign.name = campaign_data.get("name", campaign.name)
            campaign.status = campaign_data.get("status", campaign.status)
            campaign.client_id = campaign_data.get("client_id")
            campaign.client_name = campaign_data.get("client_name")
            campaign.timezone = campaign_data.get("timezone")
            campaign.track_settings = campaign_data.get("track_settings")
            campaign.last_synced_at = datetime.utcnow()
        else:
            # Create new
            campaign = Campaign(
                smartlead_id=smartlead_id,
                name=campaign_data.get("name", "Unnamed Campaign"),
                status=campaign_data.get("status", "draft"),
                client_id=campaign_data.get("client_id"),
                client_name=campaign_data.get("client_name"),
                timezone=campaign_data.get("timezone"),
                track_settings=campaign_data.get("track_settings"),
                last_synced_at=datetime.utcnow(),
            )
            self.db.add(campaign)

        await self.db.flush()
        return campaign

    async def sync_campaign_analytics(self, campaign_id: int) -> dict:
        """
        Sync analytics for a specific campaign.

        Args:
            campaign_id: Local campaign ID

        Returns:
            Sync result summary
        """
        # Get campaign
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        try:
            async with SmartleadClient() as client:
                analytics_data = await client.get_campaign_analytics(campaign.smartlead_id)

                # Upsert aggregate analytics (no date)
                await self._upsert_analytics(campaign.id, analytics_data)

            logger.info(f"Analytics sync completed for campaign {campaign_id}")
            return {"status": "success", "campaign_id": campaign_id}

        except SmartleadAPIError as e:
            logger.error(f"Analytics sync failed for campaign {campaign_id}: {e.message}")
            raise

    async def _upsert_analytics(
        self,
        campaign_id: int,
        analytics_data: dict,
        date: Optional[datetime] = None,
    ) -> CampaignAnalytics:
        """Insert or update campaign analytics."""
        # Check if analytics exist
        query = select(CampaignAnalytics).where(
            CampaignAnalytics.campaign_id == campaign_id,
            CampaignAnalytics.date == date,
        )
        result = await self.db.execute(query)
        analytics = result.scalar_one_or_none()

        # Extract metrics
        sent = analytics_data.get("sent_count", 0) or 0
        unique_sent = analytics_data.get("unique_sent_count", sent) or sent
        opens = analytics_data.get("open_count", 0) or 0
        unique_opens = analytics_data.get("unique_open_count", opens) or opens
        clicks = analytics_data.get("click_count", 0) or 0
        unique_clicks = analytics_data.get("unique_click_count", clicks) or clicks
        replies = analytics_data.get("reply_count", 0) or 0
        unique_replies = analytics_data.get("unique_reply_count", replies) or replies
        bounces = analytics_data.get("bounce_count", 0) or 0
        unsubscribes = analytics_data.get("unsubscribe_count", 0) or 0

        # Calculate rates
        open_rate = (unique_opens / unique_sent * 100) if unique_sent > 0 else 0
        click_rate = (unique_clicks / unique_sent * 100) if unique_sent > 0 else 0
        reply_rate = (unique_replies / unique_sent * 100) if unique_sent > 0 else 0
        bounce_rate = (bounces / unique_sent * 100) if unique_sent > 0 else 0

        if analytics:
            # Update existing
            analytics.sent_count = sent
            analytics.unique_sent_count = unique_sent
            analytics.open_count = opens
            analytics.unique_open_count = unique_opens
            analytics.click_count = clicks
            analytics.unique_click_count = unique_clicks
            analytics.reply_count = replies
            analytics.unique_reply_count = unique_replies
            analytics.bounce_count = bounces
            analytics.unsubscribe_count = unsubscribes
            analytics.open_rate = open_rate
            analytics.click_rate = click_rate
            analytics.reply_rate = reply_rate
            analytics.bounce_rate = bounce_rate
        else:
            # Create new
            analytics = CampaignAnalytics(
                campaign_id=campaign_id,
                date=date,
                sent_count=sent,
                unique_sent_count=unique_sent,
                open_count=opens,
                unique_open_count=unique_opens,
                click_count=clicks,
                unique_click_count=unique_clicks,
                reply_count=replies,
                unique_reply_count=unique_replies,
                bounce_count=bounces,
                unsubscribe_count=unsubscribes,
                open_rate=open_rate,
                click_rate=click_rate,
                reply_rate=reply_rate,
                bounce_rate=bounce_rate,
            )
            self.db.add(analytics)

        await self.db.flush()
        return analytics

    async def sync_all(self) -> dict:
        """
        Full sync: campaigns and their analytics.

        Returns:
            Sync result summary
        """
        sync_log = await self._create_sync_log("full")
        campaigns_synced = 0
        leads_synced = 0

        try:
            # Sync campaigns first
            campaign_result = await self.sync_campaigns()
            campaigns_synced = campaign_result["campaigns_synced"]

            # Get all campaigns and sync analytics
            result = await self.db.execute(select(Campaign))
            campaigns = result.scalars().all()

            for campaign in campaigns:
                try:
                    await self.sync_campaign_analytics(campaign.id)
                except Exception as e:
                    logger.warning(f"Failed to sync analytics for campaign {campaign.id}: {e}")

            await self._complete_sync_log(
                sync_log,
                campaigns_synced=campaigns_synced,
                leads_synced=leads_synced,
            )

            logger.info(f"Full sync completed: {campaigns_synced} campaigns")
            return {
                "status": "success",
                "campaigns_synced": campaigns_synced,
                "leads_synced": leads_synced,
            }

        except Exception as e:
            logger.error(f"Full sync failed: {str(e)}")
            await self._complete_sync_log(sync_log, status="failed", error_message=str(e))
            raise

    async def get_last_sync(self) -> Optional[SyncLog]:
        """Get the most recent sync log."""
        result = await self.db.execute(
            select(SyncLog).order_by(SyncLog.started_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()
