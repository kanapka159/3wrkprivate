"""
IMAN OS Database Configuration

Async SQLite database setup with SQLAlchemy.
"""

import os
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Database URL - SQLite with aiosqlite for async support
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./iman_os.db")

# Create async engine with SQLite-specific settings
# Use NullPool to avoid connection pooling issues with SQLite
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DEBUG", "false").lower() == "true",
    future=True,
    poolclass=NullPool,  # Disable connection pooling for SQLite
    connect_args={"timeout": 60, "check_same_thread": False},
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
    """
    # Import models to register them with Base.metadata
    from . import models  # noqa: F401

    logger.info(f"Initializing database: {DATABASE_URL}")

    async with engine.begin() as conn:
        # Enable WAL mode for better concurrency
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA busy_timeout=30000"))
        await conn.run_sync(Base.metadata.create_all)

        # Run migrations for new columns
        await _run_migrations(conn)

    logger.info("Database tables created successfully")


async def _run_migrations(conn):
    """Run schema migrations for existing databases."""
    # Check and add local_created_at column to campaigns table
    try:
        result = await conn.execute(text("PRAGMA table_info(campaigns)"))
        columns = [row[1] for row in result.fetchall()]

        if "local_created_at" not in columns:
            logger.info("Adding local_created_at column to campaigns table")
            await conn.execute(text("ALTER TABLE campaigns ADD COLUMN local_created_at DATETIME"))
            # Copy existing created_at values to local_created_at for backwards compatibility
            await conn.execute(text("UPDATE campaigns SET local_created_at = created_at WHERE local_created_at IS NULL"))
            logger.info("Migration completed: added local_created_at column")

    except Exception as e:
        logger.warning(f"Migration check failed (may be expected on fresh DB): {e}")
