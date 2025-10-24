import asyncio
import asyncpg

DATABASE_URL = "postgresql://postgres:BjojlQymkIkpytWGieJXbNEmFzBPXxgq@shuttle.proxy.rlwy.net:17945/railway"

async def main():
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            DROP TABLE IF EXISTS telethon_sessions;
        """)
        print("Table dropped successfully!")

asyncio.run(main())
