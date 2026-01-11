"""
Stats Routes

API endpoints for campaign statistics and analytics.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db, Campaign, CampaignDailyStats, LeadReply
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
    # Fix: Set cutoff to start of day (midnight) to include full days
    # Daily stats are stored at midnight, so comparing with current time would exclude partial days
    cutoff_date = (datetime.utcnow() - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)

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

    # Get aggregated stats for the period (sent, opens, bounces from daily stats)
    period_stats = await db.execute(
        select(
            func.sum(CampaignDailyStats.unique_sent),
            func.sum(CampaignDailyStats.open_count),
            func.sum(CampaignDailyStats.bounce_count),
        ).where(CampaignDailyStats.date >= cutoff_date)
    )
    row = period_stats.one()

    sent = row[0] or 0
    opens = row[1] or 0
    bounces = row[2] or 0

    # Get reply counts from LeadReply table (more accurate than daily stats)
    reply_stats = await db.execute(
        select(
            func.count(LeadReply.id),
            func.sum(case((LeadReply.is_positive == True, 1), else_=0)),
        )
    )
    reply_row = reply_stats.one()
    replied = reply_row[0] or 0
    positive = reply_row[1] or 0

    # Get per-campaign stats: sent from daily stats, replies from LeadReply
    # First get sent counts per campaign
    sent_per_campaign = await db.execute(
        select(
            CampaignDailyStats.campaign_id,
            func.sum(CampaignDailyStats.unique_sent).label("campaign_sent"),
        )
        .where(CampaignDailyStats.date >= cutoff_date)
        .group_by(CampaignDailyStats.campaign_id)
    )
    sent_by_campaign = {r.campaign_id: r.campaign_sent or 0 for r in sent_per_campaign}

    # Get reply counts per campaign from LeadReply
    replies_per_campaign = await db.execute(
        select(
            LeadReply.campaign_id,
            func.count(LeadReply.id).label("campaign_replied"),
            func.sum(case((LeadReply.is_positive == True, 1), else_=0)).label("campaign_positive"),
        )
        .group_by(LeadReply.campaign_id)
    )

    # Calculate average reply rate across campaigns (excluding 0-reply campaigns)
    reply_rates = []
    positive_rates = []
    for r in replies_per_campaign:
        camp_sent = sent_by_campaign.get(r.campaign_id, 0)
        camp_replied = r.campaign_replied or 0
        camp_positive = r.campaign_positive or 0

        if camp_sent > 0 and camp_replied > 0:  # Only include campaigns with replies
            reply_rates.append((camp_replied / camp_sent) * 100)
            if camp_replied > 0:
                positive_rates.append((camp_positive / camp_replied) * 100)

    avg_reply_rate = round(sum(reply_rates) / len(reply_rates), 2) if reply_rates else 0
    avg_positive_rate = round(sum(positive_rates) / len(positive_rates), 2) if positive_rates else 0

    # Overall rates for reference
    open_rate = round((opens / sent * 100), 2) if sent > 0 else 0
    bounce_rate = round((bounces / sent * 100), 2) if sent > 0 else 0

    # Count campaigns needing action (reply rate < 1% with > 200 sends)
    # Use sent_by_campaign and replies from LeadReply
    low_threshold = 200

    # Get reply counts by campaign from LeadReply
    reply_counts_query = await db.execute(
        select(
            LeadReply.campaign_id,
            func.count(LeadReply.id).label("reply_count"),
        )
        .group_by(LeadReply.campaign_id)
    )
    replies_by_campaign = {r.campaign_id: r.reply_count for r in reply_counts_query}

    needing_action_count = 0
    for campaign_id, total_sent in sent_by_campaign.items():
        if total_sent >= low_threshold:
            total_replied = replies_by_campaign.get(campaign_id, 0)
            rr = (total_replied / total_sent * 100) if total_sent > 0 else 0
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
            "reply_rate": avg_reply_rate,
            "positive_rate": avg_positive_rate,
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
