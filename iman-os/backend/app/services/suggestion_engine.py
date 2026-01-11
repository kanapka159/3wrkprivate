"""
Suggestion Engine Service

Provides AI-powered suggestions for improving campaign performance.
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Campaign, CampaignAnalytics

logger = logging.getLogger(__name__)


class SuggestionEngine:
    """Service for generating campaign improvement suggestions."""

    # Industry benchmarks for cold email
    BENCHMARKS = {
        "open_rate": {"good": 40, "average": 25, "poor": 15},
        "click_rate": {"good": 5, "average": 2.5, "poor": 1},
        "reply_rate": {"good": 8, "average": 3, "poor": 1},
        "bounce_rate": {"acceptable": 3, "warning": 5, "critical": 10},
    }

    def __init__(self, db: AsyncSession):
        """
        Initialize suggestion engine.

        Args:
            db: Database session
        """
        self.db = db

    async def get_campaign_suggestions(self, campaign_id: int) -> dict:
        """
        Get improvement suggestions for a specific campaign.

        Args:
            campaign_id: Local campaign ID

        Returns:
            Dictionary with suggestions and analysis
        """
        # Get campaign and analytics
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        analytics_result = await self.db.execute(
            select(CampaignAnalytics).where(
                CampaignAnalytics.campaign_id == campaign_id,
                CampaignAnalytics.date.is_(None),
            )
        )
        analytics = analytics_result.scalar_one_or_none()

        if not analytics or analytics.sent_count == 0:
            return {
                "campaign_id": campaign_id,
                "campaign_name": campaign.name,
                "suggestions": [{
                    "type": "info",
                    "category": "general",
                    "message": "Not enough data to generate suggestions. Send more emails first.",
                }],
                "health_score": None,
            }

        suggestions = []
        health_score = 100

        # Analyze open rate
        open_suggestions, open_penalty = self._analyze_open_rate(analytics.open_rate)
        suggestions.extend(open_suggestions)
        health_score -= open_penalty

        # Analyze click rate
        click_suggestions, click_penalty = self._analyze_click_rate(
            analytics.click_rate, analytics.open_rate
        )
        suggestions.extend(click_suggestions)
        health_score -= click_penalty

        # Analyze reply rate
        reply_suggestions, reply_penalty = self._analyze_reply_rate(analytics.reply_rate)
        suggestions.extend(reply_suggestions)
        health_score -= reply_penalty

        # Analyze bounce rate
        bounce_suggestions, bounce_penalty = self._analyze_bounce_rate(analytics.bounce_rate)
        suggestions.extend(bounce_suggestions)
        health_score -= bounce_penalty

        # Determine overall health
        health_score = max(0, health_score)

        return {
            "campaign_id": campaign_id,
            "campaign_name": campaign.name,
            "health_score": health_score,
            "health_status": self._get_health_status(health_score),
            "metrics": {
                "open_rate": {
                    "value": analytics.open_rate,
                    "benchmark": self.BENCHMARKS["open_rate"],
                    "status": self._get_metric_status(
                        analytics.open_rate, self.BENCHMARKS["open_rate"]
                    ),
                },
                "click_rate": {
                    "value": analytics.click_rate,
                    "benchmark": self.BENCHMARKS["click_rate"],
                    "status": self._get_metric_status(
                        analytics.click_rate, self.BENCHMARKS["click_rate"]
                    ),
                },
                "reply_rate": {
                    "value": analytics.reply_rate,
                    "benchmark": self.BENCHMARKS["reply_rate"],
                    "status": self._get_metric_status(
                        analytics.reply_rate, self.BENCHMARKS["reply_rate"]
                    ),
                },
                "bounce_rate": {
                    "value": analytics.bounce_rate,
                    "status": self._get_bounce_status(analytics.bounce_rate),
                },
            },
            "suggestions": suggestions,
        }

    def _analyze_open_rate(self, open_rate: float) -> tuple[list[dict], int]:
        """Analyze open rate and return suggestions."""
        suggestions = []
        penalty = 0

        if open_rate < self.BENCHMARKS["open_rate"]["poor"]:
            penalty = 30
            suggestions.extend([
                {
                    "type": "critical",
                    "category": "subject_line",
                    "message": "Open rate is critically low. Your subject lines need immediate attention.",
                    "actions": [
                        "Test shorter subject lines (under 50 characters)",
                        "Add personalization (first name, company name)",
                        "Create curiosity without being spammy",
                        "Avoid spam trigger words (free, guarantee, act now)",
                    ],
                },
                {
                    "type": "warning",
                    "category": "deliverability",
                    "message": "Low opens may indicate deliverability issues.",
                    "actions": [
                        "Check if emails are landing in spam folders",
                        "Verify sending domain authentication (SPF, DKIM, DMARC)",
                        "Warm up new email accounts gradually",
                    ],
                },
            ])
        elif open_rate < self.BENCHMARKS["open_rate"]["average"]:
            penalty = 15
            suggestions.append({
                "type": "warning",
                "category": "subject_line",
                "message": "Open rate is below average. Consider testing new subject lines.",
                "actions": [
                    "A/B test different subject line styles",
                    "Try asking questions in subject lines",
                    "Use numbers or specific data points",
                ],
            })
        elif open_rate >= self.BENCHMARKS["open_rate"]["good"]:
            suggestions.append({
                "type": "success",
                "category": "subject_line",
                "message": "Great open rate! Your subject lines are performing well.",
            })

        return suggestions, penalty

    def _analyze_click_rate(self, click_rate: float, open_rate: float) -> tuple[list[dict], int]:
        """Analyze click rate and return suggestions."""
        suggestions = []
        penalty = 0

        # Only analyze if people are opening
        if open_rate < 10:
            return suggestions, penalty

        if click_rate < self.BENCHMARKS["click_rate"]["poor"]:
            penalty = 20
            suggestions.append({
                "type": "warning",
                "category": "email_content",
                "message": "Click rate is low. Your email content may not be compelling enough.",
                "actions": [
                    "Make your CTA (call-to-action) clearer and more prominent",
                    "Ensure links are visible and descriptive",
                    "Test different value propositions",
                    "Reduce the number of links to focus attention",
                ],
            })
        elif click_rate < self.BENCHMARKS["click_rate"]["average"]:
            penalty = 10
            suggestions.append({
                "type": "info",
                "category": "email_content",
                "message": "Click rate could be improved with better CTAs.",
                "actions": [
                    "Use action-oriented link text",
                    "Position important links above the fold",
                ],
            })

        return suggestions, penalty

    def _analyze_reply_rate(self, reply_rate: float) -> tuple[list[dict], int]:
        """Analyze reply rate and return suggestions."""
        suggestions = []
        penalty = 0

        if reply_rate < self.BENCHMARKS["reply_rate"]["poor"]:
            penalty = 25
            suggestions.append({
                "type": "critical",
                "category": "engagement",
                "message": "Reply rate is very low. Your emails aren't generating conversations.",
                "actions": [
                    "End emails with a clear, easy-to-answer question",
                    "Make the ask smaller and less committal",
                    "Show clear relevance to the recipient's situation",
                    "Try a more conversational, less salesy tone",
                    "Consider your targeting - are you reaching the right people?",
                ],
            })
        elif reply_rate < self.BENCHMARKS["reply_rate"]["average"]:
            penalty = 12
            suggestions.append({
                "type": "warning",
                "category": "engagement",
                "message": "Reply rate is below average. Consider optimizing your ask.",
                "actions": [
                    "Test different closing questions",
                    "Provide more social proof or credibility",
                    "Make the benefit to the recipient clearer",
                ],
            })
        elif reply_rate >= self.BENCHMARKS["reply_rate"]["good"]:
            suggestions.append({
                "type": "success",
                "category": "engagement",
                "message": "Excellent reply rate! Your messaging is resonating well.",
            })

        return suggestions, penalty

    def _analyze_bounce_rate(self, bounce_rate: float) -> tuple[list[dict], int]:
        """Analyze bounce rate and return suggestions."""
        suggestions = []
        penalty = 0

        if bounce_rate >= self.BENCHMARKS["bounce_rate"]["critical"]:
            penalty = 30
            suggestions.append({
                "type": "critical",
                "category": "list_quality",
                "message": "Bounce rate is critically high! This will damage your sender reputation.",
                "actions": [
                    "IMMEDIATELY pause this campaign",
                    "Verify all email addresses before sending",
                    "Remove invalid emails from your list",
                    "Use an email verification service",
                    "Check your data source quality",
                ],
            })
        elif bounce_rate >= self.BENCHMARKS["bounce_rate"]["warning"]:
            penalty = 15
            suggestions.append({
                "type": "warning",
                "category": "list_quality",
                "message": "Bounce rate is elevated. Clean your email list to protect deliverability.",
                "actions": [
                    "Verify emails before adding to campaigns",
                    "Remove hard bounces immediately",
                    "Consider using double opt-in for new leads",
                ],
            })
        elif bounce_rate <= self.BENCHMARKS["bounce_rate"]["acceptable"]:
            suggestions.append({
                "type": "success",
                "category": "list_quality",
                "message": "Bounce rate is healthy. Your list quality is good.",
            })

        return suggestions, penalty

    def _get_metric_status(self, value: float, benchmark: dict) -> str:
        """Get status label for a metric."""
        if value >= benchmark["good"]:
            return "good"
        elif value >= benchmark["average"]:
            return "average"
        elif value >= benchmark["poor"]:
            return "below_average"
        return "poor"

    def _get_bounce_status(self, value: float) -> str:
        """Get status label for bounce rate."""
        if value <= self.BENCHMARKS["bounce_rate"]["acceptable"]:
            return "good"
        elif value <= self.BENCHMARKS["bounce_rate"]["warning"]:
            return "warning"
        return "critical"

    def _get_health_status(self, score: int) -> str:
        """Get overall health status from score."""
        if score >= 80:
            return "healthy"
        elif score >= 60:
            return "needs_attention"
        elif score >= 40:
            return "at_risk"
        return "critical"

    async def get_global_suggestions(self) -> dict:
        """
        Get suggestions across all campaigns.

        Returns:
            Dictionary with global suggestions
        """
        # Get all campaigns with analytics
        result = await self.db.execute(
            select(Campaign, CampaignAnalytics)
            .join(CampaignAnalytics, Campaign.id == CampaignAnalytics.campaign_id)
            .where(CampaignAnalytics.date.is_(None))
            .where(CampaignAnalytics.sent_count > 0)
        )
        rows = result.all()

        if not rows:
            return {
                "total_campaigns": 0,
                "suggestions": [{
                    "type": "info",
                    "message": "No campaign data available. Sync your campaigns first.",
                }],
            }

        # Calculate averages
        total_campaigns = len(rows)
        avg_open_rate = sum(a.open_rate for _, a in rows) / total_campaigns
        avg_reply_rate = sum(a.reply_rate for _, a in rows) / total_campaigns
        avg_bounce_rate = sum(a.bounce_rate for _, a in rows) / total_campaigns

        # Count campaigns needing attention
        critical_count = sum(1 for _, a in rows if a.bounce_rate > 5 or a.reply_rate < 1)
        warning_count = sum(
            1 for _, a in rows
            if (a.open_rate < 25 or a.reply_rate < 3) and not (a.bounce_rate > 5 or a.reply_rate < 1)
        )

        suggestions = []

        if critical_count > 0:
            suggestions.append({
                "type": "critical",
                "message": f"{critical_count} campaign(s) need immediate attention due to critical issues.",
            })

        if warning_count > 0:
            suggestions.append({
                "type": "warning",
                "message": f"{warning_count} campaign(s) are underperforming and could be optimized.",
            })

        if avg_bounce_rate > 3:
            suggestions.append({
                "type": "warning",
                "category": "list_quality",
                "message": f"Average bounce rate ({avg_bounce_rate:.1f}%) is elevated across campaigns.",
                "actions": ["Implement email verification for all new leads"],
            })

        return {
            "total_campaigns": total_campaigns,
            "averages": {
                "open_rate": round(avg_open_rate, 2),
                "reply_rate": round(avg_reply_rate, 2),
                "bounce_rate": round(avg_bounce_rate, 2),
            },
            "campaigns_critical": critical_count,
            "campaigns_warning": warning_count,
            "campaigns_healthy": total_campaigns - critical_count - warning_count,
            "suggestions": suggestions,
        }
