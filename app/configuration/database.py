import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from dotenv import load_dotenv
from contextlib import asynccontextmanager

# Load env vars
load_dotenv()


def _build_conninfo() -> str:
    """Build a PostgreSQL connection string compatible with Render and local environments."""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        if "sslmode=" not in database_url:
            separator = "&" if "?" in database_url else "?"
            database_url = f"{database_url}{separator}sslmode=require"
        return database_url

    conninfo = (
        f"host={os.getenv('DB_HOST')} "
        f"port={os.getenv('DB_PORT', '5432')} "
        f"dbname={os.getenv('DB_NAME')} "
        f"user={os.getenv('DB_USERNAME')} "
        f"password={os.getenv('DB_PASSWORD')}"
    )
    if "sslmode=" not in conninfo:
        conninfo = f"{conninfo} sslmode=require"
    return conninfo


# Create async pool (doesn't connect yet)
db_pool = AsyncConnectionPool(
    conninfo=_build_conninfo(),
    min_size=1,
    max_size=5,
    timeout=20,
    open=False,
)


async def init_pool():
    """Open pool and test connection."""
    await db_pool.open()
    async with db_pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT 1;")
            print("✅ Database connection pool established successfully.")


@asynccontextmanager
async def get_cursor():
    """Get safe cursor with commit/rollback handling"""
    async with db_pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            try:
                yield cur
                await conn.commit()
            except Exception as e:
                await conn.rollback()
                raise e


async def close_pool():
    """Close pool gracefully"""
    if db_pool:
        await db_pool.close()
        print("Database connection pool closed.")