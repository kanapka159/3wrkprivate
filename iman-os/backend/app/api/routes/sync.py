"""
Sync Routes

API endpoints for data synchronization with Smartlead.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...services import SyncService
from ...services.smartlead import SmartleadAPIError

router = APIRouter()


@router.post("/campaigns")
async def sync_campaigns(
    db: AsyncSession = Depends(get_db),
):
    """
    Sync all campaigns from Smartlead.

    Fetches campaign list and updates local database.
    """
    sync_service = SyncService(db)
    try:
        result = await sync_service.sync_campaigns()
        return result
    except SmartleadAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analytics/{campaign_id}")
async def sync_campaign_analytics(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Sync analytics for a specific campaign.
    """
    sync_service = SyncService(db)
    try:
        result = await sync_service.sync_campaign_analytics(campaign_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SmartleadAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/all")
async def sync_all(
    db: AsyncSession = Depends(get_db),
):
    """
    Full sync: campaigns and their analytics.

    This may take a while depending on the number of campaigns.
    """
    sync_service = SyncService(db)
    try:
        result = await sync_service.sync_all()
        return result
    except SmartleadAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_sync_status(
    db: AsyncSession = Depends(get_db),
):
    """
    Get the status of the last sync operation.
    """
    sync_service = SyncService(db)
    last_sync = await sync_service.get_last_sync()

    if not last_sync:
        return {"message": "No sync operations recorded", "last_sync": None}

    return {
        "last_sync": {
            "id": last_sync.id,
            "type": last_sync.sync_type,
            "status": last_sync.status,
            "campaigns_synced": last_sync.campaigns_synced,
            "leads_synced": last_sync.leads_synced,
            "error_message": last_sync.error_message,
            "started_at": last_sync.started_at.isoformat() if last_sync.started_at else None,
            "completed_at": last_sync.completed_at.isoformat() if last_sync.completed_at else None,
        }
    }
