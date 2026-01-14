"""
IMAN OS - Campaign Analytics Dashboard

FastAPI application for Smartlead campaign analytics and management.
"""

import os
import sys
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .api import api_router
from .db.database import init_db

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    from .services import scheduler

    # Startup
    logger.info("Starting IMAN OS Backend...")

    # Check for required API key
    if not os.getenv("SMARTLEAD_API_KEY"):
        logger.error("SMARTLEAD_API_KEY not set! Please configure .env file.")
        sys.exit(1)

    logger.info("API key configured")
    logger.info("Creating database tables...")
    await init_db()
    logger.info("Database initialized - all tables created")

    # Start background scheduler (unless disabled)
    if os.getenv("DISABLE_SCHEDULER", "false").lower() != "true":
        await scheduler.start()
        logger.info("Background scheduler started")
    else:
        logger.info("Background scheduler disabled via DISABLE_SCHEDULER env var")

    yield

    # Shutdown
    logger.info("Shutting down IMAN OS Backend...")
    await scheduler.stop()
    logger.info("Background scheduler stopped")


# Create FastAPI app (redirect_slashes=False prevents 307 redirects)
app = FastAPI(
    title="IMAN OS",
    description="Campaign Analytics Dashboard for Smartlead",
    version="0.1.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "name": "IMAN OS",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """
    Comprehensive health check endpoint.

    Returns:
    - status: "healthy" or "degraded"
    - uptime: How long the server has been running
    - lastRefresh: Timestamp of last campaign refresh
    - nextRefresh: Timestamp of next scheduled refresh
    - cacheSize: Number of items in cache
    - apiCallsLast24h: API calls made in last 24 hours
    """
    from .services import metrics, cache

    scheduler_status = metrics.get_status()
    cache_status = await cache.get_status()
    api_calls = await metrics.get_api_calls_24h()

    return {
        "status": scheduler_status["status"],
        "uptime": scheduler_status["uptime"],
        "lastRefresh": scheduler_status["last_refresh"],
        "nextRefresh": scheduler_status["next_refresh"],
        "cacheSize": cache_status["total_entries"],
        "apiCallsLast24h": api_calls,
        "scheduler": {
            "totalRefreshes": scheduler_status["total_refreshes"],
            "lastRefreshDuration": scheduler_status["last_refresh_duration_seconds"],
            "lastRefreshCampaigns": scheduler_status["last_refresh_campaigns"],
            "lastError": scheduler_status["last_error"],
        },
        "cache": {
            "hitRate": cache_status["hit_rate"],
            "totalHits": cache_status["total_hits"],
            "totalMisses": cache_status["total_misses"],
        },
    }


@app.post("/reset-db")
async def reset_database():
    """Reset the database - clears all data and recreates tables."""
    import glob
    from .db.database import engine, Base

    # Remove SQLite files
    db_files = glob.glob("*.db*")
    for f in db_files:
        try:
            os.remove(f)
            logger.info(f"Removed {f}")
        except Exception as e:
            logger.warning(f"Could not remove {f}: {e}")

    # Dispose existing connections
    await engine.dispose()

    # Recreate tables
    await init_db()

    return {"status": "database reset", "removed_files": db_files}


@app.get("/debug/campaign/{smartlead_id}")
async def debug_campaign_api(smartlead_id: int, email_status: str = None):
    """Debug endpoint to see raw Smartlead API responses for a campaign."""
    from .services import SmartleadClient

    async with SmartleadClient() as client:
        # Fetch raw responses
        analytics = await client.get_campaign_analytics(smartlead_id)
        statistics = await client.get_campaign_statistics(smartlead_id, offset=0, limit=10, email_status=email_status)

        return {
            "smartlead_id": smartlead_id,
            "email_status_filter": email_status,
            "analytics_response": analytics,
            "statistics_response_sample": statistics,
        }


@app.post("/quick-sync/{smartlead_id}")
async def quick_sync_campaign(smartlead_id: int):
    """Quick sync a single campaign with minimal database operations."""
    from fastapi import Depends
    from .services import SmartleadClient, SyncService
    from .db.database import AsyncSessionLocal, init_db

    try:
        # Ensure tables exist
        await init_db()

        async with AsyncSessionLocal() as db:
            async with SmartleadClient() as client:
                # Get campaign data
                all_campaigns = await client.get_all_campaigns()
                campaigns = all_campaigns.get("data", all_campaigns) if isinstance(all_campaigns, dict) else all_campaigns or []

                campaign_data = next((c for c in campaigns if c.get("id") == smartlead_id), None)
                if not campaign_data:
                    return {"error": f"Campaign {smartlead_id} not found in API"}

                sync_service = SyncService(db)

                # Upsert campaign
                campaign = await sync_service._upsert_campaign(campaign_data)
                logger.info(f"Upserted campaign {campaign.id}")

                # Get analytics
                analytics = await client.get_campaign_analytics(smartlead_id)
                logger.info(f"Got analytics")

                # Store analytics
                from datetime import datetime
                today = datetime.utcnow().strftime("%Y-%m-%d")
                await sync_service._upsert_daily_stats(campaign.id, {**analytics, "date": today})
                logger.info(f"Stored daily stats")

                # Get replied leads
                replied = await client.get_campaign_statistics(smartlead_id, offset=0, limit=100, email_status="replied")
                replied_data = replied.get("data", []) if isinstance(replied, dict) else []
                logger.info(f"Got {len(replied_data)} replied leads")

                # Process replied leads
                replies_count, positive_count = await sync_service._process_replied_leads(campaign.id, replied_data)
                logger.info(f"Processed replies: {replies_count} new, {positive_count} positive")

                await db.commit()
                logger.info(f"Committed to database")

                return {
                    "status": "success",
                    "campaign_id": campaign.id,
                    "smartlead_id": smartlead_id,
                    "name": campaign.name,
                    "sent_count": analytics.get("sent_count"),
                    "reply_count": analytics.get("reply_count"),
                    "replied_leads_found": len(replied_data),
                    "replies_synced": replies_count,
                    "positive_replies": positive_count,
                }

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Quick sync failed: {error_trace}")
        return {"error": str(e), "trace": error_trace}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("DEBUG", "false").lower() == "true",
    )
