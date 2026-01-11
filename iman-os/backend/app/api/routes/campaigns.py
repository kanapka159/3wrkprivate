"""
Campaign Routes

API endpoints for managing campaigns.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db, Campaign, CampaignAnalytics
from ...services import SmartleadClient
from ...services.smartlead import SmartleadAPIError

router = APIRouter()


@router.get("/")
async def list_campaigns(
    status: Optional[str] = Query(None, description="Filter by status"),
    client_id: Optional[int] = Query(None, description="Filter by client ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    List all campaigns from the local database.
    """
    query = select(Campaign)

    if status:
        query = query.where(Campaign.status == status)
    if client_id:
        query = query.where(Campaign.client_id == client_id)

    query = query.order_by(Campaign.updated_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    campaigns = result.scalars().all()

    return {
        "campaigns": [
            {
                "id": c.id,
                "smartlead_id": c.smartlead_id,
                "name": c.name,
                "status": c.status,
                "client_id": c.client_id,
                "client_name": c.client_name,
                "last_synced_at": c.last_synced_at.isoformat() if c.last_synced_at else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in campaigns
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get a single campaign by ID.
    """
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Get analytics
    analytics_result = await db.execute(
        select(CampaignAnalytics).where(
            CampaignAnalytics.campaign_id == campaign_id,
            CampaignAnalytics.date.is_(None),
        )
    )
    analytics = analytics_result.scalar_one_or_none()

    return {
        "campaign": {
            "id": campaign.id,
            "smartlead_id": campaign.smartlead_id,
            "name": campaign.name,
            "status": campaign.status,
            "client_id": campaign.client_id,
            "client_name": campaign.client_name,
            "timezone": campaign.timezone,
            "track_settings": campaign.track_settings,
            "last_synced_at": campaign.last_synced_at.isoformat() if campaign.last_synced_at else None,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
            "updated_at": campaign.updated_at.isoformat() if campaign.updated_at else None,
        },
        "analytics": {
            "sent_count": analytics.sent_count if analytics else 0,
            "open_count": analytics.open_count if analytics else 0,
            "click_count": analytics.click_count if analytics else 0,
            "reply_count": analytics.reply_count if analytics else 0,
            "bounce_count": analytics.bounce_count if analytics else 0,
            "open_rate": analytics.open_rate if analytics else 0,
            "click_rate": analytics.click_rate if analytics else 0,
            "reply_rate": analytics.reply_rate if analytics else 0,
            "bounce_rate": analytics.bounce_rate if analytics else 0,
        } if analytics else None,
    }


@router.post("/{campaign_id}/status")
async def update_campaign_status(
    campaign_id: int,
    status: str = Query(..., description="New status (STARTED, PAUSED, STOPPED)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Update campaign status via Smartlead API.
    """
    # Get campaign
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    valid_statuses = ["STARTED", "PAUSED", "STOPPED"]
    if status.upper() not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {valid_statuses}",
        )

    try:
        async with SmartleadClient() as client:
            result = await client.update_campaign_status(
                campaign.smartlead_id, status.upper()
            )

        # Update local status
        campaign.status = status.upper()
        await db.commit()

        return {
            "message": f"Campaign status updated to {status.upper()}",
            "campaign_id": campaign_id,
            "status": status.upper(),
        }

    except SmartleadAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)


@router.get("/{campaign_id}/sequences")
async def get_campaign_sequences(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get email sequences for a campaign from Smartlead API.
    """
    # Get campaign
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    try:
        async with SmartleadClient() as client:
            sequences = await client.get_campaign_sequences(campaign.smartlead_id)

        return {"campaign_id": campaign_id, "sequences": sequences}

    except SmartleadAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
