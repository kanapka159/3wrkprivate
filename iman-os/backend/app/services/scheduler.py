"""
Background Scheduler Service

Runs automatic campaign refresh every 30 minutes with rate limiting.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Scheduler configuration
REFRESH_INTERVAL_MINUTES = 30
BATCH_SIZE = 2  # 2 campaigns per batch (~10 API calls)
BATCH_DELAY_SECONDS = 2  # Wait 2 seconds between batches


class SchedulerMetrics:
    """Track scheduler and API metrics."""

    def __init__(self):
        self.start_time = datetime.utcnow()
        self.last_refresh: Optional[datetime] = None
        self.next_refresh: Optional[datetime] = None
        self.api_calls_24h: list[datetime] = []
        self.total_refreshes = 0
        self.last_refresh_duration: Optional[float] = None
        self.last_refresh_campaigns: int = 0
        self.last_error: Optional[str] = None
        self._lock = asyncio.Lock()

    @property
    def uptime(self) -> str:
        """Get uptime as human-readable string."""
        delta = datetime.utcnow() - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours}h {minutes}m"

    async def record_api_call(self, count: int = 1):
        """Record API calls for rate tracking."""
        async with self._lock:
            now = datetime.utcnow()
            for _ in range(count):
                self.api_calls_24h.append(now)
            # Clean up calls older than 24 hours
            cutoff = now - timedelta(hours=24)
            self.api_calls_24h = [t for t in self.api_calls_24h if t > cutoff]

    async def get_api_calls_24h(self) -> int:
        """Get count of API calls in last 24 hours."""
        async with self._lock:
            cutoff = datetime.utcnow() - timedelta(hours=24)
            self.api_calls_24h = [t for t in self.api_calls_24h if t > cutoff]
            return len(self.api_calls_24h)

    async def record_refresh(self, duration: float, campaigns: int, error: Optional[str] = None):
        """Record a refresh completion."""
        async with self._lock:
            self.last_refresh = datetime.utcnow()
            self.next_refresh = self.last_refresh + timedelta(minutes=REFRESH_INTERVAL_MINUTES)
            self.total_refreshes += 1
            self.last_refresh_duration = duration
            self.last_refresh_campaigns = campaigns
            self.last_error = error

    def get_status(self) -> dict:
        """Get scheduler status for health endpoint."""
        return {
            "status": "healthy" if self.last_error is None else "degraded",
            "uptime": self.uptime,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
            "next_refresh": self.next_refresh.isoformat() if self.next_refresh else None,
            "total_refreshes": self.total_refreshes,
            "last_refresh_duration_seconds": round(self.last_refresh_duration, 2) if self.last_refresh_duration else None,
            "last_refresh_campaigns": self.last_refresh_campaigns,
            "last_error": self.last_error,
        }


# Global metrics instance
metrics = SchedulerMetrics()


class BackgroundScheduler:
    """
    Background scheduler for automatic campaign refresh.

    Runs every 30 minutes and processes campaigns in batches
    to respect Smartlead API rate limits (10 calls per 2 seconds).
    """

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start the background scheduler."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info(f"Background scheduler started (refresh every {REFRESH_INTERVAL_MINUTES} minutes)")

    async def stop(self):
        """Stop the background scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Background scheduler stopped")

    async def _run_scheduler(self):
        """Main scheduler loop."""
        # Set initial next refresh time
        metrics.next_refresh = datetime.utcnow() + timedelta(minutes=REFRESH_INTERVAL_MINUTES)

        while self._running:
            try:
                # Wait for next refresh interval
                await asyncio.sleep(REFRESH_INTERVAL_MINUTES * 60)

                if not self._running:
                    break

                # Run refresh
                await self.refresh_all_campaigns()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await metrics.record_refresh(0, 0, str(e))
                # Continue running despite errors
                await asyncio.sleep(60)  # Wait a bit before retrying

    async def refresh_all_campaigns(self):
        """
        Refresh all campaigns with batch processing.

        Processes campaigns in batches of 2 with 2-second delays
        to respect API rate limits.
        """
        from ..db.database import AsyncSessionLocal
        from .sync_service import SyncService
        from .cache_service import cache

        start_time = datetime.utcnow()
        campaigns_processed = 0
        error = None

        logger.info("Starting scheduled campaign refresh")

        try:
            async with AsyncSessionLocal() as db:
                sync_service = SyncService(db)

                # Get all campaign IDs
                from sqlalchemy import select
                from ..db.models import Campaign

                result = await db.execute(
                    select(Campaign.id, Campaign.smartlead_id, Campaign.name)
                    .where(Campaign.status != "DRAFTED")
                    .where(Campaign.is_hidden == False)
                )
                campaigns = result.all()

                total_campaigns = len(campaigns)
                logger.info(f"Found {total_campaigns} campaigns to refresh")

                # Process in batches
                for i in range(0, total_campaigns, BATCH_SIZE):
                    batch = campaigns[i:i + BATCH_SIZE]

                    # Process batch concurrently
                    tasks = []
                    for campaign in batch:
                        campaign_id, smartlead_id, name = campaign
                        tasks.append(
                            self._refresh_single_campaign(
                                sync_service, campaign_id, smartlead_id, name
                            )
                        )

                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # Count successful refreshes
                    for result in results:
                        if not isinstance(result, Exception):
                            campaigns_processed += 1
                        else:
                            logger.warning(f"Campaign refresh failed: {result}")

                    # Record API calls (approximately 5 calls per campaign)
                    await metrics.record_api_call(len(batch) * 5)

                    # Wait between batches to respect rate limits
                    if i + BATCH_SIZE < total_campaigns:
                        await asyncio.sleep(BATCH_DELAY_SECONDS)

                # Commit all changes
                await db.commit()

                # Invalidate cache after refresh
                await cache.invalidate_pattern("campaigns")

        except Exception as e:
            error = str(e)
            logger.error(f"Campaign refresh failed: {e}")

        # Record metrics
        duration = (datetime.utcnow() - start_time).total_seconds()
        await metrics.record_refresh(duration, campaigns_processed, error)

        logger.info(
            f"Campaign refresh completed: {campaigns_processed} campaigns "
            f"in {duration:.2f} seconds"
        )

        return {
            "campaigns_processed": campaigns_processed,
            "duration_seconds": duration,
            "error": error,
        }

    async def _refresh_single_campaign(
        self,
        sync_service,
        campaign_id: int,
        smartlead_id: int,
        name: str,
    ):
        """Refresh a single campaign's metrics."""
        from .smartlead import SmartleadClient, SmartleadAPIError

        try:
            async with SmartleadClient() as client:
                # Get campaign from database
                from sqlalchemy import select
                from ..db.models import Campaign

                result = await sync_service.db.execute(
                    select(Campaign).where(Campaign.id == campaign_id)
                )
                campaign = result.scalar_one_or_none()

                if not campaign:
                    return

                # Fetch and update lead statistics
                try:
                    lead_stats = await client.get_campaign_lead_stats(smartlead_id)
                    if isinstance(lead_stats, dict):
                        campaign_lead_stats = lead_stats.get("campaign_lead_stats", {})
                        campaign.total_leads = sync_service._safe_int(campaign_lead_stats.get("total"))
                        campaign.leads_completed = sync_service._safe_int(campaign_lead_stats.get("completed"))
                        campaign.leads_blocked = sync_service._safe_int(campaign_lead_stats.get("blocked"))
                        campaign.leads_paused = sync_service._safe_int(campaign_lead_stats.get("paused"))
                        campaign.leads_not_started = sync_service._safe_int(campaign_lead_stats.get("notStarted"))
                        campaign.leads_in_progress = sync_service._safe_int(campaign_lead_stats.get("inprogress"))
                        campaign.leads_interested = sync_service._safe_int(campaign_lead_stats.get("interested"))

                        # Calculate progress
                        if campaign.total_leads and campaign.total_leads > 0:
                            progress = ((campaign.leads_completed + campaign.leads_blocked + campaign.leads_paused) / campaign.total_leads) * 100
                            campaign.completion_percentage = round(progress, 0)
                except SmartleadAPIError as e:
                    logger.warning(f"Failed to get lead stats for {name}: {e.message}")

                # Fetch aggregate analytics
                try:
                    analytics = await client.get_campaign_analytics(smartlead_id)
                    if isinstance(analytics, dict):
                        stats = analytics.get("data", analytics)
                        if isinstance(stats, dict):
                            campaign.total_sent = sync_service._safe_int(stats.get("sent_count") or stats.get("unique_sent_count"))
                            campaign.total_replied = sync_service._safe_int(stats.get("reply_count") or stats.get("unique_reply_count"))
                            campaign.total_opens = sync_service._safe_int(stats.get("open_count") or stats.get("unique_open_count"))
                            campaign.total_bounces = sync_service._safe_int(stats.get("bounce_count"))
                except SmartleadAPIError as e:
                    logger.warning(f"Failed to get analytics for {name}: {e.message}")

                # Update last synced timestamp
                campaign.last_synced_at = datetime.utcnow()
                await sync_service.db.flush()

                logger.debug(f"Refreshed campaign: {name}")

        except Exception as e:
            logger.error(f"Error refreshing campaign {name}: {e}")
            raise


# Global scheduler instance
scheduler = BackgroundScheduler()
