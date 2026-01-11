"""
Suggestions Routes

API endpoints for campaign improvement suggestions.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db, Campaign
from ...services import SuggestionEngine, SmartleadClient
from ...services.smartlead import SmartleadAPIError

router = APIRouter()


@router.get("")
async def get_suggestions(
    db: AsyncSession = Depends(get_db),
):
    """
    Get all campaigns needing action with suggestions.

    Returns campaigns sorted by severity:
    - RED (KILL): < 0.5% reply rate
    - ORANGE (PAUSE): 0.5-1% reply rate
    - YELLOW (MONITOR): 1-2% reply rate
    - GRAY (WAIT): < 200 sends

    Each campaign includes:
    - Suggestion (KILL, PAUSE, MONITOR, KEEP, WAIT)
    - Reason explaining the suggestion
    - Color for visual indication
    - Warnings (Low Reply Rate, Declining, Low Quality, Stalled)
    """
    engine = SuggestionEngine(db)
    campaigns = await engine.get_campaigns_needing_action()

    return {
        "campaigns": campaigns,
        "total": len(campaigns),
    }


@router.post("/{campaign_id}/apply")
async def apply_suggestion(
    campaign_id: int,
    action: str = Query(..., description="Action to apply (PAUSE, STOP, KEEP)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Apply a suggestion to a campaign by updating its status in Smartlead.

    Actions:
    - PAUSE: Pause the campaign (set status to PAUSED)
    - STOP: Stop the campaign (set status to STOPPED)
    - KEEP: Keep running (no status change, just acknowledge)

    This will:
    1. Update campaign status in Smartlead API
    2. Update local database
    3. Log the action
    """
    # Get campaign
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    valid_actions = ["PAUSE", "STOP", "KEEP"]
    action = action.upper()
    if action not in valid_actions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action. Must be one of: {valid_actions}",
        )

    # Map action to Smartlead status
    status_map = {
        "PAUSE": "PAUSED",
        "STOP": "STOPPED",
        "KEEP": None,  # No status change
    }

    new_status = status_map[action]

    if new_status:
        try:
            async with SmartleadClient() as client:
                await client.update_campaign_status(campaign.smartlead_id, new_status)

            campaign.status = new_status
            await db.commit()

            # Save to suggestion history
            engine = SuggestionEngine(db)
            await engine.save_suggestion(
                campaign_id=campaign_id,
                suggestion_text=action,
                reason=f"User applied {action} action",
            )
            await db.commit()

            return {
                "message": f"Campaign status updated to {new_status}",
                "campaign_id": campaign_id,
                "smartlead_id": campaign.smartlead_id,
                "action": action,
                "new_status": new_status,
            }

        except SmartleadAPIError as e:
            raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    else:
        # KEEP action - just acknowledge
        engine = SuggestionEngine(db)
        await engine.save_suggestion(
            campaign_id=campaign_id,
            suggestion_text=action,
            reason="User acknowledged and chose to keep running",
        )
        await db.commit()

        return {
            "message": "Campaign acknowledged, continuing to run",
            "campaign_id": campaign_id,
            "smartlead_id": campaign.smartlead_id,
            "action": action,
            "new_status": campaign.status,
        }


@router.get("/campaign/{campaign_id}")
async def get_campaign_suggestions(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed suggestion for a specific campaign.

    Returns:
    - Campaign metrics
    - Suggestion with color
    - Warnings list
    - Historical data for trend analysis
    """
    engine = SuggestionEngine(db)
    campaign_data = await engine.get_campaign_data(campaign_id)

    if not campaign_data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    suggestion = engine.generate_suggestion(campaign_data)
    warnings = engine.generate_warnings(campaign_data)

    return {
        "campaign": campaign_data,
        "suggestion": suggestion,
        "warnings": warnings,
    }


@router.get("/thresholds")
async def get_thresholds():
    """
    Get the threshold values used for suggestions.
    """
    return {
        "thresholds": {
            "low_data": {
                "value": 200,
                "description": "Minimum sends before making suggestions",
            },
            "keep": {
                "value": ">=2%",
                "color": "green",
                "description": "Strong performance, keep running",
            },
            "monitor": {
                "value": ">=1%",
                "color": "yellow",
                "description": "Acceptable, monitor closely",
            },
            "pause": {
                "value": ">=0.5%",
                "color": "orange",
                "description": "Low performance, consider pausing",
            },
            "kill": {
                "value": "<0.5%",
                "color": "red",
                "description": "Very low performance, stop immediately",
            },
        },
        "warnings": {
            "Low Reply Rate": "Reply rate below 1%",
            "Declining": "Reply rate dropped 25%+ from previous period",
            "Low Quality": "Positive reply rate below 30%",
            "Stalled": "No replies in 7+ days",
        },
    }
