"""
Suggestions Routes

API endpoints for campaign improvement suggestions.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db
from ...services import SuggestionEngine

router = APIRouter()


@router.get("/campaign/{campaign_id}")
async def get_campaign_suggestions(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get improvement suggestions for a specific campaign.

    Returns:
    - Health score (0-100)
    - Metric analysis with benchmarks
    - Actionable suggestions for improvement
    """
    engine = SuggestionEngine(db)
    try:
        return await engine.get_campaign_suggestions(campaign_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/global")
async def get_global_suggestions(
    db: AsyncSession = Depends(get_db),
):
    """
    Get suggestions across all campaigns.

    Returns:
    - Overall averages
    - Count of campaigns by health status
    - Global improvement suggestions
    """
    engine = SuggestionEngine(db)
    return await engine.get_global_suggestions()


@router.get("/benchmarks")
async def get_benchmarks():
    """
    Get industry benchmark values for cold email metrics.

    These benchmarks are used to evaluate campaign performance.
    """
    return {
        "benchmarks": {
            "open_rate": {
                "good": "40%+",
                "average": "25-40%",
                "below_average": "15-25%",
                "poor": "<15%",
                "description": "Percentage of recipients who opened the email",
            },
            "click_rate": {
                "good": "5%+",
                "average": "2.5-5%",
                "below_average": "1-2.5%",
                "poor": "<1%",
                "description": "Percentage of recipients who clicked a link",
            },
            "reply_rate": {
                "good": "8%+",
                "average": "3-8%",
                "below_average": "1-3%",
                "poor": "<1%",
                "description": "Percentage of recipients who replied",
            },
            "bounce_rate": {
                "acceptable": "<3%",
                "warning": "3-5%",
                "critical": ">5%",
                "description": "Percentage of emails that bounced",
            },
        },
        "notes": [
            "Benchmarks are for B2B cold email campaigns",
            "Results vary by industry and target audience",
            "New campaigns should aim for benchmarks after 100+ sends",
        ],
    }
