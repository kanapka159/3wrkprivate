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
from ...services.suggestion_engine import SuggestionEngine

router = APIRouter()


@router.get("")
async def list_campaigns(
    status: Optional[str] = Query(None, description="Filter by status"),
    client_id: Optional[int] = Query(None, description="Filter by client ID"),
    only_suggestions: bool = Query(False, description="Only show campaigns needing action"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    List all campaigns with stats.

    Filters:
    - status: Filter by campaign status (STARTED, PAUSED, STOPPED)
    - client_id: Filter by client ID
    - only_suggestions: Only return campaigns that need action
    """
    # Build subquery for aggregated stats
    stats_subquery = (
        select(
            CampaignDailyStats.campaign_id,
            func.sum(CampaignDailyStats.unique_sent).label("total_sent"),
            func.sum(CampaignDailyStats.unique_replied).label("total_replied"),
            func.sum(CampaignDailyStats.positive_replies).label("total_positive"),
            func.sum(CampaignDailyStats.open_count).label("total_opens"),
            func.sum(CampaignDailyStats.bounce_count).label("total_bounces"),
        )
        .group_by(CampaignDailyStats.campaign_id)
        .subquery()
    )

    # Main query
    query = (
        select(Campaign, stats_subquery)
        .outerjoin(stats_subquery, Campaign.id == stats_subquery.c.campaign_id)
    )

    if status:
        query = query.where(Campaign.status == status.upper())
    if client_id:
        query = query.where(Campaign.client_id == client_id)

    query = query.order_by(Campaign.created_at.desc())

    result = await db.execute(query)
    rows = result.all()

    # Process campaigns
    suggestion_engine = SuggestionEngine(db)
    campaigns_list = []

    for row in rows:
        campaign = row[0]
        sent = row.total_sent or 0
        replied = row.total_replied or 0
        positive = row.total_positive or 0
        opens = row.total_opens or 0
        bounces = row.total_bounces or 0

        reply_rate = round((replied / sent * 100), 2) if sent > 0 else 0
        positive_rate = round((positive / replied * 100), 2) if replied > 0 else 0
        open_rate = round((opens / sent * 100), 2) if sent > 0 else 0
        bounce_rate = round((bounces / sent * 100), 2) if sent > 0 else 0

        # Generate suggestion
        campaign_data = {
            "sent_count": sent,
            "reply_rate": reply_rate,
            "positive_rate": positive_rate,
        }
        suggestion = suggestion_engine.generate_suggestion(campaign_data)
        warnings = suggestion_engine.generate_warnings(campaign_data)

        # Filter if only_suggestions is True
        if only_suggestions:
            if suggestion["color"] == "green" and not warnings:
                continue

        campaigns_list.append({
            "id": campaign.id,
            "smartlead_id": campaign.smartlead_id,
            "name": campaign.name,
            "status": campaign.status,
            "client_id": campaign.client_id,
            "client_name": campaign.client_name,
            "last_synced_at": campaign.last_synced_at.isoformat() if campaign.last_synced_at else None,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
            "stats": {
                "sent_count": sent,
                "reply_count": replied,
                "positive_count": positive,
                "open_count": opens,
                "bounce_count": bounces,
                "reply_rate": reply_rate,
                "positive_rate": positive_rate,
                "open_rate": open_rate,
                "bounce_rate": bounce_rate,
            },
            "suggestion": suggestion,
            "warnings": warnings,
        })

    # Apply pagination after filtering
    total = len(campaigns_list)
    campaigns_list = campaigns_list[offset:offset + limit]

    return {
        "campaigns": campaigns_list,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get a single campaign by ID with detailed stats and suggestion.
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
            func.sum(CampaignDailyStats.unique_replied),
            func.sum(CampaignDailyStats.positive_replies),
            func.sum(CampaignDailyStats.open_count),
            func.sum(CampaignDailyStats.click_count),
            func.sum(CampaignDailyStats.bounce_count),
        ).where(CampaignDailyStats.campaign_id == campaign_id)
    )
    row = stats.one()

    sent = row[0] or 0
    replied = row[1] or 0
    positive = row[2] or 0
    opens = row[3] or 0
    clicks = row[4] or 0
    bounces = row[5] or 0

    reply_rate = round((replied / sent * 100), 2) if sent > 0 else 0
    positive_rate = round((positive / replied * 100), 2) if replied > 0 else 0
    open_rate = round((opens / sent * 100), 2) if sent > 0 else 0
    click_rate = round((clicks / sent * 100), 2) if sent > 0 else 0
    bounce_rate = round((bounces / sent * 100), 2) if sent > 0 else 0

    # Generate suggestion
    suggestion_engine = SuggestionEngine(db)
    campaign_data = {
        "sent_count": sent,
        "reply_rate": reply_rate,
        "positive_rate": positive_rate,
    }
    suggestion = suggestion_engine.generate_suggestion(campaign_data)
    warnings = suggestion_engine.generate_warnings(campaign_data)

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
        "stats": {
            "sent_count": sent,
            "reply_count": replied,
            "positive_count": positive,
            "open_count": opens,
            "click_count": clicks,
            "bounce_count": bounces,
            "reply_rate": reply_rate,
            "positive_rate": positive_rate,
            "open_rate": open_rate,
            "click_rate": click_rate,
            "bounce_rate": bounce_rate,
        },
        "suggestion": suggestion,
        "warnings": warnings,
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
