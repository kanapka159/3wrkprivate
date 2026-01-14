"""
Cache Routes

API endpoints for cache management and status.
"""

from fastapi import APIRouter

from ...services import cache

router = APIRouter()


@router.get("/status")
async def get_cache_status():
    """
    Get cache status and statistics.

    Returns:
    - total_entries: Number of cached items
    - total_hits: Total cache hits
    - total_misses: Total cache misses
    - hit_rate: Cache hit rate percentage
    - default_ttl_seconds: Default TTL for cache entries
    - entries: List of cached entries with metadata
    """
    status = await cache.get_status()
    return {
        "success": True,
        "data": status,
    }


@router.post("/clear")
async def clear_cache():
    """
    Clear all cache entries.

    Returns the number of entries cleared.
    """
    count = await cache.clear()
    return {
        "success": True,
        "message": f"Cleared {count} cache entries",
        "entries_cleared": count,
    }


@router.post("/invalidate/{pattern}")
async def invalidate_cache_pattern(pattern: str):
    """
    Invalidate cache entries matching a pattern.

    Pattern uses prefix matching.
    """
    count = await cache.invalidate_pattern(pattern)
    return {
        "success": True,
        "message": f"Invalidated {count} cache entries matching '{pattern}'",
        "entries_invalidated": count,
    }
