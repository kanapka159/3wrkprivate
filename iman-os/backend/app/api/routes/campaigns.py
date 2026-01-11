"""
Campaign Routes

API endpoints for managing campaigns.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db, Campaign, CampaignDailyStats, Sequence
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

    query = query.order_by(Campaign.created_at.desc()).offset(offset).limit(limit)

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
    Get a single campaign by ID with aggregated stats.
    """
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Get aggregated stats
    stats = await db.execute(
        select(
            func.sum(CampaignDailyStats.unique_sent),
            func.sum(CampaignDailyStats.open_count),
            func.sum(CampaignDailyStats.click_count),
            func.sum(CampaignDailyStats.unique_replied),
            func.sum(CampaignDailyStats.bounce_count),
        ).where(CampaignDailyStats.campaign_id == campaign_id)
    )
    row = stats.one()

    sent = row[0] or 0
    opens = row[1] or 0
    clicks = row[2] or 0
    replies = row[3] or 0
    bounces = row[4] or 0

    return {
        "campaign": {
            "id": campaign.id,
            "smartlead_id": campaign.smartlead_id,
            "name": campaign.name,
            "status": campaign.status,
            "client_id": campaign.client_id,
            "client_name": campaign.client_name,
            "last_synced_at": campaign.last_synced_at.isoformat() if campaign.last_synced_at else None,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        },
        "analytics": {
            "sent_count": sent,
            "open_count": opens,
            "click_count": clicks,
            "reply_count": replies,
            "bounce_count": bounces,
            "open_rate": round((opens / sent * 100), 2) if sent > 0 else 0,
            "click_rate": round((clicks / sent * 100), 2) if sent > 0 else 0,
            "reply_rate": round((replies / sent * 100), 2) if sent > 0 else 0,
            "bounce_rate": round((bounces / sent * 100), 2) if sent > 0 else 0,
        },
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
            await client.update_campaign_status(campaign.smartlead_id, status.upper())

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
    Get email sequences for a campaign from local database.
    """
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Get sequences from local DB
    seq_result = await db.execute(
        select(Sequence)
        .where(Sequence.campaign_id == campaign_id)
        .order_by(Sequence.seq_number)
    )
    sequences = seq_result.scalars().all()

    return {
        "campaign_id": campaign_id,
        "sequences": [
            {
                "id": s.id,
                "smartlead_id": s.smartlead_id,
                "seq_number": s.seq_number,
                "variant_label": s.variant_label,
                "subject": s.subject,
                "sent_count": s.sent_count,
                "reply_count": s.reply_count,
            }
            for s in sequences
        ],
    }


@router.get("/{campaign_id}/daily-stats")
async def get_campaign_daily_stats(
    campaign_id: int,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get daily statistics for a campaign.
    """
    from datetime import datetime

    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    query = select(CampaignDailyStats).where(
        CampaignDailyStats.campaign_id == campaign_id
    )

    if start_date:
        query = query.where(CampaignDailyStats.date >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        query = query.where(CampaignDailyStats.date <= datetime.strptime(end_date, "%Y-%m-%d"))

    query = query.order_by(CampaignDailyStats.date.desc())

    stats_result = await db.execute(query)
    daily_stats = stats_result.scalars().all()

    return {
        "campaign_id": campaign_id,
        "daily_stats": [
            {
                "date": ds.date.strftime("%Y-%m-%d") if ds.date else None,
                "sent_count": ds.sent_count,
                "unique_sent": ds.unique_sent,
                "reply_count": ds.reply_count,
                "unique_replied": ds.unique_replied,
                "positive_replies": ds.positive_replies,
                "open_count": ds.open_count,
                "click_count": ds.click_count,
                "bounce_count": ds.bounce_count,
            }
            for ds in daily_stats
        ],
    }
