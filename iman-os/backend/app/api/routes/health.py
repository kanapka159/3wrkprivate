"""
Health Routes

API endpoints for health checks and system status.
"""

from fastapi import APIRouter

from ...services import metrics, cache

router = APIRouter()


@router.get("")
async def get_health():
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


@router.post("/refresh")
async def trigger_manual_refresh():
    """
    Trigger a manual campaign refresh.

    This bypasses the scheduler and immediately refreshes all campaigns.
    """
    from ...services import scheduler

    result = await scheduler.refresh_all_campaigns()

    return {
        "success": result.get("error") is None,
        "message": "Manual refresh completed",
        "data": result,
    }
