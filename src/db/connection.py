"""
Database Connection Management

Async PostgreSQL connection pool using asyncpg, with Supabase support.
"""

import logging
import os
from typing import Optional
import asyncpg

logger = logging.getLogger(__name__)

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


async def init_db() -> None:
    """Initialize database connection pool."""
    global _pool

    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://user:password@localhost:5432/agentgate"
    )

    try:
        _pool = await asyncpg.create_pool(
            db_url,
            min_size=5,
            max_size=20,
            command_timeout=60,
        )

        logger.info("Database connection pool initialized")

        # Run migrations
        await _run_migrations()

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        raise


async def close_db() -> None:
    """Close database connection pool."""
    global _pool

    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")


async def health_check() -> bool:
    """Check database health."""
    global _pool

    if not _pool:
        return False

    try:
        async with _pool.acquire() as connection:
            await connection.fetchval("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


async def get_connection() -> asyncpg.Connection:
    """Get a connection from the pool."""
    global _pool

    if not _pool:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    return await _pool.acquire()


async def execute(query: str, *args) -> None:
    """Execute a query."""
    async with _pool.acquire() as connection:
        await connection.execute(query, *args)


async def fetch(query: str, *args) -> list:
    """Fetch multiple rows."""
    async with _pool.acquire() as connection:
        return await connection.fetch(query, *args)


async def fetchval(query: str, *args):
    """Fetch single value."""
    async with _pool.acquire() as connection:
        return await connection.fetchval(query, *args)


async def fetchrow(query: str, *args) -> Optional[dict]:
    """Fetch single row."""
    async with _pool.acquire() as connection:
        return await connection.fetchrow(query, *args)


async def _run_migrations() -> None:
    """Run database migrations."""
    global _pool

    migration_file = os.path.join(
        os.path.dirname(__file__),
        "migrations/001_initial_schema.sql"
    )

    if not os.path.exists(migration_file):
        logger.warning(f"Migration file not found: {migration_file}")
        return

    try:
        with open(migration_file, "r") as f:
            migration_sql = f.read()

        async with _pool.acquire() as connection:
            await connection.execute(migration_sql)

        logger.info("Database migrations completed")

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        # Don't fail startup for migration errors
