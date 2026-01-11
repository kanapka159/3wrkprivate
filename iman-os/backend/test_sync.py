#!/usr/bin/env python3
"""
Manual Sync Test Script

Tests the sync functionality by calling the Smartlead API directly.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_api_connection():
    """Test basic API connection."""
    from app.services.smartlead import SmartleadClient

    print("Testing Smartlead API connection...")
    print(f"API Key: {os.getenv('SMARTLEAD_API_KEY', 'NOT SET')[:20]}...")

    try:
        async with SmartleadClient() as client:
            campaigns = await client.get_all_campaigns()
            print(f"SUCCESS: Found {len(campaigns)} campaigns")
            if campaigns:
                print(f"First campaign: {campaigns[0].get('name', 'N/A')}")
            return True
    except Exception as e:
        print(f"ERROR: {e}")
        return False


async def test_full_sync():
    """Test full sync process."""
    from app.db.database import init_db, AsyncSessionLocal
    from app.services.sync_service import SyncService

    print("\nInitializing database...")
    await init_db()

    print("Running full sync...")
    async with AsyncSessionLocal() as db:
        sync_service = SyncService(db)
        try:
            result = await sync_service.sync_all_campaigns()
            print(f"SUCCESS: Sync completed")
            print(f"  Campaigns synced: {result.get('campaigns_synced', 0)}")
            print(f"  Replies synced: {result.get('total_replies', 0)}")
            print(f"  Errors: {len(result.get('errors', []))}")
            if result.get('errors'):
                for err in result['errors'][:5]:
                    print(f"    - {err}")
            return True
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False


async def test_endpoints():
    """Test API endpoints using httpx."""
    try:
        import httpx
    except ImportError:
        print("\nSkipping endpoint tests (httpx not installed)")
        return True

    base_url = "http://localhost:8000"

    print("\nTesting API endpoints...")

    async with httpx.AsyncClient() as client:
        # Test /health
        try:
            r = await client.get(f"{base_url}/health")
            print(f"GET /health -> {r.status_code}: {r.json()}")
        except Exception as e:
            print(f"GET /health -> ERROR: {e}")

        # Test /api/campaigns
        try:
            r = await client.get(f"{base_url}/api/campaigns")
            data = r.json()
            print(f"GET /api/campaigns -> {r.status_code}: {len(data.get('campaigns', []))} campaigns")
        except Exception as e:
            print(f"GET /api/campaigns -> ERROR: {e}")

        # Test /api/stats/overview
        try:
            r = await client.get(f"{base_url}/api/stats/overview?days=7")
            print(f"GET /api/stats/overview -> {r.status_code}: {r.json()}")
        except Exception as e:
            print(f"GET /api/stats/overview -> ERROR: {e}")

        # Test /api/suggestions
        try:
            r = await client.get(f"{base_url}/api/suggestions")
            data = r.json()
            print(f"GET /api/suggestions -> {r.status_code}: {len(data.get('campaigns', []))} needing action")
        except Exception as e:
            print(f"GET /api/suggestions -> ERROR: {e}")

    return True


async def main():
    """Run all tests."""
    print("=" * 50)
    print("IMAN OS - Manual Sync Test")
    print("=" * 50)

    if not os.getenv("SMARTLEAD_API_KEY"):
        print("ERROR: SMARTLEAD_API_KEY not set in .env")
        sys.exit(1)

    # Test API connection
    if not await test_api_connection():
        print("\nAPI connection failed. Check your API key.")
        sys.exit(1)

    # Test full sync
    await test_full_sync()

    # Test endpoints (requires server running)
    print("\nNote: Endpoint tests require the server to be running.")
    print("Start the server with: python run.py")
    await test_endpoints()

    print("\n" + "=" * 50)
    print("Tests completed!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
