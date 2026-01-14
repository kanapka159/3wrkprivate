"""
Campaign Routes

API endpoints for managing campaigns.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db, Campaign, CampaignDailyStats, Sequence
from ...services import SmartleadClient
from ...services.smartlead import SmartleadAPIError
from ...services.suggestion_engine import SuggestionEngine

router = APIRouter()


def get_period_stats_from_campaign(campaign, days: int) -> dict:
    """Get period stats from stored Campaign fields.

    Period stats are fetched during sync from Smartlead analytics-by-date API.
    """
    prefix = f"stats_{days}d"

    sent = getattr(campaign, f"{prefix}_sent", 0) or 0
    replied = getattr(campaign, f"{prefix}_replied", 0) or 0
    positive = getattr(campaign, f"{prefix}_positive", 0) or 0
    opens = getattr(campaign, f"{prefix}_opens", 0) or 0
    bounces = getattr(campaign, f"{prefix}_bounces", 0) or 0

    return {
        "sent_count": sent,
        "reply_count": replied,
        "positive_count": positive,
        "open_count": opens,
        "bounce_count": bounces,
        "reply_rate": round((replied / sent * 100), 2) if sent > 0 else 0,
        "positive_rate": round((positive / replied * 100), 2) if replied > 0 else 0,
        "open_rate": round((opens / sent * 100), 2) if sent > 0 else 0,
        "bounce_rate": round((bounces / sent * 100), 2) if sent > 0 else 0,
    }


@router.get("")
async def list_campaigns(
    status: Optional[str] = Query(None, description="Filter by status"),
    client_id: Optional[int] = Query(None, description="Filter by client ID"),
    only_suggestions: bool = Query(False, description="Only show campaigns needing action"),
    include_hidden: bool = Query(False, description="Include hidden campaigns"),
    only_hidden: bool = Query(False, description="Only show hidden campaigns"),
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
    - include_hidden: Include hidden campaigns in results
    - only_hidden: Only return hidden campaigns
    """
    # Main query - stats are now stored directly on Campaign model
    query = select(Campaign)

    # Filter by hidden status
    # DRAFTED campaigns are treated as hidden automatically
    if only_hidden:
        # Show hidden campaigns AND drafted campaigns
        query = query.where(
            or_(
                Campaign.is_hidden == True,
                Campaign.status == "DRAFTED"
            )
        )
    elif not include_hidden:
        # Exclude hidden campaigns AND drafted campaigns
        query = query.where(Campaign.is_hidden == False)
        query = query.where(Campaign.status != "DRAFTED")

    if status:
        query = query.where(Campaign.status == status.upper())
    if client_id:
        query = query.where(Campaign.client_id == client_id)

    query = query.order_by(Campaign.created_at.desc())

    result = await db.execute(query)
    campaigns = result.scalars().all()

    # Process campaigns
    suggestion_engine = SuggestionEngine(db)
    campaigns_list = []

    for campaign in campaigns:
        # Use stored all-time totals from Campaign model
        sent = campaign.total_sent or 0
        replied = campaign.total_replied or 0
        opens = campaign.total_opens or 0
        bounces = campaign.total_bounces or 0
        # Positive reply ratio uses leads_interested from lead-statistics API
        interested = campaign.leads_interested or 0

        reply_rate = round((replied / sent * 100), 2) if sent > 0 else 0
        # Positive rate = interested / totalReplies (not positive_replies)
        positive_rate = round((interested / replied * 100), 2) if replied > 0 else 0
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

        # Get period-specific stats from stored Campaign fields
        period_7d = get_period_stats_from_campaign(campaign, 7)
        period_14d = get_period_stats_from_campaign(campaign, 14)
        period_28d = get_period_stats_from_campaign(campaign, 28)

        campaigns_list.append({
            "id": campaign.id,
            "smartlead_id": campaign.smartlead_id,
            "name": campaign.name,
            "status": campaign.status,
            "client_id": campaign.client_id,
            "client_name": campaign.client_name,
            "is_hidden": campaign.is_hidden or False,
            "last_synced_at": campaign.last_synced_at.isoformat() if campaign.last_synced_at else None,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
            "completion_percentage": campaign.completion_percentage,
            "total_leads": campaign.total_leads,
            "lead_status": {
                "completed": campaign.leads_completed or 0,
                "blocked": campaign.leads_blocked or 0,
                "paused": campaign.leads_paused or 0,
                "not_started": campaign.leads_not_started or 0,
                "in_progress": campaign.leads_in_progress or 0,
                "interested": interested,
            },
            "stats": {
                "sent_count": sent,
                "reply_count": replied,
                "positive_count": interested,  # Now using interested count
                "open_count": opens,
                "bounce_count": bounces,
                "reply_rate": reply_rate,
                "positive_rate": positive_rate,
                "open_rate": open_rate,
                "bounce_rate": bounce_rate,
            },
            "periods": {
                "7_days": period_7d,
                "14_days": period_14d,
                "28_days": period_28d,
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

    # Use stored all-time totals from Campaign model
    sent = campaign.total_sent or 0
    replied = campaign.total_replied or 0
    opens = campaign.total_opens or 0
    bounces = campaign.total_bounces or 0
    # Positive reply ratio uses leads_interested from lead-statistics API
    interested = campaign.leads_interested or 0

    reply_rate = round((replied / sent * 100), 2) if sent > 0 else 0
    # Positive rate = interested / totalReplies
    positive_rate = round((interested / replied * 100), 2) if replied > 0 else 0
    open_rate = round((opens / sent * 100), 2) if sent > 0 else 0
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

    # Get period stats
    period_7d = get_period_stats_from_campaign(campaign, 7)
    period_14d = get_period_stats_from_campaign(campaign, 14)
    period_28d = get_period_stats_from_campaign(campaign, 28)

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
            "completion_percentage": campaign.completion_percentage,
            "total_leads": campaign.total_leads,
        },
        "lead_status": {
            "completed": campaign.leads_completed or 0,
            "blocked": campaign.leads_blocked or 0,
            "paused": campaign.leads_paused or 0,
            "not_started": campaign.leads_not_started or 0,
            "in_progress": campaign.leads_in_progress or 0,
            "interested": interested,
        },
        "stats": {
            "sent_count": sent,
            "reply_count": replied,
            "positive_count": interested,  # Using interested count
            "open_count": opens,
            "bounce_count": bounces,
            "reply_rate": reply_rate,
            "positive_rate": positive_rate,
            "open_rate": open_rate,
            "bounce_rate": bounce_rate,
        },
        "periods": {
            "7_days": period_7d,
            "14_days": period_14d,
            "28_days": period_28d,
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


@router.post("/{campaign_id}/hide")
async def toggle_campaign_hidden(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Toggle the hidden state of a campaign.
    """
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Toggle hidden state
    campaign.is_hidden = not (campaign.is_hidden or False)
    await db.commit()

    return {
        "message": f"Campaign {'hidden' if campaign.is_hidden else 'unhidden'}",
        "campaign_id": campaign_id,
        "is_hidden": campaign.is_hidden,
    }


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
