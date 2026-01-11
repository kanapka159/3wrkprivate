"""
Sync Service

Handles synchronization between Smartlead API and local database.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.sqlite import insert

from ..db.models import Campaign, CampaignDailyStats, Sequence, LeadReply, SyncLog
from .smartlead import SmartleadClient, SmartleadAPIError

logger = logging.getLogger(__name__)


class SyncService:
    """Service for syncing Smartlead data to local database."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _create_sync_log(self) -> SyncLog:
        """Create a new sync log entry."""
        sync_log = SyncLog(
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
        error_message: Optional[str] = None,
    ):
        """Update sync log on completion."""
        sync_log.status = status
        sync_log.campaigns_synced = campaigns_synced
        sync_log.error_message = error_message
        sync_log.completed_at = datetime.utcnow()

    async def sync_campaigns(self) -> dict:
        """
        Sync all campaigns from Smartlead.

        Returns:
            Sync result summary
        """
        sync_log = await self._create_sync_log()
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

        result = await self.db.execute(
            select(Campaign).where(Campaign.smartlead_id == smartlead_id)
        )
        campaign = result.scalar_one_or_none()

        if campaign:
            campaign.name = campaign_data.get("name", campaign.name)
            campaign.status = campaign_data.get("status", campaign.status)
            campaign.client_id = campaign_data.get("client_id")
            campaign.client_name = campaign_data.get("client_name")
            campaign.last_synced_at = datetime.utcnow()
        else:
            campaign = Campaign(
                smartlead_id=smartlead_id,
                name=campaign_data.get("name", "Unnamed Campaign"),
                status=campaign_data.get("status", "draft"),
                client_id=campaign_data.get("client_id"),
                client_name=campaign_data.get("client_name"),
                last_synced_at=datetime.utcnow(),
            )
            self.db.add(campaign)

        await self.db.flush()
        return campaign

    async def sync_campaign_daily_stats(
        self,
        campaign_id: int,
        start_date: str,
        end_date: str,
    ) -> dict:
        """
        Sync daily statistics for a campaign.

        Args:
            campaign_id: Local campaign ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Sync result summary
        """
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        try:
            async with SmartleadClient() as client:
                daily_data = await client.get_campaign_analytics_by_date(
                    campaign.smartlead_id, start_date, end_date
                )

                days_synced = 0
                for day_stats in daily_data:
                    await self._upsert_daily_stats(campaign.id, day_stats)
                    days_synced += 1

            logger.info(f"Daily stats sync completed for campaign {campaign_id}: {days_synced} days")
            return {"status": "success", "campaign_id": campaign_id, "days_synced": days_synced}

        except SmartleadAPIError as e:
            logger.error(f"Daily stats sync failed for campaign {campaign_id}: {e.message}")
            raise

    async def _upsert_daily_stats(self, campaign_id: int, stats_data: dict) -> CampaignDailyStats:
        """Insert or update daily campaign stats."""
        date_str = stats_data.get("date")
        if date_str:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            return None

        result = await self.db.execute(
            select(CampaignDailyStats).where(
                CampaignDailyStats.campaign_id == campaign_id,
                CampaignDailyStats.date == date,
            )
        )
        daily_stats = result.scalar_one_or_none()

        if daily_stats:
            daily_stats.sent_count = stats_data.get("sent_count", 0) or 0
            daily_stats.reply_count = stats_data.get("reply_count", 0) or 0
            daily_stats.unique_sent = stats_data.get("unique_sent_count", 0) or 0
            daily_stats.unique_replied = stats_data.get("unique_reply_count", 0) or 0
            daily_stats.positive_replies = stats_data.get("positive_reply_count", 0) or 0
            daily_stats.bounce_count = stats_data.get("bounce_count", 0) or 0
            daily_stats.open_count = stats_data.get("open_count", 0) or 0
            daily_stats.click_count = stats_data.get("click_count", 0) or 0
        else:
            daily_stats = CampaignDailyStats(
                campaign_id=campaign_id,
                date=date,
                sent_count=stats_data.get("sent_count", 0) or 0,
                reply_count=stats_data.get("reply_count", 0) or 0,
                unique_sent=stats_data.get("unique_sent_count", 0) or 0,
                unique_replied=stats_data.get("unique_reply_count", 0) or 0,
                positive_replies=stats_data.get("positive_reply_count", 0) or 0,
                bounce_count=stats_data.get("bounce_count", 0) or 0,
                open_count=stats_data.get("open_count", 0) or 0,
                click_count=stats_data.get("click_count", 0) or 0,
            )
            self.db.add(daily_stats)

        await self.db.flush()
        return daily_stats

    async def sync_sequences(self, campaign_id: int) -> dict:
        """
        Sync email sequences for a campaign.

        Args:
            campaign_id: Local campaign ID

        Returns:
            Sync result summary
        """
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        try:
            async with SmartleadClient() as client:
                sequences_data = await client.get_campaign_sequences(campaign.smartlead_id)

                sequences_synced = 0
                for seq_data in sequences_data:
                    await self._upsert_sequence(campaign.id, seq_data)
                    sequences_synced += 1

            logger.info(f"Sequences sync completed for campaign {campaign_id}: {sequences_synced} sequences")
            return {"status": "success", "campaign_id": campaign_id, "sequences_synced": sequences_synced}

        except SmartleadAPIError as e:
            logger.error(f"Sequences sync failed for campaign {campaign_id}: {e.message}")
            raise

    async def _upsert_sequence(self, campaign_id: int, seq_data: dict) -> Sequence:
        """Insert or update a sequence."""
        smartlead_id = seq_data.get("id")
        seq_number = seq_data.get("seq_number", 1)

        result = await self.db.execute(
            select(Sequence).where(
                Sequence.campaign_id == campaign_id,
                Sequence.smartlead_id == smartlead_id,
            )
        )
        sequence = result.scalar_one_or_none()

        if sequence:
            sequence.seq_number = seq_number
            sequence.variant_label = seq_data.get("variant_label")
            sequence.subject = seq_data.get("subject")
            sequence.email_body = seq_data.get("email_body")
            sequence.sent_count = seq_data.get("sent_count", 0) or 0
            sequence.reply_count = seq_data.get("reply_count", 0) or 0
        else:
            sequence = Sequence(
                smartlead_id=smartlead_id,
                campaign_id=campaign_id,
                seq_number=seq_number,
                variant_label=seq_data.get("variant_label"),
                subject=seq_data.get("subject"),
                email_body=seq_data.get("email_body"),
                sent_count=seq_data.get("sent_count", 0) or 0,
                reply_count=seq_data.get("reply_count", 0) or 0,
            )
            self.db.add(sequence)

        await self.db.flush()
        return sequence

    async def sync_lead_replies(self, campaign_id: int) -> dict:
        """
        Sync lead replies for a campaign.

        Args:
            campaign_id: Local campaign ID

        Returns:
            Sync result summary
        """
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        try:
            async with SmartleadClient() as client:
                # Get all statistics with reply status
                stats_data = await client.get_all_campaign_statistics(
                    campaign.smartlead_id,
                    email_status="REPLIED",
                )

                replies_synced = 0
                for lead_data in stats_data:
                    await self._upsert_lead_reply(campaign.id, lead_data)
                    replies_synced += 1

            logger.info(f"Lead replies sync completed for campaign {campaign_id}: {replies_synced} replies")
            return {"status": "success", "campaign_id": campaign_id, "replies_synced": replies_synced}

        except SmartleadAPIError as e:
            logger.error(f"Lead replies sync failed for campaign {campaign_id}: {e.message}")
            raise

    async def _upsert_lead_reply(self, campaign_id: int, lead_data: dict) -> LeadReply:
        """Insert or update a lead reply."""
        email = lead_data.get("email")
        if not email:
            return None

        result = await self.db.execute(
            select(LeadReply).where(
                LeadReply.campaign_id == campaign_id,
                LeadReply.lead_email == email,
            )
        )
        lead_reply = result.scalar_one_or_none()

        # Determine if positive based on category
        category = lead_data.get("lead_category", "")
        is_positive = category.lower() in ["interested", "meeting booked", "meeting completed", "closed"]

        if lead_reply:
            lead_reply.lead_name = lead_data.get("name") or lead_data.get("first_name")
            lead_reply.lead_category = category
            lead_reply.is_positive = is_positive
            lead_reply.sequence_number = lead_data.get("sequence_number")
            lead_reply.variant_id = lead_data.get("variant_id")
        else:
            lead_reply = LeadReply(
                campaign_id=campaign_id,
                lead_email=email,
                lead_name=lead_data.get("name") or lead_data.get("first_name"),
                lead_category=category,
                first_reply_time=datetime.utcnow(),
                is_positive=is_positive,
                sequence_number=lead_data.get("sequence_number"),
                variant_id=lead_data.get("variant_id"),
            )
            self.db.add(lead_reply)

        await self.db.flush()
        return lead_reply

    async def sync_all(self) -> dict:
        """
        Full sync: campaigns, daily stats, sequences, and lead replies.

        Returns:
            Sync result summary
        """
        sync_log = await self._create_sync_log()
        campaigns_synced = 0

        try:
            # Sync campaigns first
            campaign_result = await self.sync_campaigns()
            campaigns_synced = campaign_result["campaigns_synced"]

            # Get all campaigns
            result = await self.db.execute(select(Campaign))
            campaigns = result.scalars().all()

            # Sync additional data for each campaign
            for campaign in campaigns:
                try:
                    await self.sync_sequences(campaign.id)
                except Exception as e:
                    logger.warning(f"Failed to sync sequences for campaign {campaign.id}: {e}")

            await self._complete_sync_log(sync_log, campaigns_synced=campaigns_synced)

            logger.info(f"Full sync completed: {campaigns_synced} campaigns")
            return {
                "status": "success",
                "campaigns_synced": campaigns_synced,
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
