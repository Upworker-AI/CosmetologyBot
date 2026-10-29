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
    start_time: str | None = None,
    end_time: str | None = None,
):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        try:
            # Блокируем начало записи другими транзакциями.
            # Второй клиент будет ждать, пока первая заявка сохранится.
            await db.execute("BEGIN IMMEDIATE")

            # Для начала проверяем, что услуга существует.
            cursor = await db.execute(
                """
                SELECT duration_minutes
                FROM services
                WHERE id = ? AND is_active = 1
                """,
                (service_id,),
            )
            service = await cursor.fetchone()

            if service is None:
                raise ValueError("Услуга не найдена или неактивна.")

            # Для курсов дата и время могут уточняться отдельно.
            if preferred_date != "Дата уточняется":
                if not start_time or not end_time:
                    raise ValueError(
                        "Для записи необходимо указать время начала и окончания."
                    )

                # Поддерживаем оба формата даты.
                try:
                    date_obj = datetime.strptime(
                        preferred_date, "%d.%m.%Y"
                    ).date()
                except ValueError:
                    date_obj = datetime.strptime(
                        preferred_date, "%Y-%m-%d"
                    ).date()

                date_display = date_obj.strftime("%d.%m.%Y")
                date_iso = date_obj.isoformat()

                # Проверяем корректность времени.
                start_minutes = _to_minutes(start_time)
                end_minutes = _to_minutes(end_time)

                if end_minutes <= start_minutes:
                    raise ValueError("Время окончания должно быть позже начала.")

                duration = service["duration_minutes"]

                if end_minutes - start_minutes != duration:
                    raise ValueError(
                        "Продолжительность записи не совпадает с длительностью услуги."
                    )

                # Получаем время подготовки между клиентами.
                cursor = await db.execute(
                    """
                    SELECT preparation_minutes
                    FROM schedule_settings
                    WHERE id = 1
                    """
                )
                settings = await cursor.fetchone()
                preparation = (
                    settings["preparation_minutes"] if settings else 10
                )

                # Получаем все заявки, которые занимают время.
                cursor = await db.execute(
                    """
                    SELECT start_time, end_time
                    FROM booking_requests
                    WHERE preferred_date IN (?, ?)
                      AND status IN ('new', 'confirmed')
                      AND start_time IS NOT NULL
                      AND end_time IS NOT NULL
                    """,
                    (date_display, date_iso),
                )
                bookings = await cursor.fetchall()

                # Проверяем пересечение с каждой существующей записью.
                candidate_end = end_minutes + preparation

                for booking in bookings:
                    busy_start = _to_minutes(booking["start_time"])
                    busy_end = (
                        _to_minutes(booking["end_time"]) + preparation
                    )

                    if start_minutes < busy_end and busy_start < candidate_end:
                        raise ValueError(
                            "Это время уже занято. "
                            "Пожалуйста, выберите другое."
                        )

            # Если проверки пройдены, сохраняем заявку.
            cursor = await db.execute(
                """
                INSERT INTO booking_requests (
                    client_id,
                    client_telegram_id,
                    service_id,
                    preferred_date,
                    preferred_time_slot,
                    start_time,
                    end_time,
                    note
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    client_telegram_id,
                    service_id,
                    preferred_date,
                    preferred_time_slot,
                    start_time,
                    end_time,
                    note,
                ),
            )

            booking_id = cursor.lastrowid
            await db.commit()

            return booking_id

        except Exception:
            await db.rollback()
            raise

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



async def get_schedule_settings():
    """Получает настройки шага записи и времени подготовки."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT slot_step_minutes, preparation_minutes
            FROM schedule_settings
            WHERE id = 1
            """
        )
        row = await cursor.fetchone()

        if row is None:
            return {
                "slot_step_minutes": 15,
                "preparation_minutes": 10,
            }

        return dict(row)


async def get_working_hours(weekday: int):
    """Получает рабочие часы для дня недели."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT weekday, is_working, start_time, end_time
            FROM working_hours
            WHERE weekday = ?
            """,
            (weekday,),
        )
        row = await cursor.fetchone()

        return dict(row) if row else None


async def get_schedule_exception(date: str):
    """Получает индивидуальные настройки конкретной даты."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT exception_date, is_working, start_time, end_time, note
            FROM schedule_exceptions
            WHERE exception_date = ?
            """,
            (date,),
        )
        row = await cursor.fetchone()

        return dict(row) if row else None


async def get_working_breaks(weekday: int):
    """Получает регулярные перерывы для дня недели."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT id, start_time, end_time, title
            FROM working_breaks
            WHERE weekday = ?
            ORDER BY start_time
            """,
            (weekday,),
        )
        rows = await cursor.fetchall()

        return [dict(row) for row in rows]


async def get_date_breaks(date: str):
    """Получает перерывы для конкретной даты."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT id, start_time, end_time, title
            FROM date_breaks
            WHERE exception_date = ?
            ORDER BY start_time
            """,
            (date,),
        )
        rows = await cursor.fetchall()

        return [dict(row) for row in rows]


from datetime import datetime, timedelta


def _to_minutes(value: str) -> int:
    """Переводит время HH:MM в минуты от начала суток."""
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def _to_time(minutes: int) -> str:
    """Переводит минуты от начала суток в HH:MM."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _ranges_overlap(
    start1: int,
    end1: int,
    start2: int,
    end2: int,
) -> bool:
    """Проверяет пересечение двух временных промежутков."""
    return start1 < end2 and start2 < end1


async def get_available_slots(
    selected_date: str,
    service_id: int,
) -> list[str]:
    """
    Рассчитывает свободные начала записи для услуги.

    selected_date: ДД.ММ.ГГГГ или ГГГГ-ММ-ДД.
    service_id: ID услуги из таблицы services.
    """
    # Приводим дату к формату, который использует расписание.
    try:
        date_obj = datetime.strptime(
            selected_date, "%d.%m.%Y"
        ).date()
    except ValueError:
        try:
            date_obj = datetime.strptime(
                selected_date, "%Y-%m-%d"
            ).date()
        except ValueError:
            raise ValueError(
                "Дата должна быть в формате ДД.ММ.ГГГГ "
                "или ГГГГ-ММ-ДД."
            )

    date_iso = date_obj.isoformat()
    date_display = date_obj.strftime("%d.%m.%Y")
    weekday = date_obj.weekday()

    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        # Получаем длительность услуги.
        cursor = await db.execute(
            """
            SELECT duration_minutes
            FROM services
            WHERE id = ? AND is_active = 1
            """,
            (service_id,),
        )
        service = await cursor.fetchone()

        if not service:
            return []

        duration = service["duration_minutes"]

        if not duration or duration <= 0:
            return []

        # Получаем обычные рабочие часы.
        cursor = await db.execute(
            """
            SELECT is_working, start_time, end_time
            FROM working_hours
            WHERE weekday = ?
            """,
            (weekday,),
        )
        weekly_hours = await cursor.fetchone()

        # Получаем исключение для конкретной даты.
        cursor = await db.execute(
            """
            SELECT is_working, start_time, end_time
            FROM schedule_exceptions
            WHERE exception_date = ?
            """,
            (date_iso,),
        )
        exception = await cursor.fetchone()

        # Особая дата переопределяет обычный график.
        if exception:
            if not exception["is_working"]:
                return []

            work_start = exception["start_time"]
            work_end = exception["end_time"]
        else:
            if not weekly_hours or not weekly_hours["is_working"]:
                return []

            work_start = weekly_hours["start_time"]
            work_end = weekly_hours["end_time"]

        if not work_start or not work_end:
            return []

        work_start_min = _to_minutes(work_start)
        work_end_min = _to_minutes(work_end)

        if work_start_min >= work_end_min:
            return []

        # Получаем шаг слотов и время подготовки.
        cursor = await db.execute(
            """
            SELECT slot_step_minutes, preparation_minutes
            FROM schedule_settings
            WHERE id = 1
            """
        )
        settings = await cursor.fetchone()

        step = settings["slot_step_minutes"] if settings else 15
        preparation = (
            settings["preparation_minutes"] if settings else 10
        )

        if step <= 0 or preparation < 0:
            raise ValueError("Некорректные настройки расписания.")

        # Собираем все перерывы для дня недели.
        cursor = await db.execute(
            """
            SELECT start_time, end_time
            FROM working_breaks
            WHERE weekday = ?
            """,
            (weekday,),
        )
        breaks = await cursor.fetchall()

        # Добавляем перерывы, заданные для конкретной даты.
        cursor = await db.execute(
            """
            SELECT start_time, end_time
            FROM date_breaks
            WHERE exception_date = ?
            """,
            (date_iso,),
        )
        date_breaks = await cursor.fetchall()

        breaks = list(breaks) + list(date_breaks)

        break_ranges = [
            (_to_minutes(row["start_time"]),
             _to_minutes(row["end_time"]))
            for row in breaks
        ]

        # Получаем занятые интервалы активных заявок.
        # Учитываем только записи, у которых уже есть точное время.
        cursor = await db.execute(
            """
            SELECT start_time, end_time
            FROM booking_requests
            WHERE preferred_date IN (?, ?)
              AND status IN ('new', 'confirmed')
              AND start_time IS NOT NULL
              AND end_time IS NOT NULL
            """,
            (date_display, date_iso),
        )
        bookings = await cursor.fetchall()

    busy_ranges = []

    for booking in bookings:
        start = _to_minutes(booking["start_time"])
        end = _to_minutes(booking["end_time"])

        if start >= end:
            continue

        # После существующей записи резервируем время на подготовку.
        busy_ranges.append((start, end + preparation))

    # Формируем доступные варианты с заданным шагом.
    available = []
    candidate = work_start_min

    while candidate + duration <= work_end_min:
        appointment_end = candidate + duration
        blocked_end = appointment_end + preparation

        # Не разрешаем пересечение с перерывами.
        overlaps_break = any(
            _ranges_overlap(
                candidate,
                blocked_end,
                break_start,
                break_end,
            )
            for break_start, break_end in break_ranges
        )

        # Не разрешаем пересечение с другими заявками.
        overlaps_booking = any(
            _ranges_overlap(
                candidate,
                blocked_end,
                busy_start,
                busy_end,
            )
            for busy_start, busy_end in busy_ranges
        )

        if not overlaps_break and not overlaps_booking:
            available.append(_to_time(candidate))

        candidate += step

    return available
