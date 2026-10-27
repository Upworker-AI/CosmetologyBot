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
            SELECT category,  MIN(category_order) AS category_order
            FROM services
            WhERE is_active = 1
            GROUP BY category
            ORDER BY category_order, category
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

async def get_or_create_client(
    telegram_id: int,
    username: str | None,
    full_name: str | None,
    phone: str | None,
):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT id
            FROM clients
            WHERE telegram_id = ?
            """,
            (telegram_id,)
        )
        client = await cursor.fetchone()

        if client:
            return client["id"]

        cursor = await db.execute(
            """
            INSERT INTO clients
            (telegram_id, username, full_name, phone)
            VALUES (?, ?, ?, ?)
            """,
            (telegram_id, username, full_name, phone)
        )
        await db.commit()

        return cursor.lastrowid


async def create_booking_request(
    client_id: int,
    client_telegram_id: int,
    service_id: int,
    preferred_date: str,
    preferred_time_slot: str,
    note: str | None,
):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        cursor = await db.execute(
            """
            INSERT INTO booking_requests
            (client_id, client_telegram_id, service_id, preferred_date, preferred_time_slot, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                client_id,
                client_telegram_id,
                service_id,
                preferred_date,
                preferred_time_slot,
                note,
            )
        )
        await db.commit()

        return cursor.lastrowid


async def update_booking_status(booking_id: int, status: str):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            """
            UPDATE booking_requests
            SET status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, booking_id)
        )
        await db.commit()

async def get_client_telegram_id(booking_id: int):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT client_telegram_id
            FROM booking_requests
            WHERE id = ?
            """,
            (booking_id,)
        )
        row = await cursor.fetchone()
        return row["client_telegram_id"] if row else None