"""
IMAN OS - Campaign Analytics Dashboard

FastAPI application for Smartlead campaign analytics and management.
"""

import os
import sys
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .api import api_router
from .db.database import init_db

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting IMAN OS Backend...")

    # Check for required API key
    if not os.getenv("SMARTLEAD_API_KEY"):
        logger.error("SMARTLEAD_API_KEY not set! Please configure .env file.")
        sys.exit(1)

    logger.info("API key configured")
    logger.info("Creating database tables...")
    await init_db()
    logger.info("Database initialized - all tables created")
    yield
    # Shutdown
    logger.info("Shutting down IMAN OS Backend...")


# Create FastAPI app (redirect_slashes=False prevents 307 redirects)
app = FastAPI(
    title="IMAN OS",
    description="Campaign Analytics Dashboard for Smartlead",
    version="0.1.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "name": "IMAN OS",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/reset-db")
async def reset_database():
    """Reset the database - clears all data and recreates tables."""
    import glob

    # Remove SQLite files
    db_files = glob.glob("*.db*")
    for f in db_files:
        try:
            os.remove(f)
            logger.info(f"Removed {f}")
        except Exception as e:
            logger.warning(f"Could not remove {f}: {e}")

    # Recreate tables
    await init_db()

    return {"status": "database reset", "removed_files": db_files}


@app.get("/debug/campaign/{smartlead_id}")
async def debug_campaign_api(smartlead_id: int, email_status: str = None):
    """Debug endpoint to see raw Smartlead API responses for a campaign."""
    from .services import SmartleadClient

    async with SmartleadClient() as client:
        # Fetch raw responses
        analytics = await client.get_campaign_analytics(smartlead_id)
        statistics = await client.get_campaign_statistics(smartlead_id, offset=0, limit=10, email_status=email_status)

        return {
            "smartlead_id": smartlead_id,
            "email_status_filter": email_status,
            "analytics_response": analytics,
            "statistics_response_sample": statistics,
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("DEBUG", "false").lower() == "true",
    )
