import asyncpg

# вбейте своего юзера, пароль и имя БД
DATABASE_URL = "postgresql://myuser:123@localhost/mydatabase"

async def get_db_connection():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        await conn.close()