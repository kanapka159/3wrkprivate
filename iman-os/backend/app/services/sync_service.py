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
                campaigns_response = await client.get_all_campaigns()
                await asyncio.sleep(API_DELAY)

                # Handle different response formats (list vs {"data": [...]})
                if isinstance(campaigns_response, dict):
                    campaigns_data = campaigns_response.get("data", [])
                elif isinstance(campaigns_response, list):
                    campaigns_data = campaigns_response
                else:
                    campaigns_data = []

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

                        # 3b: Get aggregate analytics first (more reliable)
                        try:
                            aggregate_analytics = await client.get_campaign_analytics(smartlead_id)
                            await asyncio.sleep(API_DELAY)

                            # Log the response to understand the format
                            logger.info(f"Aggregate analytics for campaign {smartlead_id}: {aggregate_analytics}")

                            # Handle response format (could be dict with data or direct dict)
                            if isinstance(aggregate_analytics, dict):
                                analytics_data = aggregate_analytics.get("data", aggregate_analytics)
                                if isinstance(analytics_data, dict):
                                    # Store aggregate stats as today's entry
                                    today = datetime.utcnow().strftime("%Y-%m-%d")
                                    aggregate_with_date = {**analytics_data, "date": today}
                                    await self._upsert_daily_stats(campaign.id, aggregate_with_date)
                                    logger.info(f"Stored aggregate analytics for campaign {smartlead_id}")

                        except SmartleadAPIError as e:
                            logger.warning(f"Failed to get aggregate analytics for campaign {smartlead_id}: {e.message}")

                        # 3b-2: Also try analytics by date for historical data
                        end_date = datetime.utcnow().strftime("%Y-%m-%d")
                        start_date = (datetime.utcnow() - timedelta(days=28)).strftime("%Y-%m-%d")

                        try:
                            analytics_response = await client.get_campaign_analytics_by_date(
                                smartlead_id, start_date, end_date
                            )
                            await asyncio.sleep(API_DELAY)

                            # Handle different response formats
                            if isinstance(analytics_response, dict):
                                daily_analytics = analytics_response.get("data", [])
                            elif isinstance(analytics_response, list):
                                daily_analytics = analytics_response
                            else:
                                daily_analytics = []

                            logger.info(f"Got {len(daily_analytics)} days of analytics for campaign {smartlead_id}")

                            # Store daily stats
                            for day_data in daily_analytics:
                                if isinstance(day_data, dict):
                                    await self._upsert_daily_stats(campaign.id, day_data)

                        except SmartleadAPIError as e:
                            logger.warning(f"Failed to get daily analytics for campaign {smartlead_id}: {e.message}")

                        # 3c: Get REPLIED leads specifically (much faster than paginating all stats)
                        try:
                            replied_stats = await self._fetch_replied_leads(client, smartlead_id)
                            await asyncio.sleep(API_DELAY)

                            # 3d: Dedupe replies and count
                            replies_count, positive_count = await self._process_replied_leads(
                                campaign.id, replied_stats
                            )
                            total_replies_synced += replies_count

                            # Update campaign with reply counts
                            await self._update_campaign_reply_counts(campaign.id)

                        except SmartleadAPIError as e:
                            logger.warning(f"Failed to get replied leads for campaign {smartlead_id}: {e.message}")

                        # 3e: Get sequences
                        try:
                            sequences_response = await client.get_campaign_sequences(smartlead_id)
                            await asyncio.sleep(API_DELAY)

                            # Handle different response formats
                            if isinstance(sequences_response, dict):
                                sequences_data = sequences_response.get("data", [])
                            elif isinstance(sequences_response, list):
                                sequences_data = sequences_response
                            else:
                                sequences_data = []

                            for seq_data in sequences_data:
                                if isinstance(seq_data, dict):
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

    async def _fetch_replied_leads(self, client: SmartleadClient, campaign_id: int) -> list[dict]:
        """
        Fetch only replied leads using the email_status filter.

        This is much faster than fetching all leads and filtering locally.
        """
        all_replied = []
        offset = 0

        while True:
            logger.debug(f"Fetching replied leads at offset {offset}")

            # Use email_status filter to get only replied leads (lowercase!)
            result = await client.get_campaign_statistics(
                campaign_id=campaign_id,
                offset=offset,
                limit=PAGE_SIZE,
                email_status="replied",
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

            all_replied.extend(data)

            # If we got fewer than PAGE_SIZE, we're done
            if len(data) < PAGE_SIZE:
                break

            offset += PAGE_SIZE

        logger.info(f"Fetched {len(all_replied)} replied leads for campaign {campaign_id}")
        return all_replied

    async def _process_replied_leads(self, campaign_id: int, stats: list[dict]) -> tuple[int, int]:
        """
        Process replied leads - insert to lead_replies table with deduplication.

        Args:
            campaign_id: Local campaign ID
            stats: List of replied lead statistics

        Returns:
            Tuple of (total_replies_synced, positive_replies_count)
        """
        replies_synced = 0
        positive_count = 0

        if not stats:
            logger.info(f"No replied leads to process for campaign {campaign_id}")
            return 0, 0

        # Log sample data
        logger.info(f"Processing {len(stats)} replied leads for campaign {campaign_id}")
        logger.info(f"Sample replied lead: {stats[0]}")

        for lead_data in stats:
            email = lead_data.get("lead_email") or lead_data.get("email")
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

            # Determine if positive based on lead_category
            category = lead_data.get("lead_category", "") or ""
            is_positive = is_positive_category(category)

            if is_positive:
                positive_count += 1

            # Get reply time
            reply_time_str = lead_data.get("reply_time")
            reply_time = None
            if reply_time_str:
                try:
                    reply_time = datetime.fromisoformat(reply_time_str.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    reply_time = datetime.utcnow()

            if existing:
                # Update existing
                existing.lead_name = lead_data.get("lead_name") or lead_data.get("name") or lead_data.get("first_name")
                existing.lead_category = category
                existing.is_positive = is_positive
                existing.sequence_number = lead_data.get("sequence_number")
                existing.variant_id = lead_data.get("seq_variant_id") or lead_data.get("variant_id")
            else:
                # Insert new
                lead_reply = LeadReply(
                    campaign_id=campaign_id,
                    lead_email=email,
                    lead_name=lead_data.get("lead_name") or lead_data.get("name") or lead_data.get("first_name"),
                    lead_category=category,
                    first_reply_time=reply_time or datetime.utcnow(),
                    is_positive=is_positive,
                    sequence_number=lead_data.get("sequence_number"),
                    variant_id=lead_data.get("seq_variant_id") or lead_data.get("variant_id"),
                )
                self.db.add(lead_reply)
                # Flush immediately to handle duplicates
                try:
                    await self.db.flush()
                    replies_synced += 1
                except Exception as e:
                    # Skip duplicate - rollback just this entry
                    await self.db.rollback()
                    logger.debug(f"Skipping duplicate reply for {email}: {e}")

        logger.info(f"Synced {replies_synced} new replies for campaign {campaign_id}")

        return replies_synced, positive_count

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

        # Log sample data to debug field names
        if stats:
            logger.info(f"Sample lead stat for campaign {campaign_id}: {stats[0]}")

        # Filter to only replied leads - check multiple possible indicators
        replied_leads = []
        for s in stats:
            # Check various possible field names and values for replied status
            lead_status = str(s.get("lead_status", "")).upper()
            email_status = str(s.get("email_status", "")).upper()
            status = str(s.get("status", "")).upper()
            reply_status = str(s.get("reply_status", "")).upper()
            # reply_time is the key indicator in Smartlead - if not null, lead replied
            reply_time = s.get("reply_time")

            if any([
                reply_time is not None,  # Main indicator in Smartlead API
                lead_status == "REPLIED",
                email_status == "REPLIED",
                status == "REPLIED",
                reply_status == "REPLIED",
                s.get("replied", False),
                s.get("has_replied", False),
                s.get("is_replied", False),
            ]):
                replied_leads.append(s)

        logger.info(f"Found {len(replied_leads)} replied leads out of {len(stats)} total for campaign {campaign_id}")

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

        # Parse created_at from Smartlead - try multiple field names
        created_at = None
        for field in ["created_at", "createdAt", "created_time", "createdTime", "created", "create_date"]:
            date_str = campaign_data.get(field)
            if date_str:
                try:
                    # Handle various date formats from Smartlead
                    if isinstance(date_str, str):
                        # Try ISO format first
                        if "T" in date_str:
                            created_at = datetime.fromisoformat(date_str.replace('Z', '+00:00').replace('+00:00', ''))
                        else:
                            # Try common formats
                            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y"]:
                                try:
                                    created_at = datetime.strptime(date_str, fmt)
                                    break
                                except ValueError:
                                    continue
                    elif isinstance(date_str, datetime):
                        created_at = date_str
                    if created_at:
                        break
                except (ValueError, TypeError) as e:
                    logger.debug(f"Could not parse date {date_str}: {e}")
                    continue

        # Log the raw campaign data to see what fields are available
        logger.info(f"Campaign data keys for {smartlead_id}: {list(campaign_data.keys())}")
        if created_at:
            logger.info(f"Parsed created_at for campaign {smartlead_id}: {created_at}")

        # Parse completion percentage - try multiple field names
        completion = None
        for field in ["progress", "completion", "completion_percentage", "percent_complete", "campaign_progress"]:
            val = campaign_data.get(field)
            if val is not None:
                try:
                    completion = float(val)
                    break
                except (ValueError, TypeError):
                    continue

        # Parse total leads count
        total_leads = None
        for field in ["total_leads", "lead_count", "leads_count", "total_lead_count", "leads"]:
            val = campaign_data.get(field)
            if val is not None:
                try:
                    total_leads = int(val)
                    break
                except (ValueError, TypeError):
                    continue

        if campaign:
            campaign.name = campaign_data.get("name", campaign.name)
            campaign.status = campaign_data.get("status", campaign.status)
            campaign.client_id = campaign_data.get("client_id")
            campaign.client_name = campaign_data.get("client_name")
            # Update created_at if we got it from Smartlead and don't have it yet
            if created_at and not campaign.created_at:
                campaign.created_at = created_at
            # Update completion percentage
            if completion is not None:
                campaign.completion_percentage = completion
            if total_leads is not None:
                campaign.total_leads = total_leads
        else:
            campaign = Campaign(
                smartlead_id=smartlead_id,
                name=campaign_data.get("name", "Unnamed Campaign"),
                status=campaign_data.get("status", "draft"),
                client_id=campaign_data.get("client_id"),
                client_name=campaign_data.get("client_name"),
                created_at=created_at,  # Store Smartlead creation date
                completion_percentage=completion,
                total_leads=total_leads,
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

        result = await self.db.execute(
            select(CampaignDailyStats).where(
                CampaignDailyStats.campaign_id == campaign_id,
                CampaignDailyStats.date == date,
            )
        )
        daily_stats = result.scalar_one_or_none()

        # Helper to get value from multiple possible field names
        # Also handles string values (Smartlead returns strings like "4" instead of 4)
        def get_val(*keys):
            for key in keys:
                val = stats_data.get(key)
                if val is not None:
                    # Convert string to int if needed
                    if isinstance(val, str):
                        try:
                            val = int(val)
                        except ValueError:
                            continue
                    if val != 0:
                        return val
            return 0

        # Extract values using various possible field names from Smartlead API
        sent = get_val("sent_count", "sent", "emails_sent", "total_sent", "total_emails_sent")
        replied = get_val("reply_count", "replied", "replies", "total_replied", "total_replies", "reply", "total_reply")
        unique_sent = get_val("unique_sent_count", "unique_sent", "unique_emails_sent")
        unique_replied = get_val("unique_reply_count", "unique_replied", "unique_replies", "unique_reply")
        positive = get_val("positive_reply_count", "positive_replies", "positive_replied", "positive_reply", "interested")
        bounced = get_val("bounce_count", "bounced", "bounces", "total_bounced", "total_bounces")
        opened = get_val("open_count", "opened", "opens", "total_opened", "total_opens")
        clicked = get_val("click_count", "clicked", "clicks", "total_clicked", "total_clicks")

        # Log extracted values for debugging
        logger.info(f"Daily stats for campaign {campaign_id} date {date_str}: sent={sent}, replied={replied}, opened={opened}, bounced={bounced}")

        if daily_stats:
            daily_stats.sent_count = sent
            daily_stats.reply_count = replied
            daily_stats.unique_sent = unique_sent or sent  # fallback to sent if no unique
            daily_stats.unique_replied = unique_replied or replied
            daily_stats.positive_replies = positive
            daily_stats.bounce_count = bounced
            daily_stats.open_count = opened
            daily_stats.click_count = clicked
        else:
            daily_stats = CampaignDailyStats(
                campaign_id=campaign_id,
                date=date,
                sent_count=sent,
                reply_count=replied,
                unique_sent=unique_sent or sent,
                unique_replied=unique_replied or replied,
                positive_replies=positive,
                bounce_count=bounced,
                open_count=opened,
                click_count=clicked,
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
                campaigns_response = await client.get_all_campaigns()

                # Handle different response formats
                if isinstance(campaigns_response, dict):
                    campaigns_data = campaigns_response.get("data", [])
                elif isinstance(campaigns_response, list):
                    campaigns_data = campaigns_response
                else:
                    campaigns_data = []

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
