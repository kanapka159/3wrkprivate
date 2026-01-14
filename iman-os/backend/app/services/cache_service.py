"""
Cache Service

Simple in-memory cache with TTL support for API responses.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Optional

# Default cache TTL (1 hour)
DEFAULT_TTL_SECONDS = 3600


class CacheEntry:
    """A single cache entry with expiration tracking."""

    def __init__(self, data: Any, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self.data = data
        self.created_at = datetime.utcnow()
        self.expires_at = self.created_at + timedelta(seconds=ttl_seconds)
        self.ttl_seconds = ttl_seconds
        self.hits = 0

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at

    @property
    def remaining_ttl(self) -> int:
        """Remaining TTL in seconds."""
        if self.is_expired:
            return 0
        delta = self.expires_at - datetime.utcnow()
        return max(0, int(delta.total_seconds()))

    def touch(self):
        """Record a cache hit."""
        self.hits += 1


class CacheService:
    """
    Simple in-memory cache service.

    Provides caching for API responses with configurable TTL.
    """

    def __init__(self):
        self._cache: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
        self._total_hits = 0
        self._total_misses = 0

    async def get(self, key: str) -> Optional[Any]:
        """
        Get a value from cache.

        Returns None if key doesn't exist or is expired.
        """
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._total_misses += 1
                return None
            if entry.is_expired:
                del self._cache[key]
                self._total_misses += 1
                return None
            entry.touch()
            self._total_hits += 1
            return entry.data

    async def set(self, key: str, data: Any, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        """Store a value in cache with TTL."""
        async with self._lock:
            self._cache[key] = CacheEntry(data, ttl_seconds)

    async def delete(self, key: str) -> bool:
        """Delete a specific key from cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> int:
        """Clear all cache entries. Returns number of entries cleared."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching a pattern.

        Pattern uses simple prefix matching.
        """
        async with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(pattern)]
            for key in keys_to_delete:
                del self._cache[key]
            return len(keys_to_delete)

    async def get_status(self) -> dict:
        """Get cache status and statistics."""
        async with self._lock:
            # Clean up expired entries
            expired_keys = [k for k, v in self._cache.items() if v.is_expired]
            for key in expired_keys:
                del self._cache[key]

            entries = []
            for key, entry in self._cache.items():
                entries.append({
                    "key": key,
                    "created_at": entry.created_at.isoformat(),
                    "expires_at": entry.expires_at.isoformat(),
                    "remaining_ttl": entry.remaining_ttl,
                    "hits": entry.hits,
                })

            total_requests = self._total_hits + self._total_misses
            hit_rate = round((self._total_hits / total_requests * 100), 2) if total_requests > 0 else 0

            return {
                "total_entries": len(self._cache),
                "total_hits": self._total_hits,
                "total_misses": self._total_misses,
                "hit_rate": hit_rate,
                "default_ttl_seconds": DEFAULT_TTL_SECONDS,
                "entries": entries,
            }


# Global cache instance
cache = CacheService()
