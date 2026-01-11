"""
IMAN OS Database Configuration

Async SQLite database setup with SQLAlchemy.
"""

import os
import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Database URL - SQLite with aiosqlite for async support
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./iman_os.db")

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DEBUG", "false").lower() == "true",
    future=True,
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()


async def get_db():
    """
    Dependency to get database session.

    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """
    Initialize database tables on startup.

    Creates all tables defined in models if they don't exist.
    Also adds any new columns to existing tables.
    """
    # Import models to register them with Base.metadata
    from . import models  # noqa: F401

    logger.info(f"Initializing database: {DATABASE_URL}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Add new columns to campaigns table if they don't exist (for migration)
        # SQLite doesn't support IF NOT EXISTS for columns, so we check first
        try:
            from sqlalchemy import text
            # Check if total_sent column exists
            result = await conn.execute(text("PRAGMA table_info(campaigns)"))
            columns = [row[1] for row in result.fetchall()]

            if 'total_sent' not in columns:
                logger.info("Adding aggregate stats columns to campaigns table...")
                await conn.execute(text("ALTER TABLE campaigns ADD COLUMN total_sent INTEGER DEFAULT 0"))
                await conn.execute(text("ALTER TABLE campaigns ADD COLUMN total_replied INTEGER DEFAULT 0"))
                await conn.execute(text("ALTER TABLE campaigns ADD COLUMN total_positive INTEGER DEFAULT 0"))
                await conn.execute(text("ALTER TABLE campaigns ADD COLUMN total_opened INTEGER DEFAULT 0"))
                await conn.execute(text("ALTER TABLE campaigns ADD COLUMN total_bounced INTEGER DEFAULT 0"))
                await conn.execute(text("ALTER TABLE campaigns ADD COLUMN total_clicked INTEGER DEFAULT 0"))
                logger.info("Aggregate stats columns added successfully")
        except Exception as e:
            logger.warning(f"Could not add aggregate columns (may already exist): {e}")

    logger.info("Database tables created successfully")
