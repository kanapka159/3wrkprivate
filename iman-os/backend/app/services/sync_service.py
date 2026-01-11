"""
Sync Service

Handles synchronization between Smartlead API and local database.
Full sync includes: campaigns, analytics, statistics (paginated), sequences, lead replies.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Campaign, CampaignDailyStats, Sequence, LeadReply, SyncLog
from .smartlead import SmartleadClient, SmartleadAPIError
from .stats_calculator import is_positive_category

logger = logging.getLogger(__name__)

# Rate limit delay between API calls (0.25s for 10 req/2 sec limit)
API_DELAY = 0.25

# Pagination settings
PAGE_SIZE = 100


class SyncService:
    """Service for syncing Smartlead data to local database."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _create_sync_log(self) -> SyncLog:
        """Create a new sync log entry with status=running."""
        sync_log = SyncLog(
            status="running",
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
        await self.db.flush()

    async def sync_all_campaigns(self) -> dict:
        """
        Full sync of all campaigns with all related data.

        Steps:
        1. Create sync_log (status=running)
        2. Fetch all campaigns from Smartlead
        3. For each campaign:
           - Upsert campaign record
           - Get analytics (total + by date for 7/14/28 days)
           - Paginate ALL statistics (100 per page until done)
           - Dedupe replies by lead_email in lead_replies table
           - Count unique_replied and positive_replies
           - Get sequences
           - Store daily stats
        4. Update sync_log (status=completed)

        Returns:
            Sync result summary
        """
        sync_log = await self._create_sync_log()
        campaigns_synced = 0
        total_replies_synced = 0
        errors = []

        try:
            async with SmartleadClient() as client:
                # Step 2: Fetch all campaigns
                logger.info("Fetching all campaigns from Smartlead...")
                campaigns_data = await client.get_all_campaigns()
                await asyncio.sleep(API_DELAY)

                logger.info(f"Found {len(campaigns_data)} campaigns to sync")

                # Step 3: Process each campaign
                for campaign_data in campaigns_data:
                    try:
                        smartlead_id = campaign_data.get("id")
                        campaign_name = campaign_data.get("name", "Unknown")
                        logger.info(f"Syncing campaign {smartlead_id}: {campaign_name}")

                        # 3a: Upsert campaign record
                        campaign = await self._upsert_campaign(campaign_data)
                        await asyncio.sleep(API_DELAY)

                        # 3b: Get AGGREGATE analytics (all-time totals) - this is what Smartlead UI shows
                        try:
                            aggregate_analytics = await client.get_campaign_analytics(smartlead_id)
                            await asyncio.sleep(API_DELAY)

                            # Log the response for debugging
                            if not hasattr(self, '_logged_aggregate_keys'):
                                self._logged_aggregate_keys = True
                                logger.info(f"Smartlead aggregate analytics keys: {list(aggregate_analytics.keys()) if isinstance(aggregate_analytics, dict) else type(aggregate_analytics)}")
                                logger.info(f"Smartlead aggregate analytics sample: {aggregate_analytics}")

                            # Helper to safely convert string/int to int
                            def to_int(val):
                                if val is None:
                                    return 0
                                try:
                                    return int(val)
                                except (ValueError, TypeError):
                                    return 0

                            # Update Campaign with aggregate stats
                            # Smartlead API returns values as STRINGS like "2893"
                            if isinstance(aggregate_analytics, dict):
                                # Use unique_sent_count (unique leads) as primary, fall back to sent_count
                                campaign.total_sent = (
                                    to_int(aggregate_analytics.get("unique_sent_count")) or
                                    to_int(aggregate_analytics.get("sent_count"))
                                )
                                campaign.total_replied = to_int(aggregate_analytics.get("reply_count"))
                                campaign.total_bounced = to_int(aggregate_analytics.get("bounce_count"))
                                campaign.total_opened = to_int(aggregate_analytics.get("open_count"))
                                campaign.total_clicked = to_int(aggregate_analytics.get("click_count"))

                                # Get positive replies from campaign_lead_stats.interested
                                lead_stats = aggregate_analytics.get("campaign_lead_stats", {})
                                campaign.total_positive = to_int(lead_stats.get("interested", 0))

                                logger.info(f"Campaign {smartlead_id} aggregate: sent={campaign.total_sent}, replied={campaign.total_replied}, positive={campaign.total_positive}, bounced={campaign.total_bounced}")

                        except SmartleadAPIError as e:
                            logger.warning(f"Failed to get aggregate analytics for campaign {smartlead_id}: {e.message}")

                        # 3c: Get analytics by date (last 28 days) for period breakdowns
                        end_date = datetime.utcnow().strftime("%Y-%m-%d")
                        start_date = (datetime.utcnow() - timedelta(days=28)).strftime("%Y-%m-%d")

                        try:
                            daily_analytics = await client.get_campaign_analytics_by_date(
                                smartlead_id, start_date, end_date
                            )
                            await asyncio.sleep(API_DELAY)

                            # Store daily stats
                            for day_data in daily_analytics:
                                await self._upsert_daily_stats(campaign.id, day_data)

                        except SmartleadAPIError as e:
                            logger.warning(f"Failed to get daily analytics for campaign {smartlead_id}: {e.message}")

                        # 3d: Paginate ALL statistics
                        try:
                            all_stats = await self._paginate_statistics(client, smartlead_id)
                            await asyncio.sleep(API_DELAY)

                            # Dedupe replies and count
                            replies_count, positive_count = await self._dedupe_replies(
                                campaign.id, all_stats
                            )
                            total_replies_synced += replies_count

                            # Update campaign with reply counts
                            await self._update_campaign_reply_counts(campaign.id)

                        except SmartleadAPIError as e:
                            logger.warning(f"Failed to get statistics for campaign {smartlead_id}: {e.message}")

                        # 3e: Get sequences (email variants)
                        try:
                            sequences_data = await client.get_campaign_sequences(smartlead_id)
                            await asyncio.sleep(API_DELAY)

                            for seq_data in sequences_data:
                                await self._upsert_sequence(campaign.id, seq_data)

                        except SmartleadAPIError as e:
                            logger.warning(f"Failed to get sequences for campaign {smartlead_id}: {e.message}")

                        # Update last_synced_at
                        campaign.last_synced_at = datetime.utcnow()
                        campaigns_synced += 1

                    except Exception as e:
                        # Try/except per campaign so one failure doesn't stop all
                        error_msg = f"Error syncing campaign {campaign_data.get('id')}: {str(e)}"
                        logger.error(error_msg)
                        errors.append(error_msg)
                        continue

            # Step 4: Update sync_log
            await self._complete_sync_log(
                sync_log,
                status="completed" if not errors else "completed_with_errors",
                campaigns_synced=campaigns_synced,
                error_message="; ".join(errors[:5]) if errors else None,  # First 5 errors
            )

            logger.info(f"Full sync completed: {campaigns_synced} campaigns, {total_replies_synced} replies")

            return {
                "status": "success" if not errors else "completed_with_errors",
                "campaigns_synced": campaigns_synced,
                "replies_synced": total_replies_synced,
                "errors": len(errors),
                "error_messages": errors[:5] if errors else [],
            }

        except Exception as e:
            logger.error(f"Full sync failed: {str(e)}")
            await self._complete_sync_log(sync_log, status="failed", error_message=str(e))
            raise

    async def _paginate_statistics(self, client: SmartleadClient, campaign_id: int) -> list[dict]:
        """
        Fetch all pages of campaign statistics.

        Pagination: offset += 100 until data < 100

        Args:
            client: SmartleadClient instance
            campaign_id: Smartlead campaign ID

        Returns:
            Complete list of all lead statistics
        """
        all_stats = []
        offset = 0

        while True:
            logger.debug(f"Fetching statistics page at offset {offset}")

            result = await client.get_campaign_statistics(
                campaign_id=campaign_id,
                offset=offset,
                limit=PAGE_SIZE,
            )
            await asyncio.sleep(API_DELAY)

            # Handle different response formats
            if isinstance(result, dict):
                data = result.get("data", [])
            elif isinstance(result, list):
                data = result
            else:
                data = []

            if not data:
                break

            all_stats.extend(data)

            # If we got fewer than PAGE_SIZE, we're done
            if len(data) < PAGE_SIZE:
                break

            offset += PAGE_SIZE

        logger.info(f"Fetched {len(all_stats)} total statistics for campaign {campaign_id}")
        return all_stats

    async def _dedupe_replies(self, campaign_id: int, stats: list[dict]) -> tuple[int, int]:
        """
        Insert/update lead_replies, skip if email exists (dedupe).

        Args:
            campaign_id: Local campaign ID
            stats: List of lead statistics from Smartlead

        Returns:
            Tuple of (total_replies_synced, positive_replies_count)
        """
        replies_synced = 0
        positive_count = 0

        # Filter to only replied leads
        replied_leads = [s for s in stats if s.get("lead_status") == "REPLIED" or s.get("email_status") == "REPLIED"]

        for lead_data in replied_leads:
            email = lead_data.get("email")
            if not email:
                continue

            # Check if already exists (dedupe by email)
            result = await self.db.execute(
                select(LeadReply).where(
                    LeadReply.campaign_id == campaign_id,
                    LeadReply.lead_email == email,
                )
            )
            existing = result.scalar_one_or_none()

            # Determine if positive
            category = lead_data.get("lead_category", "") or ""
            is_positive = is_positive_category(category)

            if is_positive:
                positive_count += 1

            if existing:
                # Update existing
                existing.lead_name = lead_data.get("name") or lead_data.get("first_name")
                existing.lead_category = category
                existing.is_positive = is_positive
                existing.sequence_number = lead_data.get("sequence_number")
                existing.variant_id = lead_data.get("variant_id")
            else:
                # Insert new
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
                replies_synced += 1

        await self.db.flush()
        logger.info(f"Synced {replies_synced} new replies for campaign {campaign_id}")

        return replies_synced, positive_count

    async def _update_campaign_reply_counts(self, campaign_id: int):
        """Update daily stats with unique_replied and positive_replies counts."""
        # Count unique replies
        unique_replied = await self.db.scalar(
            select(func.count(LeadReply.id)).where(LeadReply.campaign_id == campaign_id)
        )

        # Count positive replies
        positive_replies = await self.db.scalar(
            select(func.count(LeadReply.id)).where(
                LeadReply.campaign_id == campaign_id,
                LeadReply.is_positive == True,
            )
        )

        # Get today's daily stats or create if not exists
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.db.execute(
            select(CampaignDailyStats).where(
                CampaignDailyStats.campaign_id == campaign_id,
                CampaignDailyStats.date == today,
            )
        )
        daily_stats = result.scalar_one_or_none()

        if daily_stats:
            daily_stats.unique_replied = unique_replied or 0
            daily_stats.positive_replies = positive_replies or 0
        else:
            # Create today's entry with reply counts
            daily_stats = CampaignDailyStats(
                campaign_id=campaign_id,
                date=today,
                unique_replied=unique_replied or 0,
                positive_replies=positive_replies or 0,
            )
            self.db.add(daily_stats)

        await self.db.flush()

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
        else:
            campaign = Campaign(
                smartlead_id=smartlead_id,
                name=campaign_data.get("name", "Unnamed Campaign"),
                status=campaign_data.get("status", "draft"),
                client_id=campaign_data.get("client_id"),
                client_name=campaign_data.get("client_name"),
            )
            self.db.add(campaign)

        await self.db.flush()
        return campaign

    async def _upsert_daily_stats(self, campaign_id: int, stats_data: dict) -> Optional[CampaignDailyStats]:
        """Insert or update daily campaign stats."""
        date_str = stats_data.get("date")
        if not date_str:
            return None

        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return None

        # Log the raw API response keys for debugging (only once per sync)
        if not hasattr(self, '_logged_stats_keys'):
            self._logged_stats_keys = True
            logger.info(f"Smartlead analytics-by-date response keys: {list(stats_data.keys())}")
            logger.info(f"Smartlead analytics-by-date sample data: {stats_data}")

        result = await self.db.execute(
            select(CampaignDailyStats).where(
                CampaignDailyStats.campaign_id == campaign_id,
                CampaignDailyStats.date == date,
            )
        )
        daily_stats = result.scalar_one_or_none()

        # Extract values with fallbacks - Smartlead API may use various field names
        # Try multiple possible field names for each metric
        sent_count = (
            stats_data.get("sent_count", 0) or
            stats_data.get("emails_sent", 0) or
            stats_data.get("total_sent", 0) or
            stats_data.get("sent", 0) or 0
        )
        reply_count = (
            stats_data.get("reply_count", 0) or
            stats_data.get("replies", 0) or
            stats_data.get("total_replies", 0) or 0
        )
        unique_sent = (
            stats_data.get("unique_sent_count", 0) or
            stats_data.get("unique_sent", 0) or
            sent_count
        )
        unique_replied = (
            stats_data.get("unique_reply_count", 0) or
            stats_data.get("unique_replied", 0) or
            reply_count
        )
        positive_replies = (
            stats_data.get("positive_reply_count", 0) or
            stats_data.get("positive_replies", 0) or 0
        )
        bounce_count = (
            stats_data.get("bounce_count", 0) or
            stats_data.get("bounced", 0) or
            stats_data.get("bounces", 0) or 0
        )
        open_count = (
            stats_data.get("open_count", 0) or
            stats_data.get("opened", 0) or
            stats_data.get("opens", 0) or 0
        )
        click_count = (
            stats_data.get("click_count", 0) or
            stats_data.get("clicked", 0) or
            stats_data.get("clicks", 0) or 0
        )

        if daily_stats:
            daily_stats.sent_count = sent_count
            daily_stats.reply_count = reply_count
            daily_stats.unique_sent = unique_sent
            daily_stats.unique_replied = unique_replied
            daily_stats.positive_replies = positive_replies
            daily_stats.bounce_count = bounce_count
            daily_stats.open_count = open_count
            daily_stats.click_count = click_count
        else:
            daily_stats = CampaignDailyStats(
                campaign_id=campaign_id,
                date=date,
                sent_count=sent_count,
                reply_count=reply_count,
                unique_sent=unique_sent,
                unique_replied=unique_replied,
                positive_replies=positive_replies,
                bounce_count=bounce_count,
                open_count=open_count,
                click_count=click_count,
            )
            self.db.add(daily_stats)

        await self.db.flush()
        return daily_stats

    async def _upsert_sequence(self, campaign_id: int, seq_data: dict) -> Sequence:
        """Insert or update a sequence."""
        smartlead_id = seq_data.get("id")
        seq_number = seq_data.get("seq_number", 1) or seq_data.get("sequence_number", 1)

        result = await self.db.execute(
            select(Sequence).where(
                Sequence.campaign_id == campaign_id,
                Sequence.smartlead_id == smartlead_id,
            )
        )
        sequence = result.scalar_one_or_none()

        if sequence:
            sequence.seq_number = seq_number
            sequence.variant_label = seq_data.get("variant_label") or seq_data.get("variant")
            sequence.subject = seq_data.get("subject")
            sequence.email_body = seq_data.get("email_body") or seq_data.get("body")
            sequence.sent_count = seq_data.get("sent_count", 0) or 0
            sequence.reply_count = seq_data.get("reply_count", 0) or 0
        else:
            sequence = Sequence(
                smartlead_id=smartlead_id,
                campaign_id=campaign_id,
                seq_number=seq_number,
                variant_label=seq_data.get("variant_label") or seq_data.get("variant"),
                subject=seq_data.get("subject"),
                email_body=seq_data.get("email_body") or seq_data.get("body"),
                sent_count=seq_data.get("sent_count", 0) or 0,
                reply_count=seq_data.get("reply_count", 0) or 0,
            )
            self.db.add(sequence)

        await self.db.flush()
        return sequence

    # Convenience methods for individual syncs

    async def sync_campaigns(self) -> dict:
        """Sync only campaigns (no related data)."""
        sync_log = await self._create_sync_log()
        campaigns_synced = 0

        try:
            async with SmartleadClient() as client:
                campaigns_data = await client.get_all_campaigns()

                for campaign_data in campaigns_data:
                    await self._upsert_campaign(campaign_data)
                    campaigns_synced += 1
                    await asyncio.sleep(API_DELAY)

            await self._complete_sync_log(sync_log, campaigns_synced=campaigns_synced)
            return {"status": "success", "campaigns_synced": campaigns_synced}

        except Exception as e:
            await self._complete_sync_log(sync_log, status="failed", error_message=str(e))
            raise

    async def sync_campaign_daily_stats(self, campaign_id: int, start_date: str, end_date: str) -> dict:
        """Sync daily stats for a specific campaign."""
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        async with SmartleadClient() as client:
            daily_data = await client.get_campaign_analytics_by_date(
                campaign.smartlead_id, start_date, end_date
            )

            days_synced = 0
            for day_stats in daily_data:
                await self._upsert_daily_stats(campaign.id, day_stats)
                days_synced += 1

        return {"status": "success", "campaign_id": campaign_id, "days_synced": days_synced}

    async def sync_sequences(self, campaign_id: int) -> dict:
        """Sync sequences for a specific campaign."""
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        async with SmartleadClient() as client:
            sequences_data = await client.get_campaign_sequences(campaign.smartlead_id)

            sequences_synced = 0
            for seq_data in sequences_data:
                await self._upsert_sequence(campaign.id, seq_data)
                sequences_synced += 1

        return {"status": "success", "campaign_id": campaign_id, "sequences_synced": sequences_synced}

    async def sync_lead_replies(self, campaign_id: int) -> dict:
        """Sync lead replies for a specific campaign."""
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        async with SmartleadClient() as client:
            all_stats = await self._paginate_statistics(client, campaign.smartlead_id)
            replies_synced, positive_count = await self._dedupe_replies(campaign.id, all_stats)

        return {
            "status": "success",
            "campaign_id": campaign_id,
            "replies_synced": replies_synced,
            "positive_replies": positive_count,
        }

    async def sync_all(self) -> dict:
        """Alias for sync_all_campaigns for backwards compatibility."""
        return await self.sync_all_campaigns()

    async def get_last_sync(self) -> Optional[SyncLog]:
        """Get the most recent sync log."""
        result = await self.db.execute(
            select(SyncLog).order_by(SyncLog.started_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()
