from fastapi import APIRouter

from .routes import campaigns, stats, sync, suggestions, cache

api_router = APIRouter()

api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(stats.router, prefix="/stats", tags=["stats"])
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(suggestions.router, prefix="/suggestions", tags=["suggestions"])
api_router.include_router(cache.router, prefix="/cache", tags=["cache"])

__all__ = ["api_router"]
