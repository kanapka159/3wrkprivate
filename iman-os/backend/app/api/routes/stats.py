"""
Stats Routes

API endpoints for campaign statistics and analytics.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db, Campaign, CampaignDailyStats
from ...services import StatsCalculator

router = APIRouter()


@router.get("/overview")
async def get_stats_overview(
    days: int = Query(7, ge=1, le=90, description="Number of days to include"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get dashboard overview statistics for the specified period.

    Returns cards data for the dashboard including:
    - Total campaigns (active/paused/stopped)
    - Total emails sent
    - Reply rate
    - Positive reply rate
    - Campaigns needing action count
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Get campaign counts by status
    status_counts = await db.execute(
        select(Campaign.status, func.count(Campaign.id))
        .group_by(Campaign.status)
    )
    campaigns_by_status = {row[0]: row[1] for row in status_counts}

    total_campaigns = sum(campaigns_by_status.values())
    active_campaigns = campaigns_by_status.get("STARTED", 0)
    paused_campaigns = campaigns_by_status.get("PAUSED", 0)
    stopped_campaigns = campaigns_by_status.get("STOPPED", 0)

    # Get aggregated stats for the period
    period_stats = await db.execute(
        select(
            func.sum(CampaignDailyStats.unique_sent),
            func.sum(CampaignDailyStats.unique_replied),
            func.sum(CampaignDailyStats.positive_replies),
            func.sum(CampaignDailyStats.open_count),
            func.sum(CampaignDailyStats.bounce_count),
        ).where(CampaignDailyStats.date >= cutoff_date)
    )
    row = period_stats.one()

    sent = row[0] or 0
    replied = row[1] or 0
    positive = row[2] or 0
    opens = row[3] or 0
    bounces = row[4] or 0

    reply_rate = round((replied / sent * 100), 2) if sent > 0 else 0
    positive_rate = round((positive / replied * 100), 2) if replied > 0 else 0
    open_rate = round((opens / sent * 100), 2) if sent > 0 else 0
    bounce_rate = round((bounces / sent * 100), 2) if sent > 0 else 0

    # Count campaigns needing action (reply rate < 1% with > 200 sends)
    low_threshold = 200
    needing_action_query = (
        select(
            CampaignDailyStats.campaign_id,
            func.sum(CampaignDailyStats.unique_sent).label("total_sent"),
            func.sum(CampaignDailyStats.unique_replied).label("total_replied"),
        )
        .group_by(CampaignDailyStats.campaign_id)
        .having(func.sum(CampaignDailyStats.unique_sent) >= low_threshold)
    )
    needing_action_result = await db.execute(needing_action_query)
    needing_action_count = 0
    for r in needing_action_result:
        if r.total_sent > 0:
            rr = (r.total_replied or 0) / r.total_sent * 100
            if rr < 1.0:  # Below MONITOR threshold
                needing_action_count += 1

    return {
        "period_days": days,
        "campaigns": {
            "total": total_campaigns,
            "active": active_campaigns,
            "paused": paused_campaigns,
            "stopped": stopped_campaigns,
        },
        "metrics": {
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
        "needing_action": needing_action_count,
    }


@router.get("/dashboard")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
):
    """
    Get overall dashboard statistics.

    Returns aggregated metrics across all campaigns.
    """
    calculator = StatsCalculator(db)
    return await calculator.get_dashboard_stats()


@router.get("/campaign/{campaign_id}")
async def get_campaign_stats(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed statistics for a single campaign.
    """
    calculator = StatsCalculator(db)
    try:
        return await calculator.get_campaign_stats(campaign_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/top-performing")
async def get_top_performing_campaigns(
    limit: int = Query(10, ge=1, le=50),
    metric: str = Query("reply_rate", description="Metric to sort by"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get top performing campaigns by a specific metric.

    Available metrics: open_rate, click_rate, reply_rate, sent_count
    """
    calculator = StatsCalculator(db)
    campaigns = await calculator.get_top_performing_campaigns(limit=limit, metric=metric)
    return {"top_campaigns": campaigns, "sorted_by": metric}


@router.get("/needs-attention")
async def get_campaigns_needing_attention(
    db: AsyncSession = Depends(get_db),
):
    """
    Get campaigns that need attention due to performance issues.

    Identifies campaigns with:
    - High bounce rates (>5%)
    - Low open rates (<10%)
    - Zero replies with significant sends
    """
    calculator = StatsCalculator(db)
    issues = await calculator.get_campaigns_needing_attention()
    return {"campaigns_with_issues": issues, "total_issues": len(issues)}
