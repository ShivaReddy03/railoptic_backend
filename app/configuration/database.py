import os
import asyncio
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from dotenv import load_dotenv
from contextlib import asynccontextmanager

# Load env vars
load_dotenv()

# Create async pool (doesn't connect yet)
db_pool = AsyncConnectionPool(
    conninfo=(
        f"host={os.getenv('DB_HOST')} "
        f"port={os.getenv('DB_PORT')} "
        f"dbname={os.getenv('DB_NAME')} "
        f"user={os.getenv('DB_USERNAME')} "
        f"password={os.getenv('DB_PASSWORD')}"
    ),
    min_size=1,
    max_size=10,
    timeout=40,
)


async def init_pool():
    """Open pool and test connection"""
    await db_pool.open()  # ✅ Explicitly open
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