"""
Stats Routes

API endpoints for campaign statistics and analytics.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...services import StatsCalculator

router = APIRouter()


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
