"""
Smartlead API Client

Handles all interactions with the Smartlead API including:
- Campaign management
- Analytics retrieval
- Lead statistics
- Rate limiting (10 requests per 2 seconds)
"""

import os
import asyncio
import logging
from datetime import datetime
from typing import Any, Optional
from functools import wraps

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple rate limiter for API calls."""

    def __init__(self, delay: float = 0.25):
        """
        Initialize rate limiter.

        Args:
            delay: Minimum delay between requests in seconds (0.25s = 4 req/sec max)
        """
        self.delay = delay
        self._last_request_time: float = 0
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait if necessary to respect rate limit."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            time_since_last = now - self._last_request_time

            if time_since_last < self.delay:
                await asyncio.sleep(self.delay - time_since_last)

            self._last_request_time = asyncio.get_event_loop().time()


class SmartleadAPIError(Exception):
    """Custom exception for Smartlead API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[dict] = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


class SmartleadClient:
    """
    Async client for Smartlead API.

    Usage:
        async with SmartleadClient() as client:
            campaigns = await client.get_all_campaigns()
    """

    BASE_URL = "https://server.smartlead.ai/api/v1"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Smartlead client.

        Args:
            api_key: Smartlead API key. If not provided, reads from SMARTLEAD_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("SMARTLEAD_API_KEY")
        if not self.api_key:
            raise ValueError("SMARTLEAD_API_KEY is required. Set it in .env or pass to constructor.")

        self._client: Optional[httpx.AsyncClient] = None
        self._rate_limiter = RateLimiter(delay=0.25)  # 0.25s delay = max 4 req/sec (safe for 10 req/2 sec limit)

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={"Content-Type": "application/json"},
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_url(self, endpoint: str) -> str:
        """Build full URL with API key."""
        separator = "&" if "?" in endpoint else "?"
        return f"{self.BASE_URL}{endpoint}{separator}api_key={self.api_key}"

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        retries: int = 3,
    ) -> Any:
        """
        Make an API request with rate limiting and error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., /campaigns)
            params: Query parameters
            json_data: JSON body for POST requests
            retries: Number of retries on failure

        Returns:
            API response data

        Raises:
            SmartleadAPIError: On API errors
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with SmartleadClient() as client:'")

        # Apply rate limiting
        await self._rate_limiter.acquire()

        url = self._get_url(endpoint)

        for attempt in range(retries):
            try:
                logger.debug(f"API Request: {method} {endpoint}")

                response = await self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                )

                # Log response status
                logger.debug(f"API Response: {response.status_code}")

                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 2))
                    logger.warning(f"Rate limited. Waiting {retry_after}s before retry.")
                    await asyncio.sleep(retry_after)
                    continue

                # Handle other errors
                if response.status_code >= 400:
                    error_data = response.json() if response.content else {}
                    raise SmartleadAPIError(
                        message=f"API error: {response.status_code}",
                        status_code=response.status_code,
                        response=error_data,
                    )

                return response.json()

            except httpx.TimeoutException:
                logger.warning(f"Request timeout (attempt {attempt + 1}/{retries})")
                if attempt == retries - 1:
                    raise SmartleadAPIError("Request timed out after retries")
                await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff

            except httpx.RequestError as e:
                logger.error(f"Request error: {e}")
                if attempt == retries - 1:
                    raise SmartleadAPIError(f"Request failed: {str(e)}")
                await asyncio.sleep(1 * (attempt + 1))

        raise SmartleadAPIError("Max retries exceeded")

    # =========================================================================
    # Campaign Methods
    # =========================================================================

    async def get_all_campaigns(self) -> list[dict]:
        """
        Get all campaigns.

        GET /campaigns

        Returns:
            List of campaign objects
        """
        logger.info("Fetching all campaigns")
        return await self._request("GET", "/campaigns")

    async def get_campaign_analytics(self, campaign_id: int) -> dict:
        """
        Get aggregate analytics for a campaign.

        GET /campaigns/{id}/analytics

        Args:
            campaign_id: Smartlead campaign ID

        Returns:
            Campaign analytics object
        """
        logger.info(f"Fetching analytics for campaign {campaign_id}")
        return await self._request("GET", f"/campaigns/{campaign_id}/analytics")

    async def get_campaign_analytics_by_date(
        self,
        campaign_id: int,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        """
        Get campaign analytics broken down by date.

        GET /campaigns/{id}/analytics-by-date

        Args:
            campaign_id: Smartlead campaign ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            List of daily analytics objects
        """
        logger.info(f"Fetching analytics by date for campaign {campaign_id} ({start_date} to {end_date})")
        return await self._request(
            "GET",
            f"/campaigns/{campaign_id}/analytics-by-date",
            params={"start_date": start_date, "end_date": end_date},
        )

    async def get_campaign_statistics(
        self,
        campaign_id: int,
        offset: int = 0,
        limit: int = 100,
        email_status: Optional[str] = None,
    ) -> dict:
        """
        Get lead statistics for a campaign.

        GET /campaigns/{id}/statistics

        Args:
            campaign_id: Smartlead campaign ID
            offset: Pagination offset
            limit: Number of results per page
            email_status: Filter by email status (e.g., 'sent', 'opened', 'clicked')

        Returns:
            Statistics object with lead data
        """
        logger.info(f"Fetching statistics for campaign {campaign_id} (offset={offset}, limit={limit})")
        params = {"offset": offset, "limit": limit}
        if email_status:
            params["email_status"] = email_status
        return await self._request("GET", f"/campaigns/{campaign_id}/statistics", params=params)

    async def get_campaign_sequences(self, campaign_id: int) -> list[dict]:
        """
        Get email sequences for a campaign.

        GET /campaigns/{id}/sequences

        Args:
            campaign_id: Smartlead campaign ID

        Returns:
            List of sequence objects
        """
        logger.info(f"Fetching sequences for campaign {campaign_id}")
        return await self._request("GET", f"/campaigns/{campaign_id}/sequences")

    async def get_campaign_lead_stats(self, campaign_id: int) -> dict:
        """
        Get lead statistics summary for a campaign.

        GET /campaigns/{id}/statistics (with limit=1 to just get totals)

        Returns campaign_lead_stats with:
        - total: Total number of leads in campaign
        - notStarted: Leads not yet contacted
        - inprogress: Leads currently being contacted
        - completed: Leads that finished sequence or replied
        - blocked: Blocked leads
        - paused: Paused leads

        Args:
            campaign_id: Smartlead campaign ID

        Returns:
            Statistics object with lead counts
        """
        logger.info(f"Fetching lead stats for campaign {campaign_id}")
        # Use limit=1 to minimize data transfer, we just need the stats summary
        return await self._request("GET", f"/campaigns/{campaign_id}/statistics", params={"limit": 1})

    async def update_campaign_status(self, campaign_id: int, status: str) -> dict:
        """
        Update campaign status.

        POST /campaigns/{id}/status

        Args:
            campaign_id: Smartlead campaign ID
            status: New status (e.g., 'STARTED', 'PAUSED', 'STOPPED')

        Returns:
            Updated campaign object
        """
        logger.info(f"Updating campaign {campaign_id} status to {status}")
        return await self._request(
            "POST",
            f"/campaigns/{campaign_id}/status",
            json_data={"status": status},
        )

    # =========================================================================
    # Lead Methods
    # =========================================================================

    async def get_lead_categories(self) -> list[dict]:
        """
        Get all lead categories.

        GET /leads/fetch-categories

        Returns:
            List of lead category objects
        """
        logger.info("Fetching lead categories")
        return await self._request("GET", "/leads/fetch-categories")

    # =========================================================================
    # Client Methods
    # =========================================================================

    async def get_all_clients(self) -> list[dict]:
        """
        Get all clients.

        GET /client/

        Returns:
            List of client objects
        """
        logger.info("Fetching all clients")
        return await self._request("GET", "/client/")

    # =========================================================================
    # Utility Methods
    # =========================================================================

    async def get_all_campaign_statistics(
        self,
        campaign_id: int,
        email_status: Optional[str] = None,
    ) -> list[dict]:
        """
        Get ALL lead statistics for a campaign (handles pagination).

        Args:
            campaign_id: Smartlead campaign ID
            email_status: Filter by email status

        Returns:
            Complete list of all leads
        """
        all_leads = []
        offset = 0
        limit = 100

        while True:
            result = await self.get_campaign_statistics(
                campaign_id=campaign_id,
                offset=offset,
                limit=limit,
                email_status=email_status,
            )

            leads = result.get("data", [])
            if not leads:
                break

            all_leads.extend(leads)
            offset += limit

            # Safety check to prevent infinite loops
            if len(leads) < limit:
                break

        logger.info(f"Fetched {len(all_leads)} total leads for campaign {campaign_id}")
        return all_leads
