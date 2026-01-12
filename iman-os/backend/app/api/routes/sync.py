"""
Sync Routes

API endpoints for data synchronization with Smartlead.
"""

import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...services import SyncService
from ...services.smartlead import SmartleadAPIError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("")
async def trigger_sync(
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a full sync of all campaigns from Smartlead.

    This will:
    1. Fetch all campaigns
    2. Sync daily stats for each campaign (last 28 days)
    3. Sync lead replies with deduplication
    4. Sync sequences

    Returns sync result with counts and any errors.
    """
    sync_service = SyncService(db)
    try:
        result = await sync_service.sync_all_campaigns()
        return result
    except SmartleadAPIError as e:
        logger.error(f"Smartlead API error: {e.message}")
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Sync failed: {error_trace}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}\n\n{error_trace}")


@router.get("/status")
async def get_sync_status(
    db: AsyncSession = Depends(get_db),
):
    """
    Get the status of the last sync operation.

    Returns:
    - Last sync timestamp
    - Status (completed, running, failed)
    - Campaigns synced count
    - Any error messages
    """
    sync_service = SyncService(db)
    last_sync = await sync_service.get_last_sync()

    if not last_sync:
        return {
            "message": "No sync operations recorded",
            "last_sync": None,
        }

    return {
        "last_sync": {
            "id": last_sync.id,
            "status": last_sync.status,
            "campaigns_synced": last_sync.campaigns_synced,
            "error_message": last_sync.error_message,
            "started_at": last_sync.started_at.isoformat() if last_sync.started_at else None,
            "completed_at": last_sync.completed_at.isoformat() if last_sync.completed_at else None,
        }
    }


@router.post("/campaigns")
async def sync_campaigns(
    db: AsyncSession = Depends(get_db),
):
    """
    Sync only campaign list from Smartlead (without stats).
    """
    sync_service = SyncService(db)
    try:
        result = await sync_service.sync_campaigns()
        return result
    except SmartleadAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/daily-stats/{campaign_id}")
async def sync_campaign_daily_stats(
    campaign_id: int,
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Sync daily statistics for a specific campaign.
    """
    sync_service = SyncService(db)
    try:
        result = await sync_service.sync_campaign_daily_stats(campaign_id, start_date, end_date)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SmartleadAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sequences/{campaign_id}")
async def sync_campaign_sequences(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Sync email sequences for a specific campaign.
    """
    sync_service = SyncService(db)
    try:
        result = await sync_service.sync_sequences(campaign_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SmartleadAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/lead-replies/{campaign_id}")
async def sync_campaign_lead_replies(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Sync lead replies for a specific campaign.
    """
    sync_service = SyncService(db)
    try:
        result = await sync_service.sync_lead_replies(campaign_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SmartleadAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
