import aiosqlite
from config import DATABASE_PATH
from datetime import  datetime

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
            INSERT INTO clients
            (telegram_id, username, full_name, phone)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                phone = excluded.phone
            """,
            (telegram_id, username, full_name, phone)
        )
        await db.commit()

        cursor = await db.execute(
            """
            SELECT id
            FROM clients
            WHERE telegram_id = ?
            """,
            (telegram_id,)
        )
        client = await cursor.fetchone()

        return client["id"]

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

async def get_client_bookings(telegram_id: int):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT
                br.id,
                br.preferred_date,
                br.preferred_time_slot,
                br.status,
                s.title AS service_title,
                s.price AS service_price
            FROM booking_requests br
            JOIN services s ON s.id = br.service_id
            WHERE br.client_telegram_id = ?
            ORDER BY br.created_at DESC
            LIMIT 10
            """,
            (telegram_id,)
        )

        return await cursor.fetchall()

async def get_client_by_telegram_id(telegram_id: int):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT id, full_name, phone
            FROM clients
            WHERE telegram_id = ?
            """,
            (telegram_id,)
        )
        return await cursor.fetchone()


async def get_admin_bookings(
    status: str | None = None,
    service_id: int | None = None,
):
    """
    Возвращает заявки для админ-панели.
    status=None — заявки всех статусов.
    service_id=None — услуги всех типов.
    """
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        query = """
            SELECT
                br.id,
                br.preferred_date,
                br.preferred_time_slot,
                br.status,
                br.note,
                br.created_at,
                br.client_telegram_id,
                c.full_name,
                c.phone,
                c.username,
                s.title AS service_title,
                s.price AS service_price,
                s.category AS service_category
            FROM booking_requests br
            LEFT JOIN clients c ON c.id = br.client_id
            LEFT JOIN services s ON s.id = br.service_id
            WHERE 1 = 1
        """
        params = []

        if status is not None:
            query += " AND br.status = ?"
            params.append(status)

        if service_id is not None:
            query += " AND br.service_id = ?"
            params.append(service_id)

        query += " ORDER BY br.created_at DESC, br.id DESC"

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        # Даты записаны в формате ДД.ММ.ГГГГ,
        # поэтому сортируем их после преобразования.
        def sort_key(row):
            try:
                date_value = datetime.strptime(
                    row["preferred_date"], "%d.%m.%Y"
                )
            except (ValueError, TypeError):
                date_value = datetime.max

            return (date_value, row["preferred_time_slot"] or "")

        return sorted(rows, key=sort_key)


async def get_admin_booking_details(booking_id: int):
    """Возвращает полную карточку одной заявки."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT
                br.id,
                br.preferred_date,
                br.preferred_time_slot,
                br.status,
                br.note,
                br.created_at,
                br.updated_at,
                br.client_telegram_id,
                c.full_name,
                c.phone,
                c.username,
                s.title AS service_title,
                s.price AS service_price,
                s.category AS service_category,
                s.duration_minutes
            FROM booking_requests br
            LEFT JOIN clients c ON c.id = br.client_id
            LEFT JOIN services s ON s.id = br.service_id
            WHERE br.id = ?
            """,
            (booking_id,),
        )

        return await cursor.fetchone()


async def get_admin_services():
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT id, title, category
            FROM services
            ORDER BY category, title
            """
        )

        return await cursor.fetchall()
