import asyncpg
import asyncio

DATABASE_URL = "postgresql://myuser:123@localhost/mydatabase"

async def create_table():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        DELETE FROM users WHERE id = 1;
    ''')
    await conn.close()

asyncio.run(create_table())