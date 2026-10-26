import aiosqlite
from config import DATABASE_PATH

DATABASE_FILE = DATABASE_PATH

async def init_db():
    async with aiosqlite.connect(DATABASE_FILE) as db:
        with open("database/models.sql","r",encoding="utf-8") as file:
            schema = file.read()

        await db.executescript(schema)
        await db.commit()

async def get_categories():
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT DISTINCT category
            FROM services
            WhERE is_active = 1
            ORDER BY category
            """
        )
        rows = await cursor.fetchall()
        return rows

async def get_services_by_category(category: str):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT id, title, price, duration_minutes
            FROM services
            WHERE category = ? AND is_active = 1
            ORDER BY sort_order, title
            """,
            (category,)
        )
        rows = await cursor.fetchall()
        return rows

async def get_service(service_id: int):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT id, category, title, description, price, duration_minutes
            FROM services
            WHERE id = ? AND is_active = 1
            """,
            (service_id,)
        )
        row = await cursor.fetchone()
        return row
